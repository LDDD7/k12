# k12_app/services/reply_service.py
"""回复建议与家长模拟服务 — 从路由层拆分的业务逻辑"""

import hashlib
import logging
import random
from datetime import datetime
from typing import List, Dict, Optional

from k12_app.backend.agent.llm.client import chat_completion
from k12_app.backend.agent.llm.reply_prompt import generate_replies as llm_generate_replies
from k12_app.backend.agent.llm.reply_prompt import infer_stage

logger = logging.getLogger(__name__)


def build_profile_for_llm(cust: dict) -> dict:
    """从客户数据构建 LLM 所需的画像字典"""
    profile = {}
    for key in ("child_name", "grade", "focus_subject", "school", "stage", "remark"):
        val = cust.get(key)
        if val:
            profile[key] = val
    if cust.get("name"):
        profile["parent_name"] = cust["name"]
    return profile


def generate_varied_replies(customer_name: str, child_name: str, grade: str, subject: str, chat_seed: str) -> list:
    """模板后备：当 LLM 不可用时使用硬编码模板生成回复"""
    seed_val = int(hashlib.md5(chat_seed.encode()).hexdigest()[:8], 16) if chat_seed else random.randint(0, 999999)
    rng = random.Random(seed_val)

    cn = customer_name or "家长"
    kn = child_name or "孩子"
    gr = grade or "目前"
    sj = subject or "学科"

    templates_pools = [
        [
            {"body": f"{cn}您好，关于{kn}的{sj}情况，建议先做一次免费学科测评，我们根据测评结果制定针对性的学习方案。测评大概30分钟，当场出报告。",
             "why": "免费测评降低决策门槛，针对性方案增强专业感", "conf": 92},
        ],
        [
            {"body": f"针对{kn}的情况，我们推荐两种方案：一是同步辅导班，小班教学性价比高；二是一对一针对性辅导，效果更显著。您可以根据预算和需求选择。",
             "why": "提供明确选项而非单一推荐，尊重客户选择权", "conf": 91},
        ],
        [
            {"body": f"{cn}您好，关于费用方面，同步辅导班约200-260元/课时，一对一约400-600元/课时。首次试听免费，现在报名还可享受早鸟优惠。建议先带{kn}来免费测评，我们再推荐最合适的方案。",
             "why": "透明报价+优惠活动，建立信任", "conf": 92},
        ],
        [
            {"body": f"针对{kn}的升学目标，我们专门开设了升学冲刺班，课程紧扣考试大纲，由带过多年毕业班的资深教师授课，包含真题精讲、考点梳理和考前模拟。",
             "why": "升学需求精准响应，展示专业备考方案", "conf": 94},
        ],
        [
            {"body": f"很多家长都有和您类似的顾虑，我们的教学方法经过多年验证，{sj}平均提分15-25分。您可以看看我们之前学员的提分案例，效果都是实打实的。",
             "why": "数据化效果展示+真实案例背书", "conf": 89},
        ],
        [
            {"body": f"{cn}您好，我仔细看了{kn}的情况，这个阶段的{sj}确实容易出现瓶颈，不过也正是最好补救的时机。我们有很多类似情况的孩子，经过系统辅导后都有了明显进步。",
             "why": "共情+专业判断，建立情感连接", "conf": 93},
        ],
    ]

    pool_indices = list(range(len(templates_pools)))
    rng.shuffle(pool_indices)
    replies = []
    for pi in pool_indices[:3]:
        pool = templates_pools[pi]
        t = pool[rng.randint(0, len(pool) - 1)]
        replies.append({
            "body": t["body"],
            "why": t["why"],
            "conf": str(t["conf"]) + "%",
        })
    return replies


