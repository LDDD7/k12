# k12_app/routes/sidebar/interrupt.py
"""侧边栏中断确认路由 — 人机协同确认"""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, field_validator
from langgraph.types import Command

from k12_app.backend.services.auth_service import get_current_user
from k12_app.backend.agent.graphs.k12_graph import get_graph

logger = logging.getLogger(__name__)
router = APIRouter()


class ConfirmRequest(BaseModel):
    interrupt_id: str
    confirmed: str  # ok / discard / recreate
    thread_id: Optional[str] = None  # type: ignore  # LangGraph thread_id

    @field_validator("confirmed")
    @classmethod
    def validate_confirmed(cls, v: str) -> str:
        if v not in ("ok", "discard", "recreate"):
            raise ValueError("confirmed 取值须为 ok / discard / recreate")
        return v


@router.get("/get_interrupt")
async def get_interrupt(current_user: dict = Depends(get_current_user)):
    """
    轮询当前用户的待确认中断事项。
    通过 LangGraph checkpoint 查询当前 thread 的中断状态。
    """
    user_id = current_user["user_id"]
    graph = get_graph()

    # 使用用户级别的 thread_id 查询中断状态
    config = {"configurable": {"thread_id": f"interrupt_{user_id}"}}
    try:
        state = graph.get_state(config)
    except Exception:
        state = None

    try:
        if state and getattr(state, "tasks", None):
            # 兼容 langgraph 0.3.x：中断信息在 StateSnapshot.tasks[i].interrupts 中
            for task in state.tasks:
                interrupts = getattr(task, "interrupts", None) or ()
                if interrupts:
                    interrupt_item = interrupts[0]
                    return {
                        "has_interrupt": True,
                        "interrupt_id": interrupt_item.value.get("interrupt_id") if hasattr(interrupt_item, "value") else None,
                        "interrupt_data": interrupt_item.value if hasattr(interrupt_item, "value") else None,
                        "options": ["ok", "discard", "recreate"],
                    }
    except Exception as e:
        logger.warning(f"查询中断状态失败: {e}")

    return {
        "has_interrupt": False,
        "interrupt_id": None,
        "interrupt_data": None,
        "options": None,
    }


@router.post("/confirm_interrupt")
async def confirm_interrupt(
    req: ConfirmRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    确认/放弃/重新生成中断任务。
    通过 LangGraph Command 恢复图执行。
    """
    graph = get_graph()
    thread_id = req.thread_id or f"interrupt_{current_user['user_id']}"
    config = {"configurable": {"thread_id": thread_id}}

    confirmed_value = req.confirmed

    try:
        # 使用 Command(resume=...) 恢复图执行（传递完整语义 ok/discard/recreate）
        result = graph.invoke(
            Command(resume=confirmed_value),
            config,
        )
        logger.info(f"中断确认完成: user={current_user['user_id']}, confirmed={req.confirmed}, thread={thread_id}")
        return {
            "success": True,
            "message": f"已处理: {req.confirmed}",
            "data": result.get("task_result") if result else None,
        }
    except Exception as e:
        logger.error(f"中断确认失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"中断处理失败: {str(e)}")
