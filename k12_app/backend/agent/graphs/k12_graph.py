# k12_app/agent/graphs/k12_graph.py
"""
LangGraph 主图 — AI 任务编排
"""

import logging
import sqlite3
from pathlib import Path
from typing import Dict, Literal
from langgraph.graph import StateGraph, END
from langgraph.types import interrupt

from k12_app.backend.agent.models.states import AgentState
from k12_app.backend.agent.llm.intent_router import route_intent
from k12_app.backend.agent.llm.profile_prompt import generate_profile
from k12_app.backend.agent.llm.reply_prompt import generate_replies
from k12_app.backend.agent.llm.tag_prompt import recommend_tags
from k12_app.backend.agent.llm.schedule_prompt import extract_schedule
from k12_app.backend.agent.llm.free_chat import free_chat, get_free_chat_context
from k12_app.backend.agent.graphs.reasoning import comprehensive_reasoning_node
from k12_app.backend.config import settings

logger = logging.getLogger(__name__)


# ============================================================
# 数据加载节点
# ============================================================

def load_employee(state: AgentState) -> AgentState:
    from k12_app.backend.dao.employee_dao import EmployeeDAO
    emp = EmployeeDAO.get_by_user_id(state["user_id"])
    state["employee_data"] = emp
    return state


def load_customer(state: AgentState) -> AgentState:
    from k12_app.backend.dao.customer_dao import CustomerDAO
    cust = CustomerDAO.get_by_external_id(
        state["external_id"],
        state["user_id"],
        state.get("data_scope", "self"),
        state["wework_account_id"],
    )
    state["customer_data"] = cust
    return state




def load_chat(state: AgentState) -> AgentState:
    from k12_app.backend.dao.message_dao import MessageDAO
    chats = MessageDAO.get_chat_history_by_external_id(
        external_id=state["external_id"],
        user_id=state["user_id"],
        data_scope=state.get("data_scope", "self"),
        wework_account_id=state["wework_account_id"],
        days=30,
        limit=50,
    )
    state["chat_records"] = chats
    return state


def load_kf(state: AgentState) -> AgentState:
    """加载客服记录"""
    from k12_app.backend.dao.message_dao import MessageDAO
    kf_records = MessageDAO.get_kf_history(
        external_id=state["external_id"],
        user_id=state["user_id"],
        data_scope=state.get("data_scope", "self"),
        wework_account_id=state["wework_account_id"],
        days=30,
        limit=50,
    )
    state["kf_records"] = kf_records
    return state

def load_orders(state: AgentState) -> AgentState:
    from k12_app.backend.dao.order_dao import OrderDAO
    if state.get("customer_data") and state["customer_data"].get("union_id"):
        orders = OrderDAO.get_by_union_id(
            state["customer_data"]["union_id"],
            state["user_id"],
            state.get("data_scope", "self"),
            state["wework_account_id"],
        )
        state["orders"] = orders
    else:
        state["orders"] = []
    return state


def load_tags(state: AgentState) -> AgentState:
    from k12_app.backend.dao.tag_dao import TagDAO
    tags = TagDAO.get_all_tags()
    flat_tags = []
    for strategy in tags:
        for group in strategy.get("groups", []):
            flat_tags.extend(group.get("tags", []))
    state["tags"] = flat_tags
    return state


def load_profile(state: AgentState) -> AgentState:
    """加载客户已确认画像字段项 + 客户标签（V3.3 二期综合推理数据源）"""
    from k12_app.backend.dao.profile_dao import ProfileDAO
    from k12_app.backend.dao.tag_dao import TagDAO
    external_id = state.get("external_id")
    user_id = state.get("user_id")
    data_scope = state.get("data_scope", "self")
    wework_account_id = state.get("wework_account_id")
    state["profile_items"] = []
    state["customer_tags"] = []
    if external_id:
        try:
            profile = ProfileDAO.get_by_external_id(
                external_id, user_id, data_scope, wework_account_id
            )
            if profile and profile.get("status") == "已确认":
                state["profile_items"] = ProfileDAO.get_items(profile["id"]) or []
        except Exception as e:
            logger.warning(f"加载客户画像失败: {e}")
        try:
            state["customer_tags"] = TagDAO.get_customer_tags(
                external_id, user_id, data_scope, wework_account_id
            )
        except Exception as e:
            logger.warning(f"加载客户标签失败: {e}")
    return state


