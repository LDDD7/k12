"""
提醒偏好服务 — 用户日程提醒偏好（4.5）
业务层：供路由层调用，数据访问委托给 RemindPreferenceDAO
"""

import logging
from typing import Dict

from k12_app.backend.dao.remind_preference_dao import (
    RemindPreferenceDAO,
    VALID_REMIND_PREFS,
)

logger = logging.getLogger(__name__)


class RemindPreferenceService:
    """提醒偏好服务"""

    VALID_REMIND_PREFS = VALID_REMIND_PREFS

    @staticmethod
    def get(user_id: str) -> Dict:
        """查询用户提醒偏好（无记录返回默认 mid）"""
        return RemindPreferenceDAO.get(user_id)

    @staticmethod
    def upsert(user_id: str, remind_pref: str) -> bool:
        """更新提醒偏好"""
        return RemindPreferenceDAO.upsert(user_id, remind_pref)
