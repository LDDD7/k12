"""
标签服务 — AI 标签推荐与确认 + 标签体系管理
分析客户行为 → 推荐添加/移除标签 → 顾问确认后同步企微
"""

import logging
from typing import Optional, List, Dict

from k12_app.backend.dao.customer_dao import CustomerDAO
from k12_app.backend.dao.tag_dao import TagDAO
from k12_app.backend.dao.task_log_dao import TaskLogDAO
from k12_app.backend.agent.tools import sync_tag

logger = logging.getLogger(__name__)


class TagService:
    """标签服务"""

    @staticmethod
    def confirm_tags(
        external_id: str,
        user_id: str,
        wework_account_id: str,
        tag_ids: List[str],
        confirmed_by: str,
        sync_to_wework: bool = True,
    ) -> bool:
        """
        确认标签 → 写入 biz_customer_tag → 同步企微

        Args:
            external_id: 客户 ID
            user_id: 顾问 ID
            wework_account_id: 企微账户 ID
            tag_ids: 标签 ID 列表
            confirmed_by: 确认人
            sync_to_wework: 是否同步到企微

        Returns:
            是否成功
        """
        try:
            for tag_id in tag_ids:
                # 添加标签到客户
                CustomerDAO.add_tag(
                    external_id=external_id,
                    tag_id=tag_id,
                    source="AI 推荐",
                    confirmed=True,
                    confirmed_by=confirmed_by,
                )

                # 同步到企微
                if sync_to_wework:
                    sync_tag(wework_account_id, external_id, tag_id, "add")

            # 记录埋点
            TaskLogDAO.log_task(
                task_type="tag",
                user_id=user_id,
                external_id=external_id,
                wework_account_id=wework_account_id,
                action="confirmed",
                action_detail={"tag_ids": tag_ids, "synced": sync_to_wework},
            )

            logger.info(f"标签确认成功: external_id={external_id}, tags={tag_ids}")
            return True

        except Exception as e:
            logger.error(f"确认标签异常: {e}", exc_info=True)
            return False

    @staticmethod
    def remove_tag(
        external_id: str,
        tag_id: str,
        wework_account_id: Optional[str] = None,
        sync_to_wework: bool = True,
    ) -> bool:
        """移除客户标签"""
        try:
            CustomerDAO.remove_tag(external_id, tag_id)
            if sync_to_wework and wework_account_id:
                sync_tag(wework_account_id, external_id, tag_id, "remove")
            return True
        except Exception as e:
            logger.error(f"移除标签异常: {e}", exc_info=True)
            return False

    # ==================== 标签体系管理（管理后台） ====================

    @staticmethod
    def get_tags_by_scope(
        user_id: str,
        data_scope: str,
        wework_account_id: Optional[str],
    ) -> List[Dict]:
        """获取标签体系（按权限范围过滤）"""
        return TagDAO.get_tags_by_scope(user_id, data_scope, wework_account_id)

    @staticmethod
    def get_all_tags() -> List[Dict]:
        """获取全量标签体系"""
        return TagDAO.get_all_tags()

    @staticmethod
    def get_tag_by_id(tag_id: str) -> Optional[Dict]:
        """按标签 ID 查询"""
        return TagDAO.get_tag_by_id(tag_id)

    @staticmethod
    def create_tag(
        tag_id: str,
        tag_name: str,
        group_id: str,
        ai_rule: Optional[str] = None,
    ) -> bool:
        """新建标签定义"""
        return TagDAO.create_tag(
            tag_id=tag_id,
            tag_name=tag_name,
            group_id=group_id,
            ai_rule=ai_rule,
        )

    @staticmethod
    def update_tag(
        tag_id: str,
        tag_name: Optional[str] = None,
        group_id: Optional[str] = None,
        ai_rule: Optional[str] = None,
        sop_template_id: Optional[int] = None,
    ) -> bool:
        """更新标签定义"""
        return TagDAO.update_tag(
            tag_id=tag_id,
            tag_name=tag_name,
            group_id=group_id,
            ai_rule=ai_rule,
            sop_template_id=sop_template_id,
        )

    @staticmethod
    def delete_tag(tag_id: str, soft: bool = True) -> bool:
        """删除标签"""
        return TagDAO.delete_tag(tag_id, soft=soft)

    @staticmethod
    def get_sop_templates() -> List[Dict]:
        """获取 SOP 模板列表"""
        return TagDAO.get_sop_templates()

    @staticmethod
    def get_customers_by_tag(
        tag_id: str,
        user_id: str,
        data_scope: str,
        wework_account_id: Optional[str],
    ) -> List[Dict]:
        """按标签查询关联客户列表"""
        return TagDAO.get_customers_by_tag(
            tag_id=tag_id,
            user_id=user_id,
            data_scope=data_scope,
            wework_account_id=wework_account_id,
        )

    @staticmethod
    def get_customer_tags(
        external_id: str,
        user_id: str,
        data_scope: str,
        wework_account_id: Optional[str],
    ) -> List[Dict]:
        """查询客户全部标签"""
        return TagDAO.get_customer_tags(
            external_id=external_id,
            user_id=user_id,
            data_scope=data_scope,
            wework_account_id=wework_account_id,
        )

    @staticmethod
    def get_tag_stats(
        user_id: str,
        data_scope: str,
        wework_account_id: Optional[str],
    ) -> List[Dict]:
        """标签使用统计报表"""
        return TagDAO.get_tag_stats(
            user_id=user_id,
            data_scope=data_scope,
            wework_account_id=wework_account_id,
        )