# ============================================================
# 意图路由节点
# ============================================================

def intent_router_node(state: AgentState) -> AgentState:
    intent = route_intent(
        state.get("message"),
        state.get("menu_id"),
    )
    state["intent"] = intent
    return state




# ============================================================
# 任务执行节点
# ============================================================



def generate_profile_node(state: AgentState) -> AgentState:
    customer_data = state.get("customer_data") or {}
    chat_records = state.get("chat_records") or []
    orders = state.get("orders") or []
    retrieved_messages = _retrieve_chat_context(state)

    profile = generate_profile(
        customer_data,
        chat_records,
        orders,
        retrieved_messages=retrieved_messages,
    )
    state["task_result"] = {"type": "profile", "data": profile}
    return state

def generate_reply_node(state: AgentState) -> AgentState:
    # 最近聊天记录（正序，家长=parent / 顾问=advisor）
    records = list(reversed(state.get("chat_records") or []))
    recent_chat = [
        {"role": "parent" if rec.get("sender") == state.get("external_id") else "advisor",
         "content": rec.get("content", "")}
        for rec in records[-10:]
    ]
    # 客户画像（从客户档案构建，图内未加载 state["profile"]）
    customer_data = state.get("customer_data") or {}
    profile = {
        k: customer_data[k]
        for k in ("child_name", "grade", "focus_subject", "school", "stage", "remark")
        if customer_data.get(k)
    }
    if customer_data.get("name"):
        profile["parent_name"] = customer_data["name"]
    retrieved_messages = _retrieve_chat_context(state)
    retrieved_scripts = _retrieve_scripts_context(state)
    replies = generate_replies(
        profile,
        recent_chat,
        retrieved_messages=retrieved_messages,
        retrieved_scripts=retrieved_scripts,
    )
    state["task_result"] = {"type": "reply", "data": replies}
    return state


def recommend_tag_node(state: AgentState) -> AgentState:
    tags = recommend_tags(
        state.get("profile", {}),
        state.get("chat_records", []),
        state.get("tags", []),
    )
    state["task_result"] = {"type": "tag", "data": tags}
    return state


def extract_schedule_node(state: AgentState) -> AgentState:
    schedules = extract_schedule(state.get("chat_records", []))
    state["task_result"] = {"type": "schedule", "data": schedules}
    return state


def _retrieve_chat_context(state: AgentState) -> list:
    """从向量库检索该客户（external_id + user_id）的历史聊天记录"""
    query = state.get("message") or ""
    if not query:
        cd = state.get("customer_data") or {}
        query = " ".join(filter(None, [cd.get("name"), cd.get("grade"), cd.get("focus_subject")])) or "客户咨询"
    try:
        from k12_app.backend.services.rag_service import RAGService
        return RAGService.retrieve_chat_messages(
            query=query,
            top_k=10,
            external_id=state.get("external_id"),
            user_id=state.get("user_id"),
        )
    except Exception as e:
        logger.warning(f"向量检索聊天记录失败: {e}")
        return []


def _retrieve_scripts_context(state: AgentState) -> list:
    """从话术库（k12_scripts）检索与当前咨询相关的专业销售话术"""
    query = state.get("message") or ""
    if not query:
        cd = state.get("customer_data") or {}
        query = " ".join(filter(None, [cd.get("name"), cd.get("grade"), cd.get("focus_subject")])) or "客户咨询"
    try:
        from k12_app.backend.services.rag_service import RAGService
        return RAGService.retrieve_scripts(query=query, top_k=5)
    except Exception as e:
        logger.warning(f"向量检索话术库失败: {e}")
        return []


def _chat_records_to_history(state: AgentState, limit: int = 20) -> list:
    """把 DB 聊天记录转成 LLM 多轮消息（正序）：家长(sender==external_id)=user / 顾问=assistant。

    load_chat 以 send_time DESC 加载 chat_records，此处反转为正序并截取最近 limit 条。
    """
    records = state.get("chat_records") or []
    external_id = state.get("external_id")
    history = []
    for rec in reversed(records):
        content = (rec.get("content") or "").strip()
        if not content:
            continue
        role = "user" if rec.get("sender") == external_id else "assistant"
        history.append({"role": role, "content": content})
    return history[-limit:]


