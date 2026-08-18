"""
二期「综合推理」多步推理节点（V3.3）— AI 像资深顾问一样分步思考

流程：查画像（这是谁）→ 匹配课程（查开班）→ 核对价格政策（查知识库）→ 综合生成建议
安全护栏：
- 步数上限（默认 3，配置可调），超限自动收敛
- 全局关停开关：关闭时退回"知识库查询/单模块回复"简化模式（秒级生效）
- 知识库未命中 → 记录盲区数据 + 生成兜底话术（嵌入顾问姓名）
- 每一步的 tool/text/来源写入 reasoning_steps，供侧边栏逐步透明展示
"""
import logging
from typing import Dict, Any, List

from k12_app.backend.dao.config_dao import ConfigDAO
from k12_app.backend.agent.llm.reasoning_prompt import plan_tool_chain, generate_final_answer
from k12_app.backend.agent.tools.kb_tools import execute_tool

logger = logging.getLogger(__name__)

# 知识库类工具（用于盲区判定：全部未命中则记录）
_KB_TOOLS = {"search_kb", "get_class_info"}


def _advisor_name(state: Dict[str, Any]) -> str:
    emp = state.get("employee_data") or {}
    return emp.get("name") or "顾问"


def _log_blind_spot(state: Dict[str, Any], scene_type: str, question: str,
                    kb_types: str = None, matched_text: str = None) -> None:
    """记录盲区数据（兜底/推理失败），不阻断主流程"""
    try:
        from k12_app.backend.dao.blind_spot_dao import BlindSpotDAO
        BlindSpotDAO.log_blind_spot(
            original_question=question,
            scene_type=scene_type,
            kb_types=kb_types,
            matched_text=matched_text,
            advisor_name=_advisor_name(state),
            user_id=state.get("user_id"),
            external_id=state.get("external_id"),
            wework_account_id=state.get("wework_account_id"),
        )
    except Exception as e:
        logger.warning(f"记录盲区数据失败: {e}")


def _run_reasoning_loop(
    user_message: str,
    state: Dict[str, Any],
    max_steps: int,
) -> tuple:
    """
    多步推理主循环（单次规划 + 顺序执行）。

    先一次性规划整条工具链（1 次 LLM），再顺序执行每个工具（工具本身不调 LLM）。
    相比逐步 ReAct 反复重规划，将 2 步工具链的 LLM 调用从 4 次降为 2 次，
    满足「综合推理 ≤5 秒」验收点；工具结果仍逐条写入 reasoning_steps 供侧边栏透明展示。

    Returns:
        (steps, had_error)
        steps: [{step_index, tool, description, text, status, matched, metadata}]
        had_error: 规划器/工具链是否发生错误（用于推理失败率标记）
    """
    steps: List[Dict[str, Any]] = []
    tried_kb = set()
    kb_missed = True  # 是否有任一知识库命中
    had_error = False

    # 1. 一次性规划整条工具链
    plan = plan_tool_chain(user_message, max_steps=max_steps)
    if plan.get("error"):
        had_error = True
        _log_blind_spot(state, "reasoning_failed", user_message)
        return steps, had_error

    # 2. 顺序执行规划的工具（超限收敛）
    for step_index, spec in enumerate((plan.get("steps") or [])[:max_steps], 1):
        tool_name = spec.get("tool", "") if isinstance(spec, dict) else ""
        args = (spec.get("args") or {}) if isinstance(spec, dict) else {}
        step = {
            "step_index": step_index,
            "tool": tool_name,
            "description": "",
            "text": "",
            "status": "running",
            "matched": None,
            "metadata": {},
        }
        try:
            result = execute_tool(tool_name, state, args)
            step["description"] = result.get("description", "")
            step["text"] = result.get("text", "")
            step["metadata"] = result.get("metadata", {})
            step["matched"] = result.get("matched")
            if tool_name in _KB_TOOLS:
                tried_kb.add(tool_name)
                if result.get("matched"):
                    kb_missed = False
            step["status"] = "done"
        except Exception as e:
            logger.warning(f"推理工具执行失败 {tool_name}: {e}")
            had_error = True
            step["status"] = "error"
            step["text"] = f"（工具执行失败：{e}）"
            step["error"] = str(e)
        steps.append(step)

        # 步数上限提示（超限自动收敛）
        if step_index >= max_steps:
            step["converged"] = True

    # 3. 知识库工具全部未命中 → 记录盲区（not_found）
    if tried_kb and kb_missed:
        _log_blind_spot(
            state, "not_found", user_message,
            kb_types=",".join(sorted(tried_kb)),
            matched_text=steps[-1].get("text", "")[:300] if steps else None,
        )

    return steps, had_error


