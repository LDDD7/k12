# k12_app/routes/admin/dashboard.py
"""管理后台 — 数据看板"""

from typing import Optional
from fastapi import APIRouter, Request, HTTPException, Depends, Query

from k12_app.backend.services.dashboard_service import DashboardService

from k12_app.backend.services.auth_service import get_admin_session

router = APIRouter()


@router.get("/dashboard/funnel")
async def funnel(current_admin: dict = Depends(get_admin_session)):
    """转化漏斗"""
    data = DashboardService.get_funnel_stats(
        user_id=current_admin["user_id"],
        data_scope=current_admin["data_scope"],
        wework_account_id=current_admin.get("wework_account_id"),
    )
    return {"success": True, "data": data}


@router.get("/dashboard/adopt_rate")
async def adopt_rate(current_admin: dict = Depends(get_admin_session)):
    """AI 采纳率"""
    data = DashboardService.get_adopt_rate(
        user_id=current_admin["user_id"],
        data_scope=current_admin["data_scope"],
        wework_account_id=current_admin.get("wework_account_id"),
    )
    return {"success": True, "data": data}


@router.get("/dashboard/renewal_rate")
async def renewal_rate(current_admin: dict = Depends(get_admin_session)):
    """续费率"""
    data = DashboardService.get_renewal_rate(
        user_id=current_admin["user_id"],
        data_scope=current_admin["data_scope"],
        wework_account_id=current_admin.get("wework_account_id"),
    )
    return {"success": True, "data": data}


@router.get("/dashboard/advisor_efficiency")
async def advisor_efficiency(
    limit: int = Query(5, ge=1, le=50),
    current_admin: dict = Depends(get_admin_session),
):
    """顾问人效 TOP N"""
    data = DashboardService.get_advisor_efficiency(
        user_id=current_admin["user_id"],
        data_scope=current_admin["data_scope"],
        wework_account_id=current_admin.get("wework_account_id"),
        limit=limit,
    )
    return {"success": True, "data": data}
