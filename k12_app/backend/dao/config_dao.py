"""
全局 AI 配置 DAO — 操作 sys_ai_config 表 + Redis 缓存（V3.3 二期新增）

用于「全局关停开关」等 key-value 配置：
- 写入：更新 DB 并同步清 Redis 缓存（秒级生效，无需改代码/重启/发版）
- 读取：优先 Redis 缓存（TTL 60s），未命中回源 DB
"""
import logging
from typing import Optional, Dict, List

from k12_app.backend.dao.db import session_scope
from k12_app.backend.cache.redis_client import redis_client
from k12_app.backend.models import SysAiConfig

logger = logging.getLogger(__name__)

# Redis 缓存键前缀
_CONFIG_CACHE_PREFIX = "ai:config:"
_CONFIG_CACHE_TTL = 60  # 秒；回源 DB 后缓存，保证秒级生效的同时避免每次打 DB


class ConfigDAO:
    """全局 AI 配置数据访问"""

    @staticmethod
    def get_config(cfg_key: str, default: Optional[str] = None) -> Optional[str]:
        """读取配置（Redis 优先，回源 DB）"""
        # 1. Redis 缓存
        cache_key = _CONFIG_CACHE_PREFIX + cfg_key
        try:
            cached = redis_client.get(cache_key)
            if cached is not None:
                return cached
        except Exception as e:
            logger.warning(f"读取配置缓存失败 cfg_key={cfg_key}: {e}")

        # 2. 回源 DB
        try:
            with session_scope() as session:
                row = (
                    session.query(SysAiConfig)
                    .filter(SysAiConfig.cfg_key == cfg_key)
                    .first()
                )
                value = row.cfg_value if row else default
        except Exception as e:
            # DB 不可用/表未迁移时降级返回默认值，保证开关读取永不阻断 AI 主流程
            logger.warning(f"读取配置回源 DB 失败 cfg_key={cfg_key}: {e}")
            value = default

        # 3. 写回缓存（含默认值，避免每次打 DB）
        if value is not None:
            try:
                redis_client.setex(cache_key, _CONFIG_CACHE_TTL, value)
            except Exception as e:
                logger.warning(f"写入配置缓存失败 cfg_key={cfg_key}: {e}")
        return value

    @staticmethod
    def set_config(
        cfg_key: str,
        cfg_value: str,
        cfg_desc: Optional[str] = None,
        updated_by: Optional[str] = None,
    ) -> bool:
        """写入配置（upsert），同步清 Redis 缓存实现秒级生效"""
        try:
            with session_scope(commit=True) as session:
                row = (
                    session.query(SysAiConfig)
                    .filter(SysAiConfig.cfg_key == cfg_key)
                    .first()
                )
                if row:
                    row.cfg_value = cfg_value
                    if cfg_desc is not None:
                        row.cfg_desc = cfg_desc
                    row.updated_by = updated_by
                else:
                    session.add(
                        SysAiConfig(
                            cfg_key=cfg_key,
                            cfg_value=cfg_value,
                            cfg_desc=cfg_desc,
                            updated_by=updated_by,
                        )
                    )
        except Exception as e:
            # DB 不可用/表未迁移时仅告警，不阻断管理操作
            logger.warning(f"写入配置失败 cfg_key={cfg_key}: {e}")
            return False
        # 清缓存，让新值立即生效
        try:
            redis_client.delete(_CONFIG_CACHE_PREFIX + cfg_key)
        except Exception as e:
            logger.warning(f"清除配置缓存失败 cfg_key={cfg_key}: {e}")
        return True

    @staticmethod
    def get_all_configs() -> List[Dict]:
        """读取全部配置（管理后台展示用）"""
        try:
            with session_scope() as session:
                rows = session.query(SysAiConfig).order_by(SysAiConfig.cfg_key).all()
                return [
                    {
                        "cfg_key": r.cfg_key,
                        "cfg_value": r.cfg_value,
                        "cfg_desc": r.cfg_desc,
                        "updated_by": r.updated_by,
                        "updated_at": r.updated_at,
                    }
                    for r in rows
                ]
        except Exception as e:
            logger.warning(f"读取全部配置失败: {e}")
            return []

    # ==================== 二期专用便捷方法 ====================

    @staticmethod
    def is_reasoning_enabled() -> bool:
        """综合推理全局开关（默认开启）"""
        value = ConfigDAO.get_config("ai_reasoning_enabled", "true")
        return str(value).strip().lower() in ("true", "1", "yes", "on")

    @staticmethod
    def get_reasoning_max_steps() -> int:
        """综合推理最大步数上限（默认 3）"""
        try:
            return max(1, min(5, int(ConfigDAO.get_config("ai_reasoning_max_steps", "3"))))
        except (TypeError, ValueError):
            return 3

    @staticmethod
    def get_kb_min_score() -> float:
        """知识库检索匹配度门槛（低于该值视为未命中，走兜底话术，默认 0.62）"""
        try:
            return float(ConfigDAO.get_config("ai_reasoning_min_score", "0.62"))
        except (TypeError, ValueError):
            return 0.62
