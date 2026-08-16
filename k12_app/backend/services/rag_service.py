"""
RAG 服务 — 知识检索增强
调用 rag/retriever.py 进行语义检索，拼入 LLM prompt 增强生成质量
详见系统设计文档 五、RAG 知识检索增强 + 十二、向量检索扩展评估
"""
import logging
from typing import List, Dict, Any, Optional

from k12_app.backend.rag.retriever import (
    retrieve_scripts as _retrieve_scripts,
    retrieve_sops as _retrieve_sops,
    answer_faq as _answer_faq,
    retrieve_similar_cases as _retrieve_similar_cases,
    retrieve_similar_customers as _retrieve_similar_customers,
    retrieve_chat_messages as _retrieve_chat_messages,
)
from k12_app.backend.dao.profile_dao import ProfileDAO

logger = logging.getLogger(__name__)


class RAGService:
    """RAG 检索服务"""

    @staticmethod
    def retrieve_scripts(query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """检索话术库（语义搜索）"""
        return _retrieve_scripts(query, top_k)

    @staticmethod
    def retrieve_sops(tag_name: str, top_k: int = 3) -> List[Dict[str, Any]]:
        """检索 SOP 流程"""
        return _retrieve_sops(tag_name, top_k)

    @staticmethod
    def answer_faq(question: str, top_k: int = 3) -> Dict[str, Any]:
        """FAQ 问答"""
        return _answer_faq(question, top_k)

    @staticmethod
    def retrieve_similar_cases(context: str, top_k: int = 3) -> List[Dict[str, Any]]:
        """检索相似成功案例"""
        return _retrieve_similar_cases(context, top_k)

    @staticmethod
    def retrieve_similar_customers(
        external_id: str,
        user_id: str,
        data_scope: str,
        wework_account_id: Optional[str],
        top_k: int = 5,
    ) -> List[Dict[str, Any]]:
        """
        检索相似客户（V3.1）。

        基于客户画像字段项构建特征文本，在 k12_customer_profiles
        向量库中搜索最相似的客户。搜索时排除当前客户自身。

        Args:
            external_id: 当前客户 external_id
            user_id: 调用者 user_id（权限过滤用）
            data_scope: 数据权限范围
            wework_account_id: 企微账户 ID
            top_k: 返回数量

        Returns:
            [{id, text, metadata, score}, ...]
        """
        # 1. 获取当前客户的画像字段项，构建查询文本
        profile = ProfileDAO.get_by_external_id(
            external_id, user_id, data_scope, wework_account_id
        )
        if not profile:
            logger.warning(f"未找到客户画像: external_id={external_id}")
            return []

        items = ProfileDAO.get_items(profile["id"])
        if not items:
            logger.warning(f"客户画像无字段项: external_id={external_id}")
            return []

        text_parts = []
        for item in items:
            name = (item.get("item_name") or "").strip()
            value = (item.get("item_value") or "").strip()
            if name and value:
                text_parts.append(f"{name}: {value}")

        if not text_parts:
            return []

        query_text = "\n".join(text_parts)
        logger.info(f"相似客户检索: external_id={external_id}, query_text_len={len(query_text)}")

        # 2. 语义检索相似客户（多返回几条，方便过滤自身）
        results = _retrieve_similar_customers(query_text, top_k + 1)

        # 3. 从结果中排除当前客户自身
        filtered = [
            r for r in results
            if r.get("metadata", {}).get("external_id") != external_id
        ]
        return filtered[:top_k]

    @staticmethod
    def retrieve_chat_messages(
        query: str,
        top_k: int = 10,
        external_id: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        语义检索聊天记录。

        从已向量化的企微聊天记录中搜索与查询最相关的历史消息，
        用于增强回复质量（找到类似场景下的成功对话）。

        Args:
            query: 搜索查询
            top_k: 返回数量
            external_id: 可选，按客户 ID 过滤
            user_id: 可选，按顾问 ID 过滤

        Returns:
            [{id, text, metadata, score}, ...]
        """
        return _retrieve_chat_messages(query, top_k, external_id, user_id)
