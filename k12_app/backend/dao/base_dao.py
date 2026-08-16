# k12_app/dao/base_dao.py
"""
DAO 层公共工具 — 三维度权限过滤的 ORM 封装

将原 apply_scope_filter（SQL 字符串拼接）改为 SQLAlchemy ORM 查询条件，
供各 DAO 在查询时直接应用：
    query = apply_scope_conditions(query, Model, data_scope, user_id, wework_account_id, owner_field)

三维度权限：
- self   ：仅本人数据（owner_field = 当前用户 AND wework_account_id = 当前账户）
- region ：本区域企微账户的数据
- all    ：不附加过滤
"""

from typing import Optional

from sqlalchemy import false, select
from sqlalchemy.orm import Query

from k12_app.backend.models import SysWeworkAccount


def apply_scope_conditions(
    query: Query,
    model,
    data_scope: str,
    user_id: str,
    wework_account_id: Optional[str],
    owner_field: str = "follow_user_id",
) -> Query:
    """
    为 ORM 查询自动附加三维度权限过滤条件。

    Args:
        query: SQLAlchemy Query 对象
        model: 被查询的 ORM 模型类
        data_scope: 权限范围（all / region / self）
        user_id: 当前登录用户 ID
        wework_account_id: 当前企微账户 ID（可能为 None，V3.2 未绑定状态）
        owner_field: 表中的"所有者"字段名（如 follow_user_id / user_id / created_by）

    Returns:
        附加过滤条件后的 Query
    """
    if data_scope == "self":
        # V3.2 安全处理：未绑定员工无权访问任何数据
        if not wework_account_id:
            return query.where(false())
        return query.where(
            getattr(model, owner_field) == user_id,
            model.wework_account_id == wework_account_id,
        )

    if data_scope == "region":
        # 区域主管：只能看本区域企微账户的数据
        if not wework_account_id:
            return query.where(false())
        region_subq = (
            select(SysWeworkAccount.region)
            .where(SysWeworkAccount.account_id == wework_account_id)
            .scalar_subquery()
        )
        account_ids_subq = select(SysWeworkAccount.account_id).where(
            SysWeworkAccount.region == region_subq
        )
        return query.where(model.wework_account_id.in_(account_ids_subq))

    # data_scope == 'all': 不加任何过滤
    return query


def apply_kf_scope_conditions(
    query: Query,
    model,
    data_scope: str,
    user_id: str,
    wework_account_id: Optional[str],
) -> Query:
    """
    msg_wxkf_chat 等无 user_id 列的表，通过 external_id 关联 biz_customer 做权限过滤。
    """
    if data_scope == "all":
        return query

    if not wework_account_id:
        return query.where(false())

    from k12_app.backend.models import BizCustomer

    if data_scope == "self":
        ext_subq = select(BizCustomer.external_id).where(
            BizCustomer.follow_user_id == user_id,
            BizCustomer.wework_account_id == wework_account_id,
        )
        return query.where(model.external_id.in_(ext_subq))

    if data_scope == "region":
        region_subq = (
            select(SysWeworkAccount.region)
            .where(SysWeworkAccount.account_id == wework_account_id)
            .scalar_subquery()
        )
        account_ids_subq = select(SysWeworkAccount.account_id).where(
            SysWeworkAccount.region == region_subq
        )
        ext_subq = select(BizCustomer.external_id).where(
            BizCustomer.wework_account_id.in_(account_ids_subq)
        )
        return query.where(model.external_id.in_(ext_subq))

    return query


def order_by_data_scope(column) -> object:
    """
    模拟 MySQL 的 ORDER BY FIELD(data_scope, 'all', 'region', 'self')：
    返回按 all(0) / region(1) / self(2) 排序的 case() 表达式。
    """
    from sqlalchemy import case

    return case(
        (column == "all", 0),
        (column == "region", 1),
        else_=2,
    )
