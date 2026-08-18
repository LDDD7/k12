# k12_app/agent/llm/client.py
"""
DeepSeek LLM 客户端 — 统一调用入口
支持：
- 单次调用（call_llm）：用于画像/标签/日程等结构化任务
- 对话调用（chat_completion）：用于 free_chat 自由对话，支持多轮上下文
"""

import logging
from typing import Optional, List, Dict, Any
from openai import OpenAI

from k12_app.backend.agent.llm.utils import format_retrieved_messages
from k12_app.backend.config import settings

logger = logging.getLogger(__name__)

# 统一从 config.settings 读取配置
DEEPSEEK_API_KEY = settings.DEEPSEEK_API_KEY
DEEPSEEK_BASE_URL = settings.DEEPSEEK_BASE_URL
DEFAULT_MODEL = settings.DEEPSEEK_MODEL
DEFAULT_TIMEOUT = settings.LLM_TIMEOUT

# 全局客户端
_client: Optional[OpenAI] = None


# ============================================================
# 客户端管理
# ============================================================

def get_llm_client() -> OpenAI:
    """获取 DeepSeek 客户端（单例）"""
    global _client
    if _client is None:
        if not DEEPSEEK_API_KEY:
            raise ValueError("DEEPSEEK_API_KEY 未配置，请检查 .env 文件")
        _client = OpenAI(
            api_key=DEEPSEEK_API_KEY,
            base_url=DEEPSEEK_BASE_URL,
            timeout=DEFAULT_TIMEOUT,
        )
        logger.info(f"DeepSeek 客户端初始化成功，模型: {DEFAULT_MODEL}")
    return _client


# ============================================================
# 核心调用函数
# ============================================================

def _complete_with_fallback(client, model_name: str, messages: List[Dict[str, str]],
                            temperature: float, max_tokens: Optional[int],
                            extra_kwargs: Optional[Dict] = None) -> str:
    """
    调用 LLM 并处理推理模型（deepseek-v4-flash）的 content 空返回问题（V3.3.2）：

    该模型偶发把完整回答放进 message.reasoning_content 而 message.content 为空。
    不能直接把 reasoning_content 当答案返回——它通常是思考过程（含噪音），
    正确做法：用思考内容作为上下文引导模型再生成一次最终回复（最多重试 1 次）。
    """
    extra_kwargs = extra_kwargs or {}
    try:
        response = client.chat.completions.create(
            model=model_name,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            **extra_kwargs,
        )
    except Exception as e:
        logger.error(f"LLM 调用失败: {e}")
        raise

    message = response.choices[0].message
    result = message.content or ""

    if not result:
        reasoning = getattr(message, "reasoning_content", None) or ""
        logger.info(f"LLM 返回空 content，reasoning_content 长度={len(reasoning)}，引导重试一次")
        if reasoning:
            try:
                retry_messages = list(messages) + [
                    {"role": "assistant", "content": reasoning},
                    {"role": "user",
                     "content": "请直接输出最终回复内容本身，不要包含任何思考、分析或说明。"},
                ]
                resp2 = client.chat.completions.create(
                    model=model_name,
                    messages=retry_messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    **extra_kwargs,
                )
                result = resp2.choices[0].message.content or ""
            except Exception as e:
                logger.warning(f"LLM 重试失败: {e}")
    return result


def call_llm(
    system_prompt: str,
    user_content: str,
    temperature: float = 0.3,
    max_tokens: Optional[int] = None,
    model: Optional[str] = None,
    reasoning_effort: Optional[str] = None,
) -> str:
    """
    单次调用 LLM（用于画像/标签/日程等结构化任务）

    Args:
        system_prompt: 系统提示词
        user_content: 用户输入内容
        temperature: 温度参数（0.0-1.0）
        max_tokens: 最大输出 token 数
        model: 模型名称
        reasoning_effort: 推理强度（low/medium/high），仅对推理模型生效，可降低延迟

    Returns:
        LLM 响应文本
    """
    if not user_content or not user_content.strip():
        logger.warning("用户输入为空，跳过 LLM 调用")
        return ""

    model_name = model or DEFAULT_MODEL
    client = get_llm_client()

    extra_kwargs = {}
    if reasoning_effort is not None:
        extra_kwargs["reasoning_effort"] = reasoning_effort

    result = _complete_with_fallback(
        client=client,
        model_name=model_name,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        temperature=temperature,
        max_tokens=max_tokens,
        extra_kwargs=extra_kwargs,
    )
    logger.debug(f"LLM 调用成功，输出长度: {len(result)} 字符")
    return result


