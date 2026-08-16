# k12_app/agent/llm/reply_prompt.py
"""
销售/客服回复建议生成
"""

import json
import logging
from typing import List, Dict, Optional

from k12_app.backend.agent.llm.client import call_llm
from k12_app.backend.agent.llm.utils import clean_data_for_json, extract_json_list, format_retrieved_messages

logger = logging.getLogger(__name__)

REPLY_SYSTEM_PROMPT = """
你是一个 K12 教育销售顾问，拥有 10 年一线销售经验，以真诚、耐心、专业著称。
根据客户画像和最近的聊天记录，生成 3 条回复建议。

【回复要求】
1. 每条建议要具体、可操作，可以直接复制使用
2. 不要编造客户没说过的话
3. 语气要温和专业，体现同理心，有人情味
4. 如果是销售场景，要自然引导到下一步（试听/诊断/报名）
5. 称呼家长时使用"家长您好"或以孩子名+家长的方式（如"小明家长您好"），不要直呼家长姓名

【礼貌规范】
1. 开头必须使用礼貌称呼（"家长您好"或"xx家长您好"），不得直接切入话题
2. 先表达理解和共情，再给出建议或方案
3. 使用积极正向的语言，避免负面或批评性表述
4. 结尾要有温暖的收束语（如"随时欢迎交流""希望能帮到孩子"等）
5. 如涉及价格等敏感话题，语气要更加委婉，先说明价值再提及费用
6. 对家长的疑虑和担忧表示充分理解，不要急于反驳或说服
7. 使用"您"而非"你"，体现尊重
8. 适当使用"呢""哦""哈"等语气词增加亲和力，但不过度

【返回格式】
必须只输出 JSON 数组，包含 3 条回复：
["回复建议1", "回复建议2", "回复建议3"]

【场景区分】
- 销售场景：引导转化、推荐课程、安排试听
- 客服场景：解决售后问题、处理投诉、提供支持

【阶段区分】
- 小学：家长关注兴趣培养、学习习惯、基础巩固，语气亲切轻松，多谈习惯养成与兴趣引导
- 初中：家长关注升学、学科均衡、偏科矫正，强调学习方法与提分路径
- 高中：家长关注高考、冲刺提分、志愿规划，语气专业且强调效率与针对性

【示例】
场景：销售，客户说"孩子几何不好"
输出：[
    "家长您好，孩子几何方面遇到困难，确实让人揪心呢。其实几何需要的是空间思维能力的建立，很多孩子刚开始都会不适应。我们这边有针对性的几何专项提升课，要不先给孩子做个免费诊断，看看具体薄弱环节在哪里？",
    "家长您好，完全理解您的担心。几何是中学数学的分水岭，很多孩子都在这个阶段需要额外帮助。我们有经验丰富的老师，擅长用图形化方式帮孩子建立空间感，方便的话可以来体验一下课程哈。",
    "家长您好，孩子几何薄弱不代表能力有问题，可能只是还没找到适合的学习方法。方便说说孩子平时做几何题时，是哪种类型的题目卡住了呢？了解具体情况后我能给您更精准的建议哦。"
]
"""


def _validate_replies(replies: list) -> bool:
    if not replies or not isinstance(replies, list):
        return False
    for r in replies:
        if not isinstance(r, str) or len(r.strip()) < 5:
            return False
    return True


def _format_scripts(scripts: Optional[List[Dict]]) -> str:
    """把话术库检索结果格式化为 prompt 文本"""
    if not scripts:
        return ""
    lines = []
    for s in scripts:
        meta = s.get("metadata") or {}
        title = meta.get("title") or ""
        text = (s.get("text") or "").strip()
        if not text:
            continue
        lines.append(f"- {title + '：' if title else ''}{text}")
    return "\n".join(lines)


def infer_stage(grade: str) -> Optional[str]:
    """根据年级推断教学阶段（小学 / 初中 / 高中），无法判断时返回 None"""
    if not grade:
        return None
    g = str(grade).strip()
    if any(k in g for k in ("高一", "高二", "高三", "高中")):
        return "高中"
    if any(k in g for k in ("初一", "初二", "初三", "七年级", "八年级", "九年级", "初中")):
        return "初中"
    if any(k in g for k in ("一年级", "二年级", "三年级", "四年级", "五年级", "六年级", "小学", "幼小")):
        return "小学"
    return None


def generate_replies(
    profile: Dict,
    recent_chat: List[Dict],
    scene: str = "销售",
    count: int = 3,
    retrieved_messages: Optional[List[Dict]] = None,
    retrieved_scripts: Optional[List[Dict]] = None,
    stage: Optional[str] = None,
) -> List[str]:
    """
    生成回复建议

    Args:
        profile: 客户画像
        recent_chat: 最近聊天记录（10-20条，来自 MySQL）
        scene: 场景（销售 / 客服）
        count: 返回条数（默认3条）
        retrieved_messages: 向量库检索到的历史聊天记录（该客户过往对话）
        retrieved_scripts: 向量库检索到的话术库知识（k12_scripts）
        stage: 教学阶段（小学 / 初中 / 高中），用于细分话术风格

    Returns:
        回复建议列表
    """
    # 清洗数据，防止 datetime 等类型无法序列化
    profile_clean = clean_data_for_json(profile) if profile else {}
    recent_chat_clean = clean_data_for_json(recent_chat) if recent_chat else []
    retrieved_text = format_retrieved_messages(retrieved_messages)
    scripts_text = _format_scripts(retrieved_scripts)

    user_content = f"""
场景：{scene}
客户画像：{json.dumps(profile_clean, ensure_ascii=False)}
最近聊天：{json.dumps(recent_chat_clean[:15], ensure_ascii=False)}
"""
    if stage:
        user_content += f"教学阶段：{stage}\n"
    if scripts_text:
        user_content += f"\n【话术库知识（向量库检索，可参考的专业销售话术）】\n{scripts_text}\n"
    if retrieved_text:
        user_content += f"\n【历史聊天记录（向量库检索，该客户过往对话）】\n{retrieved_text}\n"

    try:
        raw_response = call_llm(
            REPLY_SYSTEM_PROMPT, user_content, temperature=0.7,
            max_tokens=800, reasoning_effort="low",
        )
        data = extract_json_list(raw_response)

        if data and isinstance(data, list) and _validate_replies(data):
            return data[:count]

        logger.warning(f"回复生成返回无效数据: {raw_response[:200]}")
        return ["系统暂时无法生成回复建议，请稍后再试"]

    except Exception as e:
        logger.error(f"回复生成失败: {e}")
        return ["系统暂时无法生成回复建议，请稍后再试"]