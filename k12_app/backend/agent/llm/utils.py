# k12_app/agent/llm/utils.py
"""
LLM 工具函数 — JSON 解析 / 数据清洗
供所有 prompt 模块复用的公共工具
"""

import json
import logging
import re
from typing import Optional, Any, List, Dict
from datetime import datetime, date
from decimal import Decimal

logger = logging.getLogger(__name__)


# ============================================================
# JSON 解析
# ============================================================

def extract_json(text: str, expect_list: bool = False) -> Optional[Any]:
    """
    从 LLM 返回的文本中提取 JSON（兼容 markdown 代码块包裹）

    Args:
        text: LLM 原始响应文本
        expect_list: True 时查找 [...]，False 时查找 {...}

    Returns:
        解析后的 dict/list，失败返回 None
    """
    if not text:
        return None

    # 移除 markdown 代码块包裹
    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if match:
        text = match.group(1)

    # 查找 JSON 边界
    open_char = "[" if expect_list else "{"
    close_char = "]" if expect_list else "}"
    start = text.find(open_char)
    end = text.rfind(close_char)
    if start != -1 and end != -1 and start < end:
        text = text[start:end + 1]

    try:
        return json.loads(text.strip())
    except json.JSONDecodeError as e:
        logger.warning(f"JSON 解析失败: {e}, 原始文本: {text[:200]}")
        return None


def extract_json_dict(text: str) -> Optional[dict]:
    """从 LLM 文本中提取 JSON 对象 {...}"""
    result = extract_json(text, expect_list=False)
    if isinstance(result, dict):
        return result
    return None


def extract_json_list(text: str) -> Optional[list]:
    """从 LLM 文本中提取 JSON 数组 [...]"""
    result = extract_json(text, expect_list=True)
    if isinstance(result, list):
        return result
    return None


# ============================================================
# JSON 修复（LLM 偶发截断/损坏时基于原文修复补全）
# ============================================================

REPAIR_JSON_SYSTEM_PROMPT = """你是一个 JSON 修复助手。用户会给你一段不完整、被截断或包含多余文字的 JSON。
请将其修复为完整合法的 JSON，并只输出修复后的 JSON 本身：
- 不要输出 markdown 代码块标记（```）
- 不要输出任何解释、前言或后记
- 数组型数据输出 JSON 数组，对象型数据输出 JSON 对象
- 内容缺失无法推断的字段用 null 或合理默认值补全，不要编造超出原文的信息
- 如果原文完全无法修复，只输出 null"""


def repair_json_with_llm(
    text: str,
    expect_list: bool = False,
    max_tokens: int = 2000,
) -> Optional[Any]:
    """
    用 LLM 修复/补全截断或损坏的 JSON（缓解中文场景 max_tokens 截断问题）。

    延迟导入 client 避免循环依赖（client.py → utils.py → client.py）。

    Args:
        text: LLM 原始响应（可能被截断/含多余文字）
        expect_list: True 期望数组，False 期望对象
        max_tokens: 修复调用最大输出 token 数

    Returns:
        修复后的 dict/list，失败返回 None
    """
    if not text or not text.strip():
        return None
    from k12_app.backend.agent.llm.client import call_llm  # 延迟导入
    try:
        raw = call_llm(
            REPAIR_JSON_SYSTEM_PROMPT,
            f"需要修复的 JSON（可能被截断或包含多余文字）：\n```\n{text[:6000]}\n```",
            temperature=0.0,
            max_tokens=max_tokens,
        )
        result = extract_json(raw, expect_list)
        if result is not None:
            logger.info(f"LLM JSON 修复成功（expect_list={expect_list}）")
        return result
    except Exception as e:
        logger.warning(f"LLM JSON 修复失败: {e}")
        return None


# ============================================================
# 数据清洗
# ============================================================

def format_retrieved_messages(messages: Optional[List[Dict[str, Any]]]) -> str:
    """
    把向量检索到的历史消息格式化为 prompt 文本，标注说话人身份与时间。

    入参为 retriever 返回的 [{id, text, metadata, score}, ...]。
    """
    if not messages:
        return ""
    lines = []
    for m in messages:
        meta = m.get("metadata") or {}
        sender = meta.get("sender_name") or ""
        send_time = meta.get("send_time") or meta.get("msg_date") or ""
        text = (m.get("text") or "").strip()
        if not text:
            continue
        lines.append(f"- [{send_time}] {sender or '未知'}: {text}")
    return "\n".join(lines)


def clean_data_for_json(data: Any) -> Any:
    """
    递归清洗数据，将不可 JSON 序列化的类型转换为可序列化的类型

    处理: datetime/date → ISO 字符串, Decimal → float, bytes → str
    """
    if data is None:
        return None
    if isinstance(data, (datetime, date)):
        return data.isoformat()
    if isinstance(data, Decimal):
        return float(data)
    if isinstance(data, bytes):
        try:
            return data.decode("utf-8")
        except (UnicodeDecodeError, Exception):
            return str(data)
    if isinstance(data, dict):
        return {k: clean_data_for_json(v) for k, v in data.items()}
    if isinstance(data, (list, tuple)):
        return [clean_data_for_json(v) for v in data]
    return data
