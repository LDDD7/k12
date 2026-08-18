# k12_app/routes/admin/orders.py
"""管理后台 — 订单管理"""

import logging
from typing import Optional
from fastapi import APIRouter, Request, HTTPException, Depends, Query
from pydantic import BaseModel

logger = logging.getLogger(__name__)

from k12_app.backend.services.order_service import OrderService

from k12_app.backend.services.auth_service import get_admin_session

router = APIRouter()


@router.get("/order_list")
async def list_orders(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[str] = None,
    keyword: Optional[str] = None,
    current_admin: dict = Depends(get_admin_session),
):
    result = OrderService.get_list(
        user_id=current_admin["user_id"],
        data_scope=current_admin["data_scope"],
        wework_account_id=current_admin.get("wework_account_id"),
        status=status,
        keyword=keyword,
        page=page,
        page_size=page_size,
    )
    return {"success": True, "data": result}


class OrderCreateRequest(BaseModel):
    order_id: str
    customer_name: Optional[str] = None
    external_id: Optional[str] = None
    product_name: Optional[str] = None
    amount: Optional[float] = None
    status: str = "进行中"
    order_date: Optional[str] = None


class OrderUpdateRequest(BaseModel):
    status: Optional[str] = None
    product_name: Optional[str] = None
    amount: Optional[float] = None
    order_date: Optional[str] = None


@router.post("/order")
async def create_order(
    req: OrderCreateRequest,
    current_admin: dict = Depends(get_admin_session),
):
    """新增订单；若客户不存在则自动创建，实现订单增加 → 客户管理同步增加"""
    if req.status not in OrderService.VALID_ORDER_STATUSES:
        raise HTTPException(status_code=400, detail=f"无效的订单状态: {req.status}")

    if not req.order_id or not req.order_id.strip():
        raise HTTPException(status_code=400, detail="订单号不能为空")
    order_id = req.order_id.strip()

    if OrderService.exists(order_id):
        raise HTTPException(status_code=400, detail="订单号已存在")

    try:
        data = OrderService.create_order(
            order_id=order_id,
            customer_name=req.customer_name,
            external_id=req.external_id,
            product_name=req.product_name,
            amount=req.amount,
            status=req.status,
            order_date=req.order_date,
            current_admin=current_admin,
        )
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        logger.error(f"创建订单失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="创建订单失败，请稍后重试")

    return {"success": True, "message": "订单创建成功", "data": data}


@router.put("/orders/{order_id}")
async def update_order(
    order_id: str,
    req: OrderUpdateRequest,
    current_admin: dict = Depends(get_admin_session),
):
    """更新订单（状态流转 / 产品 / 金额 / 日期）"""
    if not OrderService.get_by_order_id(
        order_id=order_id,
        user_id=current_admin["user_id"],
        data_scope=current_admin.get("data_scope", "self"),
        wework_account_id=current_admin.get("wework_account_id"),
    ):
        raise HTTPException(status_code=404, detail="订单不存在或无访问权限")

    if req.status is not None and req.status not in OrderService.VALID_ORDER_STATUSES:
        raise HTTPException(status_code=400, detail=f"无效的订单状态: {req.status}")

    try:
        success = OrderService.update_order(
            order_id=order_id,
            status=req.status,
            product_name=req.product_name,
            amount=req.amount,
            order_date=req.order_date,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if not success:
        raise HTTPException(status_code=500, detail="更新订单失败")
    return {"success": True, "message": "订单更新成功"}
