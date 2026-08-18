"""
订单 DAO — 操作 biz_order 表（SQLAlchemy ORM）
支持：
- 通过 union_id 关联 biz_customer 进行权限过滤
- 三维度权限过滤（follow_user_id + wework_account_id）
- 订单状态统计
"""

from typing import Optional, List, Dict
from datetime import datetime, date

from sqlalchemy import func, case, and_, distinct, select, delete, update

from k12_app.backend.dao.db import session_scope
from k12_app.backend.models import BizOrder, BizCustomer, SysEmployee

# 订单状态实际取值（与 biz_order.status 数据一致）
VALID_ORDER_STATUSES = {"进行中", "待使用", "已完结", "已退款"}


def _parse_date(val: Optional[str]) -> Optional[date]:
    """将 'YYYY-MM-DD' 字符串转换为 date 对象（用于 Date 列绑定）"""
    if val is None:
        return None
    if isinstance(val, date):
        return val
    return datetime.strptime(str(val)[:10], "%Y-%m-%d").date()


class OrderDAO:
    """订单数据访问"""

    @staticmethod
    def _apply_order_scope(query, data_scope: str, user_id: str, wework_account_id: Optional[str]):
        """
        手动为订单查询添加权限过滤（使用 c.follow_user_id 和 c.wework_account_id，
        作用于已 JOIN 的 BizCustomer）
        """
        from k12_app.backend.dao.base_dao import apply_scope_conditions

        if data_scope == "self":
            if not wework_account_id:
                return None
            query = apply_scope_conditions(
                query=query,
                model=BizCustomer,
                data_scope="self",
                user_id=user_id,
                wework_account_id=wework_account_id,
                owner_field="follow_user_id",
            )
        elif data_scope == "region":
            if not wework_account_id:
                return None
            query = apply_scope_conditions(
                query=query,
                model=BizCustomer,
                data_scope="region",
                user_id=user_id,
                wework_account_id=wework_account_id,
                owner_field="follow_user_id",
            )
        return query

    @staticmethod
    def get_by_order_id(
        order_id: str,
        user_id: str,
        data_scope: str,
        wework_account_id: Optional[str],
    ) -> Optional[Dict]:
        """按订单号查询订单（带权限过滤）"""
        if not wework_account_id and data_scope != "all":
            return None

        with session_scope() as session:
            query = (
                session.query(
                    BizOrder.order_id,
                    BizOrder.union_id,
                    BizOrder.wework_account_id,
                    BizOrder.product_names,
                    BizOrder.amount,
                    BizOrder.status,
                    BizOrder.order_time,
                    BizOrder.order_date,
                    BizOrder.created_at,
                    BizOrder.updated_at,
                    BizCustomer.external_id,
                    BizCustomer.name.label("customer_name"),
                    BizCustomer.follow_user_id,
                )
                .join(BizCustomer, BizOrder.union_id == BizCustomer.union_id)
                .filter(BizOrder.order_id == order_id)
            )
            query = OrderDAO._apply_order_scope(query, data_scope, user_id, wework_account_id)
            if query is None:
                return None
            r = query.first()
            if not r:
                return None
            return {
                "order_id": r.order_id,
                "union_id": r.union_id,
                "wework_account_id": r.wework_account_id,
                "product_names": r.product_names,
                "amount": r.amount,
                "status": r.status,
                "order_time": r.order_time,
                "order_date": r.order_date,
                "created_at": r.created_at,
                "updated_at": r.updated_at,
                "external_id": r.external_id,
                "customer_name": r.customer_name,
                "follow_user_id": r.follow_user_id,
            }

    @staticmethod
    def get_by_union_id(
        union_id: str,
        user_id: str,
        data_scope: str,
        wework_account_id: Optional[str],
    ) -> List[Dict]:
        if not wework_account_id and data_scope != "all":
            return []

        with session_scope() as session:
            query = (
                session.query(
                    BizOrder.order_id,
                    BizOrder.union_id,
                    BizOrder.wework_account_id,
                    BizOrder.product_names,
                    BizOrder.amount,
                    BizOrder.status,
                    BizOrder.order_time,
                    BizOrder.order_date,
                    BizOrder.created_at,
                    BizOrder.updated_at,
                    BizCustomer.external_id,
                    BizCustomer.name.label("customer_name"),
                    BizCustomer.follow_user_id,
                )
                .join(BizCustomer, BizOrder.union_id == BizCustomer.union_id)
                .filter(BizOrder.union_id == union_id)
            )
            query = OrderDAO._apply_order_scope(query, data_scope, user_id, wework_account_id)
            if query is None:
                return []
            rows = query.order_by(BizOrder.order_time.desc()).all()
            return [
                {
                    "order_id": r.order_id,
                    "union_id": r.union_id,
                    "wework_account_id": r.wework_account_id,
                    "product_names": r.product_names,
                    "amount": r.amount,
                    "status": r.status,
                    "order_time": r.order_time,
                    "order_date": r.order_date,
                    "created_at": r.created_at,
                    "updated_at": r.updated_at,
                    "external_id": r.external_id,
                    "customer_name": r.customer_name,
                    "follow_user_id": r.follow_user_id,
                }
                for r in rows
            ]

    @staticmethod
    def get_by_external_id(
        external_id: str,
        user_id: str,
        data_scope: str,
        wework_account_id: Optional[str],
    ) -> List[Dict]:
        if not wework_account_id and data_scope != "all":
            return []

        with session_scope() as session:
            query = (
                session.query(
                    BizOrder.order_id,
                    BizOrder.union_id,
                    BizOrder.wework_account_id,
                    BizOrder.product_names,
                    BizOrder.amount,
                    BizOrder.status,
                    BizOrder.order_time,
                    BizOrder.order_date,
                    BizOrder.created_at,
                    BizOrder.updated_at,
                )
                .join(BizCustomer, BizOrder.union_id == BizCustomer.union_id)
                .filter(BizCustomer.external_id == external_id)
            )
            query = OrderDAO._apply_order_scope(query, data_scope, user_id, wework_account_id)
            if query is None:
                return []
            rows = query.order_by(BizOrder.order_time.desc()).all()
            return [
                {
                    "order_id": r.order_id,
                    "union_id": r.union_id,
                    "wework_account_id": r.wework_account_id,
                    "product_names": r.product_names,
                    "amount": r.amount,
                    "status": r.status,
                    "order_time": r.order_time,
                    "order_date": r.order_date,
                    "created_at": r.created_at,
                    "updated_at": r.updated_at,
                }
                for r in rows
            ]

    @staticmethod
    def get_list(
        user_id: str,
        data_scope: str,
        wework_account_id: Optional[str],
        status: Optional[str] = None,
        keyword: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Dict:
        if not wework_account_id and data_scope != "all":
            return {"items": [], "total": 0, "page": page, "page_size": page_size}

        with session_scope() as session:
            query = (
                session.query(
                    BizOrder.order_id,
                    BizOrder.union_id,
                    BizOrder.wework_account_id,
                    BizOrder.product_names,
                    BizOrder.amount,
                    BizOrder.status,
                    BizOrder.order_time,
                    BizOrder.order_date,
                    BizOrder.created_at,
                    BizOrder.updated_at,
                    BizCustomer.external_id,
                    BizCustomer.name.label("customer_name"),
                    BizCustomer.follow_user_id,
                )
                .join(BizCustomer, BizOrder.union_id == BizCustomer.union_id)
            )
            query = OrderDAO._apply_order_scope(query, data_scope, user_id, wework_account_id)
            if query is None:
                return {"items": [], "total": 0, "page": page, "page_size": page_size}

            if status:
                query = query.filter(BizOrder.status == status)
            if keyword:
                query = query.filter(
                    BizOrder.order_id.like(f"%{keyword}%")
                    | BizCustomer.name.like(f"%{keyword}%")
                )
            if start_date:
                query = query.filter(BizOrder.order_date >= _parse_date(start_date))
            if end_date:
                query = query.filter(BizOrder.order_date <= _parse_date(end_date))

            total = session.query(func.count()).select_from(query.subquery()).scalar()
            rows = (
                query.order_by(BizOrder.order_time.desc())
                .limit(page_size)
                .offset((page - 1) * page_size)
                .all()
            )
            items = [
                {
                    "order_id": r.order_id,
                    "union_id": r.union_id,
                    "wework_account_id": r.wework_account_id,
                    "product_names": r.product_names,
                    "amount": r.amount,
                    "status": r.status,
                    "order_time": r.order_time,
                    "order_date": r.order_date,
                    "created_at": r.created_at,
                    "updated_at": r.updated_at,
                    "external_id": r.external_id,
                    "customer_name": r.customer_name,
                    "follow_user_id": r.follow_user_id,
                }
                for r in rows
            ]
            return {"items": items, "total": total, "page": page, "page_size": page_size}

    @staticmethod
    def get_by_order_id(
        order_id: str,
        user_id: str,
        data_scope: str,
        wework_account_id: Optional[str],
    ) -> Optional[Dict]:
        if not wework_account_id and data_scope != "all":
            return None

        with session_scope() as session:
            query = (
                session.query(
                    BizOrder.order_id,
                    BizOrder.union_id,
                    BizOrder.wework_account_id,
                    BizOrder.product_names,
                    BizOrder.amount,
                    BizOrder.status,
                    BizOrder.order_time,
                    BizOrder.order_date,
                    BizOrder.created_at,
                    BizOrder.updated_at,
                    BizCustomer.external_id,
                    BizCustomer.name.label("customer_name"),
                    BizCustomer.follow_user_id,
                )
                .join(BizCustomer, BizOrder.union_id == BizCustomer.union_id)
                .filter(BizOrder.order_id == order_id)
            )
            query = OrderDAO._apply_order_scope(query, data_scope, user_id, wework_account_id)
            if query is None:
                return None
            r = query.first()
            if not r:
                return None
            return {
                "order_id": r.order_id,
                "union_id": r.union_id,
                "wework_account_id": r.wework_account_id,
                "product_names": r.product_names,
                "amount": r.amount,
                "status": r.status,
                "order_time": r.order_time,
                "order_date": r.order_date,
                "created_at": r.created_at,
                "updated_at": r.updated_at,
                "external_id": r.external_id,
                "customer_name": r.customer_name,
                "follow_user_id": r.follow_user_id,
            }

    @staticmethod
    def get_by_customer_name(
        customer_name: str,
        user_id: str,
        data_scope: str,
        wework_account_id: Optional[str],
        page: int = 1,
        page_size: int = 20,
    ) -> Dict:
        if not wework_account_id and data_scope != "all":
            return {"items": [], "total": 0, "page": page, "page_size": page_size}

        with session_scope() as session:
            query = (
                session.query(
                    BizOrder.order_id,
                    BizOrder.union_id,
                    BizOrder.wework_account_id,
                    BizOrder.product_names,
                    BizOrder.amount,
                    BizOrder.status,
                    BizOrder.order_time,
                    BizOrder.order_date,
                    BizOrder.created_at,
                    BizOrder.updated_at,
                    BizCustomer.external_id,
                    BizCustomer.name.label("customer_name"),
                    BizCustomer.follow_user_id,
                )
                .join(BizCustomer, BizOrder.union_id == BizCustomer.union_id)
                .filter(BizCustomer.name.like(f"%{customer_name}%"))
            )
            query = OrderDAO._apply_order_scope(query, data_scope, user_id, wework_account_id)
            if query is None:
                return {"items": [], "total": 0, "page": page, "page_size": page_size}

            total = session.query(func.count()).select_from(query.subquery()).scalar()
            rows = (
                query.order_by(BizOrder.order_time.desc())
                .limit(page_size)
                .offset((page - 1) * page_size)
                .all()
            )
            items = [
                {
                    "order_id": r.order_id,
                    "union_id": r.union_id,
                    "wework_account_id": r.wework_account_id,
                    "product_names": r.product_names,
                    "amount": r.amount,
                    "status": r.status,
                    "order_time": r.order_time,
                    "order_date": r.order_date,
                    "created_at": r.created_at,
                    "updated_at": r.updated_at,
                    "external_id": r.external_id,
                    "customer_name": r.customer_name,
                    "follow_user_id": r.follow_user_id,
                }
                for r in rows
            ]
            return {"items": items, "total": total, "page": page, "page_size": page_size}

    @staticmethod
    def get_stats(
        user_id: str,
        data_scope: str,
        wework_account_id: Optional[str],
    ) -> Dict:
        if not wework_account_id and data_scope != "all":
            return {
                "total_orders": 0,
                "total_amount": 0,
                "in_progress": 0,
                "pending_use": 0,
                "completed": 0,
                "refunded": 0,
            }

        with session_scope() as session:
            query = (
                session.query(
                    func.count(BizOrder.id).label("total_orders"),
                    func.sum(BizOrder.amount).label("total_amount"),
                    func.sum(case((BizOrder.status == "进行中", 1), else_=0)).label("in_progress"),
                    func.sum(case((BizOrder.status == "待使用", 1), else_=0)).label("pending_use"),
                    func.sum(case((BizOrder.status == "已完结", 1), else_=0)).label("completed"),
                    func.sum(case((BizOrder.status == "已退款", 1), else_=0)).label("refunded"),
                )
                .join(BizCustomer, BizOrder.union_id == BizCustomer.union_id)
            )
            query = OrderDAO._apply_order_scope(query, data_scope, user_id, wework_account_id)
            if query is None:
                return {
                    "total_orders": 0,
                    "total_amount": 0,
                    "in_progress": 0,
                    "pending_use": 0,
                    "completed": 0,
                    "refunded": 0,
                }
            r = query.first()
            result = {
                "total_orders": int(r.total_orders or 0),
                "total_amount": r.total_amount,
                "in_progress": int(r.in_progress or 0),
                "pending_use": int(r.pending_use or 0),
                "completed": int(r.completed or 0),
                "refunded": int(r.refunded or 0),
            }
            if result.get("total_amount") is not None:
                result["total_amount"] = float(result["total_amount"])
            return result

    @staticmethod
    def get_status_stats_by_date(
        user_id: str,
        data_scope: str,
        wework_account_id: Optional[str],
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> List[Dict]:
        if not wework_account_id and data_scope != "all":
            return []

        with session_scope() as session:
            query = (
                session.query(
                    BizOrder.order_date,
                    func.count(BizOrder.id).label("total"),
                    func.sum(case((BizOrder.status == "进行中", 1), else_=0)).label("in_progress"),
                    func.sum(case((BizOrder.status == "待使用", 1), else_=0)).label("pending_use"),
                    func.sum(case((BizOrder.status == "已完结", 1), else_=0)).label("completed"),
                    func.sum(case((BizOrder.status == "已退款", 1), else_=0)).label("refunded"),
                )
                .join(BizCustomer, BizOrder.union_id == BizCustomer.union_id)
            )
            query = OrderDAO._apply_order_scope(query, data_scope, user_id, wework_account_id)
            if query is None:
                return []

            if start_date:
                query = query.filter(BizOrder.order_date >= _parse_date(start_date))
            if end_date:
                query = query.filter(BizOrder.order_date <= _parse_date(end_date))

            rows = (
                query.group_by(BizOrder.order_date)
                .order_by(BizOrder.order_date.desc())
                .all()
            )
            return [
                {
                    "order_date": r.order_date,
                    "total": int(r.total or 0),
                    "in_progress": int(r.in_progress or 0),
                    "pending_use": int(r.pending_use or 0),
                    "completed": int(r.completed or 0),
                    "refunded": int(r.refunded or 0),
                }
                for r in rows
            ]

    @staticmethod
    def get_renewal_rate(
        user_id: str,
        data_scope: str,
        wework_account_id: Optional[str],
    ) -> Dict:
        """
        续费率（5.5）：有 2 单及以上（非退款）订单的客户数 / 有至少 1 单（非退款）订单的客户数
        """
        if not wework_account_id and data_scope != "all":
            return {"renewal_rate": 0.0, "renewed_customers": 0, "active_customers": 0}

        inner = (
            select(
                BizCustomer.union_id,
                func.count(BizOrder.order_id).label("cnt"),
            )
            .select_from(BizCustomer)
            .outerjoin(
                BizOrder,
                and_(BizCustomer.union_id == BizOrder.union_id, BizOrder.status != "已退款"),
            )
        )
        if data_scope != "all":
            inner = OrderDAO._apply_order_scope(inner, data_scope, user_id, wework_account_id)
            if inner is None:
                return {"renewal_rate": 0.0, "renewed_customers": 0, "active_customers": 0}
        oc = inner.group_by(BizCustomer.union_id).subquery()

        with session_scope() as session:
            r = session.query(
                func.count(distinct(case((oc.c.cnt >= 1, oc.c.union_id)))).label("active_customers"),
                func.count(distinct(case((oc.c.cnt >= 2, oc.c.union_id)))).label("renewed_customers"),
            ).first()
            active = int(r.active_customers or 0)
            renewed = int(r.renewed_customers or 0)
            rate = round(100.0 * renewed / active, 1) if active > 0 else 0.0
            return {
                "renewal_rate": rate,
                "renewed_customers": renewed,
                "active_customers": active,
            }

    @staticmethod
    def get_advisor_efficiency(
        user_id: str,
        data_scope: str,
        wework_account_id: Optional[str],
        limit: int = 5,
    ) -> List[Dict]:
        """
        顾问人效 TOP N（5.5）：按成单数（已完结订单）排名，返回每位顾问的客户数/订单数/成单数/成交金额/转化率
        """
        if not wework_account_id and data_scope != "all":
            return []

        with session_scope() as session:
            query = (
                session.query(
                    BizCustomer.follow_user_id.label("user_id"),
                    SysEmployee.name.label("advisor_name"),
                    func.count(distinct(BizCustomer.external_id)).label("customer_count"),
                    func.count(distinct(case((BizOrder.status != "已退款", BizOrder.order_id)))).label("order_count"),
                    func.count(distinct(case((BizOrder.status == "已完结", BizOrder.order_id)))).label("completed_count"),
                    func.coalesce(func.sum(case((BizOrder.status != "已退款", BizOrder.amount), else_=0)), 0).label("total_amount"),
                )
                .outerjoin(BizOrder, BizCustomer.union_id == BizOrder.union_id)
                .outerjoin(SysEmployee, SysEmployee.user_id == BizCustomer.follow_user_id)
            )
            query = OrderDAO._apply_order_scope(query, data_scope, user_id, wework_account_id)
            if query is None:
                return []

            rows = (
                query.group_by(BizCustomer.follow_user_id, SysEmployee.name)
                .order_by(
                    func.count(distinct(case((BizOrder.status == "已完结", BizOrder.order_id)))).desc(),
                    func.count(distinct(case((BizOrder.status != "已退款", BizOrder.order_id)))).desc(),
                )
                .limit(limit)
                .all()
            )
            result = []
            for r in rows:
                customer_count = int(r.customer_count or 0)
                order_count = int(r.order_count or 0)
                completed_count = int(r.completed_count or 0)
                total_amount = float(r.total_amount or 0)
                result.append({
                    "user_id": r.user_id,
                    "advisor_name": r.advisor_name,
                    "customer_count": customer_count,
                    "order_count": order_count,
                    "completed_count": completed_count,
                    "total_amount": total_amount,
                    "conversion_rate": round(100.0 * order_count / customer_count, 1) if customer_count > 0 else 0.0,
                })
            return result

    # ==================== 写入方法 ====================

    @staticmethod
    def create(
        order_id: str,
        union_id: str,
        wework_account_id: str,
        product_names: Optional[object] = None,
        amount: Optional[float] = None,
        status: str = "进行中",
        order_time: Optional[datetime] = None,
        order_date: Optional[str] = None,
    ) -> bool:
        """新增订单（product_names 传入 dict/list 时由 JSON 列直接序列化）"""
        order_time = order_time or datetime.now()
        order_date_obj = _parse_date(order_date) if order_date else order_time.date()

        with session_scope(commit=True) as session:
            session.add(
                BizOrder(
                    order_id=order_id,
                    union_id=union_id,
                    wework_account_id=wework_account_id,
                    product_names=product_names,
                    amount=amount,
                    status=status,
                    order_time=order_time,
                    order_date=order_date_obj,
                )
            )
            return True

    @staticmethod
    def update_status(order_id: str, status: str) -> bool:
        """更新订单状态"""
        if status not in VALID_ORDER_STATUSES:
            raise ValueError(f"无效的订单状态: {status}，允许值: {VALID_ORDER_STATUSES}")

        with session_scope(commit=True) as session:
            result = session.execute(
                update(BizOrder).where(BizOrder.order_id == order_id).values(status=status)
            )
            return result.rowcount > 0

    @staticmethod
    def update(
        order_id: str,
        product_names: Optional[object] = None,
        amount: Optional[float] = None,
        status: Optional[str] = None,
        order_time: Optional[datetime] = None,
        order_date: Optional[str] = None,
    ) -> bool:
        """更新订单信息（仅更新传入字段）"""
        with session_scope(commit=True) as session:
            row = (
                session.query(BizOrder)
                .filter(BizOrder.order_id == order_id)
                .first()
            )
            if not row:
                return False
            if product_names is not None:
                row.product_names = product_names
            if amount is not None:
                row.amount = amount
            if status is not None:
                if status not in VALID_ORDER_STATUSES:
                    raise ValueError(f"无效的订单状态: {status}")
                row.status = status
            if order_time is not None:
                row.order_time = order_time
            if order_date is not None:
                row.order_date = _parse_date(order_date)
            return True

    @staticmethod
    def delete(order_id: str) -> bool:
        """物理删除订单"""
        with session_scope(commit=True) as session:
            result = session.execute(
                delete(BizOrder).where(BizOrder.order_id == order_id)
            )
            return result.rowcount > 0

    @staticmethod
    def exists(order_id: str) -> bool:
        """检查订单是否存在"""
        with session_scope() as session:
            return (
                session.query(BizOrder)
                .filter(BizOrder.order_id == order_id)
                .first()
                is not None
            )
