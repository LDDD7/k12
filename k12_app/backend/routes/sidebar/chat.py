# k12_app/routes/sidebar/chat.py

import asyncio
import json
import logging
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, field_validator, model_validator

from k12_app.backend.services.auth_service import get_current_user
from k12_app.backend.services.chat_service import ChatService
from k12_app.backend.services.message_service import MessageService
from k12_app.backend.config import settings

logger = logging.getLogger(__name__)
router = APIRouter()


class SendMessageRequest(BaseModel):
    message: Optional[str] = None
    menu_id: Optional[str] = None
    external_id: str
    wework_account_id: str
    skip_ai: bool = False

    @model_validator(mode="after")
    def check_message_or_menu(self):
        if not self.message and not self.menu_id:
            raise ValueError("message 和 menu_id 必须至少提供一个")
        if self.message and self.menu_id:
            raise ValueError("message 和 menu_id 不能同时提供")
        return self

    @field_validator("wework_account_id")
    @classmethod
    def validate_wework_account(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("wework_account_id 不能为空")
        return v.strip()

    @field_validator("external_id")
    @classmethod
    def validate_external_id(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("external_id 不能为空")
        return v.strip()


class ClearChatRequest(BaseModel):
    external_id: str

    @field_validator("external_id")
    @classmethod
    def validate_external_id(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("external_id 不能为空")
        return v.strip()


async def _flush_chat_buffer_async(user_id: str, external_id: str) -> None:
    """后台线程执行聊天记录转存，避免阻塞请求"""
    from k12_app.backend.rag.index_builder import flush_chat_conversation
    try:
        await asyncio.to_thread(flush_chat_conversation, user_id, external_id)
    except Exception as e:
        logger.warning(f"聊天记录转存向量库失败: {e}")


def _maybe_flush_chat_buffer(user_id: str, external_id: str) -> None:
    """会话消息累积到阈值后，异步转存向量库并清空 MySQL 聊天表（不阻塞 SSE 响应）"""
    try:
        if MessageService.count_chat_messages(user_id, external_id) >= settings.CHAT_FLUSH_THRESHOLD:
            asyncio.create_task(_flush_chat_buffer_async(user_id, external_id))
    except Exception as e:
        logger.warning(f"检查聊天记录转存阈值失败: {e}")


@router.post("/send_message")
async def send_message(
    req: SendMessageRequest,
    current_user: dict = Depends(get_current_user),
):
    # 校验 wework_account_id 与 JWT 一致
    if req.wework_account_id != current_user.get("wework_account_id"):
        raise HTTPException(
            status_code=403,
            detail="无权访问该企微账户数据",
        )

    # 如果未绑定，拒绝服务
    if current_user.get("binding_status") == "unbound":
        raise HTTPException(
            status_code=403,
            detail="员工未绑定企微账户，请先绑定",
        )

    # 持久化顾问发送的消息，保证聊天记录在刷新后不丢失
    if req.message:
        try:
            MessageService.insert_chat_message(
                user_id=current_user["user_id"],
                external_id=req.external_id,
                wework_account_id=req.wework_account_id,
                content=req.message,
                sender=current_user["user_id"],
                receiver=req.external_id,
                sender_name=current_user.get("name"),
                receiver_name=None,
            )
        except Exception as e:
            logger.warning(f"保存顾问消息失败: {e}")
        else:
            _maybe_flush_chat_buffer(current_user["user_id"], req.external_id)

    # 一键发送：仅持久化消息，跳过 AI 分析，避免再次触发 free_chat 生成重复回复
    if req.skip_ai:
        return {"success": True, "message": "消息已发送"}

    async def event_stream():
        async for event in ChatService.stream_agent(
            user_id=current_user["user_id"],
            external_id=req.external_id,
            wework_account_id=req.wework_account_id,
            message=req.message,
            menu_id=req.menu_id,
            data_scope=current_user.get("data_scope", "self"),
            sender_name=current_user.get("name"),
        ):
            yield event

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/clear_chat")
async def clear_chat(
    req: ClearChatRequest,
    current_user: dict = Depends(get_current_user),
):
    """清空当前顾问与某客户的聊天记录（MySQL 表 + 向量库历史一并清除）"""
    if current_user.get("binding_status") == "unbound":
        raise HTTPException(status_code=403, detail="员工未绑定企微账户，请先绑定")

    data_scope = current_user.get("data_scope", "self")
    wework_account_id = current_user.get("wework_account_id")

    deleted = MessageService.delete_chat_messages_by_external_id(
        external_id=req.external_id,
        user_id=current_user["user_id"],
        data_scope=data_scope,
        wework_account_id=wework_account_id,
    )

    # 同步清除向量库中已归档的历史向量，避免 AI 仍保留旧记忆
    try:
        from k12_app.backend.rag.index_builder import delete_chat_vectors
        await asyncio.to_thread(
            delete_chat_vectors,
            external_id=req.external_id,
            user_id=current_user["user_id"],
            wework_account_id=wework_account_id,
            data_scope=data_scope,
        )
    except Exception as e:
        logger.warning(f"清空向量库聊天记录失败: {e}")

    return {"success": True, "deleted": deleted}
