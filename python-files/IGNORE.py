import os
import json
import aiohttp
from aiohttp import web
import asyncio
import re
import time
from colorama import init, Fore, Style
import sys
from threading import Lock

init(autoreset=True)
PORT = 8080
COOKIE_FILE = 'Cookie.txt'
CONCURRENCY_LIMIT = 300
BASE_REQUEST_DELAY = 0.1
MAX_RETRIES = 3
RETRY_BACKOFF = 1.4

session_state = {
    "roblox_cookie": "",
    "csrf_token": "",
    "user_id": None,
    "username": None,
    "upload_to_group": False,
    "group_id": ""
}

def validate_cookie(cookie):
    return cookie and len(cookie) > 100 and "_|WARNING:-DO-NOT-SHARE-THIS." in cookie

class AtomicCounter:
    def __init__(self):
        self._value = 0
        self._lock = Lock()
    
    def increment(self):
        with self._lock:
            self._value += 1
            return self._value

counter = AtomicCounter()

async def get_user_info():
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(
                "https://users.roblox.com/v1/users/authenticated",
                headers={"Cookie": f".ROBLOSECURITY={session_state['roblox_cookie']}"},
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    session_state["user_id"] = str(data.get("id"))
                    session_state["username"] = data.get("name")
                    print(f"Authenticated User: {session_state['username']} ({session_state['user_id']})")
                    return True
        except Exception as e:
            print(f"Error authenticating user: {e}")
    return False

async def refresh_csrf_token():
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(
                "https://auth.roblox.com/v2/logout",
                headers={
                    "Cookie": f".ROBLOSECURITY={session_state['roblox_cookie']}",
                    "User-Agent": "Roblox/WinInet"
                },
            ) as response:
                if response.status == 403:
                    csrf_token = response.headers.get("x-csrf-token")
                    if csrf_token:
                        session_state["csrf_token"] = csrf_token
                        return True
        except Exception as e:
            print(f"Error refreshing CSRF token: {e}")
    return False

async def fetch_animation(session, animation_id):
    for attempt in range(MAX_RETRIES):
        try:
            async with session.get(
                f"https://assetdelivery.roblox.com/v1/asset/?id={animation_id}",
                headers={
                    "Cookie": f".ROBLOSECURITY={session_state['roblox_cookie']}",
                    "Accept": "application/octet-stream",
                    "User-Agent": "Roblox/WinInet"
                },
                ssl=False
            ) as response:
                if response.status == 200:
                    return await response.read()
                elif response.status == 429:
                    await asyncio.sleep(BASE_REQUEST_DELAY * (RETRY_BACKOFF ** attempt))
                else:
                    break
        except:
            if attempt < MAX_RETRIES - 1:
                await asyncio.sleep(BASE_REQUEST_DELAY * (RETRY_BACKOFF ** attempt))
            continue
    return None

async def upload_animation(session, animation_data, animation_name, animation_id):
    if not session_state["csrf_token"]:
        if not await refresh_csrf_token():
            return None
    
    params = {
        "assetTypeName": "Animation",
        "name": f"{animation_name}_Reupload_{int(time.time())}",
        "description": "Automatically reuploaded",
        "ispublic": "False",
        "allowComments": "True",
        "groupId": session_state["group_id"] if session_state["upload_to_group"] else "",
        "isGamesAsset": "False"
    }
    
    headers = {
        "Cookie": f".ROBLOSECURITY={session_state['roblox_cookie']}",
        "X-CSRF-TOKEN": session_state["csrf_token"],
        "Content-Type": "application/octet-stream",
        "User-Agent": "Roblox/WinInet",
        "Referer": "https://www.roblox.com/develop",
        "Origin": "https://www.roblox.com"
    }
    
    for attempt in range(MAX_RETRIES):
        try:
            async with session.post(
                "https://www.roblox.com/ide/publish/uploadnewanimation",
                params=params,
                data=animation_data,
                headers=headers,
                ssl=False
            ) as response:
                if response.status == 200:
                    text = await response.text()
                    match = re.search(r"\d{9,}", text)
                    if match:
                        return match.group(0)
                elif response.status == 403:
                    if await refresh_csrf_token():
                        headers["X-CSRF-TOKEN"] = session_state["csrf_token"]
                        continue
                elif response.status == 429:
                    await asyncio.sleep(BASE_REQUEST_DELAY * (RETRY_BACKOFF ** attempt))
                else:
                    break
        except:
            if attempt < MAX_RETRIES - 1:
                await asyncio.sleep(BASE_REQUEST_DELAY * (RETRY_BACKOFF ** attempt))
            continue
    return None

async def process_animations(animation_data_list):
    total_animations = len(animation_data_list)
    results = {}
    success_count = 0
    failure_count = 0
    invalid_count = 0
    counter._value = 0
    
    print("\nReuploading Animations, This Might Take Some Seconds...")
    start_time = time.time()
    semaphore = asyncio.Semaphore(CONCURRENCY_LIMIT)
    
    async def process_single(session, data):
        nonlocal success_count, failure_count, invalid_count
        
        async with semaphore:
            animation_id = data["id"]
            animation_name = data["name"]
            
            # Fetch animation
            animation_bytes = await fetch_animation(session, animation_id)
            if not animation_bytes:
                count = counter.increment()
                print(f"[{count}/{total_animations}] {Fore.YELLOW}Invalid Instance | {animation_id} ; Invalid{Style.RESET_ALL}")
                invalid_count += 1
                return
                
            # Upload animation
            new_id = await upload_animation(session, animation_bytes, animation_name, animation_id)
            if new_id:
                count = counter.increment()
                print(f"[{count}/{total_animations}] {Fore.GREEN}Successful Instance Reuploaded | {animation_id} ; {new_id}{Style.RESET_ALL}")
                results[animation_id] = new_id
                success_count += 1
            else:
                count = counter.increment()
                print(f"[{count}/{total_animations}] {Fore.RED}Failed Instance Reupload | {animation_id} ; Failed{Style.RESET_ALL}")
                failure_count += 1
    
    async with aiohttp.ClientSession() as session:
        tasks = [process_single(session, data) for data in animation_data_list]
        await asyncio.gather(*tasks)
    
    end_time = time.time()
    
    print("\n--- SUMMARY ---")
    print(f"Total Animations Processed: {total_animations}")
    print(f"Successful Reuploads: {success_count}")
    print(f"Failed Reuploads: {failure_count}")
    print(f"Invalid Animations: {invalid_count}")
    print(f"Time Taken: {end_time - start_time:.2f} seconds")
    
    return results

async def handle_request(request):
    try:
        payload = await request.json()
        animation_data_list = payload.get("animationData", [])
        if not animation_data_list:
            return web.json_response({"error": "No animation data provided"}, status=400)
        results = await process_animations(animation_data_list)
        return web.json_response(results, status=200)
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)

