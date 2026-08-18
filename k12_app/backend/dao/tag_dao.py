"""
标签 DAO — 操作 cfg_tag_group + cfg_tag_definition + cfg_sop_template + biz_customer_tag（SQLAlchemy ORM）
支持三级结构查询（策略→分组→标签）+ 软删除 + 标签推荐规则（ai_rule）
"""

from typing import Optional, List, Dict

from sqlalchemy import func, case, distinct, select, delete, update

from k12_app.backend.dao.db import session_scope
from k12_app.backend.models import (
    CfgTagGroup,
    CfgTagDefinition,
    CfgSopTemplate,
    BizCustomerTag,
    BizCustomer,
    SysWeworkAccount,
)


class TagDAO:
    """标签数据访问（全局共享，无权限过滤）"""

    # ==================== 分组操作 ====================

    @staticmethod
    def get_group_by_id(group_id: str) -> Optional[Dict]:
        """按分组 ID 查询单个分组"""
        with session_scope() as session:
            r = (
                session.query(CfgTagGroup)
                .filter(CfgTagGroup.group_id == group_id)
                .first()
            )
            if not r:
                return None
            return {
                "group_id": r.group_id,
                "group_name": r.group_name,
                "strategy_id": r.strategy_id,
            }

    @staticmethod
    def create_group(group_id: str, group_name: str, strategy_id: int = 0) -> bool:
        """新增标签分组"""
        with session_scope(commit=True) as session:
            session.add(
                CfgTagGroup(group_id=group_id, group_name=group_name, strategy_id=strategy_id)
            )
            return True

    @staticmethod
    def update_group(group_id: str, group_name: str = None, strategy_id: int = None) -> bool:
        """更新标签分组（仅更新传入字段）"""
        with session_scope(commit=True) as session:
            row = (
                session.query(CfgTagGroup)
                .filter(CfgTagGroup.group_id == group_id)
                .first()
            )
            if not row:
                return False
            if group_name is not None:
                row.group_name = group_name
            if strategy_id is not None:
                row.strategy_id = strategy_id
            return True

    @staticmethod
    def delete_group(group_id: str, soft: bool = True) -> bool:
        """
        删除标签分组
        - soft=True: 软删除分组下所有标签（设置 deleted=1），保留分组记录
        - soft=False: 物理删除分组及其下所有标签
        """
        with session_scope(commit=True) as session:
            if soft:
                session.execute(
                    update(CfgTagDefinition)
                    .where(CfgTagDefinition.group_id == group_id)
                    .values(deleted=True)
                )
            else:
                session.execute(
                    delete(CfgTagDefinition).where(CfgTagDefinition.group_id == group_id)
                )
                session.execute(
                    delete(CfgTagGroup).where(CfgTagGroup.group_id == group_id)
                )
            return True

    # ==================== 标签操作 ====================

    @staticmethod
    def get_tag_by_id(tag_id: str) -> Optional[Dict]:
        """按标签 ID 查询单个标签（仅未删除）"""
        with session_scope() as session:
            r = (
                session.query(CfgTagDefinition)
                .filter(
                    CfgTagDefinition.tag_id == tag_id,
                    CfgTagDefinition.deleted.is_(False),
                )
                .first()
            )
            if not r:
                return None
            return {
                "tag_id": r.tag_id,
                "tag_name": r.tag_name,
                "group_id": r.group_id,
                "ai_rule": r.ai_rule,
                "sop_template_id": r.sop_template_id,
                "deleted": r.deleted,
            }

    @staticmethod
    def get_by_group_id(group_id: str) -> List[Dict]:
        """查询某分组下的所有标签（仅未删除）"""
        with session_scope() as session:
            rows = (
                session.query(CfgTagDefinition)
                .filter(
                    CfgTagDefinition.group_id == group_id,
                    CfgTagDefinition.deleted.is_(False),
                )
                .order_by(CfgTagDefinition.tag_id)
                .all()
            )
            return [
                {
                    "tag_id": r.tag_id,
                    "tag_name": r.tag_name,
                    "ai_rule": r.ai_rule,
                    "sop_template_id": r.sop_template_id,
                }
                for r in rows
            ]

    @staticmethod
    def get_tags_by_scope(
        user_id: str,
        data_scope: str,
        wework_account_id: Optional[str],
    ) -> List[Dict]:
        """按权限范围获取标签体系（all=全量，region=同区域客户标签，self=自己客户标签）"""
        if data_scope == "all":
            return TagDAO.get_all_tags()

        with session_scope() as session:
            # 查全部分组（树结构需要）
            groups = (
                session.query(CfgTagGroup)
                .order_by(CfgTagGroup.strategy_id, CfgTagGroup.group_id)
                .all()
            )

            # 按权限范围查标签
            query = (
                session.query(
                    CfgTagDefinition.tag_id,
                    CfgTagDefinition.tag_name,
                    CfgTagDefinition.group_id,
                    CfgTagDefinition.ai_rule,
                    CfgTagDefinition.sop_template_id,
                )
                .distinct()
                .join(BizCustomerTag, BizCustomerTag.tag_id == CfgTagDefinition.tag_id)
                .join(BizCustomer, BizCustomerTag.external_id == BizCustomer.external_id)
                .filter(CfgTagDefinition.deleted.is_(False))
            )

            if data_scope == "self":
                if not wework_account_id:
                    return []
                query = query.filter(
                    BizCustomer.follow_user_id == user_id,
                    BizCustomer.wework_account_id == wework_account_id,
                )
            elif data_scope == "region":
                if not wework_account_id:
                    return []
                region_subq = (
                    select(SysWeworkAccount.region)
                    .where(SysWeworkAccount.account_id == wework_account_id)
                    .scalar_subquery()
                )
                account_ids = select(SysWeworkAccount.account_id).where(
                    SysWeworkAccount.region == region_subq
                )
                query = query.filter(BizCustomer.wework_account_id.in_(account_ids))

            tags = query.all()

            # 组装树结构
            result = []
            strategy_map = {}
            for g in groups:
                sid = g.strategy_id
                if sid not in strategy_map:
                    strategy_map[sid] = {"strategy_id": sid, "groups": []}
                strategy_map[sid]["groups"].append({
                    "group_id": g.group_id,
                    "group_name": g.group_name,
                    "tags": [],
                })

            for tag in tags:
                for s in strategy_map.values():
                    for g in s["groups"]:
                        if g["group_id"] == tag.group_id:
                            g["tags"].append({
                                "tag_id": tag.tag_id,
                                "tag_name": tag.tag_name,
                                "ai_rule": tag.ai_rule,
                                "sop_template_id": tag.sop_template_id,
                            })
                            break

            for s in strategy_map.values():
                s["groups"] = [g for g in s["groups"] if g["tags"]]
            return [s for s in strategy_map.values() if s["groups"]]

    @staticmethod
    def get_all_tags() -> List[Dict]:
        """获取全量标签体系（三级结构：策略→分组→标签），仅未删除"""
        with session_scope() as session:
            groups = (
                session.query(CfgTagGroup)
                .order_by(CfgTagGroup.strategy_id, CfgTagGroup.group_id)
                .all()
            )
            tags = (
                session.query(CfgTagDefinition)
                .filter(CfgTagDefinition.deleted.is_(False))
                .all()
            )

            # 组装
            result = []
            strategy_map = {}
            for g in groups:
                sid = g.strategy_id
                if sid not in strategy_map:
                    strategy_map[sid] = {"strategy_id": sid, "groups": []}
                strategy_map[sid]["groups"].append({
                    "group_id": g.group_id,
                    "group_name": g.group_name,
                    "tags": [],
                })

            for tag in tags:
                for s in strategy_map.values():
                    for g in s["groups"]:
                        if g["group_id"] == tag.group_id:
                            g["tags"].append({
                                "tag_id": tag.tag_id,
                                "tag_name": tag.tag_name,
                                "ai_rule": tag.ai_rule,
                                "sop_template_id": tag.sop_template_id,
                            })
                            break
            return list(strategy_map.values())

    @staticmethod
    def create_tag(
        tag_id: str,
        tag_name: str,
        group_id: str,
        ai_rule: Optional[str] = None,
        sop_template_id: Optional[int] = None,
    ) -> bool:
        """新增标签"""
        with session_scope(commit=True) as session:
            session.add(
                CfgTagDefinition(
                    tag_id=tag_id,
                    tag_name=tag_name,
                    group_id=group_id,
                    ai_rule=ai_rule,
                    sop_template_id=sop_template_id,
                    deleted=False,
                )
            )
            return True

    @staticmethod
    def update_tag(
        tag_id: str,
        tag_name: Optional[str] = None,
        group_id: Optional[str] = None,
        ai_rule: Optional[str] = None,
        sop_template_id: Optional[int] = None,
    ) -> bool:
        """更新标签（仅更新传入字段）"""
        with session_scope(commit=True) as session:
            row = (
                session.query(CfgTagDefinition)
                .filter(
                    CfgTagDefinition.tag_id == tag_id,
                    CfgTagDefinition.deleted.is_(False),
                )
                .first()
            )
            if not row:
                return False
            if tag_name is not None:
                row.tag_name = tag_name
            if group_id is not None:
                row.group_id = group_id
            if ai_rule is not None:
                row.ai_rule = ai_rule
            if sop_template_id is not None:
                row.sop_template_id = sop_template_id
            return True

    @staticmethod
    def delete_tag(tag_id: str, soft: bool = True) -> bool:
        """
        删除标签
        - soft=True: 软删除（设置 deleted=1）
        - soft=False: 物理删除
        """
        with session_scope(commit=True) as session:
            if soft:
                result = session.execute(
                    update(CfgTagDefinition)
                    .where(CfgTagDefinition.tag_id == tag_id)
                    .values(deleted=True)
                )
            else:
                result = session.execute(
                    delete(CfgTagDefinition).where(CfgTagDefinition.tag_id == tag_id)
                )
            return result.rowcount > 0

    @staticmethod
    def get_customers_by_tag(
        tag_id: str,
        user_id: Optional[str] = None,
        data_scope: str = "all",
        wework_account_id: Optional[str] = None,
    ) -> List[Dict]:
        """按标签查询关联客户（按权限范围过滤）"""
        with session_scope() as session:
            query = (
                session.query(
                    BizCustomer.external_id,
                    BizCustomer.name.label("customer_name"),
                    BizCustomerTag.source,
                    BizCustomerTag.confirmed,
                    BizCustomerTag.confirmed_by,
                    BizCustomerTag.confirmed_at,
                )
                .join(BizCustomerTag, BizCustomerTag.external_id == BizCustomer.external_id)
                .filter(BizCustomerTag.tag_id == tag_id)
            )

            if data_scope == "self":
                if not wework_account_id:
                    return []
                query = query.filter(
                    BizCustomer.follow_user_id == user_id,
                    BizCustomer.wework_account_id == wework_account_id,
                )
            elif data_scope == "region":
                if not wework_account_id:
                    return []
                region_subq = (
                    select(SysWeworkAccount.region)
                    .where(SysWeworkAccount.account_id == wework_account_id)
                    .scalar_subquery()
                )
                account_ids = select(SysWeworkAccount.account_id).where(
                    SysWeworkAccount.region == region_subq
                )
                query = query.filter(BizCustomer.wework_account_id.in_(account_ids))

            rows = query.order_by(BizCustomerTag.confirmed.desc(), BizCustomer.name).all()
            return [
                {
                    "external_id": r.external_id,
                    "customer_name": r.customer_name,
                    "source": r.source,
                    "confirmed": r.confirmed,
                    "confirmed_by": r.confirmed_by,
                    "confirmed_at": r.confirmed_at,
                }
                for r in rows
            ]

    @staticmethod
    def get_customer_tags(
        external_id: str,
        user_id: Optional[str] = None,
        data_scope: str = "all",
        wework_account_id: Optional[str] = None,
    ) -> List[Dict]:
        """查询某客户的全部标签（已确认 + 待确认），按权限范围过滤"""
        with session_scope() as session:
            query = (
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
                .join(BizCustomer, BizCustomerTag.external_id == BizCustomer.external_id)
                .filter(BizCustomerTag.external_id == external_id)
            )

            if data_scope == "self":
                if not wework_account_id:
                    return []
                query = query.filter(
                    BizCustomer.follow_user_id == user_id,
                    BizCustomer.wework_account_id == wework_account_id,
                )
            elif data_scope == "region":
                if not wework_account_id:
                    return []
                region_subq = (
                    select(SysWeworkAccount.region)
                    .where(SysWeworkAccount.account_id == wework_account_id)
                    .scalar_subquery()
                )
                account_ids = select(SysWeworkAccount.account_id).where(
                    SysWeworkAccount.region == region_subq
                )
                query = query.filter(BizCustomer.wework_account_id.in_(account_ids))

            rows = query.order_by(BizCustomerTag.confirmed.desc(), CfgTagDefinition.group_id).all()
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
    def delete_customer_tags_by_external_id(
        external_id: str,
        user_id: Optional[str] = None,
        data_scope: str = "all",
        wework_account_id: Optional[str] = None,
    ) -> int:
        """删除某客户的全部标签关联（V3.3.2：「清空重置」彻底清除 AI 记忆用，带权限过滤）"""
        with session_scope(commit=True) as session:
            subq = session.query(BizCustomerTag.id).join(
                BizCustomer, BizCustomerTag.external_id == BizCustomer.external_id
            ).filter(BizCustomerTag.external_id == external_id)
            if data_scope == "self":
                if not user_id or not wework_account_id:
                    return 0
                subq = subq.filter(
                    BizCustomer.follow_user_id == user_id,
                    BizCustomer.wework_account_id == wework_account_id,
                )
            elif data_scope == "region":
                if not wework_account_id:
                    return 0
                region_subq = (
                    select(SysWeworkAccount.region)
                    .where(SysWeworkAccount.account_id == wework_account_id)
                    .scalar_subquery()
                )
                account_ids = select(SysWeworkAccount.account_id).where(
                    SysWeworkAccount.region == region_subq
                )
                subq = subq.filter(BizCustomer.wework_account_id.in_(account_ids))
            ids = [r[0] for r in subq.all()]
            if not ids:
                return 0
            result = session.execute(
                delete(BizCustomerTag).where(BizCustomerTag.id.in_(ids))
            )
            return result.rowcount

    @staticmethod
    def get_tag_stats(
        user_id: Optional[str] = None,
        data_scope: str = "all",
        wework_account_id: Optional[str] = None,
    ) -> List[Dict]:
        """标签使用统计：每个标签关联的客户数、已确认数（按权限范围过滤）"""
        if data_scope == "self" and not wework_account_id:
            return []

        with session_scope() as session:
            query = (
                session.query(
                    CfgTagDefinition.tag_id,
                    CfgTagDefinition.tag_name,
                    CfgTagDefinition.group_id,
                    CfgTagGroup.group_name,
                    func.count(BizCustomerTag.id).label("customer_count"),
                    func.sum(case((BizCustomerTag.confirmed.is_(True), 1), else_=0)).label("confirmed_count"),
                )
                .join(BizCustomerTag, BizCustomerTag.tag_id == CfgTagDefinition.tag_id)
                .join(BizCustomer, BizCustomerTag.external_id == BizCustomer.external_id)
                .filter(CfgTagDefinition.deleted.is_(False))
                .outerjoin(CfgTagGroup, CfgTagGroup.group_id == CfgTagDefinition.group_id)
            )

            if data_scope == "self":
                query = query.filter(
                    BizCustomer.follow_user_id == user_id,
                    BizCustomer.wework_account_id == wework_account_id,
                )
            elif data_scope == "region":
                if not wework_account_id:
                    return []
                region_subq = (
                    select(SysWeworkAccount.region)
                    .where(SysWeworkAccount.account_id == wework_account_id)
                    .scalar_subquery()
                )
                account_ids = select(SysWeworkAccount.account_id).where(
                    SysWeworkAccount.region == region_subq
                )
                query = query.filter(BizCustomer.wework_account_id.in_(account_ids))

            rows = (
                query.group_by(
                    CfgTagDefinition.tag_id,
                    CfgTagDefinition.tag_name,
                    CfgTagDefinition.group_id,
                    CfgTagGroup.group_name,
                )
                .order_by(
                    func.count(BizCustomerTag.id).desc(),
                    CfgTagDefinition.group_id,
                    CfgTagDefinition.tag_id,
                )
                .all()
            )
            return [
                {
                    "tag_id": r.tag_id,
                    "tag_name": r.tag_name,
                    "group_id": r.group_id,
                    "group_name": r.group_name,
                    "customer_count": int(r.customer_count or 0),
                    "confirmed_count": int(r.confirmed_count or 0),
                }
                for r in rows
            ]

    @staticmethod
    def get_sop_templates() -> List[Dict]:
        """获取全部 SOP 模板列表（cfg_sop_template 表）"""
        with session_scope() as session:
            rows = (
                session.query(CfgSopTemplate)
                .order_by(CfgSopTemplate.id)
                .all()
            )
            return [
                {
                    "id": r.id,
                    "template_name": r.template_name,
                    "steps": r.steps,
                    "created_at": r.created_at,
                    "updated_at": r.updated_at,
                }
                for r in rows
            ]
