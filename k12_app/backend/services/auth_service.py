# k12_app/services/auth_service.py
"""
认证服务 — JWT 签发/验证 + bcrypt 密码校验
V3.2: JWT payload 含 binding_status
"""

import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any

import bcrypt
import jwt
from fastapi import HTTPException, Request
from fastapi.security import HTTPBearer

from k12_app.backend.config import settings
from k12_app.backend.cache.redis_client import redis_client
from k12_app.backend.dao.employee_dao import EmployeeDAO
from k12_app.backend.dao.role_dao import RoleDAO

JWT_SECRET_KEY = settings.JWT_SECRET_KEY
JWT_EXPIRE_MINUTES = settings.JWT_EXPIRE_MINUTES

# 登录失败锁定（5.13）：连续失败 ≥5 次锁定 15 分钟
LOGIN_MAX_ATTEMPTS = 5
LOGIN_LOCK_SECONDS = 15 * 60
LOGIN_FAIL_TTL_SECONDS = 15 * 60


def _fail_key(user_id: str) -> str:
    return f"login_fail:{user_id}"


def _lock_key(user_id: str) -> str:
    return f"login_lock:{user_id}"


def _is_locked(user_id: str) -> bool:
    """账户是否处于锁定状态"""
    return bool(redis_client.exists(_lock_key(user_id)))


def _register_failure(user_id: str) -> None:
    """记录一次登录失败，达到阈值时锁定账户"""
    count = redis_client.incr(_fail_key(user_id))
    if count == 1:
        redis_client.expire(_fail_key(user_id), LOGIN_FAIL_TTL_SECONDS)
    if count >= LOGIN_MAX_ATTEMPTS:
        redis_client.setex(_lock_key(user_id), LOGIN_LOCK_SECONDS, "1")
        redis_client.delete(_fail_key(user_id))


def _reset_failures(user_id: str) -> None:
    """登录成功后清除失败计数"""
    redis_client.delete(_fail_key(user_id))


# ============================================================
# 核心认证函数
# ============================================================

def login(user_id: str, password: str) -> Optional[Dict[str, Any]]:
    """
    用户登录

    Args:
        user_id: 员工 ID（企微 user_id）
        password: 明文密码

    Returns:
        成功返回字典包含 token, user_id, name, binding_status, data_scope, role_codes
        失败返回 None
        账户锁定抛出 HTTPException(423)
    """
    # 0. 检查账户锁定状态（5.13）
    if _is_locked(user_id):
        raise HTTPException(status_code=423, detail="登录失败次数过多，账户已锁定，请 15 分钟后再试")

    # 1. 查询员工
    employee = EmployeeDAO.get_by_user_id(user_id)
    if not employee:
        return None

    # 2. 验证密码 (bcrypt)
    stored_hash = employee.get("password_hash")
    if not stored_hash:
        return None
    if not bcrypt.checkpw(password.encode('utf-8'), stored_hash.encode('utf-8')):
        _register_failure(user_id)
        return None

    # 登录成功，清除失败计数
    _reset_failures(user_id)

    # 3. 获取角色
    roles = RoleDAO.get_user_roles(user_id)
    role_codes = [r["role_code"] for r in roles]

    # 4. 计算最大 data_scope
    max_scope = RoleDAO.get_max_data_scope(user_id)

    # 5. 获取绑定状态
    binding_status = employee.get("binding_status", "unbound")
    wework_account_id = employee.get("wework_account_id")

    # 6. 签发 JWT
    payload = {
        "user_id": user_id,
        "name": employee["name"],
        "wework_account_id": wework_account_id,
        "binding_status": binding_status,
        "data_scope": max_scope,
        "role_codes": role_codes,
        "org_id": employee.get("org_id"),
        "exp": datetime.now(timezone.utc) + timedelta(minutes=JWT_EXPIRE_MINUTES),
        "iat": datetime.now(timezone.utc),
        "jti": uuid.uuid4().hex,
    }
    token = jwt.encode(payload, JWT_SECRET_KEY, algorithm="HS256")

    return {
        "token": token,
        "user_id": user_id,
        "name": employee["name"],
        "wework_account_id": wework_account_id,
        "binding_status": binding_status,
        "data_scope": max_scope,
        "role_codes": role_codes,
    }


def verify_token(token: str) -> Optional[Dict[str, Any]]:
    """
    验证 JWT Token

    Args:
        token: JWT 字符串

    Returns:
        成功返回 payload，失败返回 None（签名无效/过期/黑名单）
    """
    # 1. 解码验证签名和过期
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None

    # 2. 检查黑名单
    jti = payload.get("jti")
    if jti and redis_client.exists(f"blacklist:{jti}"):
        return None

    return payload


def blacklist_token(jti: str, expire_seconds: Optional[int] = None) -> bool:
    """
    将 Token 加入黑名单（登出时调用）

    Args:
        jti: Token 的唯一标识
        expire_seconds: 黑名单过期时间（秒），默认 JWT_EXPIRE_MINUTES * 60

    Returns:
        是否成功
    """
    if expire_seconds is None:
        expire_seconds = JWT_EXPIRE_MINUTES * 60
    redis_client.setex(f"blacklist:{jti}", expire_seconds, "1")
    return True


# ============================================================
# FastAPI 依赖注入
# ============================================================

security = HTTPBearer()

async def get_current_user(request: Request) -> Dict[str, Any]:
    """
    依赖注入：从 Authorization Header 获取并验证 JWT

    Raises:
        HTTPException 401: 认证失败

    Returns:
        JWT payload
    """
    auth_header = request.headers.get("Authorization")
    if not auth_header:
        raise HTTPException(status_code=401, detail="未提供认证信息")

    parts = auth_header.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(status_code=401, detail="认证格式错误，应为 'Bearer <token>'")

    token = parts[1]
    payload = verify_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="认证失效或过期，请重新登录")

    return payload


async def get_admin_session(request: Request) -> Dict[str, Any]:
    """
    依赖注入：管理后台 Session 认证 + 空闲超时检测（Q-01 / 5.14）

    - 未登录 → 401
    - 30 分钟无操作 → 清空会话并 401（要求重新登录）
    - 每次访问刷新 last_activity，实现滑动超时
    """
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="未登录")

    # 空闲超时检测
    now = datetime.now(timezone.utc).timestamp()
    last_activity = request.session.get("_last_activity")
    if last_activity and (now - last_activity) > settings.SESSION_IDLE_TIMEOUT_MINUTES * 60:
        request.session.clear()
        raise HTTPException(status_code=401, detail="会话已超时，请重新登录")
    request.session["_last_activity"] = now

    return {
        "user_id": user_id,
        "name": request.session.get("name"),
        "data_scope": request.session.get("data_scope", "self"),
        "role_codes": request.session.get("role_codes", []),
        "wework_account_id": request.session.get("wework_account_id"),
    }