async def initialize_server():
    if os.path.exists(COOKIE_FILE):
        with open(COOKIE_FILE, "r") as f:
            session_state["roblox_cookie"] = f.read().strip()
    
    if not validate_cookie(session_state["roblox_cookie"]):
        session_state["roblox_cookie"] = input("Enter .ROBLOSECURITY cookie: ").strip()
        if not validate_cookie(session_state["roblox_cookie"]):
            print("Invalid cookie format")
            sys.exit(1)
        with open(COOKIE_FILE, "w") as f:
            f.write(session_state["roblox_cookie"])
    
    if not await get_user_info():
        print("Authentication failed")
        sys.exit(1)
    
    if not await refresh_csrf_token():
        print("CSRF token initialization failed")
        sys.exit(1)
    
    choice = input("Would You Like To Upload To User Or Group? [User/Group]: ").strip().lower()
    if choice == "group":
        session_state["upload_to_group"] = True
        while True:
            group_id = input("Enter the custom Group ID you want to reupload to: ").strip()
            if group_id.isdigit():
                session_state["group_id"] = group_id
                break
            else:
                print("Invalid Group ID. Please enter a numeric Group ID.")
    elif choice != "user":
        print("Invalid choice. Defaulting to User upload.")
    
    app = web.Application()
    app.router.add_post("/reupload", handle_request)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "localhost", PORT)
    print("Server ready - use the plugin to submit animations")
    await site.start()
    
    while True:
        await asyncio.sleep(3600)

if __name__ == "__main__":
    asyncio.run(initialize_server())