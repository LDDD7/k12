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
COLLECTION_MAP = {
    "scripts": "k12_scripts",
    "sops": "k12_sops",
    "faqs": "k12_faqs",
    "cases": "k12_cases",
    "customer_profiles": "k12_customer_profiles",
    "chat_messages": "k12_chat_messages",
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
) -> List[Dict[str, Any]]:
    """
    语义检索聊天记录。

    从已向量化的企微聊天记录中搜索与查询最相关的历史消息。
    可选按 external_id（客户）或 user_id（顾问）过滤。

    Args:
        query: 搜索查询（如 "几何薄弱 怎么回复"、"试听课后跟进"）
        top_k: 返回数量
        external_id: 可选，按客户 ID 过滤
        user_id: 可选，按顾问 ID 过滤

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

    # 构建 ChromaDB where 过滤条件
    where_filter = None
    if external_id and user_id:
        where_filter = {
            "$and": [
                {"external_id": external_id},
                {"user_id": user_id},
            ]
        }
    elif external_id:
        where_filter = {"external_id": external_id}
    elif user_id:
        where_filter = {"user_id": user_id}

    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=top_k,
        where=where_filter,
    )
    return _to_result_list(results)
