"""
数据库基础设施 — SQLAlchemy ORM（唯一数据访问路径）

- SQLAlchemy 2.0 engine + sessionmaker：DAO 层统一走 ORM（session_scope）
- 已移除 PyMySQL + DBUtils 兼容层（get_connection/get_cursor），
  测试脚本直接使用 session_scope 做落库断言。

配置统一从 config.settings 读取（.env 由 config.py 加载，不修改 .env 内容）。
"""

import logging
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from k12_app.backend.config import settings

logger = logging.getLogger("dao.db")

# ============================================================
# SQLAlchemy ORM 基础设施
# ============================================================

DB_HOST = settings.DB_HOST
DB_PORT = settings.DB_PORT
DB_USER = settings.DB_USER
DB_PASSWORD = settings.DB_PASSWORD
DB_NAME = settings.DB_NAME

DATABASE_URL = (
    f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    "?charset=utf8mb4"
)

engine = create_engine(
    DATABASE_URL,
    pool_size=20,
    max_overflow=10,
    pool_pre_ping=True,
    pool_recycle=3600,
    echo=False,
)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    expire_on_commit=False,
    class_=Session,
)


class Base(DeclarativeBase):
    """所有 ORM 模型的公共基类"""


def get_session() -> Session:
    """获取一个新的 ORM 会话"""
    return SessionLocal()


@contextmanager
def session_scope(commit: bool = False) -> Generator[Session, None, None]:
    """
    ORM 会话上下文管理器，自动处理 commit/rollback/close。

    用法:
        with session_scope() as session:
            rows = session.query(SomeModel).all()
            return rows

        with session_scope(commit=True) as session:
            session.add(obj)
    """
    session = SessionLocal()
    try:
        yield session
        if commit:
            session.commit()
            logger.debug("ORM commit OK")
    except Exception as e:
        session.rollback()
        logger.error("ORM error: %s", e, exc_info=True)
        raise
    finally:
        session.close()
