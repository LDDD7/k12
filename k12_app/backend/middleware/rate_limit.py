"""
请求限流中间件 — Redis 滑动窗口计数器
缓存键格式：ratelimit:{api}:{ip/user_id}:{minute}

限流策略：
┌──────────────────────────┬────────────┬───────────────┬──────────────┐
│ 接口                     │ 限流维度   │ 限制          │ 超限返回     │
├──────────────────────────┼────────────┼───────────────┼──────────────┤
│ /api/sidebar/login       │ IP         │ 每分钟 5 次   │ 429          │
│ /api/sidebar/send_message│ user_id    │ 每分钟 10 次  │ 429 + 提示   │
│ /api/sidebar/get_interrupt│ user_id   │ 每秒 1 次     │ 429          │
│ /api/sidebar/confirm_interrupt│ user_id│ 每秒 3 次    │ 429          │
└──────────────────────────┴────────────┴───────────────┴──────────────┘
详见接口设计文档 3.9 请求限流策略
"""

from fastapi import Request
from starlette.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from k12_app.backend.cache.redis_client import redis_async_client
from k12_app.backend.services.auth_service import verify_token


class RateLimitMiddleware(BaseHTTPMiddleware):
    """限流中间件"""

    def __init__(self, app):
        super().__init__(app)
        # 限流规则: {路径前缀: (限流键类型, 限制次数, 窗口秒数)}
        self.limits = {
            "/api/sidebar/login": ("ip", 5, 60),           # IP 每分钟 5 次
            "/api/sidebar/send_message": ("user", 10, 60), # 用户每分钟 10 次
            "/api/sidebar/get_interrupt": ("user", 1, 1),  # 用户每秒 1 次
            "/api/sidebar/confirm_interrupt": ("user", 3, 1), # 用户每秒 3 次
        }

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # 检查是否匹配限流规则
        limit_config = None
        for prefix, config in self.limits.items():
            if path.startswith(prefix):
                limit_config = config
                break

        if limit_config:
            key_type, limit, window = limit_config

            # 获取限流键值
            if key_type == "ip":
                client_ip = request.client.host if request.client else "unknown"
                key = f"ratelimit:{path}:{client_ip}"
            else:  # user
                # 从 JWT 提取 user_id（如果有）
                auth_header = request.headers.get("Authorization")
                user_id = "anonymous"
                if auth_header and auth_header.startswith("Bearer "):
                    token = auth_header.split(" ")[1]
                    payload = verify_token(token)
                    if payload:
                        user_id = payload.get("user_id", "anonymous")
                key = f"ratelimit:{path}:{user_id}"

            # 检查限流
            count = await redis_async_client.incr(key)
            if count == 1:
                await redis_async_client.expire(key, window)

            if count > limit:
                # 中间件内不能 raise HTTPException（会被 ServerErrorMiddleware 兜底为 500），
                # 需直接构造 429 响应返回
                return JSONResponse(
                    status_code=429,
                    content={"detail": f"请求过于频繁，请稍后再试 (限制: {limit}次/{window}秒)"},
                )

        return await call_next(request)