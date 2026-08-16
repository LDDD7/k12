"""
角色与权限 DAO — 操作 sys_role + sys_user_role 表（SQLAlchemy ORM）
支持角色定义管理、用户角色分配、data_scope 计算
角色：super_admin / region_manager / normal_advisor
data_scope：all / region / self
"""

from typing import Optional, List, Dict

from sqlalchemy import select, delete, update

from k12_app.backend.dao.db import session_scope
from k12_app.backend.dao.base_dao import order_by_data_scope
from k12_app.backend.models import SysRole, SysUserRole, SysEmployee


class RoleDAO:
    """角色数据访问"""

    # ==================== 角色定义（sys_role） ====================

    @staticmethod
    def get_all_roles() -> List[Dict]:
        with session_scope() as session:
            rows = (
                session.query(SysRole)
                .order_by(
                    order_by_data_scope(SysRole.data_scope),
                    SysRole.role_code,
                )
                .all()
            )
            return [
                {
                    "role_code": r.role_code,
                    "role_name": r.role_name,
                    "description": r.description,
                    "data_scope": r.data_scope,
                    "module_permissions": r.module_permissions,
                }
                for r in rows
            ]

    @staticmethod
    def get_role_by_code(role_code: str) -> Optional[Dict]:
        with session_scope() as session:
            r = session.query(SysRole).filter(SysRole.role_code == role_code).first()
            if not r:
                return None
            return {
                "role_code": r.role_code,
                "role_name": r.role_name,
                "description": r.description,
                "data_scope": r.data_scope,
                "module_permissions": r.module_permissions,
            }

    @staticmethod
    def role_exists(role_code: str) -> bool:
        with session_scope() as session:
            return (
                session.query(SysRole).filter(SysRole.role_code == role_code).first()
                is not None
            )

    # ==================== 用户角色关联（sys_user_role） ====================

    @staticmethod
    def get_user_roles(user_id: str) -> List[Dict]:
        with session_scope() as session:
            rows = (
                session.query(SysRole.role_code, SysRole.role_name, SysRole.data_scope,
                              SysRole.module_permissions, SysUserRole.wework_account_id)
                .join(SysUserRole, SysUserRole.role_code == SysRole.role_code)
                .filter(SysUserRole.user_id == user_id)
                .order_by(order_by_data_scope(SysRole.data_scope))
                .all()
            )
            return [
                {
                    "role_code": r.role_code,
                    "role_name": r.role_name,
                    "data_scope": r.data_scope,
                    "module_permissions": r.module_permissions,
                    "wework_account_id": r.wework_account_id,
                }
                for r in rows
            ]

    @staticmethod
    def get_user_role_codes(user_id: str) -> List[str]:
        with session_scope() as session:
            rows = (
                session.query(SysUserRole.role_code)
                .filter(SysUserRole.user_id == user_id)
                .all()
            )
            return [r.role_code for r in rows]

    @staticmethod
    def get_max_data_scope(user_id: str) -> str:
        scope_priority = {"all": 3, "region": 2, "self": 1}
        with session_scope() as session:
            rows = (
                session.query(SysRole.data_scope)
                .join(SysUserRole, SysUserRole.role_code == SysRole.role_code)
                .filter(SysUserRole.user_id == user_id)
                .all()
            )
            if not rows:
                return "self"
            max_scope = "self"
            max_prio = 0
            for row in rows:
                scope = row.data_scope
                prio = scope_priority.get(scope, 0)
                if prio > max_prio:
                    max_prio = prio
                    max_scope = scope
            return max_scope

    @staticmethod
    def assign_role(user_id: str, role_code: str, wework_account_id: str, session=None) -> bool:
        if not RoleDAO.role_exists(role_code):
            raise ValueError(f"角色 {role_code} 不存在")
        if RoleDAO._has_role_assignment(user_id, role_code, wework_account_id, session):
            return True
        if session is None:
            with session_scope(commit=True) as s:
                s.add(SysUserRole(user_id=user_id, role_code=role_code, wework_account_id=wework_account_id))
            return True
        session.add(SysUserRole(user_id=user_id, role_code=role_code, wework_account_id=wework_account_id))
        return True

    @staticmethod
    def batch_assign_roles(user_id: str, roles: List[Dict[str, str]]) -> bool:
        if not roles:
            return True
        with session_scope(commit=True) as session:
            RoleDAO.remove_all_roles(user_id, session)
            for role in roles:
                RoleDAO.assign_role(user_id, role["role_code"], role["wework_account_id"], session)
        return True

    @staticmethod
    def remove_role(user_id: str, role_code: str, wework_account_id: str, session=None) -> bool:
        if session is None:
            with session_scope(commit=True) as s:
                result = s.execute(
                    delete(SysUserRole).where(
                        SysUserRole.user_id == user_id,
                        SysUserRole.role_code == role_code,
                        SysUserRole.wework_account_id == wework_account_id,
                    )
                )
                return result.rowcount > 0
        result = session.execute(
            delete(SysUserRole).where(
                SysUserRole.user_id == user_id,
                SysUserRole.role_code == role_code,
                SysUserRole.wework_account_id == wework_account_id,
            )
        )
        return result.rowcount > 0

    @staticmethod
    def remove_all_roles(user_id: str, session=None) -> bool:
        if session is None:
            with session_scope(commit=True) as s:
                s.execute(delete(SysUserRole).where(SysUserRole.user_id == user_id))
            return True
        session.execute(delete(SysUserRole).where(SysUserRole.user_id == user_id))
        return True

    @staticmethod
    def check_user_has_role(user_id: str, role_code: str) -> bool:
        with session_scope() as session:
            return (
                session.query(SysUserRole)
                .filter(SysUserRole.user_id == user_id, SysUserRole.role_code == role_code)
                .first()
                is not None
            )

    @staticmethod
    def get_users_by_role(role_code: str) -> List[Dict]:
        with session_scope() as session:
            rows = (
                session.query(SysEmployee.user_id, SysEmployee.name, SysEmployee.org_id,
                              SysEmployee.wework_account_id, SysEmployee.binding_status,
                              SysUserRole.wework_account_id.label("role_account_id"))
                .join(SysUserRole, SysUserRole.user_id == SysEmployee.user_id)
                .filter(SysUserRole.role_code == role_code)
                .all()
            )
            return [
                {
                    "user_id": r.user_id,
                    "name": r.name,
                    "org_id": r.org_id,
                    "wework_account_id": r.wework_account_id,
                    "binding_status": r.binding_status,
                    "role_account_id": r.role_account_id,
                }
                for r in rows
            ]

    @staticmethod
    def sync_roles_after_bind(user_id: str, new_account_id: str) -> bool:
        """V3.2: 员工绑定企微后，将角色关联中的 '*' 替换为实际账户 ID（超管除外）"""
        with session_scope(commit=True) as session:
            result = session.execute(
                update(SysUserRole)
                .where(SysUserRole.user_id == user_id, SysUserRole.wework_account_id == "*")
                .values(wework_account_id=new_account_id)
            )
            return result.rowcount > 0

    @staticmethod
    def _has_role_assignment(user_id: str, role_code: str, wework_account_id: str, session=None) -> bool:
        if session is None:
            with session_scope() as s:
                return (
                    s.query(SysUserRole)
                    .filter(
                        SysUserRole.user_id == user_id,
                        SysUserRole.role_code == role_code,
                        SysUserRole.wework_account_id == wework_account_id,
                    )
                    .first()
                    is not None
                )
        return (
            session.query(SysUserRole)
            .filter(
                SysUserRole.user_id == user_id,
                SysUserRole.role_code == role_code,
                SysUserRole.wework_account_id == wework_account_id,
            )
            .first()
            is not None
        )

    # 常量
    SUPER_ADMIN = "super_admin"
    REGION_MANAGER = "region_manager"
    NORMAL_ADVISOR = "normal_advisor"

    @staticmethod
    def is_super_admin(user_id: str) -> bool:
        return RoleDAO.check_user_has_role(user_id, RoleDAO.SUPER_ADMIN)

    @staticmethod
    def is_region_manager(user_id: str) -> bool:
        return RoleDAO.check_user_has_role(user_id, RoleDAO.REGION_MANAGER)
