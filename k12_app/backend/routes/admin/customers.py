# k12_app/routes/admin/customers.py
"""管理后台 — 客户管理（含权限过滤）"""

from datetime import datetime as dt
from typing import Optional

from fastapi import APIRouter, Request, HTTPException, Depends, Query
from pydantic import BaseModel

from k12_app.backend.services.customer_service import CustomerService
from k12_app.backend.services.message_service import MessageService
from k12_app.backend.services.order_service import OrderService
from k12_app.backend.services.follow_up_service import FollowUpService
from k12_app.backend.services.schedule_service import ScheduleService
from k12_app.backend.services.tag_service import TagService

from k12_app.backend.services.auth_service import get_admin_session

router = APIRouter()


@router.get("/customer_list")
async def list_customers(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    stage: Optional[str] = None,
    keyword: Optional[str] = None,
    current_admin: dict = Depends(get_admin_session),
):
    result = CustomerService.get_list(
        user_id=current_admin["user_id"],
        data_scope=current_admin["data_scope"],
        wework_account_id=current_admin.get("wework_account_id"),
        stage=stage,
        keyword=keyword,
        page=page,
        page_size=page_size,
    )
    return {"success": True, "data": result}


@router.get("/customer_detail/{user_id}/{external_id}")
async def customer_detail(
    user_id: str,
    external_id: str,
    current_admin: dict = Depends(get_admin_session),
):
    cust = CustomerService.get_by_external_id(
        external_id=external_id,
        user_id=current_admin["user_id"],
        data_scope=current_admin["data_scope"],
        wework_account_id=current_admin.get("wework_account_id"),
    )
    if not cust:
        raise HTTPException(status_code=404, detail="客户不存在")
    return {"success": True, "data": cust}


class CustomerUpdateRequest(BaseModel):
    name: Optional[str] = None
    child_name: Optional[str] = None
    school: Optional[str] = None
    grade: Optional[str] = None
    focus_subject: Optional[str] = None
    remark: Optional[str] = None
    stage: Optional[str] = None
    lead_source: Optional[str] = None


@router.put("/customers/{external_id}")
async def update_customer(
    external_id: str,
    req: CustomerUpdateRequest,
    current_admin: dict = Depends(get_admin_session),
):
    """编辑客户信息"""
    cust = CustomerService.get_by_external_id(
        external_id=external_id,
        user_id=current_admin["user_id"],
        data_scope=current_admin["data_scope"],
        wework_account_id=current_admin.get("wework_account_id"),
    )
    if not cust:
        raise HTTPException(status_code=404, detail="客户不存在或无访问权限")

    success = CustomerService.update(
        external_id=external_id,
        name=req.name,
        child_name=req.child_name,
        school=req.school,
        grade=req.grade,
        focus_subject=req.focus_subject,
        remark=req.remark,
        stage=req.stage,
        lead_source=req.lead_source,
    )
    if not success:
        raise HTTPException(status_code=500, detail="更新客户失败")
    return {"success": True, "message": "客户更新成功"}


@router.get("/chat_records/{user_id}/{external_id}")
async def chat_records(
    user_id: str,
    external_id: str,
    current_admin: dict = Depends(get_admin_session),
):
    chats = MessageService.get_chat_history(
        user_id=user_id,
        external_id=external_id,
        wework_account_id=current_admin.get("wework_account_id"),
        data_scope=current_admin["data_scope"],
        days=30,
        limit=100,
    )
    return {"success": True, "data": chats}


@router.get("/kf_records/{external_id}")
async def kf_records(
    external_id: str,
    current_admin: dict = Depends(get_admin_session),
):
    records = MessageService.get_kf_history(
        external_id=external_id,
        user_id=current_admin["user_id"],
        data_scope=current_admin["data_scope"],
        wework_account_id=current_admin.get("wework_account_id"),
        days=30,
        limit=100,
    )
    return {"success": True, "data": records}


@router.get("/customer_orders/{union_id}")
async def customer_orders(
    union_id: str,
    current_admin: dict = Depends(get_admin_session),
):
    orders = OrderService.get_by_union_id(
        union_id=union_id,
        user_id=current_admin["user_id"],
        data_scope=current_admin["data_scope"],
        wework_account_id=current_admin.get("wework_account_id"),
    )
    return {"success": True, "data": orders}


@router.get("/lead_source_stats")
async def lead_source_stats(
    current_admin: dict = Depends(get_admin_session),
):
    stats = CustomerService.get_lead_source_stats(
        user_id=current_admin["user_id"],
        data_scope=current_admin["data_scope"],
        wework_account_id=current_admin.get("wework_account_id"),
    )
    return {"success": True, "data": stats}


@router.get("/customer_timeline/{external_id}")
async def customer_timeline(
    external_id: str,
    days: int = Query(90, ge=1, le=365),
    current_admin: dict = Depends(get_admin_session),
):
    """
    客户触达时间线 — 聚合聊天 + 跟进 + 日程三表数据（V3.1）
    按时间倒序排列，形成完整的客户交互历史
    """
    timeline = CustomerService.get_timeline(
        external_id=external_id,
        user_id=current_admin["user_id"],
        data_scope=current_admin["data_scope"],
        wework_account_id=current_admin.get("wework_account_id"),
        days=days,
    )
    return {"success": True, "data": timeline}


