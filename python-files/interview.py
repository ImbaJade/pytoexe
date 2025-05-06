import pandas as pd
import random
from datetime import datetime
import gradio as gr

# 读取 Excel
def read_excel(file):
    return pd.read_excel(file, sheet_name='Sheet3')

# 分配函数
def assign_for_group_and_day(assignments, total_days_participated, officer_daily_participation,
                             group, day, availability_df, max_days_per_person,
                             internal_officers_needed, external_officers_needed):
    group_department = group.split('部')[0] + '部'
    group_department = group_department.replace('科技研发中心部', '科技研发中心')

    internal_candidates = availability_df[
        (availability_df['部门'] == group_department) & (availability_df[day] == 1)
    ]
    external_candidates = availability_df[
        (availability_df['部门'] != group_department) & (availability_df[day] == 1)
    ]

    internal_candidates = internal_candidates[
        (internal_candidates['姓名'].map(total_days_participated) < max_days_per_person) &
        (~internal_candidates['姓名'].map(officer_daily_participation).apply(lambda x: day in x))
    ]
    external_candidates = external_candidates[
        (external_candidates['姓名'].map(total_days_participated) < max_days_per_person) &
        (~external_candidates['姓名'].map(officer_daily_participation).apply(lambda x: day in x))
    ]

    managers = internal_candidates[internal_candidates['管理职务'].isin(['处长', '副处长'])]
    if managers.empty:
        return None

    manager_assigned = managers.sample(n=1, random_state=random.randint(0, 1000))['姓名'].tolist()
    internal_candidates = internal_candidates[~internal_candidates['姓名'].isin(manager_assigned)]

    additional_needed = internal_officers_needed - 1
    internal_assigned = manager_assigned
    if additional_needed > 0 and not internal_candidates.empty:
        internal_assigned += internal_candidates.sample(
            n=min(len(internal_candidates), additional_needed), random_state=random.randint(0, 1000)
        )['姓名'].tolist()

    external_assigned = []
    if not external_candidates.empty:
        external_assigned += external_candidates.sample(
            min(len(external_candidates), external_officers_needed), random_state=random.randint(0, 1000)
        )['姓名'].tolist()

    total_assigned = len(internal_assigned) + len(external_assigned)
    required_total = internal_officers_needed + external_officers_needed
    if total_assigned < required_total:
        return None

    for name in internal_assigned + external_assigned:
        total_days_participated[name] += 1
        officer_daily_participation[name].add(day)

    assignments[group][day] = internal_assigned + external_assigned
    return assignments

# 主分配逻辑
def run_assignment(file, schedule_config, internal_needed, external_needed, max_days):
    random.seed(datetime.now().timestamp())
    availability_df = read_excel(file)
    internal_needed = int(internal_needed)
    external_needed = int(external_needed)
    max_days = int(max_days)
    total_attempts = 0

    schedule = {}
    for line in schedule_config.split('\n'):
        if line.strip():
            group, days = line.split(':')
            schedule[group.strip()] = [day.strip() for day in days.split(',')]

    success = False
    while not success:
        total_attempts += 1
        try:
            assignments = {key: {day: [] for day in days} for key, days in schedule.items()}
            total_days_participated = {name: 0 for name in availability_df['姓名']}
            officer_daily_participation = {name: set() for name in availability_df['姓名']}

            for group, days in schedule.items():
                for day in days:
                    result = assign_for_group_and_day(
                        assignments, total_days_participated, officer_daily_participation,
                        group, day, availability_df, max_days,
                        internal_needed, external_needed
                    )
                    if result is None:
                        raise ValueError(f'{group} - {day} 无可用方案，重新开始')
            success = True
        except ValueError as e:
            print(f'尝试失败：第{total_attempts}次 - {e}...')

    result_df = pd.DataFrame([
        {'组别': group, '日期': day, '面试官': ', '.join(names)}
        for group, days in assignments.items()
        for day, names in days.items()
    ])

    output_path = 'assignment_result.xlsx'
    result_df.to_excel(output_path, index=False)
    return result_df, f'总共尝试分配次数：{total_attempts}', output_path

# 构建 Gradio Blocks 界面
with gr.Blocks(title='中国光大银行金融科技板块校园招聘面试官抽签') as demo:
    gr.Markdown('# 中国光大银行金融科技板块校园招聘面试官抽签')
    gr.Markdown('上传Excel并设置相关参数，点击按钮随机生成分配结果。')
    gr.Markdown('##### Compiled by ImbaJade | Version v1.0 | 2025/05/06', elem_classes='footer-text')

    with gr.Row():
        file = gr.File(label='上传 Excel 文件')
        schedule = gr.Text(
            label='日程表配置（格式：组别:日期1,日期2,...）',
            lines=6,
            value='金融科技部A组:11月26日（第一天）,11月27日（第二天）,11月28日（第三天）,11月29日（第四天）\n金融科技部B组:11月26日（第一天）,11月27日（第二天）,11月29日（第四天）\n数据资产管理部:11月26日（第一天）,11月27日（第二天）,11月28日（第三天）,11月29日（第四天）\n科技研发中心:11月26日（第一天）,11月27日（第二天）,11月28日（第三天）'
        )

    with gr.Row():
        internal_num = gr.Number(label='每天所需本部门面试官数量', value=2)
        external_num = gr.Number(label='每天所需外部门面试官数量', value=1)
        max_days = gr.Number(label='每个面试官最多可参与的天数', value=2)

    run_button = gr.Button('生成结果')
    show_table = gr.Checkbox(label='是否显示分配结果', value=True)

    with gr.Row():
        result_table = gr.Dataframe(label='分配结果', visible=True)
        result_info = gr.Textbox(label='系统信息')
    download = gr.File(label='导出分配结果')

    def assign_and_return(file, schedule_config, internal, external, max_days, show_result):
        df, info, path = run_assignment(file, schedule_config, internal, external, max_days)
        return (
            gr.update(value=df, visible=show_result),
            info,
            path
        )

    run_button.click(
        fn=assign_and_return,
        inputs=[file, schedule, internal_num, external_num, max_days, show_table],
        outputs=[result_table, result_info, download]
    )

    show_table.change(
        lambda show: gr.update(visible=show),
        inputs=show_table,
        outputs=result_table
    )

# 启动
if __name__ == '__main__':
    demo.launch(inbrowser=True)