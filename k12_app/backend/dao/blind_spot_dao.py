"""
AI 盲区数据 DAO — 操作 ai_blind_spot_log 表（V3.3 二期新增）

盲区数据 = AI 走兜底 / 推理失败 / 未命中时自动记录的原始问题，
反哺资料库内容补充与推理逻辑优化（数据闭环）。
"""
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, List

from sqlalchemy import func, case

from k12_app.backend.dao.db import session_scope
from k12_app.backend.models import AiBlindSpotLog

logger = logging.getLogger(__name__)

VALID_SCENE_TYPES = {"fallback", "reasoning_failed", "not_found"}


class BlindSpotDAO:
    """AI 盲区数据访问"""

    @staticmethod
    def log_blind_spot(
        original_question: str,
        scene_type: str,
        kb_types: Optional[str] = None,
        matched_text: Optional[str] = None,
        advisor_name: Optional[str] = None,
        user_id: Optional[str] = None,
        external_id: Optional[str] = None,
        wework_account_id: Optional[str] = None,
        task_log_id: Optional[int] = None,
    ) -> Optional[int]:
        """记录一条盲区数据"""
        if scene_type not in VALID_SCENE_TYPES:
            raise ValueError(f"无效的 scene_type: {scene_type}，允许值: {VALID_SCENE_TYPES}")

        with session_scope(commit=True) as session:
            obj = AiBlindSpotLog(
                original_question=(original_question or "")[:2000],
                scene_type=scene_type,
                kb_types=kb_types,
                matched_text=(matched_text or "")[:4000] if matched_text else None,
                advisor_name=advisor_name,
                user_id=user_id,
                external_id=external_id,
                wework_account_id=wework_account_id,
                task_log_id=task_log_id,
            )
            session.add(obj)
            session.flush()
            return obj.id

    @staticmethod
    def get_blind_spots(
        scene_type: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Dict:
        """查询盲区数据（管理后台）"""
        with session_scope() as session:
            query = session.query(AiBlindSpotLog)
            if scene_type:
                query = query.filter(AiBlindSpotLog.scene_type == scene_type)
            if start_date:
                query = query.filter(AiBlindSpotLog.created_at >= start_date)
            if end_date:
                query = query.filter(AiBlindSpotLog.created_at <= end_date)

            total = session.query(func.count()).select_from(query.subquery()).scalar()
            rows = (
                query.order_by(AiBlindSpotLog.created_at.desc())
                .limit(page_size)
                .offset((page - 1) * page_size)
                .all()
            )
            items = [
                {
                    "id": r.id,
                    "original_question": r.original_question,
                    "scene_type": r.scene_type,
                    "kb_types": r.kb_types,
                    "matched_text": r.matched_text,
                    "advisor_name": r.advisor_name,
                    "user_id": r.user_id,
                    "external_id": r.external_id,
                    "wework_account_id": r.wework_account_id,
                    "task_log_id": r.task_log_id,
                    "created_at": r.created_at,
                }
                for r in rows
            ]
            return {"items": items, "total": total, "page": page, "page_size": page_size}

    @staticmethod
    def get_blind_spot_stats(days: int = 30) -> Dict:
        """盲区统计：按场景类型计数（管理后台看板）"""
        cutoff = datetime.now() - timedelta(days=days)
        with session_scope() as session:
            rows = (
                session.query(
                    AiBlindSpotLog.scene_type,
                    func.count(AiBlindSpotLog.id).label("cnt"),
                )
                .filter(AiBlindSpotLog.created_at >= cutoff)
                .group_by(AiBlindSpotLog.scene_type)
                .all()
            )
            stats = {r.scene_type: int(r.cnt) for r in rows}
            return {
                "days": days,
                "fallback": stats.get("fallback", 0),
                "reasoning_failed": stats.get("reasoning_failed", 0),
                "not_found": stats.get("not_found", 0),
                "total": sum(stats.values()),
            }
