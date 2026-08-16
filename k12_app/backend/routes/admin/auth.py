"""
管理后台认证路由 — Session 认证
POST /api/admin/login — 管理员登录
"""

from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel
from k12_app.backend.services.auth_service import login
from k12_app.backend.services.role_service import RoleService

router = APIRouter()


class AdminLoginRequest(BaseModel):
    username: str
    password: str


@router.post("/login")
async def admin_login(req: AdminLoginRequest, request: Request):
    result = login(req.username, req.password)
    if not result:
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    roles = RoleService.get_user_roles(req.username)
    if not roles:
        raise HTTPException(status_code=403, detail="无管理后台权限")

    request.session["user_id"] = result["user_id"]
    request.session["name"] = result["name"]
    request.session["data_scope"] = result["data_scope"]
    request.session["role_codes"] = result["role_codes"]
    request.session["wework_account_id"] = result.get("wework_account_id")
    request.session["binding_status"] = result.get("binding_status")

    return {
        "success": True,
        "data": {
            "user_id": result["user_id"],
            "name": result["name"],
            "data_scope": result["data_scope"],
            "role_codes": result["role_codes"],
        }
    }


@router.post("/logout")
async def admin_logout(request: Request):
    """登出"""
    request.session.clear()
    return {"success": True}


@router.get("/me")
async def get_current_admin(request: Request):
    """获取当前登录管理员信息"""
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="未登录")
    return {
        "success": True,
        "data": {
            "user_id": user_id,
            "name": request.session.get("name"),
            "data_scope": request.session.get("data_scope"),
            "role_codes": request.session.get("role_codes", []),
        }
    }
