# k12_app/agent/tools/wechat_tool.py
"""
企业微信 API 工具 — 封装企微 API 调用
本项目为开发/演示用途，默认 Mock 模式（USE_MOCK=true），无需真实企微账号。
所有函数在 Mock 模式下直接返回模拟结果，不发起任何网络请求。
"""
import logging
import time
from typing import Optional, Dict, Any
from datetime import datetime
import os

import requests

from k12_app.backend.dao.wework_account_dao import WeWorkAccountDAO
from k12_app.backend.cache.redis_client import redis_client as _redis_client

logger = logging.getLogger(__name__)

# ============================================================
# Mock 模式开关
# ============================================================

# 默认开启 Mock（开发/演示），无需真实企微 API 凭证
USE_MOCK = os.getenv("USE_MOCK", "true").lower() == "true"

if not USE_MOCK:
    logger.info("企微 Mock 模式已关闭，将使用真实 API")

# ============================================================
# 常量
# ============================================================

TOKEN_CACHE_KEY = "wx:access_token:{account_id}"
ACCOUNT_STATUS_KEY = "wx:account_status:{account_id}"
TOKEN_EXPIRE_SECONDS = 7000
MAX_RETRY_COUNT = 3


# ============================================================
# Mock 数据生成
# ============================================================

def _mock_token(account_id: str) -> str:
    """生成模拟 token"""
    return f"mock_token_{account_id}_{int(time.time())}"


def _mock_event_id() -> str:
    """生成模拟事件 ID"""
    return f"mock_event_{int(time.time())}_{os.urandom(4).hex()}"


# ============================================================
# 核心函数
# ============================================================

def get_token(account_id: str) -> Optional[str]:
    """
    获取企微 access_token
    支持 Mock 模式：USE_MOCK=true 时返回模拟 token
    """
    # 模拟模式：直接返回模拟 token
    if USE_MOCK:
        token = _mock_token(account_id)
        logger.info(f"[MOCK] 获取 token: {account_id} -> {token}")
        return token

    cache_key = TOKEN_CACHE_KEY.format(account_id=account_id)

    # 检查是否降级
    status_key = ACCOUNT_STATUS_KEY.format(account_id=account_id)
    if _redis_client.get(status_key) == "degraded":
        logger.warning(f"账户 {account_id} 已降级")
        return None

    # 从 Redis 获取
    token = _redis_client.get(cache_key)
    if token:
        return token

    # 调用企微 API
    try:
        token, expires_in = _fetch_token_from_api(account_id)
        if token:
            _redis_client.setex(cache_key, TOKEN_EXPIRE_SECONDS, token)
            _redis_client.delete(status_key)
            logger.info(f"账户 {account_id} token 刷新成功")
            return token
        else:
            _handle_token_failure(account_id)
            return None
    except Exception as e:
        logger.error(f"获取 token 异常: {e}")
        _handle_token_failure(account_id)
        return None


def _fetch_token_from_api(account_id: str) -> tuple[Optional[str], Optional[int]]:
    """调用企微 API 获取 token"""
    # 如果是 Mock 模式，不会执行到这里（已在 get_token 中拦截）
    account = WeWorkAccountDAO.get_by_account_id(account_id)
    if not account:
        logger.error(f"企微账户 {account_id} 不存在")
        return None, None

    url = "https://qyapi.weixin.qq.com/cgi-bin/gettoken"
    resp = requests.get(
        url,
        params={
            "corpid": account["corp_id"],
            "corpsecret": account["corp_secret"],
        },
        timeout=10,
    )
    data = resp.json()

    if data.get("errcode") == 0:
        return data.get("access_token"), data.get("expires_in")
    else:
        logger.error(f"获取 token 失败: {data}")
        return None, None


def _handle_token_failure(account_id: str):
    """处理 token 获取失败"""
    status_key = ACCOUNT_STATUS_KEY.format(account_id=account_id)
    fail_count = _redis_client.get(f"{status_key}:fail_count")
    fail_count = int(fail_count) if fail_count else 0
    fail_count += 1
    _redis_client.setex(f"{status_key}:fail_count", 3600, str(fail_count))

    if fail_count >= MAX_RETRY_COUNT:
        _redis_client.setex(status_key, 3600, "degraded")
        logger.error(f"账户 {account_id} 已降级")


