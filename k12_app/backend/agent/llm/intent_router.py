# k12_app/agent/llm/intent_router.py
"""
意图识别 — 判断用户想做什么
"""

import logging
from typing import Optional

from k12_app.backend.agent.llm.client import call_llm
from k12_app.backend.agent.llm.utils import extract_json_dict

logger = logging.getLogger(__name__)

INTENT_ROUTER_SYSTEM = """
你是一个 K12 教育销售助手的意图识别器。
根据用户的输入，判断他想要执行什么操作。

【返回格式】
必须只输出 JSON，格式如下：
{"intent": "profile" | "reply" | "tag" | "schedule" | "reasoning" | "free_chat"}

【意图说明】
- profile: 用户想查看/生成客户画像（关键词：画像、分析、背景、情况）
- reply: 用户想获取聊天回复建议（关键词：怎么回、怎么说、回复、话术）
- tag: 用户想获取标签推荐（关键词：标签、分类、打标）
- schedule: 用户想识别日程/待办（关键词：日程、安排、时间、试听、跟进、提醒、这周六、明天）
- reasoning: 用户提问需要"跨多类信息综合"才能回答——既涉及客户情况/历史，又涉及课程匹配、价格政策、机构信息等（如"孩子初二数学差英语好，暑假有什么合适的班，大概什么价位"、"我们做了多少年/正规吗/获过什么奖"）。这类问题 AI 需要分步查画像→查开班→查价格后综合回答
- free_chat: 普通的闲聊或一般性问题（关键词：你好、谢谢、简单问价格、简单问课程）

【重要】
- 只有明确提到"画像"、"标签"、"日程/时间"时才返回对应意图
- 组合型/多信息综合问题（同时问课程+价格+孩子情况，或问机构背景信息）返回 reasoning
- 单纯的课程/价格单点咨询返回 free_chat；寒暄返回 free_chat

【示例】
输入："帮我看看王芳的画像" → {"intent": "profile"}
输入："怎么回复这个家长" → {"intent": "reply"}
输入："该给这个客户打什么标签" → {"intent": "tag"}
输入："这周六有试听课吗" → {"intent": "schedule"}
输入："你好，我想了解一下初一的课程" → {"intent": "free_chat"}
输入："孩子初二数学六七十分，英语不错，想暑假主攻数学顺便接触物理，有什么合适方案和价位" → {"intent": "reasoning"}
输入："你们机构正规吗？做了多少年了？获过什么奖？" → {"intent": "reasoning"}
输入："谢谢" → {"intent": "free_chat"}
"""

MENU_ID_MAPPING = {
    "profile_suggestion": "profile",
    "chat_suggestion": "reply",
    "kf_chat_suggestion": "reply",
    "tag_suggestion": "tag",
    "schedule_suggestion": "schedule",
    "reasoning_suggestion": "reasoning",
}

VALID_INTENTS = {"profile", "reply", "tag", "schedule", "reasoning", "free_chat"}

def route_intent(user_input: Optional[str] = None, menu_id: Optional[str] = None) -> str:
    if menu_id:
        return MENU_ID_MAPPING.get(menu_id, "free_chat")
    if not user_input or not user_input.strip():
        return "free_chat"

    try:
        raw_response = call_llm(INTENT_ROUTER_SYSTEM, user_input, temperature=0.1)
        data = extract_json_dict(raw_response)
        if data and "intent" in data:
            intent = data["intent"]
            if intent in VALID_INTENTS:
                return intent
        logger.warning(f"LLM 返回无效意图: {raw_response[:200]}")
        return "free_chat"
    except Exception as e:
        logger.error(f"意图识别失败: {e}")
        return "free_chat"