# k12_app/routes/admin/organizations.py
"""管理后台 — 组织架构管理"""

from fastapi import APIRouter, Request, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional

from k12_app.backend.services.organization_service import OrganizationService

from k12_app.backend.services.auth_service import get_admin_session

router = APIRouter()


class OrgCreateRequest(BaseModel):
    org_id: str
    org_name: str
    org_type: str
    wework_account_id: str
    parent_org_id: Optional[str] = None
    sort_order: int = 0


@router.get("/organizations")
async def get_organization_tree(current_admin: dict = Depends(get_admin_session)):
    """获取组织架构树（按企微账户分组）"""
    orgs = OrganizationService.get_tree(
        user_id=current_admin["user_id"],
        data_scope=current_admin["data_scope"],
        wework_account_id=current_admin.get("wework_account_id"),
    )
    return {"success": True, "data": orgs}


@router.post("/organizations")
async def create_organization(
    req: OrgCreateRequest,
    current_admin: dict = Depends(get_admin_session),
):
    """新增组织节点"""
    # 权限校验：仅超管和区域主管可操作
    if current_admin["data_scope"] == "self":
        raise HTTPException(status_code=403, detail="无权操作组织架构")

    success = OrganizationService.create(
        org_id=req.org_id,
        org_name=req.org_name,
        org_type=req.org_type,
        wework_account_id=req.wework_account_id,
        parent_org_id=req.parent_org_id,
        sort_order=req.sort_order,
    )
    if not success:
        raise HTTPException(status_code=500, detail="创建组织节点失败")
    return {"success": True, "message": "组织节点创建成功"}
