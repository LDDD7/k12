# k12_app/agent/llm/schedule_prompt.py
"""
日程/待办识别 — 从聊天记录中提取需要跟进的事项
"""

import json
import logging
import re
from typing import List, Dict
from datetime import datetime

from k12_app.backend.agent.llm.client import call_llm
from k12_app.backend.agent.llm.utils import extract_json_list, clean_data_for_json, repair_json_with_llm

logger = logging.getLogger(__name__)

SCHEDULE_SYSTEM_PROMPT = """
你是一个 K12 教育销售顾问的日程识别助手。
从聊天记录中识别出需要跟进的事项或日程安排。

【返回格式】
必须只输出 JSON 数组：
[
    {
        "title": "事项名称",
        "start_time": "YYYY-MM-DD HH:MM:SS",
        "priority": "高/中/低",
        "source": "识别依据（20字以内）",
        "confirmed": true/false
    },
    ...
]

【判断规则】
1. 没有明确日期的不输出
2. "这周六"、"明天上午"等需要转换成具体日期
3. 优先级判断标准：
   - 高：试听确认、报名跟进、合同签署
   - 中：回访、资料发送、咨询答疑
   - 低：日常关怀、非紧急提醒
4. confirmed 判定：客户已明确同意该时间（如"可以/好的/没问题/就这么定/约好了"等确认回应）→ true；仅提到时间或只是顾问提议、客户尚未同意 → false

【示例】
当前日期：2026-08-11
输入："这周六带孩子来试听"
输出：[{"title": "带孩子试听", "start_time": "2026-08-15 00:00:00", "priority": "高", "source": "客户确认这周六试听", "confirmed": true}]
"""


def _validate_schedule(item: dict) -> bool:
    """验证单个日程是否合法"""
    required = {"title", "start_time", "priority", "source"}
    if not all(k in item for k in required):
        return False
    if item.get("priority") not in {"高", "中", "低"}:
        return False
    # 兼容模型未返回 confirmed 的情况
    item.setdefault("confirmed", False)
    return True


def _format_date(date_str: str) -> str:
    """格式化日期，确保是 YYYY-MM-DD HH:MM:SS 格式"""
    # 如果已经是标准格式，直接返回
    if re.match(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", date_str):
        return date_str
    # 如果是日期格式（YYYY-MM-DD），补充时间
    if re.match(r"\d{4}-\d{2}-\d{2}", date_str):
        return f"{date_str} 00:00:00"
    return date_str


def extract_schedule(chat_records: List[Dict]) -> List[Dict]:
    """
    从聊天记录中提取日程

    Args:
        chat_records: 聊天记录列表

    Returns:
        日程列表：[{"title": "...", "start_time": "...", "priority": "...", "source": "..."}, ...]
    """
    if not chat_records:
        return []

    today = datetime.now().strftime("%Y-%m-%d")
    chat_records_clean = clean_data_for_json(chat_records)
    user_content = f"""
当前日期：{today}
聊天记录：{json.dumps(chat_records_clean, ensure_ascii=False)}
"""

    try:
        # 中文场景 max_tokens 过小易截断 JSON：给足空间，解析失败时用 LLM 修复原文
        raw_response = call_llm(SCHEDULE_SYSTEM_PROMPT, user_content, temperature=0.3, max_tokens=1500)
        data = extract_json_list(raw_response)

        if not data:
            logger.warning(f"日程识别返回无效 JSON，尝试 LLM 修复: {raw_response[:120]}")
            data = repair_json_with_llm(raw_response, expect_list=True, max_tokens=1500)

        if data and isinstance(data, list):
            valid_items = []
            for item in data:
                if _validate_schedule(item):
                    # 格式化时间
                    item["start_time"] = _format_date(item["start_time"])
                    valid_items.append(item)

            if valid_items:
                return valid_items

        logger.warning(f"日程识别返回无效数据: {raw_response[:200]}")
        return []

    except Exception as e:
        logger.error(f"日程识别失败: {e}")
        return []