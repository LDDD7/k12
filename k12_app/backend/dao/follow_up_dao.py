"""
CRM 跟进记录 DAO — 操作 biz_follow_up 表（V3.1 新增，SQLAlchemy ORM）
记录电话/试听/线下面谈/外勤拜访等非即时通讯跟进
与 msg_wxqy_chat 互补，形成完整客户触达时间线
支持三维度权限过滤（owner_field = user_id）
"""

from typing import Optional, List, Dict
from datetime import datetime

from sqlalchemy import func, case, delete, update

from k12_app.backend.dao.db import session_scope
from k12_app.backend.dao.base_dao import apply_scope_conditions
from k12_app.backend.models import BizFollowUp, BizCustomer, SysEmployee


class FollowUpDAO:
    """跟进记录数据访问"""

    FOLLOW_UP_TYPES = {"电话", "试听", "线下面谈", "外勤", "外勤拜访", "其他"}
    RESULTS = {"已联系", "未接通", "改期", "已到店", "已试听", "已成交", "拒绝", "有效联系", "有意向", "无意向", "待跟进"}

    @staticmethod
    def get_list(
        user_id: str,
        data_scope: str,
        wework_account_id: Optional[str],
        external_id: Optional[str] = None,
        follow_up_type: Optional[str] = None,
        result: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Dict:
        with session_scope() as session:
            query = (
                session.query(
                    BizFollowUp,
                    BizCustomer.name.label("customer_name"),
                    SysEmployee.name.label("advisor_name"),
                )
                .outerjoin(BizCustomer, BizCustomer.external_id == BizFollowUp.external_id)
                .outerjoin(SysEmployee, SysEmployee.user_id == BizFollowUp.user_id)
            )
            query = apply_scope_conditions(
                query=query,
                model=BizFollowUp,
                data_scope=data_scope,
                user_id=user_id,
                wework_account_id=wework_account_id,
                owner_field="user_id",
            )

            if external_id:
                query = query.filter(BizFollowUp.external_id == external_id)
            if follow_up_type:
                query = query.filter(BizFollowUp.follow_up_type == follow_up_type)
            if result:
                query = query.filter(BizFollowUp.result == result)
            if start_date:
                query = query.filter(BizFollowUp.follow_up_time >= start_date)
            if end_date:
                query = query.filter(BizFollowUp.follow_up_time <= end_date)

            total = session.query(func.count()).select_from(query.subquery()).scalar()
            rows = (
                query.order_by(BizFollowUp.follow_up_time.desc())
                .limit(page_size)
                .offset((page - 1) * page_size)
                .all()
            )
            items = []
            for r in rows:
                f = r[0]
                items.append({
                    "id": f.id,
                    "external_id": f.external_id,
                    "user_id": f.user_id,
                    "wework_account_id": f.wework_account_id,
                    "follow_up_type": f.follow_up_type,
                    "content": f.content,
                    "result": f.result,
                    "follow_up_time": f.follow_up_time,
                    "next_action": f.next_action,
                    "created_at": f.created_at,
                    "updated_at": f.updated_at,
                    "customer_name": r.customer_name,
                    "advisor_name": r.advisor_name,
                })
            return {"items": items, "total": total, "page": page, "page_size": page_size}

    @staticmethod
    def get_by_id(
        follow_up_id: int,
        user_id: str,
        data_scope: str,
        wework_account_id: Optional[str],
    ) -> Optional[Dict]:
        """按 ID 查询跟进记录（带权限过滤）"""
        with session_scope() as session:
            query = session.query(BizFollowUp).filter(BizFollowUp.id == follow_up_id)
            query = apply_scope_conditions(
                query=query,
                model=BizFollowUp,
                data_scope=data_scope,
                user_id=user_id,
                wework_account_id=wework_account_id,
                owner_field="user_id",
            )
            f = query.first()
            if not f:
                return None
            return {
                "id": f.id,
                "external_id": f.external_id,
                "user_id": f.user_id,
                "wework_account_id": f.wework_account_id,
                "follow_up_type": f.follow_up_type,
                "content": f.content,
                "result": f.result,
                "follow_up_time": f.follow_up_time,
                "next_action": f.next_action,
                "created_at": f.created_at,
                "updated_at": f.updated_at,
            }

    @staticmethod
    def get_by_external_id(
        external_id: str,
        user_id: str,
        data_scope: str,
        wework_account_id: Optional[str],
        limit: int = 50,
    ) -> List[Dict]:
        """按客户查询跟进记录（用于客户时间线）"""
        with session_scope() as session:
            query = session.query(BizFollowUp).filter(
                BizFollowUp.external_id == external_id
            )
            query = apply_scope_conditions(
                query=query,
                model=BizFollowUp,
                data_scope=data_scope,
                user_id=user_id,
                wework_account_id=wework_account_id,
                owner_field="user_id",
            )
            rows = query.order_by(BizFollowUp.follow_up_time.desc()).limit(limit).all()
            return [
                {
                    "id": r.id,
                    "external_id": r.external_id,
                    "user_id": r.user_id,
                    "wework_account_id": r.wework_account_id,
                    "follow_up_type": r.follow_up_type,
                    "content": r.content,
                    "result": r.result,
                    "follow_up_time": r.follow_up_time,
                    "next_action": r.next_action,
                    "created_at": r.created_at,
                    "updated_at": r.updated_at,
                }
                for r in rows
            ]

    @staticmethod
    def get_by_user(
        follow_user_id: str,
        user_id: str,
        data_scope: str,
        wework_account_id: Optional[str],
        limit: int = 50,
    ) -> List[Dict]:
        """按顾问查询跟进记录"""
        with session_scope() as session:
            query = session.query(BizFollowUp).filter(
                BizFollowUp.user_id == follow_user_id
            )
            query = apply_scope_conditions(
                query=query,
                model=BizFollowUp,
                data_scope=data_scope,
                user_id=user_id,
                wework_account_id=wework_account_id,
                owner_field="user_id",
            )
            rows = query.order_by(BizFollowUp.follow_up_time.desc()).limit(limit).all()
            return [
                {
                    "id": r.id,
                    "external_id": r.external_id,
                    "user_id": r.user_id,
                    "wework_account_id": r.wework_account_id,
                    "follow_up_type": r.follow_up_type,
                    "content": r.content,
                    "result": r.result,
                    "follow_up_time": r.follow_up_time,
                    "next_action": r.next_action,
                    "created_at": r.created_at,
                    "updated_at": r.updated_at,
                }
                for r in rows
            ]

    @staticmethod
    def get_by_type(
        follow_up_type: str,
        user_id: str,
        data_scope: str,
        wework_account_id: Optional[str],
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> List[Dict]:
        """按跟进类型统计查询"""
        with session_scope() as session:
            query = session.query(BizFollowUp).filter(
                BizFollowUp.follow_up_type == follow_up_type
            )
            query = apply_scope_conditions(
                query=query,
                model=BizFollowUp,
                data_scope=data_scope,
                user_id=user_id,
                wework_account_id=wework_account_id,
                owner_field="user_id",
            )
            if start_date:
                query = query.filter(BizFollowUp.follow_up_time >= start_date)
            if end_date:
                query = query.filter(BizFollowUp.follow_up_time <= end_date)
            rows = query.order_by(BizFollowUp.follow_up_time.desc()).all()
            return [
                {
                    "id": r.id,
                    "external_id": r.external_id,
                    "user_id": r.user_id,
                    "wework_account_id": r.wework_account_id,
                    "follow_up_type": r.follow_up_type,
                    "content": r.content,
                    "result": r.result,
                    "follow_up_time": r.follow_up_time,
                }
                for r in rows
            ]

    @staticmethod
    def create(
        external_id: str,
        user_id: str,
        wework_account_id: str,
        follow_up_type: str,
        follow_up_time: datetime,
        content: Optional[str] = None,
        result: Optional[str] = None,
        next_action: Optional[str] = None,
    ) -> Optional[int]:
        """创建跟进记录"""
        if follow_up_type not in FollowUpDAO.FOLLOW_UP_TYPES:
            raise ValueError(f"无效的跟进类型: {follow_up_type}，允许值: {FollowUpDAO.FOLLOW_UP_TYPES}")
        if result and result not in FollowUpDAO.RESULTS:
            raise ValueError(f"无效的跟进结果: {result}，允许值: {FollowUpDAO.RESULTS}")

        with session_scope(commit=True) as session:
            obj = BizFollowUp(
                external_id=external_id,
                user_id=user_id,
                wework_account_id=wework_account_id,
                follow_up_type=follow_up_type,
                content=content,
                result=result,
                follow_up_time=follow_up_time,
                next_action=next_action,
            )
            session.add(obj)
            session.flush()
            return obj.id

    @staticmethod
    def update(
        follow_up_id: int,
        content: Optional[str] = None,
        result: Optional[str] = None,
        follow_up_time: Optional[datetime] = None,
        next_action: Optional[str] = None,
        follow_up_type: Optional[str] = None,
    ) -> bool:
        """更新跟进记录（仅更新传入字段）"""
        with session_scope(commit=True) as session:
            row = (
                session.query(BizFollowUp)
                .filter(BizFollowUp.id == follow_up_id)
                .first()
            )
            if not row:
                return False

            if follow_up_type is not None:
                if follow_up_type not in FollowUpDAO.FOLLOW_UP_TYPES:
                    raise ValueError(f"无效的跟进类型: {follow_up_type}")
                row.follow_up_type = follow_up_type
            if content is not None:
                row.content = content
            if result is not None:
                if result not in FollowUpDAO.RESULTS:
                    raise ValueError(f"无效的跟进结果: {result}")
                row.result = result
            if follow_up_time is not None:
                row.follow_up_time = follow_up_time
            if next_action is not None:
                row.next_action = next_action
            return True

    @staticmethod
    def delete(follow_up_id: int) -> bool:
        """物理删除跟进记录"""
        with session_scope(commit=True) as session:
            result = session.execute(
                delete(BizFollowUp).where(BizFollowUp.id == follow_up_id)
            )
            return result.rowcount > 0

    @staticmethod
    def exists(follow_up_id: int) -> bool:
        """检查跟进记录是否存在"""
        with session_scope() as session:
            return (
                session.query(BizFollowUp)
                .filter(BizFollowUp.id == follow_up_id)
                .first()
                is not None
            )

    @staticmethod
    def get_type_stats(
        user_id: str,
        data_scope: str,
        wework_account_id: Optional[str],
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> List[Dict]:
        """按跟进类型统计（用于看板）"""
        with session_scope() as session:
            query = session.query(
                BizFollowUp.follow_up_type,
                func.count(BizFollowUp.id).label("total"),
                func.sum(case((BizFollowUp.result == "已联系", 1), else_=0)).label("contacted"),
                func.sum(case((BizFollowUp.result == "已到店", 1), else_=0)).label("arrived"),
                func.sum(case((BizFollowUp.result == "已试听", 1), else_=0)).label("tried"),
            )
            query = apply_scope_conditions(
                query=query,
                model=BizFollowUp,
                data_scope=data_scope,
                user_id=user_id,
                wework_account_id=wework_account_id,
                owner_field="user_id",
            )
            if start_date:
                query = query.filter(BizFollowUp.follow_up_time >= start_date)
            if end_date:
                query = query.filter(BizFollowUp.follow_up_time <= end_date)
            rows = (
                query.group_by(BizFollowUp.follow_up_type)
                .order_by(func.count(BizFollowUp.id).desc())
                .all()
            )
            return [
                {
                    "follow_up_type": r.follow_up_type,
                    "total": int(r.total or 0),
                    "contacted": int(r.contacted or 0),
                    "arrived": int(r.arrived or 0),
                    "tried": int(r.tried or 0),
                }
                for r in rows
            ]