def free_chat_node(state: AgentState) -> AgentState:
    """
    自由对话节点 — 结合客户上下文进行智能回复
    """
    user_message = state.get("message", "")
    customer_data = state.get("customer_data")

    if not user_message:
        state["task_result"] = {
            "type": "free_chat",
            "data": "请问有什么可以帮助您的？"
        }
        state["done"] = True
        return state

    try:
        # 获取上下文
        context = get_free_chat_context(customer_data) if customer_data else None

        # 获取历史对话（从 DB 聊天记录构建；当前消息已先落库，需剔除避免重复）
        chat_history = _chat_records_to_history(state)
        if chat_history and chat_history[-1].get("content") == user_message:
            chat_history = chat_history[:-1]

        # 从向量库检索该客户的历史聊天记录，增强上下文
        retrieved_messages = _retrieve_chat_context(state)

        # 调用自由对话
        response = free_chat(
            user_message=user_message,
            customer_data=customer_data,
            chat_history=chat_history,
            temperature=0.7,
            retrieved_messages=retrieved_messages,
        )

        # 更新历史对话（用于多轮上下文）
        if "chat_history" not in state:
            state["chat_history"] = []
        state["chat_history"].append({"role": "user", "content": user_message})
        state["chat_history"].append({"role": "assistant", "content": response})

        state["task_result"] = {"type": "free_chat", "data": response}
        state["current_response"] = response

    except Exception as e:
        logger.error(f"自由对话失败: {e}")
        # V3.3 兜底话术：嵌入顾问姓名，引导式兜底（不冷冰冰拒绝）
        advisor_name = ""
        emp = state.get("employee_data") or {}
        advisor_name = emp.get("name") or ""
        fallback = (
            f"抱歉，我暂时无法回答这个问题，请稍后再试。"
            + (f"如果比较着急，您的专属课程顾问{advisor_name}对这方面很了解，随时可以问她~" if advisor_name else "")
        )
        state["task_result"] = {
            "type": "free_chat",
            "data": fallback,
        }
        state["error"] = str(e)

    state["done"] = True
    return state


# ============================================================
# 中断与保存节点
# ============================================================



def interrupt_node(state: AgentState) -> AgentState:
    """中断节点 — 调用 LangGraph interrupt() 暂停执行，等待人工确认后继续"""
    task_type = state.get("intent", "")
    task_result = state.get("task_result", {})
    # LangGraph interrupt() 会在此处暂停图执行
    # 调用方通过 graph.invoke(Command(resume=confirmed), config) 恢复
    confirmed = interrupt({
        "interrupt_id": f"int_{state['external_id']}_{state['user_id']}",
        "task": task_type,
        "data": task_result,
    })

    # 保留用户完整选择语义：ok / discard / recreate
    # 兼容旧的布尔 resume 值
    if confirmed not in ("ok", "discard", "recreate"):
        confirmed = "ok" if confirmed else "discard"
    state["confirmed"] = confirmed
    return state

def save_task_result_node(state: AgentState) -> AgentState:
    """中断确认后，按任务类型将结果保存到数据库（统一走 service 层）"""
    result = state.get("task_result") or {}
    task_type = result.get("type")
    # 日程仅抽取不持久化（由侧边栏「确认添加」接口逐条落库为待确认）
    if task_type == "schedule":
        state["done"] = True
        return state
    if state.get("confirmed") != "ok":
        state["done"] = False
        return state

    from k12_app.backend.services.profile_service import ProfileService
    from k12_app.backend.services.tag_service import TagService

    data = result.get("data") or []

    external_id = state.get("external_id") or ""
    user_id = state.get("user_id") or ""
    customer_data = state.get("customer_data") or {}
    # 归属字段以客户档案为准：顾问/企微账户应取客户实际归属，而非当前确认操作人
    follow_user_id = customer_data.get("follow_user_id") or user_id
    wework_account_id = customer_data.get("wework_account_id") or state.get("wework_account_id") or ""

    try:
        if task_type == "profile" and data:
            ProfileService.confirm_profile(
                external_id=external_id,
                follow_user_id=follow_user_id,
                wework_account_id=wework_account_id,
                profile_data=data,
                confirmed_by=user_id,
            )
        elif task_type == "tag" and data:
            tag_ids = [t.get("tag_id") for t in data if isinstance(t, dict) and t.get("tag_id")]
            if tag_ids:
                TagService.confirm_tags(
                    external_id=external_id,
                    user_id=follow_user_id,
                    wework_account_id=wework_account_id,
                    tag_ids=tag_ids,
                    confirmed_by=user_id,
                )
    except Exception as e:
        logger.error(f"保存任务结果失败: {e}", exc_info=True)
        state["error"] = str(e)

    state["done"] = True
    return state

