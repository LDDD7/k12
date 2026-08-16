"""
客户 DAO — 操作 biz_customer + biz_customer_tag 表（SQLAlchemy ORM）
支持：
- 三维度权限过滤（self / region / all）
- V3.2 未绑定员工返回空
- V3.1 线索来源统计
- 客户标签关联查询
"""

from typing import Optional, List, Dict
from datetime import datetime

from sqlalchemy import func, case, select, Integer, delete, update

from k12_app.backend.dao.db import session_scope
from k12_app.backend.dao.base_dao import apply_scope_conditions
from k12_app.backend.models import BizCustomer, BizCustomerTag, CfgTagDefinition


class CustomerDAO:
    """客户数据访问"""

    @staticmethod
    def get_list(
        user_id: str,
        data_scope: str,
        wework_account_id: Optional[str],
        page: int = 1,
        page_size: int = 20,
        stage: Optional[str] = None,
        keyword: Optional[str] = None,
        lead_source: Optional[str] = None,
    ) -> Dict:
        """获取客户列表（三维度权限自动过滤）"""
        tag_count_subq = (
            select(func.count())
            .select_from(BizCustomerTag)
            .where(
                BizCustomerTag.external_id == BizCustomer.external_id,
                BizCustomerTag.confirmed.is_(True),
            )
            .scalar_subquery()
        )

        with session_scope() as session:
            query = session.query(
                BizCustomer.external_id,
                BizCustomer.name,
                BizCustomer.child_name,
                BizCustomer.school,
                BizCustomer.grade,
                BizCustomer.focus_subject,
                BizCustomer.stage,
                BizCustomer.lead_source,
                BizCustomer.wework_account_id,
                BizCustomer.follow_user_id,
                BizCustomer.remark,
                BizCustomer.created_at,
                BizCustomer.updated_at,
                tag_count_subq.label("tag_count"),
            )
            query = apply_scope_conditions(
                query=query,
                model=BizCustomer,
                data_scope=data_scope,
                user_id=user_id,
                wework_account_id=wework_account_id,
                owner_field="follow_user_id",
            )

            if stage:
                query = query.filter(BizCustomer.stage == stage)
            if keyword:
                like = f"%{keyword}%"
                query = query.filter(
                    BizCustomer.name.like(like)
                    | BizCustomer.child_name.like(like)
                    | BizCustomer.remark.like(like)
                )
            if lead_source:
                query = query.filter(BizCustomer.lead_source == lead_source)

            total = session.query(func.count()).select_from(query.subquery()).scalar()
            rows = (
                query.order_by(BizCustomer.updated_at.desc())
                .limit(page_size)
                .offset((page - 1) * page_size)
                .all()
            )
            items = [
                {
                    "external_id": r.external_id,
                    "name": r.name,
                    "child_name": r.child_name,
                    "school": r.school,
                    "grade": r.grade,
                    "focus_subject": r.focus_subject,
                    "stage": r.stage,
                    "lead_source": r.lead_source,
                    "wework_account_id": r.wework_account_id,
                    "follow_user_id": r.follow_user_id,
                    "remark": r.remark,
                    "created_at": r.created_at,
                    "updated_at": r.updated_at,
                    "tag_count": int(r.tag_count or 0),
                }
                for r in rows
            ]
            return {
                "items": items,
                "total": total,
                "page": page,
                "page_size": page_size,
            }

    @staticmethod
    def get_by_external_id(
        external_id: str,
        user_id: str,
        data_scope: str,
        wework_account_id: Optional[str],
    ) -> Optional[Dict]:
        """按 external_id 查询单个客户（带权限过滤）"""
        with session_scope() as session:
            query = session.query(BizCustomer).filter(
                BizCustomer.external_id == external_id
            )
            query = apply_scope_conditions(
                query=query,
                model=BizCustomer,
                data_scope=data_scope,
                user_id=user_id,
                wework_account_id=wework_account_id,
                owner_field="follow_user_id",
            )
            r = query.first()
            if not r:
                return None
            return {
                "external_id": r.external_id,
                "name": r.name,
                "child_name": r.child_name,
                "school": r.school,
                "grade": r.grade,
                "focus_subject": r.focus_subject,
                "stage": r.stage,
                "lead_source": r.lead_source,
                "wework_account_id": r.wework_account_id,
                "follow_user_id": r.follow_user_id,
                "remark": r.remark,
                "union_id": r.union_id,
                "created_at": r.created_at,
                "updated_at": r.updated_at,
            }

    @staticmethod
    def get_by_follow_user(
        follow_user_id: str,
        user_id: str,
        data_scope: str,
        wework_account_id: Optional[str],
    ) -> List[Dict]:
        """查询某顾问名下的所有客户（带权限过滤）"""
        with session_scope() as session:
            query = session.query(BizCustomer).filter(
                BizCustomer.follow_user_id == follow_user_id
            )
            query = apply_scope_conditions(
                query=query,
                model=BizCustomer,
                data_scope=data_scope,
                user_id=user_id,
                wework_account_id=wework_account_id,
                owner_field="follow_user_id",
            )
            rows = query.all()
            return [
                {
                    "external_id": r.external_id,
                    "name": r.name,
                    "child_name": r.child_name,
                    "grade": r.grade,
                    "stage": r.stage,
                    "lead_source": r.lead_source,
                }
                for r in rows
            ]

    @staticmethod
    def get_tags_for_customer(external_id: str) -> List[Dict]:
        """查询客户的所有标签（已确认）"""
        with session_scope() as session:
            rows = (
                session.query(
                    BizCustomerTag.tag_id,
                    CfgTagDefinition.tag_name,
                    CfgTagDefinition.group_id,
                    BizCustomerTag.source,
                    BizCustomerTag.confirmed,
                    BizCustomerTag.confirmed_by,
                    BizCustomerTag.confirmed_at,
                )
                .outerjoin(
                    CfgTagDefinition, CfgTagDefinition.tag_id == BizCustomerTag.tag_id
                )
                .filter(
                    BizCustomerTag.external_id == external_id,
                    BizCustomerTag.confirmed.is_(True),
                )
                .order_by(CfgTagDefinition.group_id, BizCustomerTag.tag_id)
                .all()
            )
            return [
                {
                    "tag_id": r.tag_id,
                    "tag_name": r.tag_name,
                    "group_id": r.group_id,
                    "source": r.source,
                    "confirmed": r.confirmed,
                    "confirmed_by": r.confirmed_by,
                    "confirmed_at": r.confirmed_at,
                }
                for r in rows
            ]

    @staticmethod
    def get_all_tags_for_customer(external_id: str) -> List[Dict]:
        """查询客户的所有标签（含未确认）"""
        with session_scope() as session:
            rows = (
                session.query(
                    BizCustomerTag.tag_id,
                    CfgTagDefinition.tag_name,
                    CfgTagDefinition.group_id,
                    BizCustomerTag.source,
                    BizCustomerTag.confirmed,
                    BizCustomerTag.confirmed_by,
                    BizCustomerTag.confirmed_at,
                )
                .outerjoin(
                    CfgTagDefinition, CfgTagDefinition.tag_id == BizCustomerTag.tag_id
                )
                .filter(BizCustomerTag.external_id == external_id)
                .order_by(BizCustomerTag.confirmed.desc(), CfgTagDefinition.group_id)
                .all()
            )
            return [
                {
                    "tag_id": r.tag_id,
                    "tag_name": r.tag_name,
                    "group_id": r.group_id,
                    "source": r.source,
                    "confirmed": r.confirmed,
                    "confirmed_by": r.confirmed_by,
                    "confirmed_at": r.confirmed_at,
                }
                for r in rows
            ]

    # ==================== V3.1 线索来源统计 ====================

    @staticmethod
    def get_lead_source_stats(
        user_id: str,
        data_scope: str,
        wework_account_id: Optional[str],
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> List[Dict]:
        """按 lead_source 统计客户转化情况（V3.1）"""
        with session_scope() as session:
            query = session.query(
                BizCustomer.lead_source,
                func.count(BizCustomer.id).label("total"),
                func.sum(case((BizCustomer.stage == "潜在", 1), else_=0)).label("potential"),
                func.sum(case((BizCustomer.stage == "高意向", 1), else_=0)).label("high_intent"),
                func.sum(case((BizCustomer.stage == "试听", 1), else_=0)).label("trial"),
                func.sum(case((BizCustomer.stage == "在读", 1), else_=0)).label("enrolled"),
            ).filter(
                BizCustomer.lead_source.isnot(None),
                BizCustomer.lead_source != "",
            )
            query = apply_scope_conditions(
                query=query,
                model=BizCustomer,
                data_scope=data_scope,
                user_id=user_id,
                wework_account_id=wework_account_id,
                owner_field="follow_user_id",
            )
            if start_date:
                query = query.filter(BizCustomer.created_at >= start_date)
            if end_date:
                query = query.filter(BizCustomer.created_at <= end_date)
            rows = (
                query.group_by(BizCustomer.lead_source)
                .order_by(func.count(BizCustomer.id).desc())
                .all()
            )
            result = []
            for r in rows:
                total = int(r.total or 0)
                enrolled = int(r.enrolled or 0)
                result.append({
                    "lead_source": r.lead_source,
                    "total": total,
                    "potential": int(r.potential or 0),
                    "high_intent": int(r.high_intent or 0),
                    "trial": int(r.trial or 0),
                    "enrolled": enrolled,
                    "conversion_rate": round(100.0 * enrolled / total, 1) if total else None,
                })
            return result

    @staticmethod
    def find_by_name(name: str) -> Optional[Dict]:
        """按客户姓名精确查找（用于订单归属客户查找）"""
        with session_scope() as session:
            r = (
                session.query(BizCustomer)
                .filter(BizCustomer.name == name)
                .limit(1)
                .first()
            )
            if not r:
                return None
            return {
                "external_id": r.external_id,
                "union_id": r.union_id,
                "name": r.name,
                "follow_user_id": r.follow_user_id,
                "wework_account_id": r.wework_account_id,
            }

    @staticmethod
    def get_next_ids() -> tuple:
        """生成下一个客户 external_id / union_id（如 C10013 / U10013）"""
        with session_scope() as session:
            max_ext = session.query(
                func.max(func.cast(func.substring(BizCustomer.external_id, 2), Integer))
            ).scalar()
            max_union = session.query(
                func.max(func.cast(func.substring(BizCustomer.union_id, 2), Integer))
            ).scalar()
            n_ext = int(max_ext or 0) + 1
            n_union = int(max_union or 0) + 1
            return f"C{n_ext}", f"U{n_union}"

    # ==================== 写入方法 ====================

    @staticmethod
    def create(
        external_id: str,
        follow_user_id: str,
        wework_account_id: str,
        name: Optional[str] = None,
        child_name: Optional[str] = None,
        school: Optional[str] = None,
        grade: Optional[str] = None,
        focus_subject: Optional[str] = None,
        remark: Optional[str] = None,
        stage: str = "潜在",
        lead_source: Optional[str] = None,
        union_id: Optional[str] = None,
    ) -> bool:
        """新增客户"""
        with session_scope(commit=True) as session:
            session.add(
                BizCustomer(
                    external_id=external_id,
                    union_id=union_id,
                    wework_account_id=wework_account_id,
                    follow_user_id=follow_user_id,
                    name=name,
                    child_name=child_name,
                    school=school,
                    grade=grade,
                    focus_subject=focus_subject,
                    remark=remark,
                    stage=stage,
                    lead_source=lead_source,
                )
            )
            return True

    @staticmethod
    def update(
        external_id: str,
        name: Optional[str] = None,
        child_name: Optional[str] = None,
        school: Optional[str] = None,
        grade: Optional[str] = None,
        focus_subject: Optional[str] = None,
        remark: Optional[str] = None,
        stage: Optional[str] = None,
        lead_source: Optional[str] = None,
    ) -> bool:
        """更新客户信息（仅更新传入字段）"""
        with session_scope(commit=True) as session:
            row = (
                session.query(BizCustomer)
                .filter(BizCustomer.external_id == external_id)
                .first()
            )
            if not row:
                return False
            if name is not None:
                row.name = name
            if child_name is not None:
                row.child_name = child_name
            if school is not None:
                row.school = school
            if grade is not None:
                row.grade = grade
            if focus_subject is not None:
                row.focus_subject = focus_subject
            if remark is not None:
                row.remark = remark
            if stage is not None:
                row.stage = stage
            if lead_source is not None:
                row.lead_source = lead_source
            return True

    @staticmethod
    def add_tag(
        external_id: str,
        tag_id: str,
        source: str = "AI 推荐",
        confirmed: bool = False,
        confirmed_by: Optional[str] = None,
    ) -> bool:
        """为客户添加标签（存在则更新）"""
        confirmed_at = datetime.now() if confirmed else None
        with session_scope(commit=True) as session:
            row = (
                session.query(BizCustomerTag)
                .filter(
                    BizCustomerTag.external_id == external_id,
                    BizCustomerTag.tag_id == tag_id,
                )
                .first()
            )
            if row:
                row.source = source
                row.confirmed = bool(confirmed)
                row.confirmed_by = confirmed_by
                row.confirmed_at = confirmed_at
            else:
                session.add(
                    BizCustomerTag(
                        external_id=external_id,
                        tag_id=tag_id,
                        source=source,
                        confirmed=bool(confirmed),
                        confirmed_by=confirmed_by,
                        confirmed_at=confirmed_at,
                    )
                )
            return True

    @staticmethod
    def remove_tag(external_id: str, tag_id: str) -> bool:
        """移除客户标签"""
        with session_scope(commit=True) as session:
            result = session.execute(
                delete(BizCustomerTag).where(
                    BizCustomerTag.external_id == external_id,
                    BizCustomerTag.tag_id == tag_id,
                )
            )
            return result.rowcount > 0

    @staticmethod
    def confirm_tag(external_id: str, tag_id: str, confirmed_by: str) -> bool:
        """确认客户标签"""
        with session_scope(commit=True) as session:
            row = (
                session.query(BizCustomerTag)
                .filter(
                    BizCustomerTag.external_id == external_id,
                    BizCustomerTag.tag_id == tag_id,
                )
                .first()
            )
            if not row:
                return False
            row.confirmed = True
            row.confirmed_by = confirmed_by
            row.confirmed_at = datetime.now()
            return True

    @staticmethod
    def delete(external_id: str) -> bool:
        """删除客户（物理删除）"""
        with session_scope(commit=True) as session:
            result = session.execute(
                delete(BizCustomer).where(BizCustomer.external_id == external_id)
            )
            return result.rowcount > 0

    @staticmethod
    def exists(external_id: str) -> bool:
        """检查客户是否存在"""
        with session_scope() as session:
            return (
                session.query(BizCustomer)
                .filter(BizCustomer.external_id == external_id)
                .first()
                is not None
            )
