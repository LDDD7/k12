"""
大模型提示词模板
┌──────────────────────────┬────────────────────┐
│ 模板                      │ 用途                │
├──────────────────────────┼────────────────────┤
│ profile_prompt.py        │ 客户画像提取提示词   │
│ reply_prompt.py          │ 销售回复话术提示词   │
│ tag_prompt.py            │ 标签推荐提示词       │
│ schedule_prompt.py       │ 日程识别提示词       │
│ intent_router.py         │ 意图识别路由提示词   │
│ free_chat.py             │ 自由对话提示词       │
│ client.py                │ LLM 统一调用入口     │
│ utils.py                 │ JSON 解析/数据清洗   │
└──────────────────────────┴────────────────────┘
模型：deepseek-v4-flash (DeepSeek，OpenAI 兼容接口)
详见系统设计文档 四、AI 任务编排
"""
