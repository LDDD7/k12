"""
K12 用户画像推荐系统 — 模块化分层单体应用入口
FastAPI 应用，统一注册 sidebar / admin / rag 三组路由

架构层次：routes/ → services/ → agent/ | dao/ | rag/
详见系统设计文档 三、整体架构 + 十三、项目目录结构
"""
# k12_app/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from starlette.middleware.sessions import SessionMiddleware
from pathlib import Path

from k12_app.backend.config import settings
from k12_app.backend.middleware.rate_limit import RateLimitMiddleware
from k12_app.backend.routes.sidebar import auth as sidebar_auth
from k12_app.backend.routes.sidebar import chat as sidebar_chat
from k12_app.backend.routes.sidebar import interrupt as sidebar_interrupt
from k12_app.backend.routes.sidebar import customer as sidebar_customer
from k12_app.backend.routes.sidebar import preferences as sidebar_preferences
from k12_app.backend.routes.sidebar import stream as sidebar_stream
from k12_app.backend.routes.admin import auth as admin_auth
from k12_app.backend.routes.admin import employees as admin_employees
from k12_app.backend.routes.admin import customers as admin_customers
from k12_app.backend.routes.admin import orders as admin_orders
from k12_app.backend.routes.admin import tags as admin_tags
from k12_app.backend.routes.admin import dashboard as admin_dashboard
from k12_app.backend.routes.admin import follow_ups as admin_follow_ups
from k12_app.backend.routes.admin import organizations as admin_orgs
from k12_app.backend.routes.admin import roles as admin_roles
from k12_app.backend.routes.admin import wework_accounts as admin_wework
from k12_app.backend.routes.rag import admin as rag_admin
from k12_app.backend.routes.rag import search as rag_search

app = FastAPI(
    title="擎天学智 K12 用户画像推荐系统",
    description="AI 智能销售辅助系统",
    version="3.2",
)

# CORS（S-02：收紧为显式配置的来源列表，默认不允许跨域）
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Session 中间件（管理后台）
if settings.ENV == "production":
    # 生产环境可设置 secure=True（需要 HTTPS）
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.SESSION_SECRET_KEY,
        session_cookie="k12_admin_session",
        max_age=settings.SESSION_IDLE_TIMEOUT_MINUTES * 60,
        same_site="lax",
        httponly=True,
        secure=True,
    )
else:
    # 开发环境
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.SESSION_SECRET_KEY,
        max_age=settings.SESSION_IDLE_TIMEOUT_MINUTES * 60,
    )

# 限流中间件
app.add_middleware(RateLimitMiddleware)

# 注册路由
app.include_router(sidebar_auth.router, prefix="/api/sidebar", tags=["侧边栏认证"])
app.include_router(sidebar_chat.router, prefix="/api/sidebar", tags=["侧边栏聊天"])
app.include_router(sidebar_interrupt.router, prefix="/api/sidebar", tags=["侧边栏中断"])
app.include_router(sidebar_customer.router, prefix="/api/sidebar", tags=["侧边栏客户数据"])
app.include_router(sidebar_preferences.router, prefix="/api/sidebar", tags=["侧边栏偏好"])
app.include_router(sidebar_stream.router, prefix="/api/sidebar", tags=["侧边栏实时推送"])
app.include_router(admin_auth.router, prefix="/api/admin", tags=["管理后台认证"])
app.include_router(admin_employees.router, prefix="/api/admin", tags=["管理后台员工"])
app.include_router(admin_customers.router, prefix="/api/admin", tags=["管理后台客户"])
app.include_router(admin_orders.router, prefix="/api/admin", tags=["管理后台订单"])
app.include_router(admin_tags.router, prefix="/api/admin", tags=["管理后台标签"])
app.include_router(admin_dashboard.router, prefix="/api/admin", tags=["管理后台看板"])
app.include_router(admin_follow_ups.router, prefix="/api/admin", tags=["管理后台跟进"])
app.include_router(admin_orgs.router, prefix="/api/admin", tags=["管理后台组织"])
app.include_router(admin_roles.router, prefix="/api/admin", tags=["管理后台角色"])
app.include_router(admin_wework.router, prefix="/api/admin", tags=["管理后台企微"])
app.include_router(rag_admin.router, prefix="/api/rag/admin", tags=["RAG索引管理"])
app.include_router(rag_search.router, prefix="/api/rag", tags=["RAG知识检索"])

@app.get("/api/health")
async def health():
    return {"status": "ok"}


# ============================================================
# 静态前端服务（侧边栏 + 管理后台）
# 部署后：
#   /          → 入口选择页
#   /sidebar   → 侧边栏前端（企微 iframe 360px）
#   /admin     → 管理后台前端
#   /static/... → 共享静态资源
# ============================================================
_STATIC_DIR = Path(__file__).parent.parent / "frontend" / "static"
if _STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")


@app.get("/")
async def index_root():
    """入口选择页（侧边栏 / 管理后台）"""
    return FileResponse(str(_STATIC_DIR / "index.html"))


@app.get("/sidebar")
async def serve_sidebar():
    return FileResponse(str(_STATIC_DIR / "sidebar" / "index.html"))


@app.get("/admin")
async def serve_admin():
    return FileResponse(str(_STATIC_DIR / "admin" / "index.html"))