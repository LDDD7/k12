"""
二期「综合推理」提示词与调用（V3.3）— AI 多步思考

- plan_tool_chain(): 一次性规划整条工具链（单次 LLM 调用，控制推理延迟）
- generate_final_answer(): 综合所有步骤信息生成带来源标注的自然语言建议
"""
import logging
from typing import Optional, Dict, List, Any

from k12_app.backend.agent.llm.client import call_llm
from k12_app.backend.agent.llm.utils import extract_json_dict, repair_json_with_llm

logger = logging.getLogger(__name__)

# ============================================================
# 规划器 System Prompt
# ============================================================

REASONING_PLANNER_SYSTEM = """
你是擎天学智的金牌销售顾问「推理规划器」。面对家长发来的复杂问题，你需要像资深顾问一样分步思考：
先判断需要哪些信息，然后一次性规划出完整的工具调用链，执行后综合给出建议。

【可用的信息工具】
{tools}

【决策规则】
1. 家长问题涉及客户本人（年级/学情/历史/订单）→ 规划 get_customer_profile / get_orders / get_tags
2. 家长问题涉及机构信息（正规吗/做了多少年/荣誉奖项）→ 规划 search_kb（kb_name=company 或 awards）
3. 家长问题涉及课程匹配（什么班合适/暑假班/价格）→ 规划 get_class_info 或 search_kb（kb_name=classes 或 faqs）
4. 组合型问题（既问孩子情况又问课程/价格）→ 把需要的工具一次列全，按「先画像/订单，再课程/价格」的顺序排列
5. 最多 {max_steps} 步。不要规划重复或多余的工具
6. 如果问题很简单（纯寒暄/无需查资料），直接 finish，不要查
7. search_kb / get_class_info 的 query 用家长问题原文或从中提取的关键词（如"初二数学暑期班"）；
   能确定资料类型时用具体的 kb_name（company|classes|awards|faqs），避免用 all 以提升检索速度

【返回格式】只输出 JSON：
- 需要查资料：{{"action": "plan", "steps": [{{"tool": "工具名", "args": {{"query": "检索词", "kb_name": "company|classes|awards|faqs|all"}}}}, ...]}}
  （get_customer_profile / get_orders / get_tags 无需 args）
- 无需查资料：{{"action": "finish"}}
"""


def _format_context(steps: List[Dict[str, Any]]) -> str:
    """把已执行的步骤格式化为上下文"""
    if not steps:
        return "（尚未执行任何步骤）"
    lines = []
    for i, step in enumerate(steps, 1):
        lines.append(f"第{i}步 [{step.get('tool', '')}] {step.get('description', '')}")
        lines.append(step.get("text", ""))
    return "\n".join(lines)


