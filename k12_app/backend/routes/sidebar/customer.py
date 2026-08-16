# k12_app/routes/sidebar/customer.py
"""
侧边栏客户数据辅助端点（JWT 认证）
用于前端在切换会话时独立拉取会话列表 / 聊天历史 / 画像 / 标签 / 日程，
无需走 send_message 的 SSE 通道。
"""

import asyncio
import logging
import uuid
from typing import List, Optional, Dict, Any
from datetime import datetime, date

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from k12_app.backend.services.auth_service import get_current_user
from k12_app.backend.services.customer_service import CustomerService
from k12_app.backend.services.message_service import MessageService
from k12_app.backend.services.profile_service import ProfileService
from k12_app.backend.services.schedule_service import ScheduleService
from k12_app.backend.services.tag_service import TagService
from k12_app.backend.services.reply_service import generate_reply_suggestions, simulate_parent_reply

router = APIRouter()

logger = logging.getLogger(__name__)


# ============================================================
# 1. 会话列表：按当前登录用户权限返回客户会话
# ============================================================
@router.get("/customers")
async def list_chat_contacts(
    keyword: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
):
    """
    返回侧边栏「客户会话」列表，含每个客户最近一条聊天预览与时间。
    权限模型：
      - data_scope=self   → 仅本人名下客户
      - data_scope=region → 本区域所有账户的客户
      - data_scope=all    → 全部客户
    """
    user_id = current_user["user_id"]
    data_scope = current_user.get("data_scope", "self")
    wework_account_id = current_user.get("wework_account_id")

    # 未绑定员工无任何客户访问权限
    if current_user.get("binding_status") == "unbound":
        raise HTTPException(status_code=403, detail="员工未绑定企微账户，请先绑定")

    if data_scope == "self" and not wework_account_id:
        return {"success": True, "data": []}

    # 调用 CustomerService 获取会话列表（按权限自动过滤）
    result = CustomerService.get_list(
        user_id=user_id,
        data_scope=data_scope,
        wework_account_id=wework_account_id,
        page=1,
        page_size=200,
        keyword=keyword,
    )

    items = result.get("items", [])

    # 为每个客户补一条「最近一条聊天消息预览 + 时间」
    contacts: List[Dict[str, Any]] = []
    for c in items:
        ext = c.get("external_id")
        last_msg = ""
        last_time = None
        try:
            chats = MessageService.get_chat_history_by_external_id(
                external_id=ext,
                user_id=user_id,
                data_scope=data_scope,
                wework_account_id=wework_account_id,
                days=30,
                limit=1,
            )
            if chats:
                last = chats[0]
                last_msg = (last.get("content") or "")[:32]
                last_time = last.get("send_time") or last.get("msg_date")
        except Exception:
            pass

        contacts.append({
            "external_id": ext,
            "name": c.get("name"),
            "child_name": c.get("child_name"),
            "grade": c.get("grade"),
            "focus_subject": c.get("focus_subject"),
            "school": c.get("school"),
            "stage": c.get("stage"),
            "remark": c.get("remark"),
            "wework_account_id": c.get("wework_account_id"),
            "follow_user_id": c.get("follow_user_id"),
            "lead_source": c.get("lead_source"),
            "tag_count": c.get("tag_count", 0),
            "last_msg": last_msg,
            "last_time": last_time,
        })

    return {"success": True, "data": contacts}


# ============================================================
# 2. 单个客户详情（基本信息）
# ============================================================
@router.get("/customer/{external_id}")
async def get_customer(
    external_id: str,
    current_user: dict = Depends(get_current_user),
):
    cust = CustomerService.get_by_external_id(
        external_id=external_id,
        user_id=current_user["user_id"],
        data_scope=current_user.get("data_scope", "self"),
        wework_account_id=current_user.get("wework_account_id"),
    )
    if not cust:
        raise HTTPException(status_code=404, detail="客户不存在或无访问权限")
    return {"success": True, "data": cust}


