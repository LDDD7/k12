"""
RAG 索引管理路由
POST /api/rag/admin/reindex          — 重建索引（可指定 kb_name，默认全部）
POST /api/rag/admin/reindex_profiles — 重建画像索引（V3.1）
GET  /api/rag/admin/status           — 索引状态（5 个 Collection）
"""
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, field_validator

from k12_app.backend.rag.index_builder import (
    reindex_kb, reindex_all, reindex_profiles, reindex_chat_messages, get_reindex_status,
)
from k12_app.backend.services.auth_service import get_admin_session

logger = logging.getLogger(__name__)
router = APIRouter()

ALLOWED_KB = {"scripts", "sops", "faqs", "cases", "customer_profiles", "chat_messages"}


class ReindexRequest(BaseModel):
    kb_name: Optional[str] = None  # 不传则重建全部
    force: bool = False

    @field_validator("kb_name")
    @classmethod
    def validate_kb(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in ALLOWED_KB:
            raise ValueError(f"无效的 kb_name: {v}，允许值: {ALLOWED_KB}")
        return v


@router.post("/reindex")
async def reindex(
    req: ReindexRequest,
    current_admin: dict = Depends(get_admin_session),
):
    """
    重建知识库索引。

    - 默认仅超管和区域主管可操作
    - 不传 kb_name 则重建全部 4 个知识库
    - force=true 删除旧 Collection 后全量重建
    """
    if current_admin["data_scope"] == "self":
        raise HTTPException(status_code=403, detail="仅管理员可操作索引重建")

    triggered_by = current_admin["user_id"]

    if req.kb_name:
        if req.kb_name == "customer_profiles":
            result = reindex_profiles(triggered_by=triggered_by, force=req.force)
        elif req.kb_name == "chat_messages":
            result = reindex_chat_messages(triggered_by=triggered_by, force=req.force)
        else:
            result = reindex_kb(req.kb_name, triggered_by=triggered_by, force=req.force)
    else:
        result = reindex_all(triggered_by=triggered_by, force=req.force)

    return {"success": True, "data": result}


@router.post("/reindex_profiles")
async def reindex_profiles_endpoint(
    current_admin: dict = Depends(get_admin_session),
):
    """
    重建画像向量索引（V3.1）。

    将已确认的客户画像批量向量化，写入 k12_customer_profiles Collection。
    """
    if current_admin["data_scope"] == "self":
        raise HTTPException(status_code=403, detail="仅管理员可操作索引重建")

    result = reindex_profiles(triggered_by=current_admin["user_id"])
    return {"success": True, "data": result}


class ReindexChatRequest(BaseModel):
    days: int = 7
    limit: int = 1000
    force: bool = False
    adopted_only: bool = False
    incremental: bool = True

    @field_validator("days")
    @classmethod
    def validate_days(cls, v: int) -> int:
        if v < 1 or v > 90:
            raise ValueError("days 取值范围 1-90")
        return v

    @field_validator("limit")
    @classmethod
    def validate_limit(cls, v: int) -> int:
        if v < 1 or v > 10000:
            raise ValueError("limit 取值范围 1-10000")
        return v


@router.post("/reindex_chat")
async def reindex_chat_endpoint(
    req: ReindexChatRequest,
    current_admin: dict = Depends(get_admin_session),
):
    """
    重建聊天记录向量索引。

    从 msg_wxqy_chat 表读取文本消息，逐条 Embedding 后写入 k12_chat_messages Collection。

    - days: 全量模式下的索引天数（默认 7）
    - limit: 单次最大索引条数（默认 1000）
    - force: 强制全量重建（忽略增量）
    - adopted_only: 仅索引被 AI 采纳过的回复对应的会话消息（默认 false）
    - incremental: 增量模式，仅索引上次同步后的新消息（默认 true）
    """
    if current_admin["data_scope"] == "self":
        raise HTTPException(status_code=403, detail="仅管理员可操作索引重建")

    result = reindex_chat_messages(
        days=req.days,
        limit=req.limit,
        triggered_by=current_admin["user_id"],
        force=req.force,
        adopted_only=req.adopted_only,
        incremental=req.incremental,
    )
    return {"success": True, "data": result}


@router.get("/status")
async def index_status(current_admin: dict = Depends(get_admin_session)):
    """
    获取所有知识库的索引状态。

    返回 5 个 Collection 各自的 doc_count / total_chunks / last_indexed_at。
    """
    stats = get_reindex_status()
    return {"success": True, "data": stats}
