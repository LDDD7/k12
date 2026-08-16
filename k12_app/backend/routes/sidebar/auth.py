"""
侧边栏认证路由 — JWT Token 认证
POST /api/sidebar/login  — 用户名+密码登录，返回 JWT（V3.2: 含 binding_status: unbound/bound）
POST /api/sidebar/logout — 登出
GET  /api/sidebar/health — 健康检查
详见接口设计文档 三、侧边栏服务接口 (V3.2)
"""
# k12_app/routes/sidebar/auth.py
"""侧边栏认证路由 — JWT 登录/登出/健康检查"""

from fastapi import APIRouter, HTTPException, Request, Depends
from pydantic import BaseModel
from typing import Optional

from k12_app.backend.services.auth_service import login, verify_token, blacklist_token

router = APIRouter()


class LoginRequest(BaseModel):
    user_id: str
    password: str


class LoginResponse(BaseModel):
    success: bool
    token: Optional[str] = None
    user_id: Optional[str] = None
    name: Optional[str] = None
    binding_status: Optional[str] = None
    wework_account_id: Optional[str] = None
    data_scope: Optional[str] = None
    role_codes: Optional[list] = None
    detail: Optional[str] = None


@router.post("/login", response_model=LoginResponse)
async def login_handler(req: LoginRequest):
    """
    侧边栏登录接口
    返回 JWT token（含 binding_status）+ 当前用户权限信息
    """
    result = login(req.user_id, req.password)
    if not result:
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    return LoginResponse(
        success=True,
        token=result["token"],
        user_id=result["user_id"],
        name=result["name"],
        binding_status=result["binding_status"],
        wework_account_id=result.get("wework_account_id"),
        data_scope=result.get("data_scope"),
        role_codes=result.get("role_codes", []),
    )


@router.post("/logout")
async def logout_handler(request: Request):
    """
    登出接口：将当前 JWT 加入黑名单
    """
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split(" ")[1]
        payload = verify_token(token)
        if payload and payload.get("jti"):
            blacklist_token(payload["jti"])
    return {"success": True}


@router.get("/health")
async def health_check():
    """健康检查"""
    return {"status": "healthy"}