# ============================================================
# 路由函数
# ============================================================

def route_by_intent(state: AgentState) -> Literal[
    "generate_profile", "generate_reply", "recommend_tag", "extract_schedule",
    "comprehensive_reasoning", "free_chat"
]:
    intent = state.get("intent", "free_chat")
    mapping = {
        "profile": "generate_profile",
        "reply": "generate_reply",
        "tag": "recommend_tag",
        "schedule": "extract_schedule",
        "reasoning": "comprehensive_reasoning",
        "free_chat": "free_chat",
    }
    return mapping.get(intent, "free_chat")


def route_after_task(state: AgentState) -> Literal["interrupt", "save_task_result", "__end__"]:
    intent = state.get("intent", "free_chat")
    # 日程仅抽取不落库：由侧边栏「确认添加」接口逐条持久化，故不进入中断
    need_confirm = {"profile", "tag"}
    if intent in need_confirm:
        return "interrupt"
    if intent == "schedule":
        return "save_task_result"
    return "__end__"

def route_after_interrupt(state: AgentState) -> Literal[
    "save_task_result", "generate_profile", "recommend_tag", "extract_schedule", "__end__"
]:
    """根据 confirmed 字段决定后续分支：ok 保存 / discard 结束 / recreate 重新生成"""
    confirmed = state.get("confirmed", "discard")
    if confirmed == "ok":
        return "save_task_result"
    if confirmed == "recreate":
        intent = state.get("intent", "")
        return {
            "profile": "generate_profile",
            "tag": "recommend_tag",
            "schedule": "extract_schedule",
        }.get(intent, "__end__")
    return "__end__"
# ============================================================
# 构建图
# ============================================================

def build_graph():
    builder = StateGraph(AgentState)

    # 添加节点
    builder.add_node("load_employee", load_employee)
    builder.add_node("load_customer", load_customer)
    builder.add_node("load_chat", load_chat)
    builder.add_node("load_kf", load_kf)
    builder.add_node("load_orders", load_orders)
    builder.add_node("load_tags", load_tags)
    builder.add_node("load_profile", load_profile)
    builder.add_node("intent_router", intent_router_node)
    builder.add_node("generate_profile", generate_profile_node)
    builder.add_node("generate_reply", generate_reply_node)
    builder.add_node("recommend_tag", recommend_tag_node)
    builder.add_node("extract_schedule", extract_schedule_node)
    builder.add_node("comprehensive_reasoning", comprehensive_reasoning_node)
    builder.add_node("free_chat", free_chat_node)
    builder.add_node("interrupt", interrupt_node)
    builder.add_node("save_task_result", save_task_result_node)

    # 设置入口
    builder.set_entry_point("load_employee")

    # 数据加载链
    builder.add_edge("load_employee", "load_customer")
    builder.add_edge("load_customer", "load_chat")
    builder.add_edge("load_chat", "load_kf")
    builder.add_edge("load_kf", "load_orders")
    builder.add_edge("load_orders", "load_tags")
    builder.add_edge("load_tags", "load_profile")
    builder.add_edge("load_profile", "intent_router")

    # 意图分发
    builder.add_conditional_edges(
        "intent_router",
        route_by_intent,
        {
            "generate_profile": "generate_profile",
            "generate_reply": "generate_reply",
            "recommend_tag": "recommend_tag",
            "extract_schedule": "extract_schedule",
            "comprehensive_reasoning": "comprehensive_reasoning",
            "free_chat": "free_chat",
        }
    )

    # 任务完成后判断是否需要中断
    builder.add_conditional_edges(
        "generate_profile",
        route_after_task,
        {"interrupt": "interrupt", "save_task_result": "save_task_result", "__end__": END}
    )
    builder.add_conditional_edges(
        "recommend_tag",
        route_after_task,
        {"interrupt": "interrupt", "save_task_result": "save_task_result", "__end__": END}
    )
    builder.add_conditional_edges(
        "extract_schedule",
        route_after_task,
        {"interrupt": "interrupt", "save_task_result": "save_task_result", "__end__": END}
    )

    # 不需要中断的任务直接结束（reply / reasoning / free_chat 仅展示，发送键在顾问手上）
    builder.add_edge("generate_reply", END)
    builder.add_edge("comprehensive_reasoning", END)
    builder.add_edge("free_chat", END)

    # 中断后保存

    builder.add_conditional_edges(
        "interrupt",
        route_after_interrupt,
        {
            "save_task_result": "save_task_result",
            "generate_profile": "generate_profile",
            "recommend_tag": "recommend_tag",
            "extract_schedule": "extract_schedule",
            "__end__": END,
        }
    )
    builder.add_edge("save_task_result", END)

    checkpointer = _build_checkpointer()
    graph = builder.compile(checkpointer=checkpointer)
    return graph


