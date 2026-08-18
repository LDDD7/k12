"""
RAG 在线检索器
- retrieve_scripts()  — 语义搜索话术库 top-K 话术（可按年级/场景过滤）
- retrieve_sops()    — 按标签名匹配跟进 SOP 流程
- answer_faq()       — 知识库问答（课程/师资/价格 FAQ）
- retrieve_similar_cases()      — 检索相似成功案例
- retrieve_similar_customers()  — 检索相似客户画像（V3.1 新增，k12_customer_profiles）
"""
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional

import chromadb

from k12_app.backend.rag.embeddings import embed_query

logger = logging.getLogger(__name__)

CHROMA_PATH = Path(__file__).parent.parent.parent / "chroma_data"
# V3.3 二期新增：company（集团概况）/ classes（开班计划）/ awards（荣誉资质）
COLLECTION_MAP = {
    "scripts": "k12_scripts",
    "sops": "k12_sops",
    "faqs": "k12_faqs",
    "cases": "k12_cases",
    "customer_profiles": "k12_customer_profiles",
    "chat_messages": "k12_chat_messages",
    "company": "k12_company",
    "classes": "k12_classes",
    "awards": "k12_awards",
}

# 全局复用客户端与 collection 缓存：PersistentClient 初始化会加载磁盘索引，
# 每次调用都重建会造成明显延迟（首次 ~0.6s），改为进程内单例。
_client = None
_collection_cache = {}


def _get_client():
    global _client
    if _client is None:
        _client = chromadb.PersistentClient(path=str(CHROMA_PATH))
    return _client


def _get_collection(kb_name: str):
    """获取 ChromaDB Collection（只读，进程内缓存）"""
    if kb_name not in COLLECTION_MAP:
        raise ValueError(f"无效的知识库: {kb_name}")
    if kb_name in _collection_cache:
        return _collection_cache[kb_name]
    col_name = COLLECTION_MAP[kb_name]
    try:
        col = _get_client().get_collection(name=col_name)
    except Exception:
        col = None
    _collection_cache[kb_name] = col
    return col


def invalidate_collection_cache(kb_name: Optional[str] = None) -> None:
    """
    失效检索缓存（V3.3 二期：资料库一键发布/重建索引后调用）。

    背景：_get_collection 会把"不存在的 Collection"缓存为 None，
    若随后才完成索引构建，本进程内仍检索不到——与"运营后台一键生效、无需重启"的要求冲突。
    索引构建成功后调用本函数清缓存（kb_name=None 清全部）。
    """
    global _collection_cache
    if kb_name is None:
        _collection_cache = {}
    else:
        _collection_cache.pop(kb_name, None)


def _to_result_list(results: Any) -> List[Dict[str, Any]]:
    """将 ChromaDB 查询结果转为统一格式"""
    if not results or not results.get("ids"):
        return []

    items = []
    ids_list = results["ids"][0] if results["ids"] else []
    docs_list = results["documents"][0] if results["documents"] else []
    metas_list = results["metadatas"][0] if results["metadatas"] else []
    dists_list = results["distances"][0] if results["distances"] else []

    for i in range(len(ids_list)):
        item = {
            "id": ids_list[i] if i < len(ids_list) else "",
            "text": docs_list[i] if i < len(docs_list) else "",
            "metadata": metas_list[i] if i < len(metas_list) else {},
            "score": round(1.0 - dists_list[i], 4) if i < len(dists_list) and dists_list[i] is not None else 0.0,
        }
        items.append(item)

    return items


def retrieve_scripts(
    query: str,
    top_k: int = 5,
    filter_tags: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """
    语义检索话术库。

    Args:
        query: 搜索查询（如 "孩子几何薄弱"、"初三英语阅读差"）
        top_k: 返回数量
        filter_tags: 按标签过滤（如 ["tag_grade7", "tag_pre_sale"]）

    Returns:
        [{id, text, metadata, score}, ...]
    """
    collection = _get_collection("scripts")
    if not collection:
        logger.warning("k12_scripts Collection 不存在，请先执行 reindex")
        return []

    query_embedding = embed_query(query)
    where_filter = None
    if filter_tags:
        # ChromaDB 不支持数组字段直接过滤，此处预留扩展
        pass

    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=top_k,
        where=where_filter,
    )
    return _to_result_list(results)


def retrieve_sops(
    tag_name: str,
    top_k: int = 3,
) -> List[Dict[str, Any]]:
    """
    按标签名匹配 SOP 模板。

    使用语义检索方式搜索 SOP 库中与该标签最相关的跟进流程。

    Args:
        tag_name: 标签名称（如 "高意向"、"试听"、"续费"）
        top_k: 返回数量

    Returns:
        [{id, text, metadata, score}, ...]
    """
    collection = _get_collection("sops")
    if not collection:
        logger.warning("k12_sops Collection 不存在，请先执行 reindex")
        return []

    query_embedding = embed_query(f"标签：{tag_name} 客户跟进流程")

    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=top_k,
    )
    return _to_result_list(results)