def generate_reply_suggestions(
    cust: dict,
    recent_chat: list,
    chat_seed: str,
    regenerate: bool,
    external_id: str,
    user_id: str,
) -> list:
    """生成回复建议（LLM 优先，模板后备），返回格式化后的建议列表"""
    if regenerate:
        chat_seed += "|regenerate_" + str(int(datetime.now().timestamp() * 1000))

    # 从向量库检索该客户的历史聊天记录 + 话术库知识，增强回复上下文
    retrieved_messages = []
    retrieved_scripts = []
    try:
        from k12_app.backend.services.rag_service import RAGService
        query = " ".join([(m.get("content") or "") for m in recent_chat[-3:]]) or "客户咨询"
        retrieved_messages = RAGService.retrieve_chat_messages(
            query=query,
            top_k=10,
            external_id=external_id,
            user_id=user_id,
        )
        retrieved_scripts = RAGService.retrieve_scripts(query=query, top_k=5)
    except Exception as e:
        logger.warning(f"向量检索聊天记录失败: {e}")

    # 优先使用 LLM 生成回复
    try:
        profile = build_profile_for_llm(cust)
        llm_replies = llm_generate_replies(
            profile=profile,
            recent_chat=recent_chat,
            scene="销售",
            count=3,
            retrieved_messages=retrieved_messages,
            retrieved_scripts=retrieved_scripts,
            stage=infer_stage(cust.get("grade")),
        )
        if llm_replies and len(llm_replies) >= 2:
            formatted = []
            for i, body in enumerate(llm_replies[:3]):
                formatted.append({
                    "body": body,
                    "why": "AI 基于客户画像和聊天记录智能生成",
                    "conf": str(90 - i * 3) + "%",
                })
            return formatted
    except Exception as e:
        logger.warning(f"LLM 回复生成失败，回退到模板: {e}")

    # 模板后备
    return generate_varied_replies(
        customer_name=cust.get("name") or "家长",
        child_name=cust.get("child_name") or "",
        grade=cust.get("grade") or "",
        subject=cust.get("focus_subject") or "",
        chat_seed=chat_seed,
    )


def simulate_parent_reply(cust: dict, messages: Optional[List[dict]] = None) -> str:
    """AI 模拟家长回复（演示用，不连接真实企微）"""
    child_name = cust.get("child_name") or "学生"
    grade = cust.get("grade") or ""
    subject = cust.get("focus_subject") or ""
    stage = cust.get("stage") or ""

    system_prompt = f"""你正在模拟一位K12教育机构的学生家长，在和课程顾问微信聊天。请以家长身份自然地回复。

【背景信息】
- 家长称呼：{cust.get('name') or '家长'}
- 学生：{child_name}
- 年级：{grade}
- 关注科目：{subject}
- 当前阶段：{stage}

【回复要求】
1. 语言自然口语化，像真实家长微信聊天
2. 根据对话上下文做出合理回应
3. 回复长度30-100字，不要太长
4. 可以表达疑问、犹豫、接受或拒绝，符合真实家长的心态
5. 偶尔使用口语化词语
6. 只输出家长说的话，不要加任何前缀或说明"""

    llm_messages = [{"role": "system", "content": system_prompt}]
    for msg in (messages or []):
        role = "assistant" if msg.get("role") == "parent" else "user"
        content = msg.get("content", "")
        if content.strip():
            llm_messages.append({"role": role, "content": content})

    if messages:
        # 有历史对话 → 以家长身份回复顾问最后一条消息
        llm_messages.append({"role": "user", "content": "请以上述家长的身份，回复顾问最后一条消息。"})
    else:
        # V3.3.2：无历史（如刚清空）→ 让家长主动发起话题，避免模型对着不存在的"最后一条消息"空转
        llm_messages.append({"role": "user",
                             "content": "请以上述家长的身份，自然地给顾问发一条消息开启对话（例如咨询孩子学习情况或课程安排）。"})

    try:
        parent_reply = chat_completion(llm_messages, temperature=0.85, max_tokens=300)
        parent_reply = (parent_reply or "").strip()
    except Exception as e:
        logger.warning(f"模拟家长回复调用失败: {e}")
        parent_reply = ""

    # V3.3.2：LLM 返回空时给温和兜底，避免前端"没反应"
    if not parent_reply:
        parent_reply = "嗯嗯，我再跟孩子商量一下，回头给您答复哈~"
    return parent_reply
