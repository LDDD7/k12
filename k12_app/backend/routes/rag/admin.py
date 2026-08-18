"""
RAG 索引管理路由
POST /api/rag/admin/reindex          — 重建索引（可指定 kb_name，默认全部）
POST /api/rag/admin/reindex_profiles — 重建画像索引（V3.1）
GET  /api/rag/admin/status           — 索引状态（9 个 Collection，V3.3 含 company/classes/awards）
资料库托管文档管理（V3.3 二期；doc_key 含 / 不适合放 URL 路径，统一用数字 id）：
GET  /api/rag/admin/docs               — 文档列表
POST /api/rag/admin/docs               — 新增文档（草稿）
PUT  /api/rag/admin/docs/{doc_id}      — 替换文档内容（版本 +1，回退草稿）
POST /api/rag/admin/docs/{doc_id}/review  — 提交审核/审核通过
POST /api/rag/admin/docs/{doc_id}/publish — 一键发布（重建索引生效）
DELETE /api/rag/admin/docs/{doc_id}    — 归档/删除
"""
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, field_validator

from k12_app.backend.rag.index_builder import (
    reindex_kb, reindex_all, reindex_profiles, reindex_chat_messages, get_reindex_status,
)
from k12_app.backend.dao.rag_dao import RAGDAO
from k12_app.backend.services.auth_service import get_admin_session

logger = logging.getLogger(__name__)
router = APIRouter()

# V3.3：新增 company / classes / awards
ALLOWED_KB = {
    "scripts", "sops", "faqs", "cases", "customer_profiles", "chat_messages",
    "company", "classes", "awards",
}


