# k12_app/routes/sidebar/preferences.py
"""侧边栏 — 用户提醒偏好（4.5）

GET  /api/sidebar/remind_preference  查询当前用户提醒偏好
PUT  /api/sidebar/remind_preference  更新提醒偏好（high / mid / low）
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel, field_validator

from k12_app.backend.services.auth_service import get_current_user
from k12_app.backend.services.remind_preference_service import RemindPreferenceService

router = APIRouter()


class RemindPreferenceUpdateRequest(BaseModel):
    remind_pref: str

    @field_validator("remind_pref")
    @classmethod
    def validate_pref(cls, v: str) -> str:
        if v not in RemindPreferenceService.VALID_REMIND_PREFS:
            raise ValueError(f"remind_pref 取值须为 {' / '.join(RemindPreferenceService.VALID_REMIND_PREFS)}")
        return v


@router.get("/remind_preference")
async def get_remind_preference(current_user: dict = Depends(get_current_user)):
    """查询当前用户提醒偏好（无记录返回默认 mid）"""
    pref = RemindPreferenceService.get(current_user["user_id"])
    return {"success": True, "data": pref}


@router.put("/remind_preference")
async def update_remind_preference(
    req: RemindPreferenceUpdateRequest,
    current_user: dict = Depends(get_current_user),
):
    """更新当前用户提醒偏好"""
    RemindPreferenceService.upsert(current_user["user_id"], req.remind_pref)
    return {
        "success": True,
        "data": {"user_id": current_user["user_id"], "remind_pref": req.remind_pref},
        "message": "提醒偏好已保存",
    }
