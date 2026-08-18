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


def _thread_id_from_interrupt(interrupt_id: str, user_id: str) -> str:
    """从 interrupt_id（int_{external}_{user}）推导该客户的线程名"""
    if interrupt_id and interrupt_id.startswith("int_"):
        parts = interrupt_id.split("_")
        if len(parts) >= 3:
            external_id = "_".join(parts[1:-1])
            return f"interrupt_{user_id}_{external_id}"
    return f"interrupt_{user_id}"


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
async def get_interrupt(
    external_id: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
):
    """
    轮询当前用户的待确认中断事项。
    通过 LangGraph checkpoint 查询指定客户 thread 的中断状态。
    external_id 缺省时回退到用户级线程（向后兼容）。
    """
    user_id = current_user["user_id"]
    graph = get_graph()

    # 优先查询指定客户的线程，否则回退用户级线程
    thread_ids = [f"interrupt_{user_id}_{external_id}"] if external_id else [f"interrupt_{user_id}"]
    state = None
    for thread_id in thread_ids:
        config = {"configurable": {"thread_id": thread_id}}
        try:
            state = graph.get_state(config)
        except Exception:
            state = None
        if state and getattr(state, "tasks", None):
            break

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

    # 未显式传 thread_id 时，从 interrupt_id（int_{external}_{user}）推导客户线程，
    # 避免多客户中断互相覆盖、确认到错误客户的待确认事项
    if not req.thread_id:
        req.thread_id = _thread_id_from_interrupt(req.interrupt_id, current_user["user_id"])
    thread_id = req.thread_id
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
        raise HTTPException(status_code=500, detail="中断处理失败，请稍后重试")
