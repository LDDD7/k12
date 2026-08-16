"""
员工服务 — 员工管理 / 企微绑定 / 员工客户查询
业务层：供路由层调用，数据访问委托给 EmployeeDAO / RoleDAO / WeWorkAccountDAO / CustomerDAO
"""

import logging
from typing import Optional, List, Dict

from k12_app.backend.dao.employee_dao import EmployeeDAO
from k12_app.backend.dao.role_dao import RoleDAO
from k12_app.backend.dao.wework_account_dao import WeWorkAccountDAO
from k12_app.backend.dao.customer_dao import CustomerDAO

logger = logging.getLogger(__name__)


class EmployeeService:
    """员工服务"""

    @staticmethod
    def get_list(
        user_id: str,
        data_scope: str,
        wework_account_id: Optional[str],
        binding_status: Optional[str] = None,
        keyword: Optional[str] = None,
        dept: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Dict:
        """获取员工列表（三维度权限过滤）"""
        return EmployeeDAO.get_list(
            user_id=user_id,
            data_scope=data_scope,
            wework_account_id=wework_account_id,
            binding_status=binding_status,
            keyword=keyword,
            dept=dept,
            page=page,
            page_size=page_size,
        )

    @staticmethod
    def get_by_user_id(user_id: str) -> Optional[Dict]:
        """按 user_id 查询员工"""
        return EmployeeDAO.get_by_user_id(user_id)

    @staticmethod
    def exists(user_id: str) -> bool:
        """检查员工是否存在"""
        return EmployeeDAO.exists(user_id)

    @staticmethod
    def create_employee(
        user_id: str,
        name: str,
        password: str,
        org_id: Optional[str] = None,
        dept: Optional[str] = None,
        wework_account_id: Optional[str] = None,
        roles: Optional[List[dict]] = None,
    ) -> bool:
        """新增员工（含角色分配）"""
        success = EmployeeDAO.create(
            user_id=user_id,
            name=name,
            password=password,
            org_id=org_id,
            dept=dept,
            wework_account_id=wework_account_id,
        )
        if not success:
            return False
        if roles:
            for role in roles:
                RoleDAO.assign_role(
                    user_id,
                    role["role_code"],
                    role.get("wework_account_id", wework_account_id or "*"),
                )
        return True

    @staticmethod
    def update_employee(
        user_id: str,
        name: Optional[str] = None,
        org_id: Optional[str] = None,
        dept: Optional[str] = None,
    ) -> bool:
        """更新员工信息"""
        return EmployeeDAO.update(user_id=user_id, name=name, org_id=org_id, dept=dept)

    @staticmethod
    def delete_employee(user_id: str) -> bool:
        """删除员工"""
        return EmployeeDAO.delete(user_id)

    @staticmethod
    def bind_wework(user_id: str, wework_account_id: str, current_admin: Dict) -> bool:
        """
        绑定企微账户（V3.2）
        校验员工存在、未绑定、账户存在、权限范围，绑定后同步角色
        """
        employee = EmployeeDAO.get_by_user_id(user_id)
        if not employee:
            raise LookupError("员工不存在")

        if employee.get("binding_status") == "bound" and employee.get("wework_account_id"):
            raise ValueError("ALREADY_BOUND")

        if not WeWorkAccountDAO.exists(wework_account_id):
            raise LookupError("企微账户不存在")

        # 权限校验
        if current_admin.get("data_scope") != "all":
            accounts = WeWorkAccountDAO.get_all(
                user_id=current_admin.get("user_id"),
                data_scope=current_admin.get("data_scope"),
                wework_account_id=current_admin.get("wework_account_id"),
            )
            accessible_accounts = [a["account_id"] for a in accounts]
            if wework_account_id not in accessible_accounts:
                raise PermissionError("无权绑定该企微账户")

        success = EmployeeDAO.bind_wework(user_id, wework_account_id)
        if not success:
            return False

        RoleDAO.sync_roles_after_bind(user_id, wework_account_id)
        return True

    @staticmethod
    def get_employee_customers(user_id: str, current_admin: Dict) -> List[Dict]:
        """获取某员工名下的客户列表"""
        employee = EmployeeDAO.get_by_user_id(user_id)
        if not employee:
            raise LookupError("员工不存在")

        wework_account_id = employee.get("wework_account_id")
        if not wework_account_id:
            return []

        return CustomerDAO.get_by_follow_user(
            follow_user_id=user_id,
            user_id=current_admin.get("user_id"),
            data_scope=current_admin.get("data_scope", "self"),
            wework_account_id=wework_account_id,
        )
