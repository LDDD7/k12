# k12_app/agent/llm/profile_prompt.py
"""
客户画像生成 — 从聊天记录、订单等数据中提取结构化画像
"""

import json
import logging
from typing import List, Dict, Any, Optional

from k12_app.backend.agent.llm.client import call_llm
from k12_app.backend.agent.llm.utils import (
    clean_data_for_json, extract_json_list, format_retrieved_messages, repair_json_with_llm,
)

logger = logging.getLogger(__name__)

PROFILE_SYSTEM_PROMPT = """
你是一个 K12 教育销售顾问的画像分析助手。
根据提供的客户信息（聊天记录、订单、客服记录），提取客户画像字段。

【返回格式】
必须只输出 JSON 数组，每个元素包含以下字段：
[
    {"item_name": "字段名", "item_value": "值", "confidence": 0.9, "source_type": "来源类型", "source_ref": "来源引用"},
    ...
]

【字段说明】
- item_name: 字段名（必须使用以下标准字段名）
- item_value: 字段值（提取的具体内容）
- confidence: 置信度（0.00-1.00，高≥0.85 / 中0.70-0.84 / 低<0.70）
- source_type: 来源类型（企微会话 / 订单 / 客服 / 人工）
- source_ref: 来源引用（如消息ID、订单号）

【标准字段名】
- 家长姓名、家长电话、学生姓名、学生年级、就读学校
- 薄弱科目、关注科目、意向程度、价格敏感度、决策周期
- 转介绍意愿、试听意向、报名意向、家庭情况、特殊需求
- 沟通偏好、跟进历史时间线

【补充字段说明】
- 沟通偏好：客户偏好的沟通方式/时间/语气（如"晚上方便联系""喜欢发语音""回复及时"）
- 跟进历史时间线：按时间顺序总结已发生的关键跟进事件（如"2026-06 首次咨询→2026-07 参加试听→2026-08 尚未报名"），无明确时间可省略

【置信度规则】
- 高（≥0.85）：客户明确说的（"我孩子数学不好" → 薄弱科目:数学, 0.95）
- 中（0.70-0.84）：从上下文推断的（家长反复问价格 → 价格敏感度:高, 0.75）
- 低（<0.70）：猜测的（"看起来像是有钱人" → 不输出）

【示例】
输入：聊天记录中包含 "我家孩子几何特别差，想找一对一"
输出：[{"item_name": "薄弱科目", "item_value": "数学", "confidence": 0.95, "source_type": "企微会话", "source_ref": "msg_001"}]
"""


def _validate_item(item: dict) -> bool:
    """验证单个画像字段项是否合法"""
    required = {"item_name", "item_value", "confidence"}
    if not all(k in item for k in required):
        return False
    if not isinstance(item.get("confidence"), (int, float)):
        return False
    if not 0 <= item.get("confidence", 0) <= 1:
        return False
    return True


def generate_profile(
    customer_data: Dict[str, Any],
    chat_records: List[Dict],
    orders: List[Dict],
    retrieved_messages: Optional[List[Dict]] = None,
) -> List[Dict]:
    """
    生成客户画像

    Args:
        customer_data: 客户基本信息（从 biz_customer 表）
        chat_records: 聊天记录列表
        orders: 订单列表
        retrieved_messages: 向量库检索到的历史聊天记录（该客户过往对话，已从 MySQL 归档）

    Returns:
        画像字段列表，每个字段包含 item_name, item_value, confidence, source_type, source_ref
    """
    # 1. 清洗数据（处理 datetime、Decimal 等不可序列化类型）
    customer_data_clean = clean_data_for_json(customer_data) if customer_data else {}
    chat_records_clean = clean_data_for_json(chat_records) if chat_records else []
    orders_clean = clean_data_for_json(orders) if orders else []
    retrieved_text = format_retrieved_messages(retrieved_messages)

    # 2. 构建用户输入
    user_content = f"""
客户信息：{json.dumps(customer_data_clean, ensure_ascii=False)}
聊天记录（最近30条）：{json.dumps(chat_records_clean[:30], ensure_ascii=False)}
订单记录：{json.dumps(orders_clean, ensure_ascii=False)}
"""
    if retrieved_text:
        user_content += f"\n【历史聊天记录（向量库检索，该客户过往对话）】\n{retrieved_text}\n"

    # 3. 调用 LLM，最多重试 2 次（缓解偶发空响应/超时导致的 500）
    #    每次解析失败先尝试 LLM 修复截断的 JSON，再重新生成（问题 5 修复）
    last_error = ""
    for attempt in range(1, 3):
        try:
            raw_response = call_llm(
                PROFILE_SYSTEM_PROMPT, user_content, temperature=0.3,
                max_tokens=2000, reasoning_effort="low",
            )
            data = extract_json_list(raw_response)

            if not data:
                logger.warning(f"画像生成返回无效 JSON（第 {attempt} 次），尝试 LLM 修复: {raw_response[:120]}")
                data = repair_json_with_llm(raw_response, expect_list=True, max_tokens=2000)

            if data and isinstance(data, list):
                valid_items = [item for item in data if _validate_item(item)]
                if valid_items:
                    return valid_items

            logger.warning(f"画像生成返回无效数据（第 {attempt} 次）: {raw_response[:200]}")
            last_error = "AI 返回内容无法解析为有效画像"
        except Exception as e:
            logger.warning(f"画像生成调用失败（第 {attempt} 次）: {e}")
            last_error = str(e)

    logger.error(f"画像生成最终失败: {last_error}")
    return []