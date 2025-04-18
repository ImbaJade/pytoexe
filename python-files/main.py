#!/usr/bin/env python3
import notify2
import time

def send_notification():
    notify2.init("реклама")  # Инициализация
    n = notify2.Notification(
        "Нужно выполнить задачу? 🚀",  # Заголовок
        "Заказывайте выполнение задач в @vznanya_m\nНажмите, чтобы скопировать ссылку.",  # Текст
        "dialog-information"  # Иконка (можно заменить)
    )
    n.set_urgency(notify2.URGENCY_NORMAL)  # Уровень важности
    n.set_timeout(15000)  # Закрыть через 15 секунд (в миллисекундах!)
    n.show()  # Показать уведомление

if __name__ == "__main__":
    while True:
        send_notification()
        time.sleep(360)  # 6 минут = 360 секунд
