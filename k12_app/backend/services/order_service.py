"""
订单服务 — 订单管理 / 订单统计 / 续费率 / 顾问人效
业务层：供路由层调用，数据访问委托给 OrderDAO / CustomerDAO
"""

import logging
from datetime import datetime
from typing import Optional, Dict, List

from k12_app.backend.dao.order_dao import OrderDAO, VALID_ORDER_STATUSES
from k12_app.backend.dao.customer_dao import CustomerDAO

logger = logging.getLogger(__name__)


class OrderService:
    """订单服务"""

    VALID_ORDER_STATUSES = VALID_ORDER_STATUSES

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
        """获取订单列表"""
        return OrderDAO.get_list(
            user_id=user_id,
            data_scope=data_scope,
            wework_account_id=wework_account_id,
            status=status,
            keyword=keyword,
            start_date=start_date,
            end_date=end_date,
            page=page,
            page_size=page_size,
        )

    @staticmethod
    def get_by_union_id(
        union_id: str,
        user_id: str,
        data_scope: str,
        wework_account_id: Optional[str],
    ) -> List[Dict]:
        """按 union_id 查询订单"""
        return OrderDAO.get_by_union_id(union_id, user_id, data_scope, wework_account_id)

    @staticmethod
    def exists(order_id: str) -> bool:
        """检查订单是否存在"""
        return OrderDAO.exists(order_id)

    @staticmethod
    def create_order(
        order_id: str,
        customer_name: Optional[str],
        external_id: Optional[str],
        product_name: Optional[str],
        amount: Optional[float],
        status: str,
        order_date: Optional[str],
        current_admin: Dict,
    ) -> Dict:
        """
        新增订单；若客户不存在则自动创建，实现订单增加 → 客户管理同步增加

        Returns:
            {"order_id": ..., "union_id": ...}
        """
        user_id = current_admin["user_id"]
        wework_account_id = current_admin.get("wework_account_id") or ""

        # 1. 解析订单归属客户（union_id）
        union_id = None
        if external_id:
            cust = CustomerDAO.get_by_external_id(
                external_id=external_id,
                user_id=user_id,
                data_scope="all",
                wework_account_id=wework_account_id,
            )
            if not cust:
                raise LookupError("客户不存在")
            union_id = cust.get("union_id")
        else:
            name = (customer_name or "").strip()
            if not name:
                raise ValueError("请填写客户姓名或客户ID")
            cust = CustomerDAO.find_by_name(name)
            if cust:
                union_id = cust.get("union_id")
            else:
                # 自动创建客户
                new_external_id, new_union_id = CustomerDAO.get_next_ids()
                CustomerDAO.create(
                    external_id=new_external_id,
                    union_id=new_union_id,
                    follow_user_id=user_id,
                    wework_account_id=wework_account_id,
                    name=name,
                    stage="潜在",
                )
                union_id = new_union_id

        if not union_id:
            raise ValueError("无法确定订单归属客户")

        # 2. 解析下单日期
        try:
            order_time = datetime.fromisoformat(order_date) if order_date else datetime.now()
        except ValueError:
            raise ValueError("日期格式错误，应为 ISO 格式")

        # 3. 创建订单（product_names 存为课程名称数组，如 ["试听券"]）
        product_names = [product_name] if product_name else None
        success = OrderDAO.create(
            order_id=order_id,
            union_id=union_id,
            wework_account_id=wework_account_id,
            product_names=product_names,
            amount=amount,
            status=status,
            order_time=order_time,
            order_date=order_date or order_time.strftime("%Y-%m-%d"),
        )
        if not success:
            raise RuntimeError("创建订单失败")
        return {"order_id": order_id, "union_id": union_id}

    @staticmethod
    def update_order(
        order_id: str,
        status: Optional[str] = None,
        product_name: Optional[str] = None,
        amount: Optional[float] = None,
        order_date: Optional[str] = None,
    ) -> bool:
        """更新订单（状态流转 / 产品 / 金额 / 日期）"""
        product_names = None
        if product_name is not None:
            product_names = [product_name]

        order_date_str = None
        if order_date:
            try:
                datetime.fromisoformat(order_date)
            except ValueError:
                raise ValueError("日期格式错误，应为 ISO 格式")
            order_date_str = order_date

        return OrderDAO.update(
            order_id=order_id,
            product_names=product_names,
            amount=amount,
            status=status,
            order_date=order_date_str,
        )

    @staticmethod
    def get_stats(
        user_id: str,
        data_scope: str,
        wework_account_id: Optional[str],
    ) -> Dict:
        """获取订单统计"""
        return OrderDAO.get_stats(user_id, data_scope, wework_account_id)

    @staticmethod
    def get_renewal_rate(
        user_id: str,
        data_scope: str,
        wework_account_id: Optional[str],
    ) -> Dict:
        """获取续费率（5.5）"""
        return OrderDAO.get_renewal_rate(user_id, data_scope, wework_account_id)

    @staticmethod
    def get_advisor_efficiency(
        user_id: str,
        data_scope: str,
        wework_account_id: Optional[str],
        limit: int = 5,
    ) -> List[Dict]:
        """获取顾问人效 TOP N（5.5）"""
        return OrderDAO.get_advisor_efficiency(user_id, data_scope, wework_account_id, limit)
