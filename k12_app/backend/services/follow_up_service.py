"""
跟进记录服务 — CRM 跟进记录管理
业务层：供路由层调用，数据访问委托给 FollowUpDAO
"""

import logging
from datetime import datetime
from typing import Optional, List, Dict

from k12_app.backend.dao.follow_up_dao import FollowUpDAO

logger = logging.getLogger(__name__)


class FollowUpService:
    """跟进记录服务"""

    @staticmethod
    def get_list(
        user_id: str,
        data_scope: str,
        wework_account_id: Optional[str],
        follow_up_type: Optional[str] = None,
        result: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Dict:
        """获取跟进记录列表"""
        return FollowUpDAO.get_list(
            user_id=user_id,
            data_scope=data_scope,
            wework_account_id=wework_account_id,
            follow_up_type=follow_up_type,
            result=result,
            page=page,
            page_size=page_size,
        )

    @staticmethod
    def get_by_external_id(
        external_id: str,
        user_id: str,
        data_scope: str,
        wework_account_id: Optional[str],
    ) -> List[Dict]:
        """按客户查询跟进记录"""
        return FollowUpDAO.get_by_external_id(
            external_id=external_id,
            user_id=user_id,
            data_scope=data_scope,
            wework_account_id=wework_account_id,
        )

    @staticmethod
    def create(
        external_id: str,
        user_id: str,
        wework_account_id: str,
        follow_up_type: str,
        follow_up_time: Optional[datetime],
        content: Optional[str] = None,
        result: Optional[str] = None,
        next_action: Optional[str] = None,
    ) -> Optional[int]:
        """创建跟进记录"""
        ft = follow_up_time or datetime.now()
        return FollowUpDAO.create(
            external_id=external_id,
            user_id=user_id,
            wework_account_id=wework_account_id,
            follow_up_type=follow_up_type,
            follow_up_time=ft,
            content=content,
            result=result,
            next_action=next_action,
        )

    @staticmethod
    def exists(follow_up_id: int) -> bool:
        """检查跟进记录是否存在"""
        return FollowUpDAO.exists(follow_up_id)

    @staticmethod
    def update(
        follow_up_id: int,
        content: Optional[str] = None,
        result: Optional[str] = None,
        follow_up_time: Optional[datetime] = None,
        next_action: Optional[str] = None,
        follow_up_type: Optional[str] = None,
    ) -> bool:
        """更新跟进记录"""
        return FollowUpDAO.update(
            follow_up_id=follow_up_id,
            content=content,
            result=result,
            follow_up_time=follow_up_time,
            next_action=next_action,
            follow_up_type=follow_up_type,
        )

    @staticmethod
    def delete(follow_up_id: int) -> bool:
        """删除跟进记录"""
        return FollowUpDAO.delete(follow_up_id)
