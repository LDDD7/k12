"""
二期「综合推理」AI 能力工具（V3.3）— 开放给 AI 的 5 个信息入口

第一期打通的信息入口：
1. get_customer_profile — 客户画像（当前客户档案 + 已确认画像字段）
2. get_orders          — 订单记录（当前客户历史订单）
3. get_tags            — 标签分析（当前客户标签 + 全量标签体系）
4. search_kb           — 集团知识库检索（概况/开班/荣誉/FAQ）
5. get_class_info      — 开班信息（静态资料库，检索开班计划）

每个工具返回 (说明文本, 元数据字典)，元数据用于来源标注（"不确定标注/来源"约束）。
"""
import logging
from typing import Dict, Any, Optional, List

from k12_app.backend.agent.llm.utils import clean_data_for_json

logger = logging.getLogger(__name__)


def _fmt_profile(customer_data: Optional[Dict], profile_items: Optional[List[Dict]]) -> str:
    """拼接客户画像文本"""
    lines = []
    if customer_data:
        mapping = [
            ("name", "家长姓名"), ("child_name", "学生姓名"), ("grade", "年级"),
            ("school", "就读学校"), ("focus_subject", "关注科目"),
            ("stage", "当前阶段"), ("remark", "备注"),
        ]
        for key, label in mapping:
            v = customer_data.get(key)
            if v:
                lines.append(f"{label}：{v}")
    if profile_items:
        for item in profile_items:
            name = (item.get("item_name") or "").strip()
            value = (item.get("item_value") or "").strip()
            if name and value:
                conf = item.get("confidence")
                conf_text = f"（置信度 {conf}）" if conf is not None else ""
                lines.append(f"{name}：{value}{conf_text}")
    return "\n".join(lines) if lines else "（暂无画像数据）"


def get_customer_profile(
    customer_data: Optional[Dict] = None,
    profile_items: Optional[List[Dict]] = None,
) -> Dict[str, Any]:
    """
    工具①：查客户画像 —— 这是谁（年级/学情/历史）。

    Args:
        customer_data: biz_customer 客户档案
        profile_items: ai_profile_item 已确认画像字段项

    Returns:
        {tool, description, text, metadata}
    """
    text = _fmt_profile(customer_data, profile_items)
    return {
        "tool": "get_customer_profile",
        "description": "客户画像（年级/学情/偏好）",
        "text": text,
        "metadata": {"source": "客户画像", "updated_at": None},
    }


def get_orders(orders: Optional[List[Dict]] = None) -> Dict[str, Any]:
    """
    工具②：查订单记录 —— 报过什么班、剩余课时、老学员身份。

    Args:
        orders: biz_order 订单列表

    Returns:
        {tool, description, text, metadata}
    """
    orders = orders or []
    if not orders:
        return {
            "tool": "get_orders",
            "description": "订单记录",
            "text": "（该客户暂无订单记录）",
            "metadata": {"source": "订单记录", "count": 0},
        }
    lines = []
    for o in orders[:10]:
        products = o.get("product_names") or []
        if isinstance(products, dict):
            products = [products.get("name") or str(products)]
        name = "、".join(str(p) for p in products) if products else "未知课程"
        amount = o.get("amount")
        amount_text = f"{amount} 元" if amount is not None else "金额未知"
        lines.append(
            f"- 订单 {o.get('order_id', '')}：{name}，{amount_text}，"
            f"状态 {o.get('status', '')}，时间 {o.get('order_date') or o.get('order_time') or ''}"
        )
    return {
        "tool": "get_orders",
        "description": "订单记录",
        "text": "\n".join(lines),
        "metadata": {"source": "订单记录", "count": len(orders)},
    }


def get_tags(
    customer_tags: Optional[List[Dict]] = None,
    all_tags: Optional[List[Dict]] = None,
) -> Dict[str, Any]:
    """
    工具③：查标签分析 —— 客户被打过什么标签（意向/学情）。

    Args:
        customer_tags: biz_customer_tag 客户标签
        all_tags: cfg_tag_definition 全量标签

    Returns:
        {tool, description, text, metadata}
    """
    customer_tags = customer_tags or []
    if customer_tags:
        tag_names = [
            t.get("tag_name") or t.get("tag_id") or ""
            for t in customer_tags
            if t.get("tag_name") or t.get("tag_id")
        ]
        text = "客户标签：" + "、".join(tag_names) if tag_names else "（暂无标签）"
    else:
        text = "（暂无客户标签）"
    return {
        "tool": "get_tags",
        "description": "标签分析",
        "text": text,
        "metadata": {"source": "标签分析", "count": len(customer_tags)},
    }


