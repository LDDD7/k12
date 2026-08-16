# k12_app/routes/admin/wework_accounts.py
"""管理后台 — 企微账户管理"""

from typing import Optional
from fastapi import APIRouter, Request, HTTPException, Depends
from pydantic import BaseModel

from k12_app.backend.services.wework_account_service import WeWorkAccountService

from k12_app.backend.services.auth_service import get_admin_session

router = APIRouter()


class WeworkAccountCreateRequest(BaseModel):
    account_id: str
    account_name: str
    corp_id: str
    corp_secret: str
    region: str
    agent_id: Optional[str] = None


class WeworkAccountUpdateRequest(BaseModel):
    account_name: Optional[str] = None
    corp_secret: Optional[str] = None
    region: Optional[str] = None
    agent_id: Optional[str] = None
    is_active: Optional[int] = None


@router.get("/wework_accounts")
async def list_accounts(current_admin: dict = Depends(get_admin_session)):
    """获取企微账户列表（三维度权限过滤）"""
    accounts = WeWorkAccountService.get_all(
        user_id=current_admin["user_id"],
        data_scope=current_admin["data_scope"],
        wework_account_id=current_admin.get("wework_account_id"),
    )
    return {"success": True, "data": accounts}


@router.post("/wework_accounts")
async def create_account(
    req: WeworkAccountCreateRequest,
    current_admin: dict = Depends(get_admin_session),
):
    """新增企微账户（仅超管）"""
    if current_admin["data_scope"] != "all":
        raise HTTPException(status_code=403, detail="仅超级管理员可新增企微账户")

    if WeWorkAccountService.exists(req.account_id):
        raise HTTPException(status_code=400, detail="企微账户 ID 已存在")

    success = WeWorkAccountService.create(
        account_id=req.account_id,
        account_name=req.account_name,
        corp_id=req.corp_id,
        corp_secret=req.corp_secret,
        region=req.region,
        agent_id=req.agent_id,
    )
    if not success:
        raise HTTPException(status_code=500, detail="创建企微账户失败")
    return {"success": True, "message": "企微账户创建成功"}


@router.put("/wework_accounts/{account_id}")
async def update_account(
    account_id: str,
    req: WeworkAccountUpdateRequest,
    current_admin: dict = Depends(get_admin_session),
):
    """更新企微账户信息"""
    if current_admin["data_scope"] != "all":
        raise HTTPException(status_code=403, detail="仅超级管理员可修改企微账户")

    if not WeWorkAccountService.exists(account_id):
        raise HTTPException(status_code=404, detail="企微账户不存在")

    success = WeWorkAccountService.update(
        account_id=account_id,
        account_name=req.account_name,
        corp_secret=req.corp_secret,
        region=req.region,
        agent_id=req.agent_id,
        is_active=req.is_active,
    )
    if not success:
        raise HTTPException(status_code=500, detail="更新企微账户失败")
    return {"success": True, "message": "企微账户更新成功"}


@router.get("/wework_accounts/{account_id}/stats")
async def account_stats(
    account_id: str,
    current_admin: dict = Depends(get_admin_session),
):
    """获取企微账户统计数据（客户数、订单数、员工数、月消息量）"""
    if not WeWorkAccountService.exists(account_id):
        raise HTTPException(status_code=404, detail="企微账户不存在")

    # 权限校验：非超管只能查看自己账户
    if current_admin["data_scope"] != "all" and account_id != current_admin.get("wework_account_id"):
        raise HTTPException(status_code=403, detail="无权查看该账户统计")

    stats = WeWorkAccountService.get_stats(account_id)
    return {"success": True, "data": stats}
