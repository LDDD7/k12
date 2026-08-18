"""
侧边栏 — 二期反馈与行为上报（V3.3）

POST /api/sidebar/task_action — 记录顾问对 AI 结果的行为（采纳/放弃/修改后发送）
POST /api/sidebar/feedback    — 顾问对 AI 推理结果点反馈（正面/负面）
对应 ai_feedback_signal 表 + ai_task_log 行为计数（采纳率/修改率）
"""
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, field_validator

from k12_app.backend.dao.task_log_dao import TaskLogDAO
from k12_app.backend.services.auth_service import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter()

VALID_ACTIONS = {"adopted", "discarded", "modified", "recreated"}


class TaskActionRequest(BaseModel):
    task_log_id: int
    action: str
    snapshot: Optional[dict] = None

    @field_validator("action")
    @classmethod
    def validate_action(cls, v: str) -> str:
        if v not in VALID_ACTIONS:
            raise ValueError(f"action 取值须为 {VALID_ACTIONS}")
        return v


class FeedbackRequest(BaseModel):
    task_log_id: int
    signal_type: str   # positive / negative
    snapshot: Optional[dict] = None

    @field_validator("signal_type")
    @classmethod
    def validate_signal(cls, v: str) -> str:
        if v not in ("positive", "negative"):
            raise ValueError("signal_type 取值须为 positive / negative")
        return v


@router.post("/task_action")
async def record_task_action(
    req: TaskActionRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    记录顾问对 AI 结果的行为：
    - adopted（采纳发送）→ 采纳率
    - modified（修改后发送）→ 修改率
    - discarded（放弃）→ 采纳率分母
    - recreated（重新生成）
    """
    try:
        TaskLogDAO.log_task(
            task_type="reply",
            user_id=current_user["user_id"],
            external_id="",
            wework_account_id=current_user.get("wework_account_id") or "",
            action=req.action,
            action_detail={
                "task_log_id": req.task_log_id,
                **(req.snapshot or {}),
            },
        )
    except Exception as e:
        logger.error(f"记录任务行为失败: {e}")
        raise HTTPException(status_code=500, detail="记录失败，请稍后重试")
    return {"success": True, "message": f"已记录行为: {req.action}"}


@router.post("/feedback")
async def submit_feedback(
    req: FeedbackRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    侧边栏反馈按钮：顾问对 AI 推理结果点反馈。
    数据进入 ai_feedback_signal，管理后台汇总成改进清单（数据闭环）。
    """
    try:
        TaskLogDAO.log_feedback(
            task_log_id=req.task_log_id,
            wework_account_id=current_user.get("wework_account_id") or "",
            signal_type=req.signal_type,
            snapshot=req.snapshot,
        )
    except Exception as e:
        logger.error(f"记录反馈失败: {e}")
        raise HTTPException(status_code=500, detail="反馈记录失败，请稍后重试")
    return {"success": True, "message": "反馈已记录，感谢您的反馈"}