# ============================================================
# 3. 聊天历史
# ============================================================
@router.get("/chat_history/{external_id}")
async def get_chat_history(
    external_id: str,
    current_user: dict = Depends(get_current_user),
):
    """
    按客户 ID 拉取聊天历史，发送方向依据 sender == 当前 user_id 判定。
    """
    data_scope = current_user.get("data_scope", "self")
    wework_account_id = current_user.get("wework_account_id")

    if current_user.get("binding_status") == "unbound":
        raise HTTPException(status_code=403, detail="员工未绑定企微账户，请先绑定")

    if data_scope == "self" and not wework_account_id:
        return {"success": True, "data": []}

    chats = MessageService.get_chat_history_by_external_id(
        external_id=external_id,
        user_id=current_user["user_id"],
        data_scope=data_scope,
        wework_account_id=wework_account_id,
        days=60,
        limit=200,
    )

    # 按时间正序返回（前端渲染方便）
    chats_sorted = sorted(chats, key=lambda x: x.get("send_time") or x.get("msg_date") or "")
    enriched = []
    for c in chats_sorted:
        # 方向判断：sender==user_id 即右（me/顾问发），否则左（them/客户发）
        advisor_user_id = c.get("user_id")
        is_me = (c.get("sender") == advisor_user_id)
        enriched.append({
            "msg_id": c.get("msg_id"),
            "who": "me" if is_me else "them",
            "advisor_user_id": advisor_user_id,
            "advisor_name": c.get("sender_name") if is_me else c.get("receiver_name"),
            "customer_name": c.get("sender_name") if not is_me else c.get("receiver_name"),
            "msg_type": c.get("msg_type"),
            "content": c.get("content"),
            "msg_date": str(c.get("msg_date") or ""),
            "send_time": str(c.get("send_time") or ""),
        })
    return {"success": True, "data": enriched}


# ============================================================
# 4. 客户画像（+ 字段项）
# ============================================================
@router.get("/customer_profile/{external_id}")
async def get_customer_profile(
    external_id: str,
    current_user: dict = Depends(get_current_user),
):
    data_scope = current_user.get("data_scope", "self")
    wework_account_id = current_user.get("wework_account_id")

    if current_user.get("binding_status") == "unbound":
        raise HTTPException(status_code=403, detail="员工未绑定企微账户，请先绑定")

    profile = ProfileService.get_profile(
        external_id=external_id,
        user_id=current_user["user_id"],
        data_scope=data_scope,
        wework_account_id=wework_account_id,
    )
    if not profile:
        return {"success": True, "data": None}

    items = ProfileService.get_profile_items(profile["id"])
    return {
        "success": True,
        "data": {
            "profile_id": profile["id"],
            "external_id": profile["external_id"],
            "status": profile["status"],
            "confirmed_by": profile.get("confirmed_by"),
            "confirmed_at": str(profile["confirmed_at"]) if profile.get("confirmed_at") else None,
            "embedding_status": profile.get("embedding_status"),
            "items": items,
        },
    }


# ============================================================
# 5. 客户标签（已确认 + AI 推荐待确认）
# ============================================================
@router.get("/customer_tags/{external_id}")
async def get_customer_tags(
    external_id: str,
    current_user: dict = Depends(get_current_user),
):
    """
    返回客户全部标签记录（已确认 + 待确认）以及全局标签库供前端渲染。
    """
    if current_user.get("binding_status") == "unbound":
        raise HTTPException(status_code=403, detail="员工未绑定企微账户，请先绑定")

    # 已确认 + 待确认的客户标签（经 DAO 三维度权限过滤）
    tags = TagService.get_customer_tags(
        external_id=external_id,
        user_id=current_user["user_id"],
        data_scope=current_user.get("data_scope", "self"),
        wework_account_id=current_user.get("wework_account_id"),
    )

    # 全局标签库（供前端展示 AI 推荐对照参考）
    all_tags = TagService.get_all_tags()
    return {
        "success": True,
        "data": {
            "tags": tags,
            "all_tags": all_tags,
        },
    }


# ============================================================
# 6. 客户日程
# ============================================================
@router.get("/customer_schedules/{external_id}")
async def get_customer_schedules(
    external_id: str,
    current_user: dict = Depends(get_current_user),
):
    data_scope = current_user.get("data_scope", "self")
    wework_account_id = current_user.get("wework_account_id")

    if current_user.get("binding_status") == "unbound":
        raise HTTPException(status_code=403, detail="员工未绑定企微账户，请先绑定")

    if data_scope == "self" and not wework_account_id:
        return {"success": True, "data": []}

    schedules = ScheduleService.get_by_external_id(
        external_id=external_id,
        user_id=current_user["user_id"],
        data_scope=data_scope,
        wework_account_id=wework_account_id,
    )
    # 序列化 datetime
    for s in schedules:
        for k, v in list(s.items()):
            if isinstance(v, (datetime, date)):
                s[k] = v.isoformat()
    return {"success": True, "data": schedules}


