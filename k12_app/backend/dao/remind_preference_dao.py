"""
提醒偏好 DAO — 操作 sys_remind_preference 表（4.5）
存储用户级日程提醒偏好：remind_pref ∈ high / mid / low
  - high：仅高优先级日程强提醒
  - mid ：高优先级强提醒 + 中优先级普通通知（默认）
  - low ：仅侧边栏/日历弱提示，不推送企微消息
"""

from typing import Dict

from sqlalchemy import text

from k12_app.backend.dao.db import session_scope
from k12_app.backend.models import SysRemindPreference

VALID_REMIND_PREFS = ("high", "mid", "low")
DEFAULT_REMIND_PREF = "mid"

_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS sys_remind_preference (
    user_id     VARCHAR(64) NOT NULL PRIMARY KEY,
    remind_pref VARCHAR(8) NOT NULL DEFAULT 'mid',
    updated_at  DATETIME(3) DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
"""

_initialized = False


def _ensure_table() -> None:
    """幂等建表（兼容已初始化的存量库，无需单独迁移步骤）"""
    global _initialized
    if _initialized:
        return
    with session_scope(commit=True) as session:
        session.execute(text(_TABLE_SQL))
    _initialized = True


class RemindPreferenceDAO:
    """提醒偏好数据访问"""

    @staticmethod
    def get(user_id: str) -> Dict:
        """获取用户提醒偏好（无记录时返回默认值）"""
        _ensure_table()
        with session_scope() as session:
            row = (
                session.query(SysRemindPreference)
                .filter(SysRemindPreference.user_id == user_id)
                .first()
            )
            if not row:
                return {"user_id": user_id, "remind_pref": DEFAULT_REMIND_PREF}
            return {"user_id": row.user_id, "remind_pref": row.remind_pref}

    @staticmethod
    def upsert(user_id: str, remind_pref: str) -> bool:
        """新增或更新提醒偏好"""
        _ensure_table()
        with session_scope(commit=True) as session:
            row = (
                session.query(SysRemindPreference)
                .filter(SysRemindPreference.user_id == user_id)
                .first()
            )
            if row:
                row.remind_pref = remind_pref
            else:
                session.add(SysRemindPreference(user_id=user_id, remind_pref=remind_pref))
            return True