def _build_checkpointer():
    """构建持久化 checkpointer（SQLite 优先，失败降级内存）。

    注：RedisSaver（langgraph-checkpoint-redis 0.1.x）在 langgraph 0.3.34 下
    无法可靠持久化 interrupt 载荷（checkpoint 的 has_writes 标志写入时序错误，
    导致 get_state 读不到待确认中断），故改用 SQLite。
    """
    try:
        from langgraph.checkpoint.sqlite import SqliteSaver
        db_path = Path(settings.CHECKPOINT_DB_PATH)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(db_path), check_same_thread=False)
        saver = SqliteSaver(conn)
        saver.setup()
        logger.info("SQLite checkpointer ready: %s", db_path)
        return saver
    except Exception as e:
        logger.warning(f"SQLite checkpointer 不可用，降级为内存存储: {e}")
        from langgraph.checkpoint.memory import MemorySaver
        return MemorySaver()



# ============================================================
# 便捷调用
# ============================================================

_graph = None

def get_graph():
    global _graph
    if _graph is None:
        _graph = build_graph()
    return _graph


def run_agent(
    user_id: str,
    external_id: str,
    wework_account_id: str,
    message: str = None,
    menu_id: str = None,
    thread_id: str = None,
    data_scope: str = None,
) -> Dict:
    if thread_id is None:
        thread_id = f"{user_id}_{external_id}"

    graph = get_graph()
    config = {"configurable": {"thread_id": thread_id}}

    # 如果 message 和 menu_id 都为空，表示从中断点恢复执行
    if message is None and menu_id is None:
        result = graph.invoke(None, config)
    else:
        initial_state = {
            "user_id": user_id,
            "external_id": external_id,
            "wework_account_id": wework_account_id,
            "data_scope": data_scope or "self",
            "message": message,
            "menu_id": menu_id,
            "done": False,
        }
        result = graph.invoke(initial_state, config)

    _extract_interrupt(graph, config, result)
    return result


def _extract_interrupt(graph, config: Dict, result: Dict) -> None:
    """从 checkpoint 待处理任务提取中断信息（langgraph 0.3.x 不再在 invoke 结果返回 __interrupt__ 键）"""
    if not isinstance(result, dict):
        return
    result["interrupt_id"] = None
    try:
        state = graph.get_state(config)
        if state and getattr(state, "tasks", None):
            for task in state.tasks:
                interrupts = getattr(task, "interrupts", None) or ()
                if interrupts:
                    value = getattr(interrupts[0], "value", interrupts[0])
                    if isinstance(value, dict):
                        result["interrupt_id"] = value.get("interrupt_id")
                    result["done"] = False
                    return
    except Exception as e:
        logger.warning(f"提取中断信息失败: {e}")