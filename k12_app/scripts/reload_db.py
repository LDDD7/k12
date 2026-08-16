"""
数据库重新初始化脚本 — 执行 init_db.sql 重建 k12_agent_db
用法：python k12_app/scripts/reload_db.py
依赖：MySQL 运行中，凭据读取自 k12_app/backend/.env（DB_USER / DB_PASSWORD / DB_HOST / DB_PORT）
"""
import os
import sys
from pathlib import Path

import pymysql

# 读取 .env 中的数据库配置（简单解析，避免依赖 k12_app 包初始化）
ENV_PATH = Path(__file__).resolve().parent.parent / "backend" / ".env"
SQL_PATH = Path(__file__).resolve().parent / "init_db.sql"


def load_env() -> dict:
    env = {}
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            env[k.strip()] = v.strip()
    return env


def main() -> int:
    if not SQL_PATH.exists():
        print(f"[ERROR] 未找到 init_db.sql: {SQL_PATH}", file=sys.stderr)
        return 1

    env = load_env()
    host = env.get("DB_HOST", "localhost")
    port = int(env.get("DB_PORT", 3306))
    user = env.get("DB_USER", "root")
    password = env.get("DB_PASSWORD", "")

    sql_text = SQL_PATH.read_text(encoding="utf-8")

    # 先删除旧库（若存在），再执行初始化脚本
    conn = pymysql.connect(host=host, port=port, user=user, password=password, charset="utf8mb4")
    try:
        with conn.cursor() as cur:
            cur.execute("DROP DATABASE IF EXISTS k12_agent_db")
            print("[OK] 已删除旧数据库 k12_agent_db")
        conn.commit()

        # 按分号拆分执行（脚本无存储过程/触发器，可安全拆分）
        statements = [s.strip() for s in sql_text.split(";") if s.strip()]
        with conn.cursor() as cur:
            for i, stmt in enumerate(statements, 1):
                cur.execute(stmt)
        conn.commit()
        print(f"[OK] 已执行 {len(statements)} 条 SQL 语句，数据库初始化完成")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
