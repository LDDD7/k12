"""
配置管理 — 读取 .env 环境变量
管理：数据库连接、Redis 连接、JWT 密钥、DashScope API Key、企微多账户配置
详见系统设计文档 二、完整技术栈 + 接口设计文档 附录 A
"""
# k12_app/config.py
import os
import hashlib
import base64
from pathlib import Path
from dotenv import load_dotenv

# 加载 .env 文件
env_path = Path(__file__).parent / '.env'
load_dotenv(dotenv_path=env_path)


class Settings:
    """应用配置"""
    # 环境
    ENV = os.getenv("ENV", "development")
    DEBUG = os.getenv("DEBUG", "true").lower() == "true"

    # JWT
    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY")
    if not JWT_SECRET_KEY:
        raise ValueError("JWT_SECRET_KEY 未配置，请检查 .env 文件")

    # Session 签名密钥与 JWT 密钥分离：未显式配置时从 JWT 密钥派生
    SESSION_SECRET_KEY = os.getenv("SESSION_SECRET_KEY") or hashlib.sha256(
        ("session:" + JWT_SECRET_KEY).encode("utf-8")
    ).hexdigest()

    JWT_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", 30))

    # 管理后台会话空闲超时（分钟），5.14 要求 30 分钟无操作自动退出
    SESSION_IDLE_TIMEOUT_MINUTES = int(os.getenv("SESSION_IDLE_TIMEOUT_MINUTES", 30))

    # 数据库
    DB_HOST = os.getenv("DB_HOST", "localhost")
    DB_PORT = int(os.getenv("DB_PORT", 3306))
    DB_USER = os.getenv("DB_USER", "root")
    DB_PASSWORD = os.getenv("DB_PASSWORD", "")
    DB_NAME = os.getenv("DB_NAME", "k12_agent_db")

    # Redis
    REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
    REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
    REDIS_PASSWORD = os.getenv("REDIS_PASSWORD")
    REDIS_DB = int(os.getenv("REDIS_DB", 0))

    # DeepSeek
    DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
    DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash")
    LLM_TIMEOUT = int(os.getenv("LLM_TIMEOUT", 30))

    # DashScope（Embedding）
    DASHSCOPE_API_KEY = os.getenv("DASHSCOPE_API_KEY")

    # 启动时自动补建缺失的向量索引（问题 3 修复；best-effort，失败不影响启动）
    AUTO_INDEX_ON_STARTUP = os.getenv("AUTO_INDEX_ON_STARTUP", "true").lower() == "true"

    # 聊天记录缓冲区转存向量库阈值
    CHAT_FLUSH_THRESHOLD = int(os.getenv("CHAT_FLUSH_THRESHOLD", 30))

    # LangGraph checkpoint 持久化（SQLite 文件路径，存放人机协同中断状态）
    CHECKPOINT_DB_PATH = os.getenv(
        "CHECKPOINT_DB_PATH",
        str(Path(__file__).parent / "data" / "checkpoints.sqlite"),
    )

    # CORS 允许的来源：逗号分隔，为空则不允许任何跨域（前后端同源部署）
    CORS_ALLOWED_ORIGINS = [
        o.strip()
        for o in os.getenv("CORS_ALLOWED_ORIGINS", "").split(",")
        if o.strip()
    ]

    # 敏感字段加密密钥（S-08，用于企微 CorpSecret 等）：Fernet 密钥需 32 字节 urlsafe base64。
    # 未显式配置时从 JWT 密钥派生，保证跨重启稳定。
    SECRET_ENCRYPTION_KEY = os.getenv("SECRET_ENCRYPTION_KEY") or base64.urlsafe_b64encode(
        hashlib.sha256(("secret:" + JWT_SECRET_KEY).encode("utf-8")).digest()
    ).decode("utf-8")


settings = Settings()