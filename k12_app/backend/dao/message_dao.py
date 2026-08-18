"""
消息 DAO — 操作 msg_wxqy_chat + msg_wxkf_chat 表（SQLAlchemy ORM）
支持：
- 按月分区表查询（必须带日期条件，否则全分区扫描）
- sorted_key 查询（员工ID + 客户ID 排序拼接）
- 三维度权限过滤（owner_field = user_id）
- V3.2 未绑定员工返回空
"""

from typing import Optional, List, Dict
from datetime import datetime, timedelta, date

from sqlalchemy import func, delete, update

from k12_app.backend.dao.db import session_scope
from k12_app.backend.dao.base_dao import apply_scope_conditions, apply_kf_scope_conditions
from k12_app.backend.models import MsgWxqyChat, MsgWxkfChat


class MessageDAO:
    """消息数据访问"""

    # ==================== 企微聊天消息 ====================

    @staticmethod
    def get_chat_history(
        user_id: str,
        external_id: str,
        wework_account_id: Optional[str],
        data_scope: str,
        days: int = 30,
        limit: int = 100,
        msg_type: Optional[str] = None,
    ) -> List[Dict]:
        """
        查询企微聊天历史（按 sorted_key 索引，必须带日期范围）
        sorted_key = sorted([user_id, external_id]) 拼接，保证双向查询一致
        """
        # 计算日期范围（分区裁剪关键）
        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=days)

        # 生成 sorted_key
        sorted_ids = sorted([user_id, external_id])
        sorted_key = f"{sorted_ids[0]}_{sorted_ids[1]}"

        # V3.2 安全：如果 wework_account_id 为空，直接返回空
        if not wework_account_id:
            return []

        with session_scope() as session:
            query = session.query(MsgWxqyChat).filter(
                MsgWxqyChat.sorted_key == sorted_key,
                MsgWxqyChat.msg_date.between(start_date, end_date),
                MsgWxqyChat.user_id == user_id,
                MsgWxqyChat.external_id == external_id,
            )
            query = apply_scope_conditions(
                query=query,
                model=MsgWxqyChat,
                data_scope=data_scope,
                user_id=user_id,
                wework_account_id=wework_account_id,
                owner_field="user_id",
            )
            if msg_type:
                query = query.filter(MsgWxqyChat.msg_type == msg_type)

            rows = query.order_by(MsgWxqyChat.send_time.desc()).limit(limit).all()
            return [
                {
                    "msg_id": r.msg_id,
                    "sorted_key": r.sorted_key,
                    "user_id": r.user_id,
                    "external_id": r.external_id,
                    "wework_account_id": r.wework_account_id,
                    "sender": r.sender,
                    "receiver": r.receiver,
                    "sender_name": r.sender_name,
                    "receiver_name": r.receiver_name,
                    "msg_type": r.msg_type,
                    "content": r.content,
                    "msg_date": r.msg_date,
                    "send_time": r.send_time,
                    "created_at": r.created_at,
                }
                for r in rows
            ]

    @staticmethod
    def get_chat_history_by_external_id(
        external_id: str,
        user_id: str,
        data_scope: str,
        wework_account_id: Optional[str],
        days: int = 30,
        limit: int = 100,
    ) -> List[Dict]:
        """
        按客户 ID 查询聊天记录（所有顾问与该客户的聊天）
        用于客户详情页
        """
        if not wework_account_id:
            return []

        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=days)

        with session_scope() as session:
            query = session.query(MsgWxqyChat).filter(
                MsgWxqyChat.external_id == external_id,
                MsgWxqyChat.msg_date.between(start_date, end_date),
            )
            # V3.3.2：聊天记录权限按"客户归属"过滤（external_id → biz_customer.follow_user_id），
            # 而非消息自身的 user_id——否则模拟家长/代发消息按操作人分散后，客户顾问会漏看自己的会话
            query = apply_kf_scope_conditions(
                query=query,
                model=MsgWxqyChat,
                data_scope=data_scope,
                user_id=user_id,
                wework_account_id=wework_account_id,
            )
            rows = query.order_by(MsgWxqyChat.send_time.desc()).limit(limit).all()
            return [
                {
                    "msg_id": r.msg_id,
                    "sorted_key": r.sorted_key,
                    "user_id": r.user_id,
                    "external_id": r.external_id,
                    "wework_account_id": r.wework_account_id,
                    "sender": r.sender,
                    "receiver": r.receiver,
                    "sender_name": r.sender_name,
                    "receiver_name": r.receiver_name,
                    "msg_type": r.msg_type,
                    "content": r.content,
                    "msg_date": r.msg_date,
                    "send_time": r.send_time,
                    "created_at": r.created_at,
                }
                for r in rows
            ]

    @staticmethod
    def get_chat_history_by_user(
        follow_user_id: str,
        user_id: str,
        data_scope: str,
        wework_account_id: Optional[str],
        days: int = 30,
        limit: int = 100,
    ) -> List[Dict]:
        """
        按顾问 ID 查询聊天记录
        用于顾问自己的消息历史
        """
        if not wework_account_id:
            return []

        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=days)

        with session_scope() as session:
            query = session.query(MsgWxqyChat).filter(
                MsgWxqyChat.user_id == follow_user_id,
                MsgWxqyChat.msg_date.between(start_date, end_date),
            )
            query = apply_scope_conditions(
                query=query,
                model=MsgWxqyChat,
                data_scope=data_scope,
                user_id=user_id,
                wework_account_id=wework_account_id,
                owner_field="user_id",
            )
            rows = query.order_by(MsgWxqyChat.send_time.desc()).limit(limit).all()
            return [
                {
                    "msg_id": r.msg_id,
                    "sorted_key": r.sorted_key,
                    "user_id": r.user_id,
                    "external_id": r.external_id,
                    "wework_account_id": r.wework_account_id,
                    "sender": r.sender,
                    "receiver": r.receiver,
                    "sender_name": r.sender_name,
                    "receiver_name": r.receiver_name,
                    "msg_type": r.msg_type,
                    "content": r.content,
                    "msg_date": r.msg_date,
                    "send_time": r.send_time,
                    "created_at": r.created_at,
                }
                for r in rows
            ]

    @staticmethod
    def get_recent_chat_by_external_id(
        external_id: str,
        user_id: str,
        data_scope: str,
        wework_account_id: Optional[str],
        limit: int = 20,
    ) -> List[Dict]:
        """
        获取与某客户最近的聊天记录（最近 limit 条）
        用于侧边栏快速预览
        """
        return MessageDAO.get_chat_history_by_external_id(
            external_id=external_id,
            user_id=user_id,
            data_scope=data_scope,
            wework_account_id=wework_account_id,
            days=7,
            limit=limit,
        )

    @staticmethod
    def get_chat_count_by_date(
        user_id: str,
        data_scope: str,
        wework_account_id: Optional[str],
        days: int = 7,
    ) -> List[Dict]:
        """
        按日期统计消息量（用于看板）
        """
        if not wework_account_id:
            return []

        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=days)

        with session_scope() as session:
            query = (
                session.query(
                    MsgWxqyChat.msg_date,
                    func.count(MsgWxqyChat.id).label("count"),
                    func.count(func.distinct(MsgWxqyChat.external_id)).label("customer_count"),
                )
                .filter(MsgWxqyChat.msg_date.between(start_date, end_date))
            )
            query = apply_scope_conditions(
                query=query,
                model=MsgWxqyChat,
                data_scope=data_scope,
                user_id=user_id,
                wework_account_id=wework_account_id,
                owner_field="user_id",
            )
            rows = (
                query.group_by(MsgWxqyChat.msg_date)
                .order_by(MsgWxqyChat.msg_date.desc())
                .all()
            )
            return [
                {
                    "msg_date": r.msg_date,
                    "count": int(r.count or 0),
                    "customer_count": int(r.customer_count or 0),
                }
                for r in rows
            ]

    @staticmethod
    def insert_chat_message(
        msg_id: str,
        sorted_key: str,
        user_id: str,
        external_id: str,
        wework_account_id: str,
        sender: Optional[str],
        receiver: Optional[str],
        sender_name: Optional[str],
        receiver_name: Optional[str],
        msg_type: str,
        content: Optional[str],
        msg_date: str,
        send_time: datetime,
    ) -> bool:
        """插入企微聊天消息（按 msg_id+msg_date 唯一键 upsert）"""
        msg_date_obj = (
            msg_date
            if isinstance(msg_date, date)
            else datetime.strptime(str(msg_date)[:10], "%Y-%m-%d").date()
        )
        with session_scope(commit=True) as session:
            row = (
                session.query(MsgWxqyChat)
                .filter(
                    MsgWxqyChat.msg_id == msg_id,
                    MsgWxqyChat.msg_date == msg_date_obj,
                )
                .first()
            )
            if row:
                row.content = content
                row.send_time = send_time
            else:
                session.add(
                    MsgWxqyChat(
                        msg_id=msg_id,
                        sorted_key=sorted_key,
                        user_id=user_id,
                        external_id=external_id,
                        wework_account_id=wework_account_id,
                        sender=sender,
                        receiver=receiver,
                        sender_name=sender_name,
                        receiver_name=receiver_name,
                        msg_type=msg_type,
                        content=content,
                        msg_date=msg_date_obj,
                        send_time=send_time,
                    )
                )
            return True

    @staticmethod
    def batch_insert_chat_messages(messages: List[Dict]) -> int:
        """批量插入企微聊天消息"""
        if not messages:
            return 0
        with session_scope(commit=True) as session:
            for m in messages:
                MessageDAO.insert_chat_message(
                    msg_id=m.get("msg_id"),
                    sorted_key=m.get("sorted_key"),
                    user_id=m.get("user_id"),
                    external_id=m.get("external_id"),
                    wework_account_id=m.get("wework_account_id"),
                    sender=m.get("sender"),
                    receiver=m.get("receiver"),
                    sender_name=m.get("sender_name"),
                    receiver_name=m.get("receiver_name"),
                    msg_type=m.get("msg_type"),
                    content=m.get("content"),
                    msg_date=m.get("msg_date"),
                    send_time=m.get("send_time"),
                )
            return len(messages)

    @staticmethod
    def get_chat_by_msg_id(msg_id: str) -> Optional[Dict]:
        """按消息 ID 查询企微聊天"""
        with session_scope() as session:
            r = (
                session.query(MsgWxqyChat)
                .filter(MsgWxqyChat.msg_id == msg_id)
                .first()
            )
            if not r:
                return None
            return {
                "msg_id": r.msg_id,
                "sorted_key": r.sorted_key,
                "user_id": r.user_id,
                "external_id": r.external_id,
                "wework_account_id": r.wework_account_id,
                "sender": r.sender,
                "receiver": r.receiver,
                "sender_name": r.sender_name,
                "receiver_name": r.receiver_name,
                "msg_type": r.msg_type,
                "content": r.content,
                "msg_date": r.msg_date,
                "send_time": r.send_time,
            }

    @staticmethod
    def count_chat_messages(user_id: str, external_id: str) -> int:
        """统计某会话（顾问 + 客户）当前的聊天消息数量"""
        sorted_key = MessageDAO.generate_sorted_key(user_id, external_id)
        with session_scope() as session:
            return (
                session.query(func.count(MsgWxqyChat.id))
                .filter(MsgWxqyChat.sorted_key == sorted_key)
                .scalar()
            )

    @staticmethod
    def customer_message_exists_with_content(
        user_id: str, external_id: str, content: str
    ) -> bool:
        """判断会话中是否已有客户（sender=external_id）发过完全相同的内容。

        用于防止「复制客户原话再发一遍」被以顾问身份重复入库：
        顾问发送内容若与会话内客户已有消息完全一致，视为复制重发，跳过写入。
        """
        sorted_key = MessageDAO.generate_sorted_key(user_id, external_id)
        with session_scope() as session:
            row = (
                session.query(MsgWxqyChat.id)
                .filter(
                    MsgWxqyChat.sorted_key == sorted_key,
                    MsgWxqyChat.sender == external_id,
                    MsgWxqyChat.content == content,
                )
                .first()
            )
            return row is not None

    @staticmethod
    def get_chat_messages_for_flush(
        user_id: str,
        external_id: str,
        limit: int = 1000,
    ) -> List[Dict]:
        """读取某会话全部文本消息（按时间正序），用于转存向量库"""
        sorted_key = MessageDAO.generate_sorted_key(user_id, external_id)
        with session_scope() as session:
            rows = (
                session.query(MsgWxqyChat)
                .filter(
                    MsgWxqyChat.sorted_key == sorted_key,
                    MsgWxqyChat.msg_type == "text",
                    MsgWxqyChat.content.isnot(None),
                    MsgWxqyChat.content != "",
                )
                .order_by(MsgWxqyChat.send_time.asc())
                .limit(limit)
                .all()
            )
            return [
                {
                    "msg_id": r.msg_id,
                    "user_id": r.user_id,
                    "external_id": r.external_id,
                    "wework_account_id": r.wework_account_id,
                    "sender_name": r.sender_name,
                    "receiver_name": r.receiver_name,
                    "msg_type": r.msg_type,
                    "content": r.content,
                    "send_time": r.send_time,
                    "msg_date": r.msg_date,
                }
                for r in rows
            ]

    @staticmethod
    def delete_chat_messages_by_conversation(user_id: str, external_id: str) -> int:
        """删除某会话（顾问 + 客户）的全部聊天消息，返回删除行数"""
        sorted_key = MessageDAO.generate_sorted_key(user_id, external_id)
        with session_scope(commit=True) as session:
            result = session.execute(
                delete(MsgWxqyChat).where(
                    MsgWxqyChat.sorted_key == sorted_key,
                    MsgWxqyChat.user_id == user_id,
                    MsgWxqyChat.external_id == external_id,
                )
            )
            return result.rowcount

    @staticmethod
    def delete_chat_messages_by_external_id(
        external_id: str,
        user_id: str,
        data_scope: str,
        wework_account_id: Optional[str],
    ) -> int:
        """按客户删除聊天消息（与 get_chat_history_by_external_id 使用相同权限过滤）。

        V3.3.2：权限过滤与查询一致——按"客户归属"（external_id → biz_customer.follow_user_id）
        而非消息自身 user_id，确保清空能删掉该客户全部消息（含其它操作人代发/模拟家长的消息）。
        """
        if not wework_account_id:
            return 0

        with session_scope(commit=True) as session:
            query = delete(MsgWxqyChat).where(MsgWxqyChat.external_id == external_id)
            query = apply_kf_scope_conditions(
                query=query,
                model=MsgWxqyChat,
                data_scope=data_scope,
                user_id=user_id,
                wework_account_id=wework_account_id,
            )
            result = session.execute(query)
            return result.rowcount

    @staticmethod
    def delete_chat_messages_by_msg_ids(msg_ids: List[str]) -> int:
        """按 msg_id 批量删除聊天消息（归档时保留最近 N 条，删除更早的），返回删除行数"""
        if not msg_ids:
            return 0
        total = 0
        with session_scope(commit=True) as session:
            for i in range(0, len(msg_ids), 200):
                batch = msg_ids[i:i + 200]
                result = session.execute(
                    delete(MsgWxqyChat).where(MsgWxqyChat.msg_id.in_(batch))
                )
                total += result.rowcount
            return total

    # ==================== 客服消息 ====================

    @staticmethod
    def get_kf_history(
        external_id: str,
        user_id: str,
        data_scope: str,
        wework_account_id: Optional[str],
        days: int = 30,
        limit: int = 100,
    ) -> List[Dict]:
        """查询客服消息历史（通过 external_id 关联 biz_customer 做权限过滤）"""
        if not wework_account_id:
            return []

        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=days)

        with session_scope() as session:
            query = session.query(MsgWxkfChat).filter(
                MsgWxkfChat.external_id == external_id,
                MsgWxkfChat.msg_date.between(start_date, end_date),
            )
            query = apply_kf_scope_conditions(
                query=query,
                model=MsgWxkfChat,
                data_scope=data_scope,
                user_id=user_id,
                wework_account_id=wework_account_id,
            )
            rows = query.order_by(MsgWxkfChat.send_time.desc()).limit(limit).all()
            return [
                {
                    "msg_id": r.msg_id,
                    "external_id": r.external_id,
                    "wework_account_id": r.wework_account_id,
                    "kf_account": r.kf_account,
                    "sender": r.sender,
                    "sender_role": r.sender_role,
                    "sender_name": r.sender_name,
                    "msg_type": r.msg_type,
                    "content": r.content,
                    "msg_date": r.msg_date,
                    "send_time": r.send_time,
                    "created_at": r.created_at,
                }
                for r in rows
            ]

    @staticmethod
    def get_kf_count_by_date(
        user_id: str,
        data_scope: str,
        wework_account_id: Optional[str],
        days: int = 7,
    ) -> List[Dict]:
        """按日期统计客服消息量（通过 external_id 关联 biz_customer 做权限过滤）"""
        if not wework_account_id:
            return []

        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=days)

        with session_scope() as session:
            query = (
                session.query(
                    MsgWxkfChat.msg_date,
                    func.count(MsgWxkfChat.id).label("count"),
                    func.count(func.distinct(MsgWxkfChat.external_id)).label("customer_count"),
                )
                .filter(MsgWxkfChat.msg_date.between(start_date, end_date))
            )
            query = apply_kf_scope_conditions(
                query=query,
                model=MsgWxkfChat,
                data_scope=data_scope,
                user_id=user_id,
                wework_account_id=wework_account_id,
            )
            rows = (
                query.group_by(MsgWxkfChat.msg_date)
                .order_by(MsgWxkfChat.msg_date.desc())
                .all()
            )
            return [
                {
                    "msg_date": r.msg_date,
                    "count": int(r.count or 0),
                    "customer_count": int(r.customer_count or 0),
                }
                for r in rows
            ]

    @staticmethod
    def insert_kf_message(
        msg_id: str,
        external_id: str,
        wework_account_id: str,
        sender: Optional[str],
        sender_role: str,
        sender_name: Optional[str],
        msg_type: str,
        content: Optional[str],
        msg_date: str,
        send_time: datetime,
        kf_account: Optional[str] = None,
    ) -> bool:
        """插入客服消息（按 msg_id+msg_date 唯一键 upsert）"""
        msg_date_obj = (
            msg_date
            if isinstance(msg_date, date)
            else datetime.strptime(str(msg_date)[:10], "%Y-%m-%d").date()
        )
        with session_scope(commit=True) as session:
            row = (
                session.query(MsgWxkfChat)
                .filter(
                    MsgWxkfChat.msg_id == msg_id,
                    MsgWxkfChat.msg_date == msg_date_obj,
                )
                .first()
            )
            if row:
                row.content = content
                row.send_time = send_time
            else:
                session.add(
                    MsgWxkfChat(
                        msg_id=msg_id,
                        external_id=external_id,
                        wework_account_id=wework_account_id,
                        kf_account=kf_account,
                        sender=sender,
                        sender_role=sender_role,
                        sender_name=sender_name,
                        msg_type=msg_type,
                        content=content,
                        msg_date=msg_date_obj,
                        send_time=send_time,
                    )
                )
            return True

    @staticmethod
    def batch_insert_kf_messages(messages: List[Dict]) -> int:
        """批量插入客服消息"""
        if not messages:
            return 0
        with session_scope(commit=True) as session:
            for m in messages:
                MessageDAO.insert_kf_message(
                    msg_id=m.get("msg_id"),
                    external_id=m.get("external_id"),
                    wework_account_id=m.get("wework_account_id"),
                    kf_account=m.get("kf_account"),
                    sender=m.get("sender"),
                    sender_role=m.get("sender_role"),
                    sender_name=m.get("sender_name"),
                    msg_type=m.get("msg_type"),
                    content=m.get("content"),
                    msg_date=m.get("msg_date"),
                    send_time=m.get("send_time"),
                )
            return len(messages)

    @staticmethod
    def get_messages_for_reindex(
        external_ids: Optional[List[str]] = None,
        after_time: Optional[datetime] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        limit: int = 1000,
        offset: int = 0,
    ) -> List[Dict]:
        """按条件批量读取待索引的文本消息（RAG 索引器用）。

        支持两种模式：
        - external_ids 模式：按 external_id 列表（配合可选 after_time 增量过滤）
        - 日期范围模式：按 msg_date BETWEEN start_date AND end_date
        统一过滤 msg_type='text' 且 content 非空，按 send_time 倒序，limit/offset 分页。
        """
        if not start_date and not end_date and not external_ids:
            return []
        with session_scope() as session:
            query = session.query(MsgWxqyChat).filter(
                MsgWxqyChat.msg_type == "text",
                MsgWxqyChat.content.isnot(None),
                MsgWxqyChat.content != "",
            )
            if external_ids:
                query = query.filter(MsgWxqyChat.external_id.in_(external_ids))
                if after_time:
                    query = query.filter(MsgWxqyChat.send_time > after_time)
            else:
                query = query.filter(MsgWxqyChat.msg_date.between(start_date, end_date))

            rows = query.order_by(MsgWxqyChat.send_time.desc()).limit(limit).offset(offset).all()
            return [
                {
                    "msg_id": r.msg_id,
                    "user_id": r.user_id,
                    "external_id": r.external_id,
                    "wework_account_id": r.wework_account_id,
                    "sender_name": r.sender_name,
                    "receiver_name": r.receiver_name,
                    "msg_type": r.msg_type,
                    "content": r.content,
                    "send_time": r.send_time,
                    "msg_date": r.msg_date,
                }
                for r in rows
            ]

    @staticmethod
    def generate_sorted_key(user_id: str, external_id: str) -> str:
        """
        生成 sorted_key：user_id 和 external_id 排序后拼接
        用于双向查询保证索引命中
        """
        sorted_ids = sorted([user_id, external_id])
        return f"{sorted_ids[0]}_{sorted_ids[1]}"
