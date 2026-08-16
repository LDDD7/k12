"""
客户服务 — 客户信息 / 客户标签 / 客户时间线 / 线索来源统计
业务层：供路由层调用，数据访问委托给 CustomerDAO / TagDAO / MessageDAO / FollowUpDAO / ScheduleDAO
"""

import logging
from datetime import datetime
from typing import Optional, List, Dict

from k12_app.backend.dao.customer_dao import CustomerDAO
from k12_app.backend.dao.tag_dao import TagDAO
from k12_app.backend.dao.message_dao import MessageDAO
from k12_app.backend.dao.follow_up_dao import FollowUpDAO
from k12_app.backend.dao.schedule_dao import ScheduleDAO

logger = logging.getLogger(__name__)


class CustomerService:
    """客户服务"""

    # ==================== 客户信息 ====================

    @staticmethod
    def get_list(
        user_id: str,
        data_scope: str,
        wework_account_id: Optional[str],
        page: int = 1,
        page_size: int = 20,
        stage: Optional[str] = None,
        keyword: Optional[str] = None,
        lead_source: Optional[str] = None,
    ) -> Dict:
        """获取客户列表（三维度权限过滤）"""
        return CustomerDAO.get_list(
            user_id=user_id,
            data_scope=data_scope,
            wework_account_id=wework_account_id,
            page=page,
            page_size=page_size,
            stage=stage,
            keyword=keyword,
            lead_source=lead_source,
        )

    @staticmethod
    def get_by_external_id(
        external_id: str,
        user_id: str,
        data_scope: str,
        wework_account_id: Optional[str],
    ) -> Optional[Dict]:
        """按 external_id 查询单个客户（带权限过滤）"""
        return CustomerDAO.get_by_external_id(
            external_id=external_id,
            user_id=user_id,
            data_scope=data_scope,
            wework_account_id=wework_account_id,
        )

    @staticmethod
    def exists(external_id: str) -> bool:
        """检查客户是否存在"""
        return CustomerDAO.exists(external_id)

    @staticmethod
    def update(
        external_id: str,
        name: Optional[str] = None,
        child_name: Optional[str] = None,
        school: Optional[str] = None,
        grade: Optional[str] = None,
        focus_subject: Optional[str] = None,
        remark: Optional[str] = None,
        stage: Optional[str] = None,
        lead_source: Optional[str] = None,
    ) -> bool:
        """更新客户信息（仅更新传入字段）"""
        return CustomerDAO.update(
            external_id=external_id,
            name=name,
            child_name=child_name,
            school=school,
            grade=grade,
            focus_subject=focus_subject,
            remark=remark,
            stage=stage,
            lead_source=lead_source,
        )

    @staticmethod
    def find_by_name(name: str) -> Optional[Dict]:
        """按客户姓名精确查找（订单归属客户）"""
        return CustomerDAO.find_by_name(name)

    @staticmethod
    def get_next_ids() -> tuple:
        """生成下一个客户 external_id / union_id"""
        return CustomerDAO.get_next_ids()

    @staticmethod
    def create(
        external_id: str,
        follow_user_id: str,
        wework_account_id: str,
        name: Optional[str] = None,
        child_name: Optional[str] = None,
        school: Optional[str] = None,
        grade: Optional[str] = None,
        focus_subject: Optional[str] = None,
        remark: Optional[str] = None,
        stage: str = "潜在",
        lead_source: Optional[str] = None,
        union_id: Optional[str] = None,
    ) -> bool:
        """新增客户"""
        return CustomerDAO.create(
            external_id=external_id,
            follow_user_id=follow_user_id,
            wework_account_id=wework_account_id,
            name=name,
            child_name=child_name,
            school=school,
            grade=grade,
            focus_subject=focus_subject,
            remark=remark,
            stage=stage,
            lead_source=lead_source,
            union_id=union_id,
        )

    # ==================== 线索来源统计 ====================

    @staticmethod
    def get_lead_source_stats(
        user_id: str,
        data_scope: str,
        wework_account_id: Optional[str],
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> List[Dict]:
        """按 lead_source 统计客户转化情况（V3.1）"""
        return CustomerDAO.get_lead_source_stats(
            user_id, data_scope, wework_account_id, start_date, end_date
        )

    # ==================== 客户标签 ====================

    @staticmethod
    def get_customer_tags(
        external_id: str,
        user_id: str,
        data_scope: str,
        wework_account_id: Optional[str],
    ) -> List[Dict]:
        """查询客户全部标签（已确认 + 待确认，按权限过滤）"""
        return TagDAO.get_customer_tags(
            external_id=external_id,
            user_id=user_id,
            data_scope=data_scope,
            wework_account_id=wework_account_id,
        )

    @staticmethod
    def add_tag(
        external_id: str,
        tag_id: str,
        source: str = "AI 推荐",
        confirmed: bool = False,
        confirmed_by: Optional[str] = None,
    ) -> bool:
        """为客户添加/更新标签"""
        return CustomerDAO.add_tag(
            external_id=external_id,
            tag_id=tag_id,
            source=source,
            confirmed=confirmed,
            confirmed_by=confirmed_by,
        )

    @staticmethod
    def remove_tag(external_id: str, tag_id: str) -> bool:
        """移除客户标签"""
        return CustomerDAO.remove_tag(external_id, tag_id)

    @staticmethod
    def confirm_tag(external_id: str, tag_id: str, confirmed_by: str) -> bool:
        """确认客户标签"""
        return CustomerDAO.confirm_tag(external_id, tag_id, confirmed_by)

    # ==================== 客户触达时间线 ====================

    @staticmethod
    def get_timeline(
        external_id: str,
        user_id: str,
        data_scope: str,
        wework_account_id: Optional[str],
        days: int = 90,
    ) -> List[Dict]:
        """
        客户触达时间线 — 聚合聊天 + 跟进 + 日程三表数据（V3.1）
        按时间倒序排列，形成完整的客户交互历史
        """
        timeline: List[Dict] = []

        # 1. 聊天记录
        try:
            chats = MessageDAO.get_chat_history_by_external_id(
                external_id=external_id,
                user_id=user_id,
                data_scope=data_scope,
                wework_account_id=wework_account_id,
                days=days,
                limit=200,
            )
            for c in chats:
                timeline.append({
                    "type": "chat",
                    "time": str(c.get("send_time") or c.get("created_at", "")),
                    "data": {
                        "sender_name": c.get("sender_name"),
                        "content": c.get("content"),
                        "msg_type": c.get("msg_type"),
                    },
                })
        except Exception:
            logger.exception("加载聊天时间线失败")

        # 2. 跟进记录
        try:
            follow_ups = FollowUpDAO.get_by_external_id(
                external_id=external_id,
                user_id=user_id,
                data_scope=data_scope,
                wework_account_id=wework_account_id,
            )
            for f in follow_ups:
                timeline.append({
                    "type": "follow_up",
                    "time": str(f.get("follow_up_time") or f.get("created_at", "")),
                    "data": {
                        "follow_up_type": f.get("follow_up_type"),
                        "content": f.get("content"),
                        "result": f.get("result"),
                    },
                })
        except Exception:
            logger.exception("加载跟进时间线失败")

        # 3. 日程记录
        try:
            schedules = ScheduleDAO.get_by_external_id(
                external_id=external_id,
                user_id=user_id,
                data_scope=data_scope,
                wework_account_id=wework_account_id,
            )
            for s in schedules:
                timeline.append({
                    "type": "schedule",
                    "time": str(s.get("start_time") or s.get("created_at", "")),
                    "data": {
                        "title": s.get("title"),
                        "priority": s.get("priority"),
                        "status": s.get("status"),
                    },
                })
        except Exception:
            logger.exception("加载日程时间线失败")

        # 按时间倒序排列
        timeline.sort(key=lambda x: x["time"], reverse=True)
        return timeline