def chat_completion(
    messages: List[Dict[str, str]],
    temperature: float = 0.7,
    max_tokens: Optional[int] = None,
    model: Optional[str] = None,
) -> str:
    """
    多轮对话调用（用于 free_chat 自由对话 / 模拟家长等）

    Args:
        messages: 消息列表 [{"role": "system"|"user"|"assistant", "content": "..."}]
        temperature: 温度参数（创作类任务用 0.7，分析类用 0.3）
        max_tokens: 最大输出 token 数
        model: 模型名称

    Returns:
        LLM 响应文本
    """
    if not messages:
        logger.warning("消息列表为空，跳过 LLM 调用")
        return ""

    # 过滤空消息
    messages = [m for m in messages if m.get("content", "").strip()]

    if not messages:
        return ""

    model_name = model or DEFAULT_MODEL
    client = get_llm_client()

    result = _complete_with_fallback(
        client=client,
        model_name=model_name,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    logger.debug(f"对话调用成功，输出长度: {len(result)} 字符")
    return result


# ============================================================
# 便捷函数
# ============================================================

def build_chat_messages(
    user_message: str,
    system_prompt: Optional[str] = None,
    context: Optional[Dict[str, Any]] = None,
    chat_history: Optional[List[Dict[str, str]]] = None,
    retrieved_messages: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, str]]:
    """
    构建标准对话消息列表（供 chat_with_context 复用）

    Args:
        user_message: 用户当前输入
        system_prompt: 系统提示词
        context: 上下文信息（如客户画像等）
        chat_history: 历史对话记录
        retrieved_messages: 向量库检索到的历史聊天记录

    Returns:
        消息列表 [{"role": "...", "content": "..."}, ...]
    """
    messages: List[Dict[str, str]] = []

    # 1. 构建系统提示词
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    else:
        messages.append({
            "role": "system",
            "content": """
你是擎天学智的 K12 教育销售助手，拥有丰富的课程咨询经验。
你的任务是帮助销售顾问回答家长的问题，提供专业的建议。

核心原则：
1. 专业、耐心、有同理心
2. 基于提供的客户信息回答问题
3. 如果需要，可以引导家长了解课程或安排试听
4. 不确定的事情不要瞎编，建议顾问确认
"""
        })

    # 2. 添加上下文信息（如果有）
    if context:
        context_text = f"""
【客户信息】
- 学生姓名：{context.get('child_name', '未知')}
- 年级：{context.get('grade', '未知')}
- 关注科目：{context.get('focus_subject', '未知')}
- 学校：{context.get('school', '未知')}
- 当前阶段：{context.get('stage', '未知')}
- 备注：{context.get('remark', '无')}
"""
        messages.append({
            "role": "system",
            "content": f"以下是当前客户的背景信息，请基于这些信息回答：\n{context_text}"
        })

    # 3. 添加历史对话（如果有）
    if chat_history:
        messages.extend(chat_history)

    # 3.5 添加向量库检索到的历史聊天记录（如果有）
    retrieved_text = format_retrieved_messages(retrieved_messages)
    if retrieved_text:
        messages.append({
            "role": "system",
            "content": f"以下是该客户过往的相关聊天记录（用于理解上下文，非当前对话）：\n{retrieved_text}",
        })

    # 4. 添加当前用户消息
    messages.append({"role": "user", "content": user_message})

    return messages


def chat_with_context(
    user_message: str,
    context: Optional[Dict[str, Any]] = None,
    chat_history: Optional[List[Dict[str, str]]] = None,
    system_prompt: Optional[str] = None,
    temperature: float = 0.7,
    retrieved_messages: Optional[List[Dict[str, Any]]] = None,
) -> str:
    """
    带上下文的对话（用于 free_chat 结合客户信息）

    Args:
        user_message: 用户当前输入
        context: 上下文信息（如客户画像、聊天记录等）
        chat_history: 历史对话记录
        system_prompt: 系统提示词
        temperature: 温度参数
        retrieved_messages: 向量库检索到的历史聊天记录

    Returns:
        LLM 响应文本
    """
    messages = build_chat_messages(
        user_message=user_message,
        system_prompt=system_prompt,
        context=context,
        chat_history=chat_history,
        retrieved_messages=retrieved_messages,
    )
    return chat_completion(messages, temperature=temperature)