"""
消息服务 — 企微聊天 / 客服消息读取与写入
业务层：供路由层调用，数据访问委托给 MessageDAO
"""

import logging
import uuid
from datetime import datetime
from typing import Optional, List, Dict

from k12_app.backend.dao.message_dao import MessageDAO

logger = logging.getLogger(__name__)


class MessageService:
    """消息服务"""

    @staticmethod
    def get_chat_history(
        user_id: str,
        external_id: str,
        wework_account_id: Optional[str],
        data_scope: str,
        days: int = 30,
        limit: int = 100,
    ) -> List[Dict]:
        """查询企微聊天历史"""
        return MessageDAO.get_chat_history(
            user_id=user_id,
            external_id=external_id,
            wework_account_id=wework_account_id,
            data_scope=data_scope,
            days=days,
            limit=limit,
        )

    @staticmethod
    def get_chat_history_by_external_id(
        external_id: str,
        user_id: str,
        data_scope: str,
        wework_account_id: Optional[str],
        days: int = 30,
        limit: int = 100,
    ) -> List[Dict]:
        """按客户 ID 查询聊天记录"""
        return MessageDAO.get_chat_history_by_external_id(
            external_id=external_id,
            user_id=user_id,
            data_scope=data_scope,
            wework_account_id=wework_account_id,
            days=days,
            limit=limit,
        )

    @staticmethod
    def get_recent_chat_by_external_id(
        external_id: str,
        user_id: str,
        data_scope: str,
        wework_account_id: Optional[str],
        limit: int = 20,
    ) -> List[Dict]:
        """获取与某客户最近的聊天记录"""
        return MessageDAO.get_recent_chat_by_external_id(
            external_id=external_id,
            user_id=user_id,
            data_scope=data_scope,
            wework_account_id=wework_account_id,
            limit=limit,
        )

    @staticmethod
    def get_kf_history(
        external_id: str,
        user_id: str,
        data_scope: str,
        wework_account_id: Optional[str],
        days: int = 30,
        limit: int = 100,
    ) -> List[Dict]:
        """查询客服消息历史"""
        return MessageDAO.get_kf_history(
            external_id=external_id,
            user_id=user_id,
            data_scope=data_scope,
            wework_account_id=wework_account_id,
            days=days,
            limit=limit,
        )

    @staticmethod
    def insert_chat_message(
        user_id: str,
        external_id: str,
        wework_account_id: str,
        content: str,
        sender: str,
        receiver: str,
        sender_name: Optional[str] = None,
        receiver_name: Optional[str] = None,
        send_time: Optional[datetime] = None,
    ) -> bool:
        """插入企微聊天消息（自动生成 msg_id / sorted_key / msg_date）"""
        now = send_time or datetime.now()
        return MessageDAO.insert_chat_message(
            msg_id=uuid.uuid4().hex,
            sorted_key=MessageDAO.generate_sorted_key(user_id, external_id),
            user_id=user_id,
            external_id=external_id,
            wework_account_id=wework_account_id,
            sender=sender,
            receiver=receiver,
            sender_name=sender_name,
            receiver_name=receiver_name,
            msg_type="text",
            content=content,
            msg_date=now.strftime("%Y-%m-%d"),
            send_time=now,
        )

    @staticmethod
    def insert_raw_chat_message(**kwargs) -> bool:
        """直接插入聊天消息（完整参数透传，供 AI 持久化等场景使用）"""
        return MessageDAO.insert_chat_message(**kwargs)

    @staticmethod
    def count_chat_messages(user_id: str, external_id: str) -> int:
        """统计某会话当前的聊天消息数量"""
        return MessageDAO.count_chat_messages(user_id, external_id)

    @staticmethod
    def delete_chat_messages_by_external_id(
        external_id: str,
        user_id: str,
        data_scope: str,
        wework_account_id: Optional[str],
    ) -> int:
        """按客户删除聊天消息（带权限过滤）"""
        return MessageDAO.delete_chat_messages_by_external_id(
            external_id=external_id,
            user_id=user_id,
            data_scope=data_scope,
            wework_account_id=wework_account_id,
        )

    @staticmethod
    def generate_sorted_key(user_id: str, external_id: str) -> str:
        """生成 sorted_key"""
        return MessageDAO.generate_sorted_key(user_id, external_id)
