# k12_app/routes/admin/roles.py
"""管理后台 — 角色与权限管理"""

from fastapi import APIRouter, Request, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional

from k12_app.backend.services.role_service import RoleService
from k12_app.backend.dao.role_dao import RoleDAO

from k12_app.backend.services.auth_service import get_admin_session

router = APIRouter()


class AssignRoleRequest(BaseModel):
    user_id: str
    role_code: str
    wework_account_id: Optional[str] = "*"


@router.get("/roles")
async def list_roles(current_admin: dict = Depends(get_admin_session)):
    """获取角色列表"""
    roles = RoleService.get_all_roles()
    return {"success": True, "data": roles}


@router.get("/user_roles/{user_id}")
async def get_user_roles(
    user_id: str,
    current_admin: dict = Depends(get_admin_session),
):
    """查询指定员工的角色分配"""
    roles = RoleService.get_user_roles(user_id)
    return {"success": True, "data": roles}


@router.post("/user_roles")
async def assign_role(
    req: AssignRoleRequest,
    current_admin: dict = Depends(get_admin_session),
):
    """分配/修改用户角色（仅超级管理员）"""
    if not RoleDAO.is_super_admin(current_admin["user_id"]):
        raise HTTPException(status_code=403, detail="仅超级管理员可分配角色")
    try:
        success = RoleService.assign_role(
            user_id=req.user_id,
            role_code=req.role_code,
            wework_account_id=req.wework_account_id or "*",
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not success:
        raise HTTPException(status_code=500, detail="角色分配失败")
    return {"success": True, "message": "角色分配成功"}


@router.delete("/user_roles/{user_id}/{role_code}")
async def remove_role(
    user_id: str,
    role_code: str,
    current_admin: dict = Depends(get_admin_session),
):
    """移除用户角色（仅超级管理员）"""
    if not RoleDAO.is_super_admin(current_admin["user_id"]):
        raise HTTPException(status_code=403, detail="仅超级管理员可移除角色")
    if user_id == current_admin["user_id"] and role_code == RoleDAO.SUPER_ADMIN:
        raise HTTPException(status_code=403, detail="不能移除自己的超级管理员权限")
    if not RoleService.remove_role(user_id, role_code):
        raise HTTPException(status_code=404, detail="该用户没有此角色")
    return {"success": True, "message": "角色已移除"}
