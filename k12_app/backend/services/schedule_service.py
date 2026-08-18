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
        """物理删除日程（任意状态，权限校验由调用方负责）"""
        return ScheduleDAO.delete(schedule_id)

    @staticmethod
    def add_schedule_pending(
        external_id: str,
        user_id: str,
        wework_account_id: str,
        sched: Dict[str, Any],
        operator_id: str,
    ) -> Optional[int]:
        """添加 AI 建议日程为「待确认」（不自动确认、不同步，供操作员后续确认）"""
        try:
            schedule_id = ScheduleDAO.create(
                external_id=external_id,
                user_id=user_id,
                wework_account_id=wework_account_id,
                title=sched.get("title", "待办事项"),
                start_time=sched.get("start_time") or datetime.now(),
                end_time=sched.get("end_time"),
                priority=sched.get("priority", "中"),
                source=sched.get("source", "AI 识别"),
                status="待确认",
            )
            if not schedule_id:
                logger.error(f"添加待确认日程失败: external_id={external_id}")
                return None
            TaskLogDAO.log_task(
                task_type="schedule",
                user_id=user_id,
                external_id=external_id,
                wework_account_id=wework_account_id,
                action="modified",
                action_detail={"schedule_id": schedule_id, "op": "add_pending", "by": operator_id},
            )
            logger.info(f"待确认日程已添加: schedule_id={schedule_id}")
            return schedule_id
        except Exception as e:
            logger.error(f"添加待确认日程异常: {e}", exc_info=True)
            return None

    @staticmethod
    def confirm_by_operator(
        schedule_id: int,
        confirmed_by: str,
        user_id: str,
        data_scope: str,
        wework_account_id: Optional[str],
    ) -> Optional[Dict]:
        """操作员确认日程（待确认 → 已确认，锁定后 AI 不再改动）"""
        s = ScheduleService.get_by_id(
            schedule_id=schedule_id,
            user_id=user_id,
            data_scope=data_scope,
            wework_account_id=wework_account_id,
        )
        if not s:
            return None
        if s.get("status") == "已确认" and s.get("confirm_source") == "operator":
            return s  # 已被操作员锁定
        if not ScheduleDAO.confirm_by_operator(schedule_id, confirmed_by):
            return None
        ScheduleService._finalize_confirmed(s)
        return s

    @staticmethod
    def auto_confirm_matches(
        external_id: str,
        ai_schedules: List[Dict],
        user_id: str,
        data_scope: str,
        wework_account_id: Optional[str],
    ) -> int:
        """AI 自动确认：AI 判定客户已同意的日程 与 待确认日程匹配，命中即转已确认

        仅作用于待确认日程；操作员已确认的（status=已确认 且 confirm_source=operator）天然被跳过。
        """
        if not ai_schedules:
            return 0
        confirmed_ai = [
            s for s in ai_schedules
            if isinstance(s, dict) and s.get("confirmed")
        ]
        if not confirmed_ai:
            return 0
        pendings = [
            s for s in ScheduleDAO.get_by_external_id(
                external_id=external_id,
                user_id=user_id,
                data_scope=data_scope,
                wework_account_id=wework_account_id,
            )
            if s.get("status") == "待确认"
        ]
        count = 0
        for pend in pendings:
            for ai in confirmed_ai:
                if ScheduleService._match_schedule(pend, ai):
                    if ScheduleDAO.confirm_by_ai(pend["id"]):
                        ScheduleService._finalize_confirmed(pend)
                        count += 1
                    break
        if count:
            logger.info(f"AI 自动确认日程 {count} 条: external_id={external_id}")
        return count

    @staticmethod
    def _match_schedule(pend: Dict, ai: Dict) -> bool:
        """匹配规则：开始日期相同 且 标题归一化后相等或互为子串"""
        pd = ScheduleService._date_of(pend.get("start_time"))
        ad = ScheduleService._date_of(ai.get("start_time"))
        if pd is None or ad is None or pd != ad:
            return False
        pt = "".join(str(pend.get("title") or "").split()).lower()
        at = "".join(str(ai.get("title") or "").split()).lower()
        return pt == at or (pt and at and (pt in at or at in pt))

    @staticmethod
    def _date_of(value):
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, str):
            try:
                return datetime.strptime(value.strip()[:10], "%Y-%m-%d").date()
            except Exception:
                return None
        return None

    @staticmethod
    def _finalize_confirmed(schedule: Dict) -> None:
        """日程确认后的收尾：同步企微日历 + 分级提醒 + 埋点"""
        schedule_id = schedule.get("id")
        external_id = schedule.get("external_id")
        wework_account_id = schedule.get("wework_account_id")
        owner_id = schedule.get("user_id")
        priority = schedule.get("priority", "中")
        wx_event_id = None
        try:
            wx_event_id = sync_calendar(wework_account_id, {
                "title": schedule.get("title"),
                "start_time": schedule.get("start_time"),
                "end_time": schedule.get("end_time"),
            })
            if wx_event_id:
                ScheduleDAO.set_wx_event(schedule_id, wx_event_id)
        except Exception as e:
            logger.warning(f"同步企微日历失败: {e}")
        if _should_notify(owner_id, priority):
            content = (
                f"⏰ 高优先级日程提醒: {schedule.get('title')}"
                if priority == "高"
                else f"📋 日程提醒: {schedule.get('title')}"
            )
            try:
                send_notify(account_id=wework_account_id, user_id=owner_id, content=content)
            except Exception as e:
                logger.warning(f"发送日程提醒失败: {e}")
        TaskLogDAO.log_task(
            task_type="schedule",
            user_id=owner_id,
            external_id=external_id,
            wework_account_id=wework_account_id,
            action="confirmed",
            action_detail={"schedule_id": schedule_id, "wx_event_id": wx_event_id, "priority": priority},
        )

    @staticmethod
    def exists(schedule_id: int) -> bool:
        """检查日程是否存在"""
        return ScheduleDAO.exists(schedule_id)