# ============================================================
# 客户标签同步
# ============================================================

def sync_tag(
    account_id: str,
    external_id: str,
    tag_id: str,
    action: str,  # "add" 或 "remove"
) -> bool:
    """同步企微客户标签"""
    if USE_MOCK:
        logger.info(f"[MOCK] 同步标签: {account_id}, {external_id}, {action}, {tag_id}")
        return True

    token = get_token(account_id)
    if not token:
        logger.error(f"账户 {account_id} token 无效")
        return False

    url = "https://qyapi.weixin.qq.com/cgi-bin/externalcontact/mark_tag"
    params = {"access_token": token}

    body = {
        "userid": account_id,
        "external_userid": external_id,
    }
    if action == "add":
        body["add_tag"] = [tag_id]
    else:
        body["remove_tag"] = [tag_id]

    try:
        resp = requests.post(url, params=params, json=body, timeout=10)
        data = resp.json()
        if data.get("errcode") == 0:
            logger.info(f"标签同步成功: {external_id} {action} {tag_id}")
            return True
        else:
            logger.error(f"标签同步失败: {data}")
            return False
    except Exception as e:
        logger.error(f"标签同步异常: {e}")
        return False


# ============================================================
# 日程同步
# ============================================================

def sync_calendar(account_id: str, schedule_data: Dict[str, Any]) -> Optional[str]:
    """同步日程到企微日历"""
    if USE_MOCK:
        event_id = _mock_event_id()
        logger.info(f"[MOCK] 同步日程: {account_id}, {schedule_data.get('title')} -> {event_id}")
        return event_id

    token = get_token(account_id)
    if not token:
        logger.error(f"账户 {account_id} token 无效")
        return None

    url = "https://qyapi.weixin.qq.com/cgi-bin/calendar/add"
    params = {"access_token": token}

    body = {
        "organizer": account_id,
        "summary": schedule_data.get("title", "待办事项"),
        "start_time": _to_timestamp(schedule_data.get("start_time")),
        "end_time": _to_timestamp(schedule_data.get("end_time")),
        "attendees": [],
    }

    try:
        resp = requests.post(url, params=params, json=body, timeout=10)
        data = resp.json()
        if data.get("errcode") == 0:
            event_id = data.get("event_id")
            logger.info(f"日程同步成功: {event_id}")
            return event_id
        else:
            logger.error(f"日程同步失败: {data}")
            return None
    except Exception as e:
        logger.error(f"日程同步异常: {e}")
        return None


def _to_timestamp(time_value) -> Optional[int]:
    if time_value is None:
        return None
    if isinstance(time_value, datetime):
        return int(time_value.timestamp())
    if isinstance(time_value, str):
        try:
            dt = datetime.fromisoformat(time_value.replace("Z", "+00:00"))
            return int(dt.timestamp())
        except ValueError:
            return None
    return None


# ============================================================
# 应用消息推送
# ============================================================

def send_notify(
    account_id: str,
    user_id: str,
    content: str,
    msg_type: str = "text",
) -> bool:
    """推送应用消息给顾问"""
    if USE_MOCK:
        logger.info(f"[MOCK] 发送通知: {account_id}, {user_id}, {content[:50]}...")
        return True

    token = get_token(account_id)
    if not token:
        logger.error(f"账户 {account_id} token 无效")
        return False

    account = WeWorkAccountDAO.get_by_account_id(account_id)
    if not account:
        logger.error(f"企微账户 {account_id} 不存在")
        return False

    url = "https://qyapi.weixin.qq.com/cgi-bin/message/send"
    params = {"access_token": token}

    body = {
        "touser": user_id,
        "msgtype": msg_type,
        "agentid": int(account.get("agent_id", 0)),
        "text": {"content": content},
    }

    try:
        resp = requests.post(url, params=params, json=body, timeout=10)
        data = resp.json()
        if data.get("errcode") == 0:
            logger.info(f"通知发送成功: {user_id}")
            return True
        else:
            logger.error(f"通知发送失败: {data}")
            return False
    except Exception as e:
        logger.error(f"通知发送异常: {e}")
        return False