def answer_faq(
    question: str,
    top_k: int = 3,
) -> Dict[str, Any]:
    """
    FAQ 知识库问答。

    从 FAQ 库中检索与用户问题最匹配的回答。

    Args:
        question: 用户提问（如 "试听课要收费吗？"、"你们老师有证吗？"）
        top_k: 返回数量

    Returns:
        {answer: str, sources: [{id, text, metadata, score}, ...]}
    """
    collection = _get_collection("faqs")
    if not collection:
        logger.warning("k12_faqs Collection 不存在，请先执行 reindex")
        return {
            "answer": "抱歉，知识库检索功能正在建设中，请稍后再试。",
            "sources": [],
        }

    query_embedding = embed_query(question)

    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=top_k,
    )
    sources = _to_result_list(results)

    # 缝合回答：取 top-1 的文本作为答案
    answer = sources[0]["text"] if sources else "抱歉，没有找到相关的回答，您可以换个问题试试。"

    return {
        "answer": answer,
        "sources": sources,
    }


def retrieve_similar_cases(
    context: str,
    top_k: int = 3,
) -> List[Dict[str, Any]]:
    """
    检索相似成功案例。

    基于客户场景描述（如 "数学差"、"初二"、"几何"）搜索相似转化案例。

    Args:
        context: 场景描述
        top_k: 返回数量

    Returns:
        [{id, text, metadata, score}, ...]
    """
    collection = _get_collection("cases")
    if not collection:
        logger.warning("k12_cases Collection 不存在，请先执行 reindex")
        return []

    query_embedding = embed_query(context)

    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=top_k,
    )
    return _to_result_list(results)


def retrieve_similar_customers(
    query_text: str,
    top_k: int = 5,
) -> List[Dict[str, Any]]:
    """
    检索相似客户画像（V3.1 新增）。

    基于画像特征文本，在客户画像向量库中搜索最相似的客户。

    Args:
        query_text: 画像特征描述（如 "初一数学薄弱，几何困难"）
        top_k: 返回数量

    Returns:
        [{id, text, metadata, score}, ...]
    """
    collection = _get_collection("customer_profiles")
    if not collection:
        logger.warning("k12_customer_profiles Collection 不存在")
        return []

    query_embedding = embed_query(query_text)

    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=top_k,
    )
    return _to_result_list(results)


def retrieve_chat_messages(
    query: str,
    top_k: int = 10,
    external_id: Optional[str] = None,
    user_id: Optional[str] = None,
    scope_user_id: Optional[str] = None,
    data_scope: str = "self",
) -> List[Dict[str, Any]]:
    """
    语义检索聊天记录。

    从已向量化的企微聊天记录中搜索与查询最相关的历史消息。
    可选按 external_id（客户）或 user_id（顾问）过滤。
    data_scope="self" 时强制附加调用者 user_id 过滤，防止跨顾问泄露。

    Args:
        query: 搜索查询（如 "几何薄弱 怎么回复"、"试听课后跟进"）
        top_k: 返回数量
        external_id: 可选，按客户 ID 过滤
        user_id: 可选，按顾问 ID 过滤
        scope_user_id: 调用者 user_id（self 范围强制过滤）
        data_scope: 调用者数据权限范围（self/region/all）

    Returns:
        [{id, text, metadata, score}, ...]
        其中 metadata 包含: msg_id, external_id, user_id, wework_account_id,
                            sender_name, msg_type, send_time, msg_date
    """
    collection = _get_collection("chat_messages")
    if not collection:
        logger.warning("k12_chat_messages Collection 不存在，请先执行 reindex")
        return []

    query_embedding = embed_query(query)

    # 强制 self 范围仅检索调用者本人消息；其余范围允许按请求参数过滤
    scope_user_id = scope_user_id if data_scope == "self" else None

    # 构建 ChromaDB where 过滤条件
    where_filter = None
    clauses = []
    if scope_user_id:
        clauses.append({"user_id": scope_user_id})
    if external_id:
        clauses.append({"external_id": external_id})
    if user_id and not scope_user_id:
        clauses.append({"user_id": user_id})

    if len(clauses) == 1:
        where_filter = clauses[0]
    elif len(clauses) > 1:
        where_filter = {"$and": clauses}

    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=top_k,
        where=where_filter,
    )
    return _to_result_list(results)


# ============================================================
# V3.3 二期新增：集团知识库（第一层）
# ============================================================

def retrieve_kb(
    kb_name: str,
    query: str,
    top_k: int = 3,
) -> List[Dict[str, Any]]:
    """
    通用集团知识库检索（company / classes / awards / faqs）。

    Args:
        kb_name: 知识库类型（company=集团概况 / classes=开班计划 / awards=荣誉资质 / faqs=FAQ）
        query: 用户问题
        top_k: 返回数量

    Returns:
        [{id, text, metadata, score}, ...]
    """
    if kb_name not in COLLECTION_MAP:
        raise ValueError(f"无效的知识库: {kb_name}，允许值: {list(COLLECTION_MAP.keys())}")
    collection = _get_collection(kb_name)
    if not collection:
        logger.warning(f"{COLLECTION_MAP[kb_name]} Collection 不存在，请先执行 reindex")
        return []

    query_embedding = embed_query(query)
    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=top_k,
    )
    return _to_result_list(results)


def retrieve_company_info(
    question: str,
    top_k: int = 3,
) -> List[Dict[str, Any]]:
    """检索集团概况（成立年限/规模/简介）"""
    return retrieve_kb("company", question, top_k)


def retrieve_class_info(
    question: str,
    top_k: int = 3,
) -> List[Dict[str, Any]]:
    """检索开班计划（学期/暑期班、课程、价格）"""
    return retrieve_kb("classes", question, top_k)


def retrieve_awards(
    question: str,
    top_k: int = 3,
) -> List[Dict[str, Any]]:
    """检索荣誉资质（奖项、颁发机构、年份）"""
    return retrieve_kb("awards", question, top_k)
