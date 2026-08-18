"""
角色服务 — 角色定义 / 用户角色分配
业务层：供路由层调用，数据访问委托给 RoleDAO
"""

import logging
from typing import List, Dict

from k12_app.backend.dao.role_dao import RoleDAO

logger = logging.getLogger(__name__)


class RoleService:
    """角色服务"""

    @staticmethod
    def get_all_roles() -> List[Dict]:
        """获取角色列表"""
        return RoleDAO.get_all_roles()

    @staticmethod
    def get_user_roles(user_id: str) -> List[Dict]:
        """查询指定员工的角色分配"""
        return RoleDAO.get_user_roles(user_id)

    @staticmethod
    def assign_role(user_id: str, role_code: str, wework_account_id: str = "*") -> bool:
        """分配/修改用户角色"""
        return RoleDAO.assign_role(user_id, role_code, wework_account_id)

    @staticmethod
    def remove_role(user_id: str, role_code: str) -> bool:
        """移除用户角色（忽略 wework_account_id，删除该用户该角色的所有关联行）"""
        return RoleDAO.remove_role_any(user_id, role_code)
