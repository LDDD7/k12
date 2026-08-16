"""
企微账户服务 — 企微账户管理
业务层：供路由层调用，数据访问委托给 WeWorkAccountDAO
"""

import logging
from typing import Optional, List, Dict

from k12_app.backend.dao.wework_account_dao import WeWorkAccountDAO

logger = logging.getLogger(__name__)


class WeWorkAccountService:
    """企微账户服务"""

    @staticmethod
    def get_all(
        user_id: str,
        data_scope: str,
        wework_account_id: Optional[str],
    ) -> List[Dict]:
        """获取企微账户列表（三维度权限过滤）"""
        return WeWorkAccountDAO.get_all(
            user_id=user_id,
            data_scope=data_scope,
            wework_account_id=wework_account_id,
        )

    @staticmethod
    def exists(account_id: str) -> bool:
        """检查企微账户是否存在"""
        return WeWorkAccountDAO.exists(account_id)

    @staticmethod
    def create(
        account_id: str,
        account_name: str,
        corp_id: str,
        corp_secret: str,
        region: str,
        agent_id: Optional[str] = None,
    ) -> bool:
        """新增企微账户"""
        return WeWorkAccountDAO.create(
            account_id=account_id,
            account_name=account_name,
            corp_id=corp_id,
            corp_secret=corp_secret,
            region=region,
            agent_id=agent_id,
        )

    @staticmethod
    def update(
        account_id: str,
        account_name: Optional[str] = None,
        corp_secret: Optional[str] = None,
        region: Optional[str] = None,
        agent_id: Optional[str] = None,
        is_active: Optional[int] = None,
    ) -> bool:
        """更新企微账户信息"""
        return WeWorkAccountDAO.update(
            account_id=account_id,
            account_name=account_name,
            corp_secret=corp_secret,
            region=region,
            agent_id=agent_id,
            is_active=is_active,
        )

    @staticmethod
    def get_stats(account_id: str) -> Dict:
        """获取企微账户统计数据"""
        return WeWorkAccountDAO.get_stats(account_id)
