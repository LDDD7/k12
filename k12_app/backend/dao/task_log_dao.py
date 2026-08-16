"""
AI 任务日志 DAO — 操作 ai_task_log + ai_feedback_signal 表（SQLAlchemy ORM）
支持：
- AI 任务埋点（shown/adopted/discarded/recreated/confirmed）
- 反馈信号记录
- 采纳率统计（adopted / (adopted + discarded)）
"""

from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta

from sqlalchemy import func, case, delete

from k12_app.backend.dao.db import session_scope
from k12_app.backend.dao.base_dao import apply_scope_conditions
from k12_app.backend.models import AiTaskLog, AiFeedbackSignal, SysEmployee


class TaskLogDAO:
    """AI 任务日志数据访问"""

    ACTIONS = {"shown", "adopted", "discarded", "recreated", "confirmed"}

    @staticmethod
    def log_task(
        task_type: str,
        user_id: str,
        external_id: str,
        wework_account_id: str,
        action: str,
        action_detail: Optional[Dict] = None,
        duration_ms: Optional[int] = None,
    ) -> Optional[int]:
        """记录 AI 任务日志"""
        if action not in TaskLogDAO.ACTIONS:
            raise ValueError(f"无效的 action: {action}，允许值: {TaskLogDAO.ACTIONS}")

        with session_scope(commit=True) as session:
            obj = AiTaskLog(
                task_type=task_type,
                user_id=user_id,
                external_id=external_id,
                wework_account_id=wework_account_id,
                action=action,
                action_detail=action_detail,
                duration_ms=duration_ms,
            )
            session.add(obj)
            session.flush()
            return obj.id

    @staticmethod
    def log_feedback(
        task_log_id: int,
        wework_account_id: str,
        signal_type: str,
        snapshot: Optional[Dict] = None,
    ) -> Optional[int]:
        """记录反馈信号"""
        if signal_type not in {"positive", "negative"}:
            raise ValueError(f"无效的 signal_type: {signal_type}，允许值: positive / negative")

        with session_scope(commit=True) as session:
            obj = AiFeedbackSignal(
                task_log_id=task_log_id,
                wework_account_id=wework_account_id,
                signal_type=signal_type,
                snapshot=snapshot,
            )
            session.add(obj)
            session.flush()
            return obj.id

    @staticmethod
    def get_task_logs(
        user_id: str,
        data_scope: str,
        wework_account_id: Optional[str],
        task_type: Optional[str] = None,
        action: Optional[str] = None,
        external_id: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Dict:
        """查询任务日志（带权限过滤）"""
        with session_scope() as session:
            query = session.query(AiTaskLog)
            query = apply_scope_conditions(
                query=query,
                model=AiTaskLog,
                data_scope=data_scope,
                user_id=user_id,
                wework_account_id=wework_account_id,
                owner_field="user_id",
            )

            if task_type:
                query = query.filter(AiTaskLog.task_type == task_type)
            if action:
                query = query.filter(AiTaskLog.action == action)
            if external_id:
                query = query.filter(AiTaskLog.external_id == external_id)
            if start_date:
                query = query.filter(AiTaskLog.created_at >= start_date)
            if end_date:
                query = query.filter(AiTaskLog.created_at <= end_date)

            total = session.query(func.count()).select_from(query.subquery()).scalar()
            rows = (
                query.order_by(AiTaskLog.created_at.desc())
                .limit(page_size)
                .offset((page - 1) * page_size)
                .all()
            )
            items = [
                {
                    "id": r.id,
                    "task_type": r.task_type,
                    "user_id": r.user_id,
                    "external_id": r.external_id,
                    "wework_account_id": r.wework_account_id,
                    "action": r.action,
                    "action_detail": r.action_detail,
                    "duration_ms": r.duration_ms,
                    "created_at": r.created_at,
                    "updated_at": r.updated_at,
                }
                for r in rows
            ]
            return {"items": items, "total": total, "page": page, "page_size": page_size}

    @staticmethod
    def get_feedback_by_task(task_log_id: int) -> Optional[Dict]:
        """查询某任务对应的反馈信号"""
        with session_scope() as session:
            r = (
                session.query(AiFeedbackSignal)
                .filter(AiFeedbackSignal.task_log_id == task_log_id)
                .first()
            )
            if not r:
                return None
            return {
                "id": r.id,
                "task_log_id": r.task_log_id,
                "wework_account_id": r.wework_account_id,
                "signal_type": r.signal_type,
                "snapshot": r.snapshot,
                "created_at": r.created_at,
            }

    @staticmethod
    def get_adopt_rate(
        user_id: str,
        data_scope: str,
        wework_account_id: Optional[str],
        days: int = 30,
    ) -> Dict:
        """计算采纳率（adopted / (adopted + discarded)）"""
        cutoff = datetime.now() - timedelta(days=days)

        with session_scope() as session:
            query = (
                session.query(
                    AiTaskLog.user_id,
                    SysEmployee.name.label("user_name"),
                    func.sum(case((AiTaskLog.action == "shown", 1), else_=0)).label("shown_count"),
                    func.sum(case((AiTaskLog.action == "adopted", 1), else_=0)).label("adopted_count"),
                    func.sum(case((AiTaskLog.action == "discarded", 1), else_=0)).label("discarded_count"),
                    func.sum(case((AiTaskLog.action == "confirmed", 1), else_=0)).label("confirmed_count"),
                )
                .outerjoin(SysEmployee, SysEmployee.user_id == AiTaskLog.user_id)
                .filter(AiTaskLog.created_at >= cutoff)
            )
            query = apply_scope_conditions(
                query=query,
                model=AiTaskLog,
                data_scope=data_scope,
                user_id=user_id,
                wework_account_id=wework_account_id,
                owner_field="user_id",
            )
            rows = (
                query.group_by(AiTaskLog.user_id, SysEmployee.name)
                .all()
            )

            # 如果只有单用户，直接返回
            if not rows:
                return {"adopt_rate": 0, "shown": 0, "adopted": 0, "discarded": 0}

            row_dicts = [
                {
                    "user_id": r.user_id,
                    "user_name": r.user_name,
                    "shown_count": int(r.shown_count or 0),
                    "adopted_count": int(r.adopted_count or 0),
                    "discarded_count": int(r.discarded_count or 0),
                    "confirmed_count": int(r.confirmed_count or 0),
                }
                for r in rows
            ]

            # 计算总采纳率
            total_shown = sum(r["shown_count"] for r in row_dicts)
            total_adopted = sum(r["adopted_count"] for r in row_dicts)
            total_discarded = sum(r["discarded_count"] for r in row_dicts)
            total_confirmed = sum(r["confirmed_count"] for r in row_dicts)

            total_decided = total_adopted + total_discarded
            adopt_rate = round(100.0 * total_adopted / total_decided, 1) if total_decided > 0 else 0

            return {
                "adopt_rate": adopt_rate,
                "shown": total_shown,
                "adopted": total_adopted,
                "discarded": total_discarded,
                "confirmed": total_confirmed,
                "by_user": row_dicts,
            }

    @staticmethod
    def get_adopt_rate_by_task_type(
        user_id: str,
        data_scope: str,
        wework_account_id: Optional[str],
        days: int = 30,
    ) -> List[Dict]:
        """按任务类型统计采纳率"""
        cutoff = datetime.now() - timedelta(days=days)

        with session_scope() as session:
            query = (
                session.query(
                    AiTaskLog.task_type,
                    func.sum(case((AiTaskLog.action == "adopted", 1), else_=0)).label("adopted"),
                    func.sum(case((AiTaskLog.action == "discarded", 1), else_=0)).label("discarded"),
                    func.sum(case((AiTaskLog.action == "confirmed", 1), else_=0)).label("confirmed"),
                )
                .filter(AiTaskLog.created_at >= cutoff)
            )
            query = apply_scope_conditions(
                query=query,
                model=AiTaskLog,
                data_scope=data_scope,
                user_id=user_id,
                wework_account_id=wework_account_id,
                owner_field="user_id",
            )
            rows = query.group_by(AiTaskLog.task_type).all()

            result = []
            for r in rows:
                adopted = int(r.adopted or 0)
                discarded = int(r.discarded or 0)
                confirmed = int(r.confirmed or 0)
                total = adopted + discarded
                result.append({
                    "task_type": r.task_type,
                    "adopted": adopted,
                    "discarded": discarded,
                    "confirmed": confirmed,
                    "adopt_rate": round(100.0 * adopted / total, 1) if total > 0 else 0,
                })
            return result

    @staticmethod
    def get_recent_tasks(
        user_id: str,
        data_scope: str,
        wework_account_id: Optional[str],
        limit: int = 10,
    ) -> List[Dict]:
        """获取最近的 AI 任务（用于侧边栏历史）"""
        with session_scope() as session:
            query = session.query(AiTaskLog)
            query = apply_scope_conditions(
                query=query,
                model=AiTaskLog,
                data_scope=data_scope,
                user_id=user_id,
                wework_account_id=wework_account_id,
                owner_field="user_id",
            )
            rows = (
                query.order_by(AiTaskLog.created_at.desc())
                .limit(limit)
                .all()
            )
            return [
                {
                    "id": r.id,
                    "task_type": r.task_type,
                    "user_id": r.user_id,
                    "external_id": r.external_id,
                    "action": r.action,
                    "action_detail": r.action_detail,
                    "duration_ms": r.duration_ms,
                    "created_at": r.created_at,
                }
                for r in rows
            ]

    @staticmethod
    def get_adopted_external_ids(
        after_time: Optional[datetime] = None,
        limit: int = 200,
    ) -> List[str]:
        """获取被采纳（adopted）回复建议对应的客户 external_id 列表（RAG 索引器用）"""
        with session_scope() as session:
            query = (
                session.query(AiTaskLog.external_id)
                .filter(
                    AiTaskLog.task_type == "reply",
                    AiTaskLog.action == "adopted",
                )
            )
            if after_time:
                query = query.filter(AiTaskLog.created_at > after_time)
            rows = query.distinct().limit(limit).all()
            return [r.external_id for r in rows]
