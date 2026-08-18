# k12_app/services/chat_service.py
"""
聊天服务 — SSE 事件流编排
将 send_message 请求 → Agent 执行 → SSE 事件流
"""

import json
import logging
import asyncio
import uuid
from functools import partial
from concurrent.futures import ThreadPoolExecutor
from typing import AsyncGenerator, Optional, Dict, Any
from datetime import datetime

from k12_app.backend.agent.graphs.k12_graph import run_agent
from k12_app.backend.dao.task_log_dao import TaskLogDAO
from k12_app.backend.dao.message_dao import MessageDAO

logger = logging.getLogger(__name__)


class ChatService:
    """聊天服务 — 编排 Agent 执行和 SSE 事件流"""

    @staticmethod
    async def stream_agent(
        user_id: str,
        external_id: str,
        wework_account_id: str,
        message: Optional[str] = None,
        menu_id: Optional[str] = None,
        data_scope: Optional[str] = None,
        sender_name: Optional[str] = None,
    ) -> AsyncGenerator[str, None]:
        """
        执行 Agent 并生成 SSE 事件流
        """
        try:
            # 1. 发送开始事件
            yield ChatService._format_event("node_result", {
                "node_name": "start",
                "message": "开始处理请求...",
                "status": "running",
            })

            # 2. 记录开始时间（用于埋点）
            start_time = datetime.now()

            # 3. 执行 Agent
            result = await ChatService._run_agent_async(
                user_id=user_id,
                external_id=external_id,
                wework_account_id=wework_account_id,
                message=message,
                menu_id=menu_id,
                data_scope=data_scope,
            )

            # 4. 计算耗时
            duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)

            # 5. 提取结果
            intent = result.get("intent", "free_chat")
            task_result = result.get("task_result")
            interrupt_id = result.get("interrupt_id")
            done = result.get("done", True)

            # 5.5 二期：综合推理逐步透明展示（step_start / step_result 事件）
            reasoning_steps = result.get("reasoning_steps") or []
            for step in reasoning_steps:
                yield ChatService._format_event("step_start", {
                    "step_index": step.get("step_index"),
                    "tool": step.get("tool"),
                    "description": step.get("description") or step.get("tool", ""),
                    "status": "running",
                })
                yield ChatService._format_event("step_result", {
                    "step_index": step.get("step_index"),
                    "tool": step.get("tool"),
                    "text": step.get("text", ""),
                    "status": step.get("status", "done"),
                    "matched": step.get("matched"),
                    "converged": step.get("converged", False),
                })

            # 6. 持久化 AI 助手回复（free_chat），保证聊天记录刷新后不丢失
            ChatService._persist_free_chat_reply(
                intent=intent,
                task_result=task_result,
                user_id=user_id,
                external_id=external_id,
                wework_account_id=wework_account_id,
                sender_name=sender_name,
            )

            # 7. 推送 task_result
            if task_result:
                task_type = task_result.get("type")
                yield ChatService._format_event("task_result", {
                    "task_type": task_type,
                    "data": task_result.get("data"),
                })

            # 8. 中断处理
            if interrupt_id and not done:
                yield ChatService._format_event("interrupt_required", {
                    "interrupt_id": interrupt_id,
                    "description": f"请确认 {intent} 结果",
                    "options": ["ok", "discard", "recreate"],
                    "data": task_result.get("data") if task_result else None,
                })

            # 9. 记录埋点（返回 task_log_id 供前端反馈/行为上报）
            task_log_id = await ChatService._log_task(
                user_id=user_id,
                external_id=external_id,
                wework_account_id=wework_account_id,
                intent=intent,
                result=result,
                duration_ms=duration_ms,
            )

            # 10. 发送完成事件
            yield ChatService._format_event("done", {"task_log_id": task_log_id})

            logger.info(f"Agent 执行完成: user={user_id}, intent={intent}, duration={duration_ms}ms")

        except Exception as e:
            logger.error(f"Agent 执行失败: {e}", exc_info=True)
            yield ChatService._format_event("error", {
                "error_code": "AGENT_ERROR",
                "message": f"AI 服务处理失败: {str(e)}",
            })

    @staticmethod
    async def _run_agent_async(
        user_id: str,
        external_id: str,
        wework_account_id: str,
        message: Optional[str] = None,
        menu_id: Optional[str] = None,
        data_scope: Optional[str] = None,
    ) -> Dict[str, Any]:
        """在线程池中执行 Agent（因为 run_agent 是同步的）"""
        loop = asyncio.get_event_loop()
        with ThreadPoolExecutor(max_workers=1) as executor:
            result = await loop.run_in_executor(
                executor,
                partial(
                    run_agent,
                    user_id=user_id,
                    external_id=external_id,
                    wework_account_id=wework_account_id,
                    message=message,
                    menu_id=menu_id,
                    data_scope=data_scope,
                    # 与 get_interrupt / confirm_interrupt 使用同一线程，保证聊天触发的中断可被轮询与确认
                    # 按客户隔离线程，避免同一顾问多客户操作时 checkpoint 互相覆盖
                    thread_id=f"interrupt_{user_id}_{external_id}",
                ),
            )
        return result

    @staticmethod
    def _persist_free_chat_reply(
        intent: str,
        task_result: Any,
        user_id: str,
        external_id: str,
        wework_account_id: str,
        sender_name: Optional[str] = None,
    ) -> None:
        """持久化 AI 助手（free_chat）回复，避免刷新/重新进入后聊天记录丢失"""
        if intent != "free_chat":
            return
        if not isinstance(task_result, dict) or task_result.get("type") != "free_chat":
            return
        reply_text = task_result.get("data")
        if not isinstance(reply_text, str) or not reply_text.strip():
            return
        try:
            now = datetime.now()
            MessageDAO.insert_chat_message(
                msg_id=uuid.uuid4().hex,
                sorted_key=MessageDAO.generate_sorted_key(user_id, external_id),
                user_id=user_id,
                external_id=external_id,
                wework_account_id=wework_account_id,
                sender=user_id,
                receiver=external_id,
                sender_name=sender_name,
                receiver_name=None,
                msg_type="text",
                content=reply_text.strip(),
                msg_date=now.strftime("%Y-%m-%d"),
                send_time=now,
            )
        except Exception as e:
            logger.warning(f"保存 AI 助手回复失败: {e}")

    @staticmethod
    async def _log_task(
        user_id: str,
        external_id: str,
        wework_account_id: str,
        intent: str,
        result: Dict[str, Any],
        duration_ms: int,
    ) -> Optional[int]:
        """记录任务日志（埋点），返回 task_log_id（前端反馈/行为上报用）"""
        try:
            task_result = result.get("task_result", {})
            action = "shown"
            if result.get("done") and task_result:
                action = "confirmed"

            # V3.3 二期：综合推理/知识库查询的兜底与失败标记
            action_detail = {
                "has_result": bool(task_result),
                "has_interrupt": bool(result.get("interrupt_id")),
            }
            if isinstance(task_result, dict) and task_result.get("type") == "reasoning":
                data = task_result.get("data") or {}
                mode = data.get("mode", "")
                action_detail["reasoning_mode"] = mode
                action_detail["steps"] = len(data.get("steps") or [])
                if mode == "error":
                    action = "failed"        # 推理失败率
                elif mode == "simplified":
                    action = "fallback"      # 兜底率（开关关闭退回简化模式）
                else:
                    action = "shown"

            log_id = TaskLogDAO.log_task(
                task_type=intent,
                user_id=user_id,
                external_id=external_id,
                wework_account_id=wework_account_id,
                action=action,
                action_detail=action_detail,
                duration_ms=duration_ms,
            )
            return log_id
        except Exception as e:
            logger.warning(f"任务日志记录失败: {e}")
            return None

    @staticmethod
    def _format_event(event_type: str, data: Dict[str, Any]) -> str:
        """格式化 SSE 事件"""
        event = {"type": event_type, **data}
        return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"