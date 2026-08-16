"""
员工 DAO — 操作 sys_employee 表（SQLAlchemy ORM）
支持：
- 登录认证（bcrypt 密码验证）
- V3.2 注册-绑定分离流程（binding_status / bound_at）
- 三维度权限过滤（self / region / all）
- 组织层级过滤（普通顾问/区域主管/超级管理员）
"""

from typing import Optional, List, Dict
from datetime import datetime

import bcrypt
from sqlalchemy import func, delete, update

from k12_app.backend.dao.db import session_scope
from k12_app.backend.dao.base_dao import apply_scope_conditions
from k12_app.backend.models import SysEmployee, SysOrganization, SysWeworkAccount


def _employee_status(binding_status: Optional[str]) -> str:
    """binding_status → 在线/离线"""
    return "在线" if binding_status == "bound" else "离线"


class EmployeeDAO:
    """员工数据访问"""

    # ==================== 查询方法 ====================

    @staticmethod
    def get_by_user_id(user_id: str) -> Optional[Dict]:
        """按 user_id 查询员工（含 binding_status）"""
        with session_scope() as session:
            r = (
                session.query(SysEmployee)
                .filter(SysEmployee.user_id == user_id)
                .first()
            )
            if not r:
                return None
            return {
                "user_id": r.user_id,
                "name": r.name,
                "org_id": r.org_id,
                "dept": r.dept,
                "wework_account_id": r.wework_account_id,
                "password_hash": r.password_hash,
                "binding_status": r.binding_status,
                "bound_at": r.bound_at,
                "status": _employee_status(r.binding_status),
                "created_at": r.created_at,
                "updated_at": r.updated_at,
            }

    @staticmethod
    def get_by_user_id_with_org(user_id: str) -> Optional[Dict]:
        """按 user_id 查询员工（含组织信息）"""
        with session_scope() as session:
            r = (
                session.query(
                    SysEmployee,
                    SysOrganization.org_name,
                    SysOrganization.parent_org_id,
                    SysOrganization.org_type,
                    SysOrganization.wework_account_id.label("org_wework_account_id"),
                )
                .outerjoin(SysOrganization, SysOrganization.org_id == SysEmployee.org_id)
                .filter(SysEmployee.user_id == user_id)
                .first()
            )
            if not r:
                return None
            e = r[0]
            return {
                "user_id": e.user_id,
                "name": e.name,
                "org_id": e.org_id,
                "dept": e.dept,
                "wework_account_id": e.wework_account_id,
                "password_hash": e.password_hash,
                "binding_status": e.binding_status,
                "bound_at": e.bound_at,
                "status": _employee_status(e.binding_status),
                "org_name": r.org_name,
                "parent_org_id": r.parent_org_id,
                "org_type": r.org_type,
                "org_wework_account_id": r.org_wework_account_id,
            }

    @staticmethod
    def get_list(
        user_id: str,
        data_scope: str,
        wework_account_id: Optional[str],
        org_id: Optional[str] = None,
        binding_status: Optional[str] = None,
        keyword: Optional[str] = None,
        dept: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Dict:
        with session_scope() as session:
            query = (
                session.query(
                    SysEmployee.user_id,
                    SysEmployee.name,
                    SysEmployee.org_id,
                    SysEmployee.dept,
                    SysEmployee.wework_account_id,
                    SysEmployee.binding_status,
                    SysEmployee.bound_at,
                    SysEmployee.created_at,
                    SysOrganization.org_name.label("org_name"),
                    SysWeworkAccount.account_name.label("wework_account_name"),
                )
                .outerjoin(SysOrganization, SysOrganization.org_id == SysEmployee.org_id)
                .outerjoin(
                    SysWeworkAccount,
                    SysWeworkAccount.account_id == SysEmployee.wework_account_id,
                )
            )
            query = apply_scope_conditions(
                query=query,
                model=SysEmployee,
                data_scope=data_scope,
                user_id=user_id,
                wework_account_id=wework_account_id,
                owner_field="user_id",
            )

            if binding_status:
                query = query.filter(SysEmployee.binding_status == binding_status)
            if keyword:
                query = query.filter(SysEmployee.name.like(f"%{keyword}%"))
            if dept:
                query = query.filter(SysEmployee.dept.like(f"%{dept}%"))

            total = session.query(func.count()).select_from(query.subquery()).scalar()
            rows = (
                query.order_by(SysEmployee.created_at.desc())
                .limit(page_size)
                .offset((page - 1) * page_size)
                .all()
            )
            items = [
                {
                    "user_id": r.user_id,
                    "name": r.name,
                    "org_id": r.org_id,
                    "dept": r.dept,
                    "wework_account_id": r.wework_account_id,
                    "binding_status": r.binding_status,
                    "bound_at": r.bound_at,
                    "status": _employee_status(r.binding_status),
                    "org_name": r.org_name,
                    "wework_account_name": r.wework_account_name,
                }
                for r in rows
            ]
            return {"items": items, "total": total, "page": page, "page_size": page_size}

    @staticmethod
    def get_by_org_id(org_id: str) -> List[Dict]:
        """查询某组织下的所有员工（不含权限过滤，供内部调用）"""
        with session_scope() as session:
            rows = (
                session.query(SysEmployee)
                .filter(SysEmployee.org_id == org_id)
                .order_by(SysEmployee.name)
                .all()
            )
            return [
                {
                    "user_id": r.user_id,
                    "name": r.name,
                    "wework_account_id": r.wework_account_id,
                    "binding_status": r.binding_status,
                    "status": _employee_status(r.binding_status),
                }
                for r in rows
            ]

    @staticmethod
    def get_by_binding_status(binding_status: str) -> List[Dict]:
        """按 binding_status 查询员工（V3.2）"""
        with session_scope() as session:
            rows = (
                session.query(SysEmployee)
                .filter(SysEmployee.binding_status == binding_status)
                .order_by(SysEmployee.created_at.desc())
                .all()
            )
            return [
                {
                    "user_id": r.user_id,
                    "name": r.name,
                    "org_id": r.org_id,
                    "wework_account_id": r.wework_account_id,
                    "bound_at": r.bound_at,
                }
                for r in rows
            ]

    @staticmethod
    def get_unbound_employees(wework_account_id: Optional[str] = None) -> List[Dict]:
        """查询未绑定企微的员工列表（V3.2）"""
        with session_scope() as session:
            query = session.query(SysEmployee).filter(
                SysEmployee.binding_status == "unbound"
            )
            if wework_account_id:
                query = query.filter(SysEmployee.wework_account_id.is_(None))
            rows = query.all()
            return [
                {
                    "user_id": r.user_id,
                    "name": r.name,
                    "org_id": r.org_id,
                    "created_at": r.created_at,
                }
                for r in rows
            ]

    # ==================== 认证方法 ====================

    @staticmethod
    def verify_password(user_id: str, password: str) -> bool:
        """验证用户密码（bcrypt）"""
        employee = EmployeeDAO.get_by_user_id(user_id)
        if not employee:
            return False
        stored_hash = employee.get("password_hash")
        if not stored_hash:
            return False
        return bcrypt.checkpw(password.encode("utf-8"), stored_hash.encode("utf-8"))

    @staticmethod
    def hash_password(password: str) -> str:
        """对密码进行 bcrypt 哈希"""
        salt = bcrypt.gensalt()
        return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")

    # ==================== 写入方法 ====================

    @staticmethod
    def create(
        user_id: str,
        name: str,
        password: str,
        org_id: Optional[str] = None,
        dept: Optional[str] = None,
        wework_account_id: Optional[str] = None,
    ) -> bool:
        """
        新增员工（V3.2：wework_account_id 可选，默认 binding_status='unbound'）
        """
        password_hash = EmployeeDAO.hash_password(password)
        binding_status = "bound" if wework_account_id else "unbound"
        bound_at = datetime.now() if wework_account_id else None

        with session_scope(commit=True) as session:
            session.add(
                SysEmployee(
                    user_id=user_id,
                    name=name,
                    org_id=org_id,
                    dept=dept,
                    wework_account_id=wework_account_id,
                    password_hash=password_hash,
                    binding_status=binding_status,
                    bound_at=bound_at,
                )
            )
            return True

    @staticmethod
    def update(
        user_id: str,
        name: Optional[str] = None,
        org_id: Optional[str] = None,
        dept: Optional[str] = None,
    ) -> bool:
        """更新员工信息（仅更新传入字段）"""
        with session_scope(commit=True) as session:
            row = (
                session.query(SysEmployee)
                .filter(SysEmployee.user_id == user_id)
                .first()
            )
            if not row:
                return False
            if name is not None:
                row.name = name
            if org_id is not None:
                row.org_id = org_id
            if dept is not None:
                row.dept = dept
            return True

    @staticmethod
    def update_password(user_id: str, new_password: str) -> bool:
        """更新密码"""
        password_hash = EmployeeDAO.hash_password(new_password)
        with session_scope(commit=True) as session:
            result = session.execute(
                update(SysEmployee)
                .where(SysEmployee.user_id == user_id)
                .values(password_hash=password_hash)
            )
            return result.rowcount > 0

    # ==================== V3.2 绑定/解绑方法 ====================

    @staticmethod
    def update_binding_status(
        user_id: str,
        wework_account_id: Optional[str],
        binding_status: str,
        bound_at: Optional[datetime] = None,
    ) -> bool:
        """
        更新员工的企微绑定状态（V3.2）
        binding_status: 'unbound' | 'bound'
        """
        with session_scope(commit=True) as session:
            result = session.execute(
                update(SysEmployee)
                .where(SysEmployee.user_id == user_id)
                .values(
                    wework_account_id=wework_account_id,
                    binding_status=binding_status,
                    bound_at=bound_at,
                )
            )
            return result.rowcount > 0

    @staticmethod
    def bind_wework(user_id: str, wework_account_id: str) -> bool:
        """绑定企微账户（V3.2）"""
        return EmployeeDAO.update_binding_status(
            user_id=user_id,
            wework_account_id=wework_account_id,
            binding_status="bound",
            bound_at=datetime.now(),
        )

    @staticmethod
    def unbind_wework(user_id: str) -> bool:
        """解绑企微账户（V3.2）"""
        return EmployeeDAO.update_binding_status(
            user_id=user_id,
            wework_account_id=None,
            binding_status="unbound",
            bound_at=None,
        )

    @staticmethod
    def delete(user_id: str) -> bool:
        """删除员工（物理删除）"""
        with session_scope(commit=True) as session:
            result = session.execute(
                delete(SysEmployee).where(SysEmployee.user_id == user_id)
            )
            return result.rowcount > 0

    @staticmethod
    def exists(user_id: str) -> bool:
        """检查员工是否存在"""
        with session_scope() as session:
            return (
                session.query(SysEmployee)
                .filter(SysEmployee.user_id == user_id)
                .first()
                is not None
            )
