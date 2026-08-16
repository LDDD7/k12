"""
客户画像 DAO — 操作 ai_customer_profile + ai_profile_item 表（SQLAlchemy ORM）
支持：
- 草稿 → 确认流转
- embedding_status 管理（pending / indexed / stale）
- 画像字段项批量管理
- 三维度权限过滤
"""

from typing import Optional, List, Dict, Any
from datetime import datetime

from sqlalchemy import func, case, delete, update

from k12_app.backend.dao.db import session_scope
from k12_app.backend.dao.base_dao import apply_scope_conditions
from k12_app.backend.models import AiCustomerProfile, AiProfileItem


def _profile_dict(r: AiCustomerProfile) -> Dict:
    return {
        "id": r.id,
        "external_id": r.external_id,
        "wework_account_id": r.wework_account_id,
        "follow_user_id": r.follow_user_id,
        "status": r.status,
        "confirmed_by": r.confirmed_by,
        "confirmed_at": r.confirmed_at,
        "embedding_status": r.embedding_status,
        "created_at": r.created_at,
        "updated_at": r.updated_at,
    }


class ProfileDAO:
    """客户画像数据访问"""

    # ==================== 画像主表操作 ====================

    @staticmethod
    def get_by_external_id(
        external_id: str,
        user_id: str,
        data_scope: str,
        wework_account_id: Optional[str],
    ) -> Optional[Dict]:
        """按客户 ID 查询画像（带权限过滤）"""
        with session_scope() as session:
            query = session.query(AiCustomerProfile).filter(
                AiCustomerProfile.external_id == external_id
            )
            query = apply_scope_conditions(
                query=query,
                model=AiCustomerProfile,
                data_scope=data_scope,
                user_id=user_id,
                wework_account_id=wework_account_id,
                owner_field="follow_user_id",
            )
            r = query.order_by(AiCustomerProfile.id.desc()).limit(1).first()
            return _profile_dict(r) if r else None

    @staticmethod
    def get_by_id(
        profile_id: int,
        user_id: str,
        data_scope: str,
        wework_account_id: Optional[str],
    ) -> Optional[Dict]:
        """按画像 ID 查询（带权限过滤）"""
        with session_scope() as session:
            query = session.query(AiCustomerProfile).filter(
                AiCustomerProfile.id == profile_id
            )
            query = apply_scope_conditions(
                query=query,
                model=AiCustomerProfile,
                data_scope=data_scope,
                user_id=user_id,
                wework_account_id=wework_account_id,
                owner_field="follow_user_id",
            )
            r = query.first()
            return _profile_dict(r) if r else None

    @staticmethod
    def get_by_follow_user(
        follow_user_id: str,
        user_id: str,
        data_scope: str,
        wework_account_id: Optional[str],
        status: Optional[str] = None,
    ) -> List[Dict]:
        """查询某顾问名下的所有画像"""
        with session_scope() as session:
            query = session.query(AiCustomerProfile).filter(
                AiCustomerProfile.follow_user_id == follow_user_id
            )
            if status:
                query = query.filter(AiCustomerProfile.status == status)
            query = apply_scope_conditions(
                query=query,
                model=AiCustomerProfile,
                data_scope=data_scope,
                user_id=user_id,
                wework_account_id=wework_account_id,
                owner_field="follow_user_id",
            )
            rows = query.order_by(AiCustomerProfile.updated_at.desc()).all()
            return [_profile_dict(r) for r in rows]

    @staticmethod
    def get_by_embedding_status(
        embedding_status: str,
        user_id: str,
        data_scope: str,
        wework_account_id: Optional[str],
        limit: int = 100,
    ) -> List[Dict]:
        """按向量化状态查询画像（用于异步同步任务）"""
        with session_scope() as session:
            query = session.query(AiCustomerProfile).filter(
                AiCustomerProfile.embedding_status == embedding_status,
                AiCustomerProfile.status == "已确认",
            )
            query = apply_scope_conditions(
                query=query,
                model=AiCustomerProfile,
                data_scope=data_scope,
                user_id=user_id,
                wework_account_id=wework_account_id,
                owner_field="follow_user_id",
            )
            rows = (
                query.order_by(AiCustomerProfile.updated_at.asc())
                .limit(limit)
                .all()
            )
            return [
                {
                    "id": r.id,
                    "external_id": r.external_id,
                    "wework_account_id": r.wework_account_id,
                    "follow_user_id": r.follow_user_id,
                    "status": r.status,
                    "embedding_status": r.embedding_status,
                }
                for r in rows
            ]

    @staticmethod
    def get_indexable_profiles() -> List[Dict]:
        """获取待向量化的已确认画像（RAG 索引器用，无权限过滤、无分页）"""
        with session_scope() as session:
            rows = (
                session.query(AiCustomerProfile)
                .filter(
                    AiCustomerProfile.status == "已确认",
                    AiCustomerProfile.embedding_status.in_(["pending", "stale"]),
                )
                .order_by(AiCustomerProfile.updated_at.asc())
                .all()
            )
            return [
                {
                    "id": r.id,
                    "external_id": r.external_id,
                    "follow_user_id": r.follow_user_id,
                    "wework_account_id": r.wework_account_id,
                }
                for r in rows
            ]

    @staticmethod
    def get_pending_embeddings(
        user_id: str,
        data_scope: str,
        wework_account_id: Optional[str],
        limit: int = 100,
    ) -> List[Dict]:
        """获取待向量化的画像（pending 状态）"""
        return ProfileDAO.get_by_embedding_status("pending", user_id, data_scope, wework_account_id, limit)

    @staticmethod
    def get_stale_embeddings(
        user_id: str,
        data_scope: str,
        wework_account_id: Optional[str],
        limit: int = 100,
    ) -> List[Dict]:
        """获取需要重建向量的画像（stale 状态）"""
        return ProfileDAO.get_by_embedding_status("stale", user_id, data_scope, wework_account_id, limit)

    @staticmethod
    def get_confirmed_count(
        user_id: str,
        data_scope: str,
        wework_account_id: Optional[str],
    ) -> int:
        """获取已确认画像数量（用于向量索引状态统计）"""
        with session_scope() as session:
            query = session.query(AiCustomerProfile).filter(
                AiCustomerProfile.status == "已确认"
            )
            query = apply_scope_conditions(
                query=query,
                model=AiCustomerProfile,
                data_scope=data_scope,
                user_id=user_id,
                wework_account_id=wework_account_id,
                owner_field="follow_user_id",
            )
            return query.count()

    @staticmethod
    def get_embedding_status_stats(
        user_id: str,
        data_scope: str,
        wework_account_id: Optional[str],
    ) -> Dict:
        """获取向量化状态统计（用于监控）"""
        with session_scope() as session:
            query = (
                session.query(
                    func.count(AiCustomerProfile.id).label("total"),
                    func.sum(case((AiCustomerProfile.embedding_status == "pending", 1), else_=0)).label("pending"),
                    func.sum(case((AiCustomerProfile.embedding_status == "indexed", 1), else_=0)).label("indexed"),
                    func.sum(case((AiCustomerProfile.embedding_status == "stale", 1), else_=0)).label("stale"),
                )
                .filter(AiCustomerProfile.status == "已确认")
            )
            query = apply_scope_conditions(
                query=query,
                model=AiCustomerProfile,
                data_scope=data_scope,
                user_id=user_id,
                wework_account_id=wework_account_id,
                owner_field="follow_user_id",
            )
            r = query.first()
            return {
                "total": int(r.total or 0),
                "pending": int(r.pending or 0),
                "indexed": int(r.indexed or 0),
                "stale": int(r.stale or 0),
            }

    @staticmethod
    def create_draft(
        external_id: str,
        follow_user_id: str,
        wework_account_id: str,
        items: List[Dict[str, Any]],
    ) -> Optional[int]:
        """
        创建画像草稿（含字段项）
        items: [{"item_name": "...", "item_value": "...", "confidence": 0.9, "confidence_level": "高", "source_type": "企微会话", "source_ref": "msg_001"}]
        """
        with session_scope(commit=True) as session:
            # 1. 检查是否已有草稿，有则更新，无则创建
            existing = (
                session.query(AiCustomerProfile)
                .filter(
                    AiCustomerProfile.external_id == external_id,
                    AiCustomerProfile.status == "草稿",
                )
                .first()
            )

            if existing:
                profile_id = existing.id
                existing.updated_at = datetime.now()
                session.execute(
                    delete(AiProfileItem).where(AiProfileItem.profile_id == profile_id)
                )
            else:
                obj = AiCustomerProfile(
                    external_id=external_id,
                    follow_user_id=follow_user_id,
                    wework_account_id=wework_account_id,
                    status="草稿",
                    embedding_status="pending",
                )
                session.add(obj)
                session.flush()
                profile_id = obj.id

            # 2. 插入字段项
            for item in items:
                session.add(
                    AiProfileItem(
                        profile_id=profile_id,
                        item_name=item.get("item_name"),
                        item_value=item.get("item_value"),
                        confidence=item.get("confidence"),
                        confidence_level=item.get("confidence_level"),
                        source_type=item.get("source_type"),
                        source_ref=item.get("source_ref"),
                    )
                )

            return profile_id

    @staticmethod
    def confirm(
        profile_id: int,
        confirmed_by: str,
        embedding_status: str = "pending",
    ) -> bool:
        """确认画像（草稿 → 已确认）"""
        with session_scope(commit=True) as session:
            result = session.execute(
                update(AiCustomerProfile)
                .where(AiCustomerProfile.id == profile_id, AiCustomerProfile.status == "草稿")
                .values(
                    status="已确认",
                    confirmed_by=confirmed_by,
                    confirmed_at=datetime.now(),
                    embedding_status=embedding_status,
                )
            )
            return result.rowcount > 0

    @staticmethod
    def discard(profile_id: int) -> bool:
        """放弃草稿（删除草稿）"""
        with session_scope(commit=True) as session:
            # 先删除字段项
            session.execute(delete(AiProfileItem).where(AiProfileItem.profile_id == profile_id))
            # 再删除画像
            result = session.execute(
                delete(AiCustomerProfile).where(
                    AiCustomerProfile.id == profile_id,
                    AiCustomerProfile.status == "草稿",
                )
            )
            return result.rowcount > 0

    @staticmethod
    def update_embedding_status(profile_id: int, embedding_status: str) -> bool:
        """更新向量化状态（V3.1）"""
        with session_scope(commit=True) as session:
            result = session.execute(
                update(AiCustomerProfile)
                .where(AiCustomerProfile.id == profile_id)
                .values(embedding_status=embedding_status)
            )
            return result.rowcount > 0

    @staticmethod
    def mark_embedding_stale(external_id: str) -> bool:
        """标记画像向量为 stale（画像变更后调用）"""
        with session_scope(commit=True) as session:
            result = session.execute(
                update(AiCustomerProfile)
                .where(AiCustomerProfile.external_id == external_id)
                .values(embedding_status="stale")
            )
            return result.rowcount > 0

    @staticmethod
    def batch_update_embedding_status(profile_ids: List[int], embedding_status: str) -> int:
        """批量更新向量化状态"""
        if not profile_ids:
            return 0
        with session_scope(commit=True) as session:
            result = session.execute(
                update(AiCustomerProfile)
                .where(AiCustomerProfile.id.in_(profile_ids))
                .values(embedding_status=embedding_status)
            )
            return result.rowcount

    @staticmethod
    def delete(external_id: str) -> bool:
        """删除客户画像（物理删除）"""
        with session_scope(commit=True) as session:
            row = (
                session.query(AiCustomerProfile)
                .filter(AiCustomerProfile.external_id == external_id)
                .first()
            )
            if not row:
                return False
            session.execute(
                delete(AiProfileItem).where(AiProfileItem.profile_id == row.id)
            )
            session.execute(
                delete(AiCustomerProfile).where(AiCustomerProfile.external_id == external_id)
            )
            return True

    # ==================== 画像字段项操作 ====================

    @staticmethod
    def get_items(profile_id: int) -> List[Dict]:
        """查询画像的所有字段项"""
        with session_scope() as session:
            rows = (
                session.query(AiProfileItem)
                .filter(AiProfileItem.profile_id == profile_id)
                .order_by(AiProfileItem.item_name)
                .all()
            )
            return [
                {
                    "id": r.id,
                    "profile_id": r.profile_id,
                    "item_name": r.item_name,
                    "item_value": r.item_value,
                    "confidence": r.confidence,
                    "confidence_level": r.confidence_level,
                    "source_type": r.source_type,
                    "source_ref": r.source_ref,
                    "created_at": r.created_at,
                    "updated_at": r.updated_at,
                }
                for r in rows
            ]

    @staticmethod
    def get_item_by_name(profile_id: int, item_name: str) -> Optional[Dict]:
        """按字段名查询单个字段项"""
        with session_scope() as session:
            r = (
                session.query(AiProfileItem)
                .filter(
                    AiProfileItem.profile_id == profile_id,
                    AiProfileItem.item_name == item_name,
                )
                .first()
            )
            if not r:
                return None
            return {
                "id": r.id,
                "profile_id": r.profile_id,
                "item_name": r.item_name,
                "item_value": r.item_value,
                "confidence": r.confidence,
                "confidence_level": r.confidence_level,
                "source_type": r.source_type,
                "source_ref": r.source_ref,
            }
