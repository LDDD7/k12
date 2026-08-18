"""
进程内事件总线 — 用于 SSE 实时推送

单进程部署下（单 uvicorn worker），发布/订阅在同一个事件循环线程内完成，
使用 asyncio.Queue 作为订阅队列即可。发布方（如 ProfileService.confirm_profile）
在 graph.invoke 的同步阻塞调用中执行，与订阅方（SSE 生成器）同线程，
put_nowait 是安全的。
"""

import asyncio
import json
from typing import Dict, List

_subscribers: Dict[str, List["asyncio.Queue[str]"]] = {}


class EventBus:
    """轻量发布/订阅总线"""

    @classmethod
    def publish(cls, channel: str, data: dict) -> None:
        """发布事件到指定 channel 的所有订阅者"""
        payload = json.dumps(data, ensure_ascii=False)
        for q in list(_subscribers.get(channel, [])):
            try:
                q.put_nowait(payload)
            except asyncio.QueueFull:
                pass

    @classmethod
    def subscribe(cls, channel: str) -> "asyncio.Queue[str]":
        """订阅 channel，返回异步队列"""
        q: "asyncio.Queue[str]" = asyncio.Queue(maxsize=100)
        _subscribers.setdefault(channel, []).append(q)
        return q

    @classmethod
    def unsubscribe(cls, channel: str, q: "asyncio.Queue[str]") -> None:
        """取消订阅"""
        lst = _subscribers.get(channel)
        if lst and q in lst:
            lst.remove(q)