class ReindexRequest(BaseModel):
    kb_name: Optional[str] = None  # 不传则重建全部
    force: bool = False

    @field_validator("kb_name")
    @classmethod
    def validate_kb(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in ALLOWED_KB:
            raise ValueError(f"无效的 kb_name: {v}，允许值: {ALLOWED_KB}")
        return v


@router.post("/reindex")
async def reindex(
    req: ReindexRequest,
    current_admin: dict = Depends(get_admin_session),
):
    """
    重建知识库索引。

    - 默认仅超管和区域主管可操作
    - 不传 kb_name 则重建全部 7 个知识库（V3.3：含 company/classes/awards）
    - force=true 删除旧 Collection 后全量重建
    """
    if current_admin["data_scope"] == "self":
        raise HTTPException(status_code=403, detail="仅管理员可操作索引重建")

    triggered_by = current_admin["user_id"]

    if req.kb_name:
        if req.kb_name == "customer_profiles":
            result = reindex_profiles(triggered_by=triggered_by, force=req.force)
        elif req.kb_name == "chat_messages":
            result = reindex_chat_messages(triggered_by=triggered_by, force=req.force)
        else:
            result = reindex_kb(req.kb_name, triggered_by=triggered_by, force=req.force)
    else:
        result = reindex_all(triggered_by=triggered_by, force=req.force)

    return {"success": True, "data": result}


@router.post("/reindex_profiles")
async def reindex_profiles_endpoint(
    current_admin: dict = Depends(get_admin_session),
):
    """
    重建画像向量索引（V3.1）。

    将已确认的客户画像批量向量化，写入 k12_customer_profiles Collection。
    """
    if current_admin["data_scope"] == "self":
        raise HTTPException(status_code=403, detail="仅管理员可操作索引重建")

    result = reindex_profiles(triggered_by=current_admin["user_id"])
    return {"success": True, "data": result}


class ReindexChatRequest(BaseModel):
    days: int = 7
    limit: int = 1000
    force: bool = False
    adopted_only: bool = False
    incremental: bool = True

    @field_validator("days")
    @classmethod
    def validate_days(cls, v: int) -> int:
        if v < 1 or v > 90:
            raise ValueError("days 取值范围 1-90")
        return v

    @field_validator("limit")
    @classmethod
    def validate_limit(cls, v: int) -> int:
        if v < 1 or v > 10000:
            raise ValueError("limit 取值范围 1-10000")
        return v


@router.post("/reindex_chat")
async def reindex_chat_endpoint(
    req: ReindexChatRequest,
    current_admin: dict = Depends(get_admin_session),
):
    """
    重建聊天记录向量索引。

    从 msg_wxqy_chat 表读取文本消息，逐条 Embedding 后写入 k12_chat_messages Collection。

    - days: 全量模式下的索引天数（默认 7）
    - limit: 单次最大索引条数（默认 1000）
    - force: 强制全量重建（忽略增量）
    - adopted_only: 仅索引被 AI 采纳过的回复对应的会话消息（默认 false）
    - incremental: 增量模式，仅索引上次同步后的新消息（默认 true）
    """
    if current_admin["data_scope"] == "self":
        raise HTTPException(status_code=403, detail="仅管理员可操作索引重建")

    result = reindex_chat_messages(
        days=req.days,
        limit=req.limit,
        triggered_by=current_admin["user_id"],
        force=req.force,
        adopted_only=req.adopted_only,
        incremental=req.incremental,
    )
    return {"success": True, "data": result}


@router.get("/status")
async def index_status(current_admin: dict = Depends(get_admin_session)):
    """
    获取所有知识库的索引状态。

    返回 6 个 Collection 各自的 doc_count / total_chunks / last_indexed_at。
    """
    stats = get_reindex_status()
    return {"success": True, "data": stats}


# ============================================================
# 资料库托管文档管理（V3.3 二期：运营自助上传/替换/审核/一键生效）
# ============================================================

MANAGED_KB_NAMES = RAGDAO.MANAGED_KB_NAMES


class ManagedDocRequest(BaseModel):
    kb_name: str
    title: str
    content: str
    doc_status: str = "draft"

    @field_validator("kb_name")
    @classmethod
    def validate_kb(cls, v: str) -> str:
        if v not in MANAGED_KB_NAMES:
            raise ValueError(f"无效的 kb_name: {v}，允许值: {MANAGED_KB_NAMES}")
        return v

    @field_validator("title")
    @classmethod
    def validate_title(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("title 不能为空")
        if len(v) > 128:
            raise ValueError("title 长度不能超过 128")
        return v

    @field_validator("content")
    @classmethod
    def validate_content(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("content 不能为空")
        if len(v) > 20000:
            raise ValueError("content 长度不能超过 20000 字符")
        return v

    @field_validator("doc_status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        if v not in RAGDAO.DOC_STATUSES:
            raise ValueError(f"无效的 doc_status: {v}")
        return v


class ReviewRequest(BaseModel):
    approved: bool = True
    review_comment: Optional[str] = None


def _require_admin(current_admin: dict) -> None:
    if current_admin["data_scope"] == "self":
        raise HTTPException(status_code=403, detail="仅管理员可操作资料库管理")


def _notify_advisors(doc_title: str, kb_name: str) -> None:
    """资料库更新后推送通知给已绑定顾问（best-effort，失败不影响发布；Mock 模式零网络）"""
    import threading
    from concurrent.futures import ThreadPoolExecutor

    def _do_notify():
        try:
            from k12_app.backend.dao.employee_dao import EmployeeDAO
            from k12_app.backend.agent.tools.wechat_tool import send_notify

            advisors = EmployeeDAO.get_by_binding_status("bound") or []
            notified = 0
            for emp in advisors:
                account_id = emp.get("wework_account_id")
                if not account_id:
                    continue
                try:
                    send_notify(
                        account_id,
                        emp["user_id"],
                        f"【资料库更新】{doc_title}（{kb_name}）已发布生效，可在 AI 侧边栏直接使用新资料。",
                        msg_type="text",
                    )
                    notified += 1
                except Exception:
                    continue
            logger.info(f"资料库更新通知完成: {doc_title}, notified={notified}/{len(advisors)}")
        except Exception as e:
            logger.warning(f"资料库更新通知失败: {e}")

    try:
        threading.Thread(target=_do_notify, daemon=True).start()
    except Exception as e:
        logger.warning(f"启动资料库更新通知线程失败: {e}")


@router.get("/docs")
async def list_managed_docs(
    kb_name: Optional[str] = None,
    doc_status: Optional[str] = None,
    page: int = 1,
    page_size: int = 50,
    current_admin: dict = Depends(get_admin_session),
):
    """资料库文档列表（可按知识库类型/状态过滤）"""
    result = RAGDAO.list_managed_docs(
        kb_name=kb_name, doc_status=doc_status, page=page, page_size=page_size
    )
    return {"success": True, "data": result}


@router.post("/docs")
async def create_managed_doc(
    req: ManagedDocRequest,
    current_admin: dict = Depends(get_admin_session),
):
    """新增资料库文档（默认草稿，需审核后发布）"""
    _require_admin(current_admin)
    doc_key = f"{req.kb_name}/{req.title.strip()[:40]}"
    doc = RAGDAO.upsert_managed_doc(
        doc_key=doc_key,
        kb_name=req.kb_name,
        title=req.title,
        content=req.content,
        doc_status=req.doc_status,
        created_by=current_admin["user_id"],
    )
    return {"success": True, "data": doc}


@router.put("/docs/{doc_id}")
async def update_managed_doc(
    doc_id: int,
    req: ManagedDocRequest,
    current_admin: dict = Depends(get_admin_session),
):
    """替换文档内容（版本 +1 并回退草稿，需重新审核发布）"""
    _require_admin(current_admin)
    existing = RAGDAO.get_managed_doc_by_id(doc_id)
    if not existing:
        raise HTTPException(status_code=404, detail="文档不存在")
    doc = RAGDAO.upsert_managed_doc(
        doc_key=existing["doc_key"],
        kb_name=req.kb_name,
        title=req.title,
        content=req.content,
        doc_status="draft",  # 替换后强制回退草稿，走审核流程
        created_by=current_admin["user_id"],
    )
    return {"success": True, "data": doc}


@router.post("/docs/{doc_id}/review")
async def review_managed_doc(
    doc_id: int,
    req: ReviewRequest,
    current_admin: dict = Depends(get_admin_session),
):
    """审核文档：approved=true 通过（进入已发布），false 退回草稿"""
    _require_admin(current_admin)
    existing = RAGDAO.get_managed_doc_by_id(doc_id)
    if not existing:
        raise HTTPException(status_code=404, detail="文档不存在")
    new_status = "published" if req.approved else "draft"
    doc = RAGDAO.update_managed_doc_status(
        doc_key=existing["doc_key"],
        doc_status=new_status,
        reviewed_by=current_admin["user_id"],
        review_comment=req.review_comment,
    )
    # 审核通过即发布 → 重建索引一键生效 + 通知顾问
    if new_status == "published":
        reindex_kb(existing["kb_name"], triggered_by=current_admin["user_id"], force=False)
        _notify_advisors(existing["title"], existing["kb_name"])
    return {"success": True, "data": doc}


@router.post("/docs/{doc_id}/publish")
async def publish_managed_doc(
    doc_id: int,
    current_admin: dict = Depends(get_admin_session),
):
    """一键发布：状态置为已发布并重建索引（秒级生效，无需重启）"""
    _require_admin(current_admin)
    existing = RAGDAO.get_managed_doc_by_id(doc_id)
    if not existing:
        raise HTTPException(status_code=404, detail="文档不存在")
    doc = RAGDAO.update_managed_doc_status(
        doc_key=existing["doc_key"],
        doc_status="published",
        reviewed_by=current_admin["user_id"],
        review_comment="一键发布",
    )
    result = reindex_kb(existing["kb_name"], triggered_by=current_admin["user_id"], force=False)
    # 发布后推送通知顾问（异步 best-effort）
    _notify_advisors(existing["title"], existing["kb_name"])
    return {"success": True, "data": {"doc": doc, "reindex": result}}


@router.delete("/docs/{doc_id}")
async def delete_managed_doc(
    doc_id: int,
    current_admin: dict = Depends(get_admin_session),
):
    """删除文档（同时重建该知识库索引移除向量）"""
    _require_admin(current_admin)
    existing = RAGDAO.get_managed_doc_by_id(doc_id)
    if not existing:
        raise HTTPException(status_code=404, detail="文档不存在")
    RAGDAO.delete_managed_doc(existing["doc_key"])
    reindex_kb(existing["kb_name"], triggered_by=current_admin["user_id"], force=False)
    return {"success": True, "message": "文档已删除"}
