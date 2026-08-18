# k12_app/agent/models/states.py
"""
LangGraph 状态定义
"""

from typing import TypedDict, Optional, List, Dict, Any, Annotated

def last_write_wins(a: Optional[Any], b: Optional[Any]) -> Optional[Any]:
    return b if b is not None else a

class AgentState(TypedDict):
    """Agent 主状态"""

    # ===== 输入（使用 Reducer 避免并发更新冲突） =====
    user_id: Annotated[Optional[str], last_write_wins]
    external_id: Annotated[Optional[str], last_write_wins]   # ✅ 添加 Reducer
    wework_account_id: Annotated[Optional[str], last_write_wins]  # 建议也加上（如果可能被修改）
    data_scope: Annotated[Optional[str], last_write_wins]         # all / region / self
    message: Annotated[Optional[str], last_write_wins]            # 同样建议
    menu_id: Annotated[Optional[str], last_write_wins]            # 同样建议

    # ===== 中间数据 =====
    intent: Annotated[Optional[str], last_write_wins]
    customer_data: Annotated[Optional[Dict], last_write_wins]
    employee_data: Annotated[Optional[Dict], last_write_wins]
    chat_records: Annotated[List[Dict], last_write_wins]
    kf_records: Annotated[List[Dict], last_write_wins]
    orders: Annotated[List[Dict], last_write_wins]
    tags: Annotated[List[Dict], last_write_wins]
    profile: Annotated[Optional[Dict], last_write_wins]
    # ===== 二期综合推理（V3.3）=====
    profile_items: Annotated[Optional[List[Dict]], last_write_wins]   # 已确认画像字段项
    customer_tags: Annotated[Optional[List[Dict]], last_write_wins]   # 客户标签
    reasoning_steps: Annotated[Optional[List[Dict]], last_write_wins]  # 推理轨迹（逐步透明展示）
    # ===== free_chat 多轮对话上下文 (V3.2 新增) =====
    chat_history: Annotated[List[Dict[str, str]], last_write_wins]
    current_response: Annotated[Optional[str], last_write_wins]

    # ===== 结果 =====
    task_result: Annotated[Optional[Any], last_write_wins]
    error: Annotated[Optional[str], last_write_wins]

    # ===== 控制 =====
    done: Annotated[bool, last_write_wins]
    # 中断确认结果："ok" 保存 / "discard" 放弃 / "recreate" 重新生成
    confirmed: Annotated[Optional[str], last_write_wins]