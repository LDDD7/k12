"""
企微账户 DAO — 操作 sys_wework_account 表（SQLAlchemy ORM）
支持：
- 多企微账户管理（sz / sh / bj）
- CorpSecret 加密存储（应用层负责加解密）
- 三维度权限过滤（self / region / all）
"""

from typing import Optional, List, Dict
from datetime import datetime, timedelta

from sqlalchemy import func, select

from k12_app.backend.dao.db import session_scope
from k12_app.backend.models import (
    SysWeworkAccount,
    BizCustomer,
    BizOrder,
    SysEmployee,
    MsgWxqyChat,
)
from k12_app.backend.services.secret_crypto import encrypt_secret, decrypt_secret


class WeWorkAccountDAO:
    """企微账户数据访问"""

    @staticmethod
    def get_all(
        user_id: Optional[str] = None,
        data_scope: str = "all",
        wework_account_id: Optional[str] = None,
        region: Optional[str] = None,
    ) -> List[Dict]:
        """
        获取企微账户列表（按权限过滤）
        - all: 返回全部
        - region: 返回本区域
        - self: 仅返回当前账户
        """
        with session_scope() as session:
            query = session.query(SysWeworkAccount)

            if data_scope == "self":
                if not wework_account_id:
                    return []
                query = query.filter(SysWeworkAccount.account_id == wework_account_id)
            elif data_scope == "region":
                if not region:
                    # 如果 region 未传入，尝试从 wework_account_id 反查
                    if wework_account_id:
                        account = WeWorkAccountDAO.get_by_account_id(wework_account_id)
                        if account:
                            region = account.get("region")
                    if not region:
                        return []
                query = query.filter(SysWeworkAccount.region == region)
            # data_scope == 'all': 不加过滤

            rows = query.order_by(SysWeworkAccount.region, SysWeworkAccount.account_id).all()
            return [
                {
                    "account_id": r.account_id,
                    "account_name": r.account_name,
                    "corp_id": r.corp_id,
                    "region": r.region,
                    "agent_id": r.agent_id,
                    "is_active": r.is_active,
                    "created_at": r.created_at,
                    "updated_at": r.updated_at,
                }
                for r in rows
            ]

    @staticmethod
    def get_by_account_id(account_id: str) -> Optional[Dict]:
        """按 account_id 查询企微账户"""
        with session_scope() as session:
            row = (
                session.query(SysWeworkAccount)
                .filter(SysWeworkAccount.account_id == account_id)
                .first()
            )
            if not row:
                return None
            result = {
                "account_id": row.account_id,
                "account_name": row.account_name,
                "corp_id": row.corp_id,
                "corp_secret": row.corp_secret,
                "region": row.region,
                "agent_id": row.agent_id,
                "is_active": row.is_active,
                "created_at": row.created_at,
                "updated_at": row.updated_at,
            }
            if result.get("corp_secret"):
                result["corp_secret"] = decrypt_secret(result["corp_secret"])
            return result

    @staticmethod
    def get_active_by_account_id(account_id: str) -> Optional[Dict]:
        """查询启用的企微账户"""
        with session_scope() as session:
            row = (
                session.query(SysWeworkAccount)
                .filter(
                    SysWeworkAccount.account_id == account_id,
                    SysWeworkAccount.is_active.is_(True),
                )
                .first()
            )
            if not row:
                return None
            result = {
                "account_id": row.account_id,
                "account_name": row.account_name,
                "corp_id": row.corp_id,
                "corp_secret": row.corp_secret,
                "region": row.region,
                "agent_id": row.agent_id,
            }
            if result.get("corp_secret"):
                result["corp_secret"] = decrypt_secret(result["corp_secret"])
            return result

    @staticmethod
    def get_by_region(region: str) -> List[Dict]:
        """按区域查询企微账户"""
        with session_scope() as session:
            rows = (
                session.query(SysWeworkAccount)
                .filter(SysWeworkAccount.region == region)
                .order_by(SysWeworkAccount.account_id)
                .all()
            )
            return [
                {
                    "account_id": r.account_id,
                    "account_name": r.account_name,
                    "region": r.region,
                    "is_active": r.is_active,
                }
                for r in rows
            ]

    @staticmethod
    def get_regions() -> List[str]:
        """获取所有区域列表"""
        with session_scope() as session:
            rows = (
                session.query(SysWeworkAccount.region)
                .distinct()
                .order_by(SysWeworkAccount.region)
                .all()
            )
            return [r.region for r in rows]

    @staticmethod
    def get_corp_secret(account_id: str) -> Optional[str]:
        """获取企微 CorpSecret（解密后，用于调用企微 API）"""
        with session_scope() as session:
            row = (
                session.query(SysWeworkAccount.corp_secret)
                .filter(SysWeworkAccount.account_id == account_id)
                .first()
            )
            if not row or not row.corp_secret:
                return None
            return decrypt_secret(row.corp_secret)

    @staticmethod
    def create(
        account_id: str,
        account_name: str,
        corp_id: str,
        corp_secret: str,
        region: str,
        agent_id: Optional[str] = None,
        is_active: int = 1,
    ) -> bool:
        """新增企微账户（corp_secret 在此加密后入库）"""
        encrypted_secret = encrypt_secret(corp_secret)
        with session_scope(commit=True) as session:
            session.add(
                SysWeworkAccount(
                    account_id=account_id,
                    account_name=account_name,
                    corp_id=corp_id,
                    corp_secret=encrypted_secret,
                    region=region,
                    agent_id=agent_id,
                    is_active=bool(is_active),
                )
            )
            return True

    @staticmethod
    def update(
        account_id: str,
        account_name: Optional[str] = None,
        corp_secret: Optional[str] = None,
        region: Optional[str] = None,
        agent_id: Optional[str] = None,
        is_active: Optional[int] = None,
    ) -> bool:
        """更新企微账户（仅更新传入字段）"""
        with session_scope(commit=True) as session:
            row = (
                session.query(SysWeworkAccount)
                .filter(SysWeworkAccount.account_id == account_id)
                .first()
            )
            if not row:
                return False
            if account_name is not None:
                row.account_name = account_name
            if corp_secret is not None:
                row.corp_secret = encrypt_secret(corp_secret)
            if region is not None:
                row.region = region
            if agent_id is not None:
                row.agent_id = agent_id
            if is_active is not None:
                row.is_active = bool(is_active)
            return True

    @staticmethod
    def update_corp_secret(account_id: str, corp_secret: str) -> bool:
        """仅更新 CorpSecret（在此加密后入库）"""
        with session_scope(commit=True) as session:
            row = (
                session.query(SysWeworkAccount)
                .filter(SysWeworkAccount.account_id == account_id)
                .first()
            )
            if not row:
                return False
            row.corp_secret = encrypt_secret(corp_secret)
            return True

    @staticmethod
    def delete(account_id: str) -> bool:
        """删除企微账户（物理删除）"""
        with session_scope(commit=True) as session:
            row = (
                session.query(SysWeworkAccount)
                .filter(SysWeworkAccount.account_id == account_id)
                .first()
            )
            if not row:
                return False
            session.delete(row)
            return True

    @staticmethod
    def exists(account_id: str) -> bool:
        """检查企微账户是否存在"""
        with session_scope() as session:
            return (
                session.query(SysWeworkAccount)
                .filter(SysWeworkAccount.account_id == account_id)
                .first()
                is not None
            )

    @staticmethod
    def get_stats(account_id: str) -> Dict:
        """获取企微账户统计数据（V2.1）"""
        month_ago = datetime.now().date() - timedelta(days=30)
        with session_scope() as session:
            total_customers = (
                session.query(func.count(BizCustomer.id))
                .filter(BizCustomer.wework_account_id == account_id)
                .scalar()
            )
            total_orders = (
                session.query(func.count(BizOrder.id))
                .filter(BizOrder.wework_account_id == account_id)
                .scalar()
            )
            total_employees = (
                session.query(func.count(SysEmployee.id))
                .filter(SysEmployee.wework_account_id == account_id)
                .scalar()
            )
            monthly_messages = (
                session.query(func.count(MsgWxqyChat.id))
                .filter(
                    MsgWxqyChat.wework_account_id == account_id,
                    MsgWxqyChat.msg_date >= month_ago,
                )
                .scalar()
            )
            return {
                "total_customers": total_customers or 0,
                "total_orders": total_orders or 0,
                "total_employees": total_employees or 0,
                "monthly_messages": monthly_messages or 0,
            }

    @staticmethod
    def get_same_region_account_ids(account_id: str) -> List[str]:
        """获取与指定企微账户同区域的全部账户 ID（RAG 索引器用）"""
        if not account_id:
            return []
        with session_scope() as session:
            region_subq = (
                select(SysWeworkAccount.region)
                .where(SysWeworkAccount.account_id == account_id)
                .scalar_subquery()
            )
            rows = (
                session.query(SysWeworkAccount.account_id)
                .filter(SysWeworkAccount.region == region_subq)
                .all()
            )
            return [r.account_id for r in rows]
