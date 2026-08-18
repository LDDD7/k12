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
        # V3.3.1：允许 message 与 menu_id 同时提供——
        # 侧边栏「手动综合推理」按钮场景：menu_id 强制意图（reasoning_suggestion），message 作为推理内容
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
    # V3.3.2：reset_memory=true 时除聊天记录外，一并清除 AI 画像/标签/相关向量（彻底重置 AI 记忆）
    reset_memory: bool = False

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

    # 校验客户归属，防止向他人客户会话注入消息（IDOR）
    from k12_app.backend.services.customer_service import CustomerService
    cust = CustomerService.get_by_external_id(
        external_id=req.external_id,
        user_id=current_user["user_id"],
        data_scope=current_user.get("data_scope", "self"),
        wework_account_id=current_user.get("wework_account_id"),
    )
    if not cust:
        raise HTTPException(status_code=404, detail="客户不存在或无访问权限")

    # 持久化「真实发送」的顾问消息，保证聊天记录在刷新后不丢失。
    # menu 驱动的分析（如「手动综合推理」自动复用的最近一条家长消息）只是 AI 推理输入，
    # 并非顾问真正发送，不写入聊天记录——否则客户原话会被以顾问身份重复入库。
    if req.message and not req.menu_id:
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
    """
    清空当前顾问与某客户的聊天记录（MySQL 表 + 向量库历史一并清除）。

    reset_memory=true（V3.3.2「彻底重置」）：额外清除该客户的 AI 画像（含画像向量）、
    客户标签——AI 将不再记得该客户（订单为业务财务数据，保留）。
    """
    if current_user.get("binding_status") == "unbound":
        raise HTTPException(status_code=403, detail="员工未绑定企微账户，请先绑定")

    data_scope = current_user.get("data_scope", "self")
    wework_account_id = current_user.get("wework_account_id")

    # 校验客户可访问（reset_memory 会删除画像/标签，必须先确认归属）
    if req.reset_memory:
        from k12_app.backend.services.customer_service import CustomerService
        cust = CustomerService.get_by_external_id(
            external_id=req.external_id,
            user_id=current_user["user_id"],
            data_scope=data_scope,
            wework_account_id=wework_account_id,
        )
        if not cust:
            raise HTTPException(status_code=404, detail="客户不存在或无访问权限")

    cleared = {"reset_memory": req.reset_memory}

    # V3.3.2：彻底重置 —— 先删 MySQL 画像/标签（失败则中止，此时聊天记录未受影响，可安全重试）
    if req.reset_memory:
        try:
            from k12_app.backend.dao.profile_dao import ProfileDAO
            from k12_app.backend.dao.tag_dao import TagDAO

            cleared["profile_deleted"] = ProfileDAO.delete_all_by_external_id(req.external_id)
            cleared["tags_deleted"] = TagDAO.delete_customer_tags_by_external_id(
                external_id=req.external_id,
                user_id=current_user["user_id"],
                data_scope=data_scope,
                wework_account_id=wework_account_id,
            )
            logger.info(
                f"已清除客户画像/标签: external_id={req.external_id}, "
                f"by user={current_user['user_id']}, scope={data_scope}"
            )
        except Exception as e:
            logger.error(f"重置客户 AI 记忆失败（聊天记录未受影响）: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail="重置失败，聊天记录未受影响，请重试")

    deleted = MessageService.delete_chat_messages_by_external_id(
        external_id=req.external_id,
        user_id=current_user["user_id"],
        data_scope=data_scope,
        wework_account_id=wework_account_id,
    )
    cleared["chat_deleted"] = deleted

    # 向量库删除均为尽力而为，失败不阻断主流程
    try:
        from k12_app.backend.rag.index_builder import delete_chat_vectors, delete_profile_vectors
        await asyncio.to_thread(
            delete_chat_vectors,
            external_id=req.external_id,
            user_id=current_user["user_id"],
            wework_account_id=wework_account_id,
            data_scope=data_scope,
        )
        if req.reset_memory:
            await asyncio.to_thread(delete_profile_vectors, req.external_id)
    except Exception as e:
        logger.warning(f"清空向量库记录失败: {e}")

    return {"success": True, "deleted": deleted, "cleared": cleared}