@router.get("/customer_tags/{external_id}")
async def admin_customer_tags(
    external_id: str,
    current_admin: dict = Depends(get_admin_session),
):
    """管理后台查看客户标签（无需 JWT）"""
    tags = TagService.get_customer_tags(
        external_id=external_id,
        user_id=current_admin["user_id"],
        data_scope=current_admin["data_scope"],
        wework_account_id=current_admin.get("wework_account_id"),
    )
    for t in tags:
        for k, v in list(t.items()):
            if isinstance(v, (dt,)):
                t[k] = v.isoformat()
    all_tags = TagService.get_all_tags()
    return {"success": True, "data": {"tags": tags, "all_tags": all_tags}}


# ============================================================
# 日程管理
# ============================================================


class ScheduleUpdateRequest(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    priority: Optional[str] = None
    status: Optional[str] = None


@router.get("/schedules")
async def list_schedules(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_admin: dict = Depends(get_admin_session),
):
    """管理后台查看所有日程"""
    user_id = current_admin["user_id"]
    data_scope = current_admin.get("data_scope", "self")
    wwa = current_admin.get("wework_account_id")

    result = ScheduleService.get_admin_list(
        user_id=user_id,
        data_scope=data_scope,
        wework_account_id=wwa,
        page=page,
        page_size=page_size,
    )
    items = result.get("items", [])
    for it in items:
        for k, v in list(it.items()):
            if isinstance(v, (dt,)):
                it[k] = v.isoformat()
    return {"success": True, "data": result}


@router.put("/schedules/{schedule_id}")
async def update_schedule(
    schedule_id: int,
    req: ScheduleUpdateRequest,
    current_admin: dict = Depends(get_admin_session),
):
    """更新日程"""
    s = ScheduleService.get_by_id(
        schedule_id=schedule_id,
        user_id=current_admin["user_id"],
        data_scope=current_admin.get("data_scope", "self"),
        wework_account_id=current_admin.get("wework_account_id"),
    )
    if not s:
        raise HTTPException(status_code=404, detail="日程不存在或无访问权限")

    success = ScheduleService.update_schedule(
        schedule_id=schedule_id,
        title=req.title,
        start_time=dt.fromisoformat(req.start_time) if req.start_time else None,
        end_time=dt.fromisoformat(req.end_time) if req.end_time else None,
        priority=req.priority,
        status=req.status,
    )
    if not success:
        raise HTTPException(status_code=404, detail="日程更新失败")
    return {"success": True, "message": "日程更新成功"}


class ScheduleCreateRequest(BaseModel):
    external_id: str
    title: str
    start_time: str
    end_time: Optional[str] = None
    priority: str = "中"


@router.post("/schedules")
async def create_schedule(
    req: ScheduleCreateRequest,
    current_admin: dict = Depends(get_admin_session),
):
    """管理后台手动新增日程（状态：待确认，来源：人工创建）"""
    cust = CustomerService.get_by_external_id(
        external_id=req.external_id,
        user_id=current_admin["user_id"],
        data_scope=current_admin.get("data_scope", "self"),
        wework_account_id=current_admin.get("wework_account_id"),
    )
    if not cust:
        raise HTTPException(status_code=404, detail="客户不存在或无访问权限")

    follow_user_id = cust.get("follow_user_id") or current_admin["user_id"]
    wework_account_id = cust.get("wework_account_id") or current_admin.get("wework_account_id", "")

    schedule_id = ScheduleService.add_schedule_pending(
        external_id=req.external_id,
        user_id=follow_user_id,
        wework_account_id=wework_account_id,
        sched={
            "title": req.title,
            "start_time": dt.fromisoformat(req.start_time),
            "end_time": dt.fromisoformat(req.end_time) if req.end_time else None,
            "priority": req.priority,
            "source": "人工创建",
        },
        operator_id=current_admin["user_id"],
    )
    if not schedule_id:
        raise HTTPException(status_code=500, detail="日程添加失败")
    return {"success": True, "data": {"schedule_id": schedule_id}}


@router.delete("/schedules/{schedule_id}")
async def delete_schedule(
    schedule_id: int,
    current_admin: dict = Depends(get_admin_session),
):
    """删除日程（任意状态）"""
    s = ScheduleService.get_by_id(
        schedule_id=schedule_id,
        user_id=current_admin["user_id"],
        data_scope=current_admin.get("data_scope", "self"),
        wework_account_id=current_admin.get("wework_account_id"),
    )
    if not s:
        raise HTTPException(status_code=404, detail="日程不存在或无访问权限")

    if not ScheduleService.delete(schedule_id):
        raise HTTPException(status_code=404, detail="日程删除失败")
    return {"success": True, "message": "日程删除成功"}
