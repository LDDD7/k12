"""
画像服务 — AI 画像生成与管理
生成/确认/重新生成客户 360 度画像
画像 → 确认后写入 ai_customer_profile + ai_profile_item，异步生成向量索引
详见系统设计文档 四、AI 任务编排 + 数据库设计文档 3.11/3.12
"""
# k12_app/services/profile_service.py
"""
画像服务 — 画像确认/保存/向量化触发
"""

import logging
from typing import Optional, Dict, Any

from k12_app.backend.dao.profile_dao import ProfileDAO
from k12_app.backend.dao.task_log_dao import TaskLogDAO

logger = logging.getLogger(__name__)


class ProfileService:
    """画像服务"""

    @staticmethod
    def confirm_profile(
        external_id: str,
        follow_user_id: str,
        wework_account_id: str,
        profile_data: list,
        confirmed_by: str,
    ) -> Optional[int]:
        """
        确认画像 → 保存到数据库 → 触发向量化

        Args:
            external_id: 客户 ID
            follow_user_id: 顾问 ID
            wework_account_id: 企微账户 ID
            profile_data: 画像字段列表
            confirmed_by: 确认人 user_id

        Returns:
            profile_id 或 None
        """
        try:
            # 1. 创建草稿
            profile_id = ProfileDAO.create_draft(
                external_id=external_id,
                follow_user_id=follow_user_id,
                wework_account_id=wework_account_id,
                items=profile_data,
            )

            if not profile_id:
                logger.error(f"创建画像草稿失败: {external_id}")
                return None

            # 2. 确认画像
            success = ProfileDAO.confirm(profile_id, confirmed_by, embedding_status="pending")
            if not success:
                logger.error(f"确认画像失败: {profile_id}")
                return None

            # 3. 记录埋点
            TaskLogDAO.log_task(
                task_type="profile",
                user_id=follow_user_id,
                external_id=external_id,
                wework_account_id=wework_account_id,
                action="confirmed",
                action_detail={"profile_id": profile_id, "item_count": len(profile_data)},
            )

            logger.info(f"画像确认成功: external_id={external_id}, profile_id={profile_id}")

            # 4. 实时推送画像变更通知：订阅该客户画像流的 SSE 客户端自动刷新
            try:
                from k12_app.backend.services.event_bus import EventBus
                EventBus.publish(f"profile_update:{external_id}", {
                    "external_id": external_id,
                    "event": "profile_confirmed",
                    "profile_id": profile_id,
                    "confirmed_by": confirmed_by,
                })
            except Exception as e:
                logger.warning(f"推送画像变更通知失败: {e}")

            # 5. 触发异步向量化（这里由调用方决定是否立即执行）
            # 可由 M5 的定时任务或异步任务处理
            # ProfileDAO.update_embedding_status(profile_id, "pending")

            return profile_id

        except Exception as e:
            logger.error(f"确认画像异常: {e}", exc_info=True)
            return None

    @staticmethod
    def confirm_existing(
        external_id: str,
        confirmed_by: str,
        user_id: str,
        data_scope: str,
        wework_account_id: str,
    ) -> Optional[int]:
        """直接确认某客户最新画像草稿（无需中断上下文）

        Returns:
            已确认/已存在的 profile_id，或 None
        """
        profile = ProfileService.get_profile(external_id, user_id, data_scope, wework_account_id)
        if not profile:
            return None
        if profile["status"] == "已确认":
            return profile["id"]

        ok = ProfileDAO.confirm(profile["id"], confirmed_by, embedding_status="pending")
        if not ok:
            logger.error(f"直接确认画像失败: profile_id={profile['id']}")
            return None

        logger.info(f"画像直接确认成功: external_id={external_id}, profile_id={profile['id']}, confirmed_by={confirmed_by}")

        try:
            from k12_app.backend.services.event_bus import EventBus
            EventBus.publish(f"profile_update:{external_id}", {
                "external_id": external_id,
                "event": "profile_confirmed",
                "profile_id": profile["id"],
                "confirmed_by": confirmed_by,
            })
        except Exception as e:
            logger.warning(f"推送画像变更通知失败: {e}")

        TaskLogDAO.log_task(
            task_type="profile",
            user_id=profile["follow_user_id"],
            external_id=external_id,
            wework_account_id=profile.get("wework_account_id", ""),
            action="confirmed",
            action_detail={"profile_id": profile["id"], "item_count": 0},
        )
        return profile["id"]

    @staticmethod
    def get_profile(external_id: str, user_id: str, data_scope: str, wework_account_id: str) -> Optional[Dict]:
        """获取客户画像"""
        return ProfileDAO.get_by_external_id(external_id, user_id, data_scope, wework_account_id)

    @staticmethod
    def get_profile_items(profile_id: int) -> list:
        """获取画像字段项"""
        return ProfileDAO.get_items(profile_id)