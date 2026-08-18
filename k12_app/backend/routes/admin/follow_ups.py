# k12_app/routes/admin/follow_ups.py
"""管理后台 — 跟进记录管理"""

from typing import Optional
from datetime import datetime
from fastapi import APIRouter, Request, HTTPException, Depends, Query
from pydantic import BaseModel

from k12_app.backend.services.follow_up_service import FollowUpService

from k12_app.backend.services.auth_service import get_admin_session

router = APIRouter()


class FollowUpCreateRequest(BaseModel):
    external_id: str
    follow_up_type: str
    content: str
    result: Optional[str] = None
    next_action: Optional[str] = None
    follow_up_time: Optional[str] = None


class FollowUpUpdateRequest(BaseModel):
    content: Optional[str] = None
    result: Optional[str] = None
    follow_up_time: Optional[str] = None
    next_action: Optional[str] = None
    follow_up_type: Optional[str] = None


@router.get("/follow_up_list")
async def list_follow_ups(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    follow_up_type: Optional[str] = Query(None),
    result: Optional[str] = Query(None),
    current_admin: dict = Depends(get_admin_session),
):
    data = FollowUpService.get_list(
        user_id=current_admin["user_id"],
        data_scope=current_admin["data_scope"],
        wework_account_id=current_admin.get("wework_account_id"),
        follow_up_type=follow_up_type,
        result=result,
        page=page,
        page_size=page_size,
    )
    return {"success": True, "data": data}


@router.post("/follow_up")
async def create_follow_up(
    req: FollowUpCreateRequest,
    current_admin: dict = Depends(get_admin_session),
):
    try:
        ft = datetime.fromisoformat(req.follow_up_time) if req.follow_up_time else None
    except ValueError:
        raise HTTPException(status_code=400, detail="日期格式错误，应为 ISO 格式")
    success = FollowUpService.create(
        external_id=req.external_id,
        user_id=current_admin["user_id"],
        wework_account_id=current_admin.get("wework_account_id", ""),
        follow_up_type=req.follow_up_type,
        follow_up_time=ft,
        content=req.content,
        result=req.result,
        next_action=req.next_action,
    )
    if not success:
        raise HTTPException(status_code=500, detail="创建跟进记录失败")
    return {"success": True, "message": "跟进记录创建成功"}


@router.put("/follow_ups/{follow_up_id}")
async def update_follow_up(
    follow_up_id: int,
    req: FollowUpUpdateRequest,
    current_admin: dict = Depends(get_admin_session),
):
    """更新跟进记录"""
    if not FollowUpService.get_by_id(
        follow_up_id=follow_up_id,
        user_id=current_admin["user_id"],
        data_scope=current_admin.get("data_scope", "self"),
        wework_account_id=current_admin.get("wework_account_id"),
    ):
        raise HTTPException(status_code=404, detail="跟进记录不存在或无访问权限")

    follow_up_time = None
    if req.follow_up_time:
        try:
            follow_up_time = datetime.fromisoformat(req.follow_up_time)
        except ValueError:
            raise HTTPException(status_code=400, detail="日期格式错误，应为 ISO 格式")

    try:
        success = FollowUpService.update(
            follow_up_id=follow_up_id,
            content=req.content,
            result=req.result,
            follow_up_time=follow_up_time,
            next_action=req.next_action,
            follow_up_type=req.follow_up_type,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if not success:
        raise HTTPException(status_code=500, detail="更新跟进记录失败")
    return {"success": True, "message": "跟进记录更新成功"}


@router.delete("/follow_ups/{follow_up_id}")
async def delete_follow_up(
    follow_up_id: int,
    current_admin: dict = Depends(get_admin_session),
):
    """删除跟进记录"""
    if not FollowUpService.get_by_id(
        follow_up_id=follow_up_id,
        user_id=current_admin["user_id"],
        data_scope=current_admin.get("data_scope", "self"),
        wework_account_id=current_admin.get("wework_account_id"),
    ):
        raise HTTPException(status_code=404, detail="跟进记录不存在或无访问权限")

    success = FollowUpService.delete(follow_up_id)
    if not success:
        raise HTTPException(status_code=500, detail="删除跟进记录失败")
    return {"success": True, "message": "跟进记录删除成功"}
