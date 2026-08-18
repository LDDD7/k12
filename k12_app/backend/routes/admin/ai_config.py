"""
管理后台 — 二期「RAG 知识库 + 综合推理」配置与数据汇总路由（V3.3）

GET  /api/admin/ai/config         — 读取全局 AI 配置（关停开关等）
PUT  /api/admin/ai/config         — 更新全局 AI 配置（秒级生效）
GET  /api/admin/ai/stats          — 二期验收指标（兜底率/修改率/推理失败率/采纳率）
GET  /api/admin/ai/blind_spots    — 盲区数据列表
GET  /api/admin/ai/feedback       — 顾问反馈汇总
"""
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, field_validator

from k12_app.backend.dao.config_dao import ConfigDAO
from k12_app.backend.dao.blind_spot_dao import BlindSpotDAO
from k12_app.backend.dao.task_log_dao import TaskLogDAO
from k12_app.backend.services.auth_service import get_admin_session

logger = logging.getLogger(__name__)
router = APIRouter()


def _require_admin(current_admin: dict) -> None:
    if current_admin["data_scope"] == "self":
        raise HTTPException(status_code=403, detail="仅管理员可操作 AI 配置")


class AiConfigUpdateRequest(BaseModel):
    reasoning_enabled: Optional[bool] = None      # 全局关停开关
    max_steps: Optional[int] = None               # 步数上限
    min_score: Optional[float] = None             # 知识库匹配度门槛

    @field_validator("max_steps")
    @classmethod
    def validate_steps(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and not (1 <= v <= 5):
            raise ValueError("max_steps 取值范围 1-5")
        return v

    @field_validator("min_score")
    @classmethod
    def validate_score(cls, v: Optional[float]) -> Optional[float]:
        if v is not None and not (0.0 <= v <= 1.0):
            raise ValueError("min_score 取值范围 0-1")
        return v


@router.get("/config")
async def get_ai_config(current_admin: dict = Depends(get_admin_session)):
    """读取全局 AI 配置"""
    configs = ConfigDAO.get_all_configs()
    data = {
        "reasoning_enabled": ConfigDAO.is_reasoning_enabled(),
        "max_steps": ConfigDAO.get_reasoning_max_steps(),
        "min_score": ConfigDAO.get_kb_min_score(),
        "items": configs,
    }
    return {"success": True, "data": data}


@router.put("/config")
async def update_ai_config(
    req: AiConfigUpdateRequest,
    current_admin: dict = Depends(get_admin_session),
):
    """更新全局 AI 配置（关停开关秒级生效）"""
    _require_admin(current_admin)
    updated = {}
    if req.reasoning_enabled is not None:
        ConfigDAO.set_config(
            "ai_reasoning_enabled",
            "true" if req.reasoning_enabled else "false",
            "综合推理开关：true=开启 / false=关闭（关闭后 AI 退回知识库查询/单模块回复）",
            current_admin["user_id"],
        )
        updated["reasoning_enabled"] = req.reasoning_enabled
    if req.max_steps is not None:
        ConfigDAO.set_config(
            "ai_reasoning_max_steps",
            str(req.max_steps),
            "综合推理最大步数上限（防跑偏）",
            current_admin["user_id"],
        )
        updated["max_steps"] = req.max_steps
    if req.min_score is not None:
        ConfigDAO.set_config(
            "ai_reasoning_min_score",
            str(req.min_score),
            "知识库检索匹配度门槛（低于该值视为未命中，走兜底话术）",
            current_admin["user_id"],
        )
        updated["min_score"] = req.min_score
    if not updated:
        raise HTTPException(status_code=400, detail="没有可更新的配置项")
    return {"success": True, "data": {"updated": updated}}


@router.get("/stats")
async def get_ai_stats(
    days: int = 30,
    current_admin: dict = Depends(get_admin_session),
):
    """二期验收指标统计（兜底率/修改率/推理失败率/采纳率）"""
    stats = TaskLogDAO.get_phase2_stats(
        user_id=current_admin["user_id"],
        data_scope=current_admin["data_scope"],
        wework_account_id=current_admin.get("wework_account_id"),
        days=days,
    )
    blind_stats = BlindSpotDAO.get_blind_spot_stats(days=days)
    stats["blind_spot"] = blind_stats
    return {"success": True, "data": stats}


@router.get("/blind_spots")
async def get_blind_spots(
    scene_type: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
    current_admin: dict = Depends(get_admin_session),
):
    """盲区数据列表（AI 走兜底/推理失败时自动记录的原始问题）"""
    data = BlindSpotDAO.get_blind_spots(
        scene_type=scene_type,
        page=page,
        page_size=page_size,
    )
    return {"success": True, "data": data}


@router.get("/feedback")
async def get_feedback_list(
    signal_type: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
    current_admin: dict = Depends(get_admin_session),
):
    """顾问反馈汇总（侧边栏反馈按钮采集）"""
    data = TaskLogDAO.get_feedbacks(
        signal_type=signal_type,
        page=page,
        page_size=page_size,
    )
    return {"success": True, "data": data}
