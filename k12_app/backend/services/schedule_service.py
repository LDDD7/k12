"""
日程服务 — AI 日程识别与提醒 + 日程管理
从聊天记录中识别时间信息 → 生成日程 → 顾问确认后同步企微日历
priority 字段分级：高（续费/试听）/ 中 / 低
"""

import logging
from typing import Optional, Dict, Any, List
from datetime import datetime

from k12_app.backend.dao.schedule_dao import ScheduleDAO
from k12_app.backend.dao.task_log_dao import TaskLogDAO
from k12_app.backend.dao.remind_preference_dao import RemindPreferenceDAO
from k12_app.backend.agent.tools import sync_calendar, send_notify

logger = logging.getLogger(__name__)


def _should_notify(user_id: str, priority: str) -> bool:
    """根据用户提醒偏好 + 日程优先级决定是否推送通知（4.4 / 4.5）"""
    try:
        pref = RemindPreferenceDAO.get(user_id).get("remind_pref", "mid")
    except Exception as e:
        logger.warning(f"读取提醒偏好失败，使用默认 mid: {e}")
        pref = "mid"

    if pref == "high":
        return priority == "高"
    if pref == "mid":
        return priority in ("高", "中")
    # low：全部不推送（仅侧边栏/日历弱提示）
    return False


class ScheduleService:
    """日程服务"""

    @staticmethod
    def confirm_schedule(
        external_id: str,
        user_id: str,
        wework_account_id: str,
        schedule_data: Dict[str, Any],
        confirmed_by: str,
        sync_to_wework: bool = True,
    ) -> Optional[int]:
        """
        确认日程 → 写入数据库 → 同步企微日历 → 发送通知

        Args:
            external_id: 客户 ID
            user_id: 顾问 ID
            wework_account_id: 企微账户 ID
            schedule_data: 日程数据（title, start_time, end_time, priority, source）
            confirmed_by: 确认人
            sync_to_wework: 是否同步到企微

        Returns:
            schedule_id 或 None
        """
        try:
            # 1. 创建日程
            schedule_id = ScheduleDAO.create(
                external_id=external_id,
                user_id=user_id,
                wework_account_id=wework_account_id,
                title=schedule_data.get("title", "待办事项"),
                start_time=schedule_data.get("start_time", datetime.now()),
                end_time=schedule_data.get("end_time"),
                priority=schedule_data.get("priority", "中"),
                source=schedule_data.get("source", "AI 识别"),
                status="待确认",
            )

            if not schedule_id:
                logger.error(f"创建日程失败: {external_id}")
                return None

            # 2. 确认日程
            ScheduleDAO.confirm(schedule_id)

            # 3. 同步到企微日历
            wx_event_id = None
            if sync_to_wework:
                wx_event_id = sync_calendar(wework_account_id, {
                    "title": schedule_data.get("title"),
                    "start_time": schedule_data.get("start_time"),
                    "end_time": schedule_data.get("end_time"),
                })
                if wx_event_id:
                    ScheduleDAO.mark_synced(schedule_id, wx_event_id)

            # 4. 分级提醒 + 用户偏好（4.4 / 4.5 / N15）
            priority = schedule_data.get("priority", "中")
            if _should_notify(user_id, priority):
                content = (
                    f"⏰ 高优先级日程提醒: {schedule_data.get('title')}"
                    if priority == "高"
                    else f"📋 日程提醒: {schedule_data.get('title')}"
                )
                send_notify(
                    account_id=wework_account_id,
                    user_id=user_id,
                    content=content,
                )

            # 5. 记录埋点
            TaskLogDAO.log_task(
                task_type="schedule",
                user_id=user_id,
                external_id=external_id,
                wework_account_id=wework_account_id,
                action="confirmed",
                action_detail={
                    "schedule_id": schedule_id,
                    "wx_event_id": wx_event_id,
                    "priority": priority,
                },
            )

            logger.info(f"日程确认成功: external_id={external_id}, schedule_id={schedule_id}")
            return schedule_id

        except Exception as e:
            logger.error(f"确认日程异常: {e}", exc_info=True)
            return None

    @staticmethod
    def complete_schedule(schedule_id: int) -> bool:
        """标记日程为已完成"""
        return ScheduleDAO.complete(schedule_id)

    # ==================== 日程管理（管理后台 / 侧边栏） ====================

    @staticmethod
    def get_admin_list(
        user_id: str,
        data_scope: str,
        wework_account_id: Optional[str],
        page: int = 1,
        page_size: int = 20,
    ) -> Dict:
        """管理后台日程列表（含客户名称）"""
        return ScheduleDAO.get_admin_list(
            user_id=user_id,
            data_scope=data_scope,
            wework_account_id=wework_account_id,
            page=page,
            page_size=page_size,
        )

    @staticmethod
    def get_list(
        user_id: str,
        data_scope: str,
        wework_account_id: Optional[str],
        status: Optional[str] = None,
        priority: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Dict:
        """获取日程列表"""
        return ScheduleDAO.get_list(
            user_id=user_id,
            data_scope=data_scope,
            wework_account_id=wework_account_id,
            status=status,
            priority=priority,
            start_date=start_date,
            end_date=end_date,
            page=page,
            page_size=page_size,
        )

    @staticmethod
    def get_by_external_id(
        external_id: str,
        user_id: str,
        data_scope: str,
        wework_account_id: Optional[str],
    ) -> List[Dict]:
        """按客户查询日程"""
        return ScheduleDAO.get_by_external_id(
            external_id=external_id,
            user_id=user_id,
            data_scope=data_scope,
            wework_account_id=wework_account_id,
        )

    @staticmethod
    def get_by_id(
        schedule_id: int,
        user_id: str,
        data_scope: str,
        wework_account_id: Optional[str],
    ) -> Optional[Dict]:
        """按 ID 查询日程"""
        return ScheduleDAO.get_by_id(
            schedule_id=schedule_id,
            user_id=user_id,
            data_scope=data_scope,
            wework_account_id=wework_account_id,
        )

    @staticmethod
    def update_schedule(
        schedule_id: int,
        title: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        priority: Optional[str] = None,
        status: Optional[str] = None,
    ) -> bool:
        """更新日程（仅更新传入字段）"""
        return ScheduleDAO.update(
            schedule_id=schedule_id,
            title=title,
            start_time=start_time,
            end_time=end_time,
            priority=priority,
            status=status,
        )

    @staticmethod
    def confirm(schedule_id: int) -> bool:
        """确认日程（待确认 → 已确认）"""
        return ScheduleDAO.confirm(schedule_id)

    @staticmethod
    def mark_synced(schedule_id: int, wx_calendar_event_id: str) -> bool:
        """标记已同步企微日历"""
        return ScheduleDAO.mark_synced(schedule_id, wx_calendar_event_id)

    @staticmethod
    def discard(schedule_id: int) -> bool:
        """放弃日程（仅待确认状态可删除）"""
        return ScheduleDAO.discard(schedule_id)

    @staticmethod
    def delete(schedule_id: int) -> bool:
        """物理删除日程（仅已完成状态可删除）"""
        return ScheduleDAO.delete(schedule_id)

    @staticmethod
    def exists(schedule_id: int) -> bool:
        """检查日程是否存在"""
        return ScheduleDAO.exists(schedule_id)
