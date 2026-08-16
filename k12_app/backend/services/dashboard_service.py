"""
看板服务 — 数据看板统计
转化漏斗 / AI 采纳率 / 线索来源转化统计（V3.1）
详见接口设计文档 4.13 - 4.14 + 5.2.6
"""
# k12_app/services/dashboard_service.py
"""
看板服务 — 聚合统计数据
"""

import logging
from typing import Optional, Dict, Any

from k12_app.backend.dao.task_log_dao import TaskLogDAO
from k12_app.backend.dao.customer_dao import CustomerDAO
from k12_app.backend.dao.order_dao import OrderDAO
from k12_app.backend.dao.follow_up_dao import FollowUpDAO

logger = logging.getLogger(__name__)


class DashboardService:
    """看板数据服务"""

    @staticmethod
    def get_adopt_rate(
        user_id: str,
        data_scope: str,
        wework_account_id: Optional[str],
        days: int = 30,
    ) -> Dict[str, Any]:
        """获取 AI 采纳率"""
        return TaskLogDAO.get_adopt_rate(user_id, data_scope, wework_account_id, days)

    @staticmethod
    def get_adopt_rate_by_task_type(
        user_id: str,
        data_scope: str,
        wework_account_id: Optional[str],
        days: int = 30,
    ) -> list:
        """按任务类型获取采纳率"""
        return TaskLogDAO.get_adopt_rate_by_task_type(user_id, data_scope, wework_account_id, days)

    @staticmethod
    def get_lead_source_stats(
        user_id: str,
        data_scope: str,
        wework_account_id: Optional[str],
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> list:
        """获取线索来源统计（V3.1）"""
        return CustomerDAO.get_lead_source_stats(user_id, data_scope, wework_account_id, start_date, end_date)

    @staticmethod
    def get_funnel_stats(
        user_id: str,
        data_scope: str,
        wework_account_id: Optional[str],
    ) -> Dict[str, Any]:
        """获取转化漏斗数据"""
        from k12_app.backend.dao.customer_dao import CustomerDAO

        result = CustomerDAO.get_list(
            user_id=user_id,
            data_scope=data_scope,
            wework_account_id=wework_account_id,
            page=1,
            page_size=1,
        )
        # 获取各阶段统计
        stages = ["潜在", "高意向", "试听", "在读"]
        stats = {}
        for stage in stages:
            r = CustomerDAO.get_list(
                user_id=user_id,
                data_scope=data_scope,
                wework_account_id=wework_account_id,
                stage=stage,
                page=1,
                page_size=1,
            )
            stats[stage] = r.get("total", 0)

        return {
            "steps": [
                {"name": "潜在", "count": stats.get("潜在", 0)},
                {"name": "高意向", "count": stats.get("高意向", 0)},
                {"name": "试听", "count": stats.get("试听", 0)},
                {"name": "在读", "count": stats.get("在读", 0)},
            ],
            "conversion_rate": DashboardService._calc_conversion_rate(stats),
        }

    @staticmethod
    def _calc_conversion_rate(stats: Dict[str, int]) -> float:
        """计算转化率"""
        potential = stats.get("潜在", 0)
        enrolled = stats.get("在读", 0)
        if potential == 0:
            return 0.0
        return round(100.0 * enrolled / potential, 1)

    @staticmethod
    def get_order_stats(
        user_id: str,
        data_scope: str,
        wework_account_id: Optional[str],
    ) -> Dict[str, Any]:
        """获取订单统计"""
        return OrderDAO.get_stats(user_id, data_scope, wework_account_id)

    @staticmethod
    def get_renewal_rate(
        user_id: str,
        data_scope: str,
        wework_account_id: Optional[str],
    ) -> Dict[str, Any]:
        """获取续费率（5.5）"""
        return OrderDAO.get_renewal_rate(user_id, data_scope, wework_account_id)

    @staticmethod
    def get_advisor_efficiency(
        user_id: str,
        data_scope: str,
        wework_account_id: Optional[str],
        limit: int = 5,
    ) -> list:
        """获取顾问人效 TOP N（5.5）"""
        return OrderDAO.get_advisor_efficiency(user_id, data_scope, wework_account_id, limit)