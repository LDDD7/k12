"""
日程 DAO — 操作 biz_schedule 表（SQLAlchemy ORM）
支持：
- 状态流转：待确认 → 已确认 → 已同步企微日历 → 已完成
- 三维度权限过滤（owner_field = user_id）
- 优先级分级（高/中/低）
"""

from typing import Optional, List, Dict
from datetime import datetime

from sqlalchemy import func, delete, update

from k12_app.backend.dao.db import session_scope
from k12_app.backend.dao.base_dao import apply_scope_conditions
from k12_app.backend.models import BizSchedule, BizCustomer


class ScheduleDAO:
    """日程数据访问"""

    @staticmethod
    def get_admin_list(
        user_id: str,
        data_scope: str,
        wework_account_id: Optional[str],
        page: int = 1,
        page_size: int = 20,
    ) -> Dict:
        """管理后台日程列表（含客户名称，三维度权限过滤）"""
        with session_scope() as session:
            query = (
                session.query(
                    BizSchedule.id,
                    BizSchedule.external_id,
                    BizSchedule.title,
                    BizSchedule.start_time,
                    BizSchedule.end_time,
                    BizSchedule.priority,
                    BizSchedule.status,
                    BizSchedule.wework_account_id,
                    BizSchedule.user_id,
                    BizSchedule.created_at,
                    BizSchedule.updated_at,
                    BizCustomer.name.label("customer_name"),
                )
                .outerjoin(BizCustomer, BizCustomer.external_id == BizSchedule.external_id)
            )
            query = apply_scope_conditions(
                query=query,
                model=BizSchedule,
                data_scope=data_scope,
                user_id=user_id,
                wework_account_id=wework_account_id,
                owner_field="user_id",
            )
            if data_scope == "self" and not wework_account_id:
                return {"items": [], "total": 0, "page": page, "page_size": page_size}

            total = session.query(func.count()).select_from(query.subquery()).scalar()
            rows = (
                query.order_by(BizSchedule.start_time.desc())
                .limit(page_size)
                .offset((page - 1) * page_size)
                .all()
            )
            items = [
                {
                    "id": r.id,
                    "external_id": r.external_id,
                    "title": r.title,
                    "start_time": r.start_time,
                    "end_time": r.end_time,
                    "priority": r.priority,
                    "status": r.status,
                    "wework_account_id": r.wework_account_id,
                    "user_id": r.user_id,
                    "created_at": r.created_at,
                    "updated_at": r.updated_at,
                    "customer_name": r.customer_name,
                }
                for r in rows
            ]
            return {"items": items, "total": total, "page": page, "page_size": page_size}

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
        """获取日程列表（三维度权限过滤）"""
        with session_scope() as session:
            query = session.query(BizSchedule)
            query = apply_scope_conditions(
                query=query,
                model=BizSchedule,
                data_scope=data_scope,
                user_id=user_id,
                wework_account_id=wework_account_id,
                owner_field="user_id",
            )

            if status:
                query = query.filter(BizSchedule.status == status)
            if priority:
                query = query.filter(BizSchedule.priority == priority)
            if start_date:
                query = query.filter(BizSchedule.start_time >= start_date)
            if end_date:
                query = query.filter(BizSchedule.end_time <= end_date)

            total = session.query(func.count()).select_from(query.subquery()).scalar()
            rows = (
                query.order_by(BizSchedule.start_time.asc())
                .limit(page_size)
                .offset((page - 1) * page_size)
                .all()
            )
            items = [
                {
                    "id": r.id,
                    "external_id": r.external_id,
                    "user_id": r.user_id,
                    "wework_account_id": r.wework_account_id,
                    "title": r.title,
                    "start_time": r.start_time,
                    "end_time": r.end_time,
                    "priority": r.priority,
                    "source": r.source,
                    "status": r.status,
                    "wx_calendar_event_id": r.wx_calendar_event_id,
                    "created_at": r.created_at,
                    "updated_at": r.updated_at,
                }
                for r in rows
            ]
            return {"items": items, "total": total, "page": page, "page_size": page_size}

    @staticmethod
    def get_by_id(
        schedule_id: int,
        user_id: str,
        data_scope: str,
        wework_account_id: Optional[str],
    ) -> Optional[Dict]:
        """按 ID 查询日程（带权限过滤）"""
        with session_scope() as session:
            query = session.query(BizSchedule).filter(BizSchedule.id == schedule_id)
            query = apply_scope_conditions(
                query=query,
                model=BizSchedule,
                data_scope=data_scope,
                user_id=user_id,
                wework_account_id=wework_account_id,
                owner_field="user_id",
            )
            r = query.first()
            if not r:
                return None
            return {
                "id": r.id,
                "external_id": r.external_id,
                "user_id": r.user_id,
                "wework_account_id": r.wework_account_id,
                "title": r.title,
                "start_time": r.start_time,
                "end_time": r.end_time,
                "priority": r.priority,
                "source": r.source,
                "status": r.status,
                "wx_calendar_event_id": r.wx_calendar_event_id,
                "created_at": r.created_at,
                "updated_at": r.updated_at,
            }

    @staticmethod
    def get_by_external_id(
        external_id: str,
        user_id: str,
        data_scope: str,
        wework_account_id: Optional[str],
    ) -> List[Dict]:
        """按客户查询日程"""
        with session_scope() as session:
            query = session.query(BizSchedule).filter(BizSchedule.external_id == external_id)
            query = apply_scope_conditions(
                query=query,
                model=BizSchedule,
                data_scope=data_scope,
                user_id=user_id,
                wework_account_id=wework_account_id,
                owner_field="user_id",
            )
            rows = query.order_by(BizSchedule.start_time.asc()).all()
            return [
                {
                    "id": r.id,
                    "external_id": r.external_id,
                    "user_id": r.user_id,
                    "wework_account_id": r.wework_account_id,
                    "title": r.title,
                    "start_time": r.start_time,
                    "end_time": r.end_time,
                    "priority": r.priority,
                    "source": r.source,
                    "status": r.status,
                    "wx_calendar_event_id": r.wx_calendar_event_id,
                }
                for r in rows
            ]

    @staticmethod
    def get_pending(
        user_id: str,
        data_scope: str,
        wework_account_id: Optional[str],
    ) -> List[Dict]:
        """获取待确认的日程"""
        return ScheduleDAO.get_list(
            user_id=user_id,
            data_scope=data_scope,
            wework_account_id=wework_account_id,
            status="待确认",
            page=1,
            page_size=100,
        )["items"]

    @staticmethod
    def create(
        external_id: str,
        user_id: str,
        wework_account_id: str,
        title: str,
        start_time: datetime,
        end_time: Optional[datetime] = None,
        priority: str = "中",
        source: str = "人工创建",
        status: str = "待确认",
    ) -> Optional[int]:
        """创建日程"""
        with session_scope(commit=True) as session:
            obj = BizSchedule(
                external_id=external_id,
                user_id=user_id,
                wework_account_id=wework_account_id,
                title=title,
                start_time=start_time,
                end_time=end_time,
                priority=priority,
                source=source,
                status=status,
            )
            session.add(obj)
            session.flush()
            return obj.id

    @staticmethod
    def update(
        schedule_id: int,
        title: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        priority: Optional[str] = None,
        status: Optional[str] = None,
    ) -> bool:
        """更新日程（仅更新传入字段）"""
        with session_scope(commit=True) as session:
            row = (
                session.query(BizSchedule).filter(BizSchedule.id == schedule_id).first()
            )
            if not row:
                return False
            if title is not None:
                row.title = title
            if start_time is not None:
                row.start_time = start_time
            if end_time is not None:
                row.end_time = end_time
            if priority is not None:
                row.priority = priority
            if status is not None:
                row.status = status
            return True

    @staticmethod
    def confirm(schedule_id: int) -> bool:
        """确认日程（待确认 → 已确认）"""
        with session_scope(commit=True) as session:
            result = session.execute(
                update(BizSchedule)
                .where(BizSchedule.id == schedule_id, BizSchedule.status == "待确认")
                .values(status="已确认")
            )
            return result.rowcount > 0

    @staticmethod
    def mark_synced(schedule_id: int, wx_calendar_event_id: str) -> bool:
        """标记已同步企微日历（已确认 → 已同步企微日历）"""
        with session_scope(commit=True) as session:
            result = session.execute(
                update(BizSchedule)
                .where(BizSchedule.id == schedule_id, BizSchedule.status == "已确认")
                .values(status="已同步企微日历", wx_calendar_event_id=wx_calendar_event_id)
            )
            return result.rowcount > 0

    @staticmethod
    def complete(schedule_id: int) -> bool:
        """完成日程（已同步企微日历 → 已完成）"""
        with session_scope(commit=True) as session:
            result = session.execute(
                update(BizSchedule)
                .where(BizSchedule.id == schedule_id, BizSchedule.status == "已同步企微日历")
                .values(status="已完成")
            )
            return result.rowcount > 0

    @staticmethod
    def discard(schedule_id: int) -> bool:
        """放弃日程（仅待确认状态可删除）"""
        with session_scope(commit=True) as session:
            result = session.execute(
                delete(BizSchedule).where(
                    BizSchedule.id == schedule_id, BizSchedule.status == "待确认"
                )
            )
            return result.rowcount > 0

    @staticmethod
    def delete(schedule_id: int) -> bool:
        """物理删除日程（仅已完成状态可删除）"""
        with session_scope(commit=True) as session:
            result = session.execute(
                delete(BizSchedule).where(
                    BizSchedule.id == schedule_id, BizSchedule.status == "已完成"
                )
            )
            return result.rowcount > 0

    @staticmethod
    def exists(schedule_id: int) -> bool:
        """检查日程是否存在"""
        with session_scope() as session:
            return (
                session.query(BizSchedule)
                .filter(BizSchedule.id == schedule_id)
                .first()
                is not None
            )
