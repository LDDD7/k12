# k12_app/agent/llm/free_chat.py
"""
自由对话处理 — 结合客户上下文进行智能回复
"""

import logging
from typing import Optional, List, Dict

from k12_app.backend.agent.llm.client import chat_with_context

logger = logging.getLogger(__name__)

# ============================================================
# 系统提示词
# ============================================================

FREE_CHAT_SYSTEM_PROMPT = """
你是擎天学智的 K12 教育销售助手，拥有丰富的课程咨询经验。
你的任务是帮助销售顾问回答家长的问题，提供专业的建议。

【核心原则】
1. 专业、耐心、有同理心，回复有人情味
2. 基于提供的客户信息回答问题
3. 如果需要，可以引导家长了解课程或安排试听
4. 不确定的事情不要瞎编，建议顾问确认
5. 回答要简洁、清晰、有温度
6. 称呼家长时使用"家长您好"或以孩子名+家长的方式，不要直呼家长姓名

【礼貌规范】
1. 开头必须使用礼貌称呼（"家长您好"或"xx家长您好"），不得直接切入话题
2. 先表达理解和共情，再给出建议或方案，让家长感受到被倾听和尊重
3. 使用积极正向的语言，避免负面或批评性表述，多肯定孩子的优点和潜力
4. 结尾要有温暖的收束语（如"希望能帮到孩子""有任何问题随时联系我们"等）
5. 如涉及价格等敏感话题，语气要更加委婉，先说明课程价值再提及费用
6. 对家长的疑虑和担忧表示充分理解，不要急于反驳或说服
7. 使用"您"而非"你"，体现尊重
8. 适当使用"呢""哦""哈"等语气词增加亲和力，但不过度

【禁止行为】
1. 不要编造客户没有提供的信息
2. 不要承诺无法兑现的事情
3. 不要使用过于销售化的语气，保持真诚而非推销感
4. 不要泄露其他客户的隐私信息
5. 不要直呼家长姓名，始终使用礼貌称呼
6. 不要对家长的教育方式或孩子的能力做出负面评价

【常见问题类型】
- 课程咨询：介绍课程体系、班型、师资
- 价格咨询：说明收费标准、优惠活动
- 学习问题：提供学习方法建议
- 试听预约：安排试听时间、地点
- 投诉处理：安抚情绪、记录问题、转交处理
"""


# ============================================================
# 核心函数
# ============================================================

def get_free_chat_context(customer_data: Optional[Dict]) -> Optional[Dict]:
    """
    从客户数据中提取自由对话所需的上下文

    Args:
        customer_data: 客户数据（从 biz_customer 表查询）

    Returns:
        上下文字典，包含学生姓名、年级、关注科目等
    """
    if not customer_data:
        return None

    return {
        "child_name": customer_data.get("child_name"),
        "grade": customer_data.get("grade"),
        "focus_subject": customer_data.get("focus_subject"),
        "school": customer_data.get("school"),
        "stage": customer_data.get("stage"),
        "remark": customer_data.get("remark"),
    }


def free_chat(
    user_message: str,
    customer_data: Optional[Dict] = None,
    chat_history: Optional[List[Dict[str, str]]] = None,
    temperature: float = 0.7,
    retrieved_messages: Optional[List[Dict]] = None,
) -> str:
    """
    自由对话（非流式）

    Args:
        user_message: 用户输入
        customer_data: 客户数据
        chat_history: 历史对话（用于多轮上下文）
        temperature: 温度参数
        retrieved_messages: 向量库检索到的历史聊天记录

    Returns:
        LLM 回复文本
    """
    # 提取上下文
    context = get_free_chat_context(customer_data) if customer_data else None

    return chat_with_context(
        user_message=user_message,
        context=context,
        chat_history=chat_history,
        system_prompt=FREE_CHAT_SYSTEM_PROMPT,
        temperature=temperature,
        retrieved_messages=retrieved_messages,
    )