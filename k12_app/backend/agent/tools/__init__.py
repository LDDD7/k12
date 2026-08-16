"""
企业微信 API 封装
access_token 管理 / 创建日程 / 更新客户标签 / 发送应用消息 / 会话存档
多账户 token 隔离：Redis 缓存键 wx:access_token:{account_id}
详见接口设计文档 八、外部接口 + 系统设计文档 3.4 多企微账户架构
"""
# k12_app/agent/tools/__init__.py
"""企微 API 工具"""

from .wechat_tool import (
    get_token,
    sync_tag,
    sync_calendar,
    send_notify,
)

__all__ = [
    "get_token",
    "sync_tag",
    "sync_calendar",
    "send_notify",
]