def plan_tool_chain(
    user_message: str,
    max_steps: int = 3,
) -> Dict[str, Any]:
    """
    一次性规划整个推理工具链（单次 LLM 调用）。

    相比逐步 ReAct 重规划，单次规划把 LLM 调用从「每步一次」降到「全程一次」：
    2 步工具链由 4 次调用降为 2 次（规划 + 综合），支撑「综合推理 ≤5 秒」验收点。

    Returns:
        {"action": "plan"|"finish", "steps": [{"tool": ..., "args": {...}}, ...],
         "error": bool, "reason": str|None}
    """
    from k12_app.backend.agent.tools.kb_tools import format_tool_descriptions, TOOL_REGISTRY

    system_prompt = REASONING_PLANNER_SYSTEM.format(
        tools=format_tool_descriptions(),
        max_steps=max_steps,
    )
    user_content = f"【家长问题】\n{user_message}\n\n请一次性规划需要调用的信息工具链。"

    # 中文场景下 max_tokens 过小易截断 JSON；解析失败先 LLM 修复原文，再重生成（最多各 1 次）
    last_reason = "规划器输出无法解析"
    for attempt in range(2):
        try:
            raw = call_llm(system_prompt, user_content, temperature=0.1, max_tokens=900,
                           reasoning_effort="low")
            data = extract_json_dict(raw)
            if not data:
                logger.warning(f"规划器返回无效 JSON(第{attempt + 1}次)，尝试 LLM 修复: {raw[:120]}")
                data = repair_json_with_llm(raw, expect_list=False, max_tokens=900)
            if not data:
                logger.warning(f"规划器修复失败(第{attempt + 1}次): {raw[:200]}")
                user_content += "\n\n注意：请只输出一个合法 JSON 对象，不要包含解释、多余文字或截断。"
                continue
            action = data.get("action")
            if action == "finish":
                return {"action": "finish", "steps": [], "error": False}
            if action == "plan":
                steps = []
                for s in (data.get("steps") or [])[:max_steps]:
                    if isinstance(s, dict) and s.get("tool") in TOOL_REGISTRY:
                        steps.append({
                            "tool": s["tool"],
                            "args": s.get("args") or {},
                        })
                return {"action": "plan", "steps": steps, "error": False}
            logger.warning(f"规划器返回无效动作(第{attempt + 1}次): {raw[:200]}")
        except Exception as e:
            logger.error(f"推理规划失败(第{attempt + 1}次): {e}")
            last_reason = str(e)
    return {"action": "finish", "error": True, "reason": last_reason}


# ============================================================
# 最终综合 System Prompt
# ============================================================

REASONING_FINAL_SYSTEM = """
你是擎天学智的金牌销售顾问，正在帮一线顾问把查到的信息综合成一段给家长的自然语言回复建议。

【核心要求】
1. 以"家长您好"或"xx家长您好"礼貌开头，语气专业、有温度、简洁
2. 结合「已收集的信息」回答家长的全部问题点，先共情再给方案
3. 每条关键信息标注来源：如（画像标签，最近更新 8月1日）/（2026 暑期开班计划）/（集团知识库 FAQ）
4. 不确定的信息必须老实标注："该建议基于部分信息推断，建议核实 XX 后再发送"
5. 知识库未命中、信息不足时，明确说明缺什么，并给出引导式兜底：
   "这个问题我暂时帮不上忙，您的专属课程顾问【顾问姓名】对这方面很了解，随时可以问她~"
6. 绝不编造：资料里没有的机构信息（成立年限/奖项/价格）一律不说，只标注来源里有的内容
7. 输出为一段完整的回复建议（可直接复制发送），控制在 200 字以内

【家长问题】
{question}

【已收集的信息】
{context}

请给出综合回复建议。
"""


def generate_final_answer(
    user_message: str,
    steps: List[Dict[str, Any]],
    advisor_name: str = "",
) -> str:
    """
    综合所有步骤信息生成最终回复建议（带来源标注）。

    Args:
        user_message: 家长原始问题
        steps: 推理步骤（含工具返回文本）
        advisor_name: 顾问姓名（兜底话术嵌入）

    Returns:
        建议文本
    """
    system_prompt = REASONING_FINAL_SYSTEM.replace("【顾问姓名】", advisor_name or "顾问")
    context = _format_context(steps)
    user_content = f"【家长问题】\n{user_message}\n\n【已收集的信息】\n{context}"
    try:
        answer = call_llm(system_prompt, user_content, temperature=0.5, max_tokens=1200,
                          reasoning_effort="low")
        answer = (answer or "").strip()
        if len(answer) < 10:
            raise ValueError("综合回复过短")
        return answer
    except Exception as e:
        logger.error(f"综合推理最终生成失败: {e}")
        # 降级兜底：拼接已收集信息要点
        lines = [f"家长您好，针对您的问题，我整理了以下信息供参考："]
        for i, step in enumerate(steps, 1):
            if step.get("text"):
                lines.append(f"{i}. {step['text'][:120]}")
        if advisor_name:
            lines.append(f"更详细的情况，可以随时咨询您的专属课程顾问{advisor_name}~")
        return "\n".join(lines)
