"""
RAG 知识检索路由（V3.0 新增，V3.1 扩展）
POST /api/rag/search_scripts    — 话术检索（语义搜索 top-K 话术模板）
POST /api/rag/search_sops       — SOP 检索（按标签名匹配跟进流程）
POST /api/rag/ask               — 知识库问答（FAQ 问答）
POST /api/rag/similar_customers — 相似客户检索（V3.1 新增，基于画像向量）
详见接口设计文档 五、RAG 知识检索接口
"""
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, field_validator

from k12_app.backend.services.rag_service import RAGService
from k12_app.backend.services.auth_service import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter()


class SearchScriptsRequest(BaseModel):
    query: str
    top_k: int = 5

    @field_validator("query")
    @classmethod
    def validate_query(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("query 不能为空")
        return v.strip()

    @field_validator("top_k")
    @classmethod
    def validate_top_k(cls, v: int) -> int:
        if v < 1 or v > 20:
            raise ValueError("top_k 取值范围 1-20")
        return v


class SearchSopsRequest(BaseModel):
    tag_name: str
    top_k: int = 3

    @field_validator("tag_name")
    @classmethod
    def validate_tag(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("tag_name 不能为空")
        return v.strip()


class AskRequest(BaseModel):
    question: str
    top_k: int = 3

    @field_validator("question")
    @classmethod
    def validate_question(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("question 不能为空")
        return v.strip()


class SimilarCustomersRequest(BaseModel):
    external_id: str
    top_k: int = 5


@router.post("/search_scripts")
async def search_scripts(req: SearchScriptsRequest, user: dict = Depends(get_current_user)):
    """语义检索话术库 — 输入客户问题描述，返回 top-K 匹配话术"""
    results = RAGService.retrieve_scripts(req.query, req.top_k)
    return {"success": True, "data": results}


@router.post("/search_sops")
async def search_sops(req: SearchSopsRequest, user: dict = Depends(get_current_user)):
    """按标签名检索 SOP 跟进流程"""
    results = RAGService.retrieve_sops(req.tag_name, req.top_k)
    return {"success": True, "data": results}


@router.post("/ask")
async def ask_faq(req: AskRequest, user: dict = Depends(get_current_user)):
    """FAQ 知识库问答"""
    result = RAGService.answer_faq(req.question, req.top_k)
    return {"success": True, "data": result}


@router.post("/similar_customers")
async def similar_customers(req: SimilarCustomersRequest, user: dict = Depends(get_current_user)):
    """检索相似客户画像（V3.1）"""
    results = RAGService.retrieve_similar_customers(
        external_id=req.external_id,
        user_id=user.get("user_id", ""),
        data_scope=user.get("data_scope", "self"),
        wework_account_id=user.get("wework_account_id"),
        top_k=req.top_k,
    )
    return {"success": True, "data": results}


class SearchChatRequest(BaseModel):
    query: str
    top_k: int = 10
    external_id: Optional[str] = None
    user_id: Optional[str] = None

    @field_validator("query")
    @classmethod
    def validate_query(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("query 不能为空")
        return v.strip()

    @field_validator("top_k")
    @classmethod
    def validate_top_k(cls, v: int) -> int:
        if v < 1 or v > 50:
            raise ValueError("top_k 取值范围 1-50")
        return v


@router.post("/search_chat")
async def search_chat(req: SearchChatRequest, user: dict = Depends(get_current_user)):
    """
    语义检索聊天记录。

    从已向量化的企微聊天记录中搜索与查询最相关的历史消息。
    可选按 external_id（客户）或 user_id（顾问）过滤。
    """
    results = RAGService.retrieve_chat_messages(
        query=req.query,
        top_k=req.top_k,
        external_id=req.external_id,
        user_id=req.user_id,
    )
    return {"success": True, "data": results}