def _simplified_kb_answer(user_message: str, state: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    简化模式（全局开关关闭时）：仅做一次知识库查询 + 单模块回复。
    对应"退回知识库查询/单模块回复"的回退链路。
    """
    from k12_app.backend.agent.tools.kb_tools import search_kb
    min_score = ConfigDAO.get_kb_min_score()
    result = search_kb(query=user_message, kb_name="all", min_score=min_score)
    step = {
        "step_index": 1,
        "tool": "search_kb",
        "description": "集团知识库检索（简化模式）",
        "text": result.get("text", ""),
        "status": "done",
        "matched": result.get("matched", False),
        "metadata": result.get("metadata", {}),
        "simplified": True,
    }
    if not result.get("matched", False):
        _log_blind_spot(state, "fallback", user_message, kb_types="all")
    return [step]


def comprehensive_reasoning_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    综合推理节点（LangGraph）：
    开关开启 → 多步工具链推理；开关关闭 → 简化模式。
    结果写入 state["task_result"] = {"type": "reasoning", "data": {...}}
    """
    user_message = (state.get("message") or "").strip()
    advisor_name = _advisor_name(state)

    if not user_message:
        state["task_result"] = {
            "type": "reasoning",
            "data": {"reply": "请问有什么可以帮助您的？", "steps": [], "sources": [], "mode": "empty"},
        }
        state["done"] = True
        return state

    reasoning_enabled = ConfigDAO.is_reasoning_enabled()
    max_steps = ConfigDAO.get_reasoning_max_steps()

    try:
        if reasoning_enabled:
            steps, had_error = _run_reasoning_loop(user_message, state, max_steps)
            mode = "error" if had_error else "reasoning"
        else:
            steps = _simplified_kb_answer(user_message, state)
            had_error = False
            mode = "simplified"

        # 4. 综合生成最终建议（带来源标注）
        reply = generate_final_answer(
            user_message=user_message,
            steps=steps,
            advisor_name=advisor_name,
        )

        # 提取来源元数据（供前端"来源标注"展示）
        sources = []
        for s in steps:
            meta = s.get("metadata") or {}
            src = meta.get("sources") or []
            for item in src:
                sources.append({
                    "step": s.get("step_index"),
                    "tool": s.get("tool"),
                    "title": (item.get("metadata") or {}).get("title") or "",
                    "text": (item.get("text") or "")[:200],
                    "score": item.get("score"),
                })

        state["task_result"] = {
            "type": "reasoning",
            "data": {
                "reply": reply,
                "steps": steps,
                "sources": sources,
                "mode": mode,
                "advisor_name": advisor_name,
            },
        }
        # 写入推理轨迹供 SSE 逐步透明展示
        state["reasoning_steps"] = steps

    except Exception as e:
        logger.error(f"综合推理失败: {e}", exc_info=True)
        _log_blind_spot(state, "reasoning_failed", user_message)
        fallback = (
            f"抱歉，AI 综合推理暂时不可用。这个问题我暂时帮不上忙，"
            f"您的专属课程顾问{advisor_name}对这方面很了解，随时可以问她~"
        )
        state["task_result"] = {
            "type": "reasoning",
            "data": {"reply": fallback, "steps": [], "sources": [], "mode": "error"},
        }
        state["error"] = str(e)

    state["done"] = True
    return state
