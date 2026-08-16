# init_env.py
"""
项目环境初始化脚本
在项目根目录执行：python init_env.py
功能：生成 JWT_SECRET_KEY 并写入 .env（如果缺失）
"""

import os
import secrets
from pathlib import Path

# 项目根目录（当前文件所在目录）
BASE_DIR = Path(__file__).parent

# .env 文件路径（/.env）
ENV_FILE = BASE_DIR /".env"

def init_env():
    if not ENV_FILE.exists():
        print(f"❌ .env 文件不存在: {ENV_FILE}")
        print("   请先创建 .env 文件（可以复制 .env.example）")
        return False

    # 读取现有内容
    with open(ENV_FILE, "r", encoding="utf-8") as f:
        content = f.read()

    检查是否已有 JWT_SECRET_KEY
    if "JWT_SECRET_KEY=" in content:
        print("✅ JWT_SECRET_KEY 已存在，跳过生成")
        return True

    # 生成强随机密钥（32字节）
    secret = secrets.token_hex(32)

    # 追加到 .env 文件末尾
    with open(ENV_FILE, "a", encoding="utf-8") as f:
        f.write("\n# ===== JWT 配置（自动生成，请勿修改）=====\n")
        f.write(f"JWT_SECRET_KEY={secret}\n")
        f.write(f"JWT_EXPIRE_MINUTES=30\n")

    print(f"✅ JWT_SECRET_KEY 已生成并写入 {ENV_FILE}")
    print(f"   密钥: {secret[:8]}...（请勿泄露）")
    return True

if __name__ == "__main__":
    init_env()