# k12_app/agent/llm/tag_prompt.py
"""
标签推荐 — 从客户数据中推荐最匹配的标签
"""

import json
import logging
from typing import List, Dict

from k12_app.backend.agent.llm.client import call_llm
from k12_app.backend.agent.llm.utils import extract_json_list, clean_data_for_json

logger = logging.getLogger(__name__)


def _get_tag_recommendation_system(tags_list: List[Dict]) -> str:
    """动态生成带标签列表的 system prompt"""
    # 按分组整理标签
    tags_text = "\n".join([
        f"  - {t['tag_id']}: {t['tag_name']}（{t.get('ai_rule', '无规则描述')}）"
        for t in tags_list
    ])

    return f"""
你是一个 K12 教育销售顾问的标签推荐助手。
根据客户信息，从以下标签中选择最匹配的标签（最多 5 个）。

【可用标签】
{tags_text}

【返回格式】
必须只输出 JSON 数组：
[
    {{"tag_id": "标签ID", "reason": "推荐理由"}},
    ...
]

【推荐规则】
1. 只从上述标签中选择
2. 每个标签都要有明确、具体的推荐理由
3. 如果没有任何标签匹配，返回空数组 []

【示例】
输入：客户聊天提到"数学成绩一直上不来"
输出：[{{"tag_id": "tag_shuxueruo", "reason": "聊天中提到数学成绩不好"}}]
"""


def _validate_tag_recommendation(item: dict) -> bool:
    """验证单个标签推荐是否合法"""
    if not item or not isinstance(item, dict):
        return False
    if "tag_id" not in item or "reason" not in item:
        return False
    if not item["tag_id"] or not item["reason"]:
        return False
    return True


def recommend_tags(
    profile: Dict,
    chat_records: List[Dict],
    tags_list: List[Dict],
) -> List[Dict]:
    """
    推荐标签

    Args:
        profile: 客户画像
        chat_records: 聊天记录
        tags_list: 全量标签列表

    Returns:
        推荐的标签列表：[{"tag_id": "...", "reason": "..."}, ...]
    """
    if not tags_list:
        return []

    system_prompt = _get_tag_recommendation_system(tags_list)
    user_content = f"""
客户画像：{json.dumps(clean_data_for_json(profile), ensure_ascii=False)}
最近聊天：{json.dumps(clean_data_for_json(chat_records[:20]), ensure_ascii=False)}
"""

    try:
        raw_response = call_llm(system_prompt, user_content, temperature=0.3)
        data = extract_json_list(raw_response)

        if data and isinstance(data, list):
            # 过滤无效推荐
            valid_items = [item for item in data if _validate_tag_recommendation(item)]
            if valid_items:
                # 额外验证：推荐的 tag_id 必须在可用标签中
                available_tag_ids = {t["tag_id"] for t in tags_list}
                valid_items = [
                    item for item in valid_items
                    if item["tag_id"] in available_tag_ids
                ]
                if valid_items:
                    return valid_items[:5]  # 最多5个

        logger.warning(f"标签推荐返回无效数据: {raw_response[:200]}")
        return []

    except Exception as e:
        logger.error(f"标签推荐失败: {e}")
        return []