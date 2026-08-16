# k12_app/routes/sidebar/stream.py
"""侧边栏 — SSE 实时推送（N2）

GET /api/sidebar/profile_stream/{external_id}
    订阅某客户的画像变更事件，画像确认后推送通知，前端据此自动刷新。
"""

import asyncio
import logging

from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import StreamingResponse

from k12_app.backend.services.auth_service import get_current_user
from k12_app.backend.services.event_bus import EventBus
from k12_app.backend.services.customer_service import CustomerService

logger = logging.getLogger(__name__)
router = APIRouter()

_HEARTBEAT_SECONDS = 15.0


@router.get("/profile_stream/{external_id}")
async def profile_stream(
    external_id: str,
    current_user: dict = Depends(get_current_user),
):
    """订阅客户画像变更事件（SSE）"""
    cust = CustomerService.get_by_external_id(
        external_id=external_id,
        user_id=current_user["user_id"],
        data_scope=current_user.get("data_scope", "self"),
        wework_account_id=current_user.get("wework_account_id"),
    )
    if not cust:
        raise HTTPException(status_code=404, detail="客户不存在或无访问权限")

    channel = f"profile_update:{external_id}"

    async def event_gen():
        q = EventBus.subscribe(channel)
        try:
            yield f"event: ready\ndata: {external_id}\n\n"
            while True:
                try:
                    payload = await asyncio.wait_for(q.get(), timeout=_HEARTBEAT_SECONDS)
                    yield f"event: profile_update\ndata: {payload}\n\n"
                except asyncio.TimeoutError:
                    yield ": ping\n\n"
        finally:
            EventBus.unsubscribe(channel, q)

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