def search_kb(query: str, kb_name: str = "all", min_score: Optional[float] = None) -> Dict[str, Any]:
    """
    工具④：查集团知识库 —— 集团概况 / 开班计划 / 荣誉资质 / FAQ。

    Args:
        query: 用户问题（如 "你们正规吗做了多少年"）
        kb_name: company / classes / awards / faqs / all
        min_score: 匹配度门槛（低于视为未命中）；None 时取全局配置 ai_reasoning_min_score（默认 0.62）

    Returns:
        {tool, description, text, metadata, matched}
    """
    if min_score is None:
        from k12_app.backend.dao.config_dao import ConfigDAO
        min_score = ConfigDAO.get_kb_min_score()
    from k12_app.backend.services.rag_service import RAGService
    try:
        result = RAGService.search_kb(query=query, kb_name=kb_name, top_k=3, min_score=min_score)
    except Exception as e:
        logger.warning(f"集团知识库检索失败: {e}")
        return {
            "tool": "search_kb",
            "description": f"集团知识库（{kb_name}）",
            "text": "（知识库检索暂不可用）",
            "metadata": {"source": "集团知识库", "matched": False},
            "matched": False,
        }

    sources = result.get("sources") or []
    lines = []
    for s in sources:
        title = s.get("metadata", {}).get("title") or ""
        lines.append(f"[{title}·相似度{s.get('score', 0)}] {s.get('text', '')[:300]}")
    text = "\n".join(lines) if lines else "（未检索到匹配内容）"
    return {
        "tool": "search_kb",
        "description": f"集团知识库（{kb_name}）",
        "text": text,
        "metadata": {
            "source": "集团知识库",
            "matched": result.get("matched", False),
            "top_score": result.get("top_score", 0.0),
            "sources": sources,
        },
        "matched": result.get("matched", False),
    }


def get_class_info(query: str, min_score: Optional[float] = None) -> Dict[str, Any]:
    """
    工具⑤：查开班信息 —— 学期/暑期班、课程匹配（静态资料库）。

    Args:
        query: 匹配需求（如 "初二数学暑假班"）
        min_score: 匹配度门槛（None 时取全局配置）

    Returns:
        {tool, description, text, metadata, matched}
    """
    return search_kb(query=query, kb_name="classes", min_score=min_score)


# 工具注册表：供推理规划器使用（名称 → 执行函数）
TOOL_REGISTRY = {
    "get_customer_profile": get_customer_profile,
    "get_orders": get_orders,
    "get_tags": get_tags,
    "search_kb": search_kb,
    "get_class_info": get_class_info,
}

# 工具说明（注入规划器 prompt）
TOOL_DESCRIPTIONS = [
    {
        "name": "get_customer_profile",
        "desc": "查询当前客户的画像（年级/学情/历史记录），回答'这个孩子是谁'。参数：无。",
    },
    {
        "name": "get_orders",
        "desc": "查询当前客户的订单记录（报过什么班/金额/状态），判断是否老学员。参数：无。",
    },
    {
        "name": "get_tags",
        "desc": "查询当前客户的标签（意向程度/学情标签）。参数：无。",
    },
    {
        "name": "search_kb",
        "desc": "检索集团官方知识库（集团概况/开班计划/荣誉资质/FAQ），回答机构信息与价格政策类问题。参数：query=问题文本, kb_name=company|classes|awards|faqs|all。",
    },
    {
        "name": "get_class_info",
        "desc": "检索开班计划（暑期班/学期班课程与价格），为具体年级科目匹配课程。参数：query=匹配需求（如'初二数学暑假班'）。",
    },
]


def format_tool_descriptions() -> str:
    """把工具说明格式化为规划器可读文本"""
    return "\n".join(f"- {t['name']}: {t['desc']}" for t in TOOL_DESCRIPTIONS)


def execute_tool(name: str, state: Dict[str, Any], args: Optional[Dict] = None) -> Dict[str, Any]:
    """按名称执行工具（从 state 取上下文数据）"""
    args = args or {}
    if name == "get_customer_profile":
        return get_customer_profile(
            customer_data=state.get("customer_data"),
            profile_items=state.get("profile_items"),
        )
    if name == "get_orders":
        return get_orders(state.get("orders"))
    if name == "get_tags":
        return get_tags(
            customer_tags=state.get("customer_tags"),
            all_tags=state.get("tags"),
        )
    if name == "search_kb":
        return search_kb(
            query=args.get("query", state.get("message", "")),
            kb_name=args.get("kb_name", "all"),
            min_score=args.get("min_score"),
        )
    if name == "get_class_info":
        return get_class_info(
            query=args.get("query", state.get("message", "")),
            min_score=args.get("min_score"),
        )
    raise ValueError(f"未知工具: {name}")
