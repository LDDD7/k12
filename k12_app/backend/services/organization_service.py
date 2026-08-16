"""
组织架构服务 — 组织树 / 组织节点管理
业务层：供路由层调用，数据访问委托给 OrganizationDAO
"""

import logging
from typing import Optional, List, Dict

from k12_app.backend.dao.organization_dao import OrganizationDAO

logger = logging.getLogger(__name__)


class OrganizationService:
    """组织架构服务"""

    @staticmethod
    def get_tree(
        user_id: str,
        data_scope: str,
        wework_account_id: Optional[str],
    ) -> List[Dict]:
        """获取组织架构树（按权限过滤）"""
        return OrganizationDAO.get_tree(
            user_id=user_id,
            data_scope=data_scope,
            wework_account_id=wework_account_id,
        )

    @staticmethod
    def create(
        org_id: str,
        org_name: str,
        org_type: str,
        wework_account_id: str,
        parent_org_id: Optional[str] = None,
        sort_order: int = 0,
    ) -> bool:
        """新增组织节点"""
        return OrganizationDAO.create(
            org_id=org_id,
            org_name=org_name,
            org_type=org_type,
            wework_account_id=wework_account_id,
            parent_org_id=parent_org_id,
            sort_order=sort_order,
        )