# ============================================================
# 6.1 客户日程 AI 识别（走 LangGraph 中断流程）
# ============================================================
@router.post("/customer_schedules/{external_id}/generate")
async def generate_customer_schedules(
    external_id: str,
    current_user: dict = Depends(get_current_user),
):
    """为客户 AI 识别日程（真实 LLM，待顾问确认后生效）"""
    if current_user.get("binding_status") == "unbound":
        raise HTTPException(status_code=403, detail="员工未绑定企微账户，请先绑定")

    cust = CustomerService.get_by_external_id(
        external_id=external_id,
        user_id=current_user["user_id"],
        data_scope=current_user.get("data_scope", "self"),
        wework_account_id=current_user.get("wework_account_id"),
    )
    if not cust:
        raise HTTPException(status_code=404, detail="客户不存在或无访问权限")

    try:
        from k12_app.backend.agent.graphs.k12_graph import run_agent

        # 与 get_interrupt / confirm_interrupt 使用同一线程，保证中断可被轮询与确认
        thread_id = f"interrupt_{current_user['user_id']}"
        wework_account_id = cust.get("wework_account_id") or current_user.get("wework_account_id", "")

        result = await asyncio.to_thread(
            run_agent,
            user_id=current_user["user_id"],
            external_id=external_id,
            wework_account_id=wework_account_id,
            menu_id="schedule_suggestion",
            thread_id=thread_id,
            data_scope=current_user.get("data_scope", "self"),
        )

        task_result = result.get("task_result") or {}
        schedules = task_result.get("data") or []
        interrupt_id = result.get("interrupt_id")

        return {
            "success": True,
            "data": {
                "external_id": external_id,
                "schedules": schedules,
                "interrupt_id": interrupt_id if schedules else None,
                "thread_id": thread_id,
            },
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"识别日程失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"识别日程失败：{str(e)}")


# ============================================================
# 7. 客户标签确认 / 移除
# ============================================================
class TagConfirmRequest(BaseModel):
    tag_id: str
    source: str = "手动"


class ReplyGenerateRequest(BaseModel):
    regenerate: bool = False


@router.post("/customer_tags/{external_id}/confirm")
async def confirm_customer_tag(
    external_id: str,
    req: TagConfirmRequest,
    current_user: dict = Depends(get_current_user),
):
    """确认客户标签（将标签标记为已确认）"""
    if current_user.get("binding_status") == "unbound":
        raise HTTPException(status_code=403, detail="员工未绑定企微账户，请先绑定")

    success = CustomerService.add_tag(
        external_id=external_id,
        tag_id=req.tag_id,
        source=req.source,
        confirmed=True,
        confirmed_by=current_user["user_id"],
    )
    if not success:
        raise HTTPException(status_code=500, detail="确认标签失败")
    return {"success": True, "message": "标签已确认"}


@router.delete("/customer_tags/{external_id}/{tag_id}")
async def remove_customer_tag(
    external_id: str,
    tag_id: str,
    current_user: dict = Depends(get_current_user),
):
    """移除客户标签"""
    if current_user.get("binding_status") == "unbound":
        raise HTTPException(status_code=403, detail="员工未绑定企微账户，请先绑定")

    success = CustomerService.remove_tag(external_id=external_id, tag_id=tag_id)
    if not success:
        raise HTTPException(status_code=404, detail="标签不存在或已移除")
    return {"success": True, "message": "标签已移除"}


# ============================================================
# 8. 客户画像生成（走 LangGraph 中断流程）
# ============================================================
@router.post("/customer_profile/{external_id}/generate")
async def generate_customer_profile(
    external_id: str,
    current_user: dict = Depends(get_current_user),
):
    """为客户生成/重新生成 AI 画像（真实 LLM，待顾问确认后生效）"""
    if current_user.get("binding_status") == "unbound":
        raise HTTPException(status_code=403, detail="员工未绑定企微账户，请先绑定")

    # 查客户信息
    cust = CustomerService.get_by_external_id(
        external_id=external_id,
        user_id=current_user["user_id"],
        data_scope=current_user.get("data_scope", "self"),
        wework_account_id=current_user.get("wework_account_id"),
    )
    if not cust:
        raise HTTPException(status_code=404, detail="客户不存在或无访问权限")

    try:
        from k12_app.backend.agent.graphs.k12_graph import run_agent

        # 与 get_interrupt / confirm_interrupt 使用同一线程，保证中断可被轮询与确认
        thread_id = f"interrupt_{current_user['user_id']}"
        wework_account_id = cust.get("wework_account_id") or current_user.get("wework_account_id", "")

        # 走 LangGraph 中断流程：生成真实 LLM 画像 → 在 interrupt 节点暂停等待确认
        result = await asyncio.to_thread(
            run_agent,
            user_id=current_user["user_id"],
            external_id=external_id,
            wework_account_id=wework_account_id,
            menu_id="profile_suggestion",
            thread_id=thread_id,
            data_scope=current_user.get("data_scope", "self"),
        )

        task_result = result.get("task_result") or {}
        items = task_result.get("data") or []
        interrupt_id = result.get("interrupt_id")

        if not items:
            raise HTTPException(status_code=500, detail="AI 未能生成有效画像，请稍后重试")

        return {
            "success": True,
            "data": {
                "external_id": external_id,
                "status": "待确认",
                "follow_user_id": cust.get("follow_user_id") or current_user["user_id"],
                "items": items,
                "interrupt_id": interrupt_id,
                "thread_id": thread_id,
            },
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"生成画像失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"生成画像失败：{str(e)}")


# ============================================================
# 9. AI 回复建议生成
# ============================================================
@router.post("/generate_replies/{external_id}")
async def generate_replies(
    external_id: str,
    req: ReplyGenerateRequest = ReplyGenerateRequest(),
    current_user: dict = Depends(get_current_user),
):
    """为客户生成AI回复建议（LLM 优先，模板后备）"""
    if current_user.get("binding_status") == "unbound":
        raise HTTPException(status_code=403, detail="员工未绑定企微账户，请先绑定")

    cust = CustomerService.get_by_external_id(
        external_id=external_id,
        user_id=current_user["user_id"],
        data_scope=current_user.get("data_scope", "self"),
        wework_account_id=current_user.get("wework_account_id"),
    )
    if not cust:
        raise HTTPException(status_code=404, detail="客户不存在或无访问权限")

    chat_seed = ""
    recent_chat = []
    try:
        chats = MessageService.get_chat_history_by_external_id(
            external_id=external_id,
            user_id=current_user["user_id"],
            data_scope=current_user.get("data_scope", "self"),
            wework_account_id=current_user.get("wework_account_id"),
            days=30,
            limit=15,
        )
        if chats:
            customer_name = cust.get("name") or ""
            recent_chat = [
                {"role": "parent" if c.get("sender_name") == customer_name else "advisor",
                 "content": c.get("content", "")}
                for c in chats[-15:]
            ]
            chat_seed = "|".join([(c.get("content") or "")[:50] for c in chats[-5:]])
    except Exception:
        pass

    replies = await asyncio.to_thread(
        generate_reply_suggestions,
        cust=cust,
        recent_chat=recent_chat,
        chat_seed=chat_seed,
        regenerate=req.regenerate,
        external_id=external_id,
        user_id=current_user["user_id"],
    )
    return {"success": True, "data": {"replies": replies}}


class SimulateParentRequest(BaseModel):
    external_id: str
    messages: Optional[List[dict]] = None


@router.post("/simulate_parent")
async def simulate_parent(
    req: SimulateParentRequest,
    current_user: dict = Depends(get_current_user),
):
    """AI 模拟家长回复（演示用，不连接真实企微）"""
    cust = CustomerService.get_by_external_id(
        external_id=req.external_id,
        user_id=current_user["user_id"],
        data_scope=current_user.get("data_scope", "self"),
        wework_account_id=current_user.get("wework_account_id"),
    )
    if not cust:
        raise HTTPException(status_code=404, detail="客户不存在或无访问权限")

    try:
        parent_reply = await asyncio.to_thread(
            simulate_parent_reply, cust=cust, messages=req.messages
        )
        if parent_reply and parent_reply.strip():
            try:
                now = datetime.now()
                MessageService.insert_chat_message(
                    user_id=current_user["user_id"],
                    external_id=req.external_id,
                    wework_account_id=current_user.get("wework_account_id"),
                    content=parent_reply.strip(),
                    sender=req.external_id,
                    receiver=current_user["user_id"],
                    sender_name=cust.get("name"),
                    receiver_name=current_user.get("name"),
                    send_time=now,
                )
            except Exception as e:
                logger.warning(f"保存模拟家长回复失败: {e}")
        return {"success": True, "data": {"role": "parent", "content": parent_reply}}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI 模拟家长失败：{str(e)}")
