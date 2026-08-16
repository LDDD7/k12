# k12_app/routes/admin/tags.py
"""管理后台 — 标签管理与 SOP 模板"""

from fastapi import APIRouter, Request, HTTPException, Depends
from pydantic import BaseModel, field_validator
from typing import Optional, List

from k12_app.backend.services.tag_service import TagService
from k12_app.backend.services.customer_service import CustomerService

from k12_app.backend.services.auth_service import get_admin_session

router = APIRouter()

# 可衡量判定标准关键词（3.6）：ai_rule 需包含至少一个可观察/可量化的信号
_MEASURABLE_INDICATORS = (
    "≥", ">", "<", "≤", "=", "提及", "表达", "询问", "咨询", "连续", "记录",
    "次数", "天", "周", "月", "年", "未", "完成", "存在", "主动", "明确", "多次", "经常", "/",
)


def _validate_ai_rule(v: Optional[str]) -> Optional[str]:
    """校验 ai_rule 规则可衡量、可行动（3.6）"""
    if v is None:
        return v
    rule = v.strip()
    if not rule:
        raise ValueError("ai_rule 不能为空")
    if len(rule) < 4:
        raise ValueError("ai_rule 描述过于简短，请说明可衡量的判定标准")
    if not any(k in rule for k in _MEASURABLE_INDICATORS):
        raise ValueError("ai_rule 需包含可衡量的判定标准（如 '提及'/'≥3天'/'连续'/'多次' 等）")
    return rule


class TagCreateRequest(BaseModel):
    tag_id: str
    tag_name: str
    group_id: Optional[str] = None
    ai_rule: Optional[str] = None

    @field_validator("ai_rule")
    @classmethod
    def validate_ai_rule(cls, v: Optional[str]) -> Optional[str]:
        return _validate_ai_rule(v)


class TagUpdateRequest(BaseModel):
    tag_name: Optional[str] = None
    group_id: Optional[str] = None
    ai_rule: Optional[str] = None
    sop_template_id: Optional[int] = None

    @field_validator("ai_rule")
    @classmethod
    def validate_ai_rule(cls, v: Optional[str]) -> Optional[str]:
        return _validate_ai_rule(v)


@router.get("/tags")
async def get_tags(current_admin: dict = Depends(get_admin_session)):
    """获取标签体系（按权限范围过滤：all=全量，region=同区域，self=自己客户）"""
    tags = TagService.get_tags_by_scope(
        user_id=current_admin["user_id"],
        data_scope=current_admin["data_scope"],
        wework_account_id=current_admin.get("wework_account_id"),
    )
    return {"success": True, "data": tags}


@router.post("/tags")
async def create_tag(
    req: TagCreateRequest,
    current_admin: dict = Depends(get_admin_session),
):
    """新建标签定义"""
    success = TagService.create_tag(
        tag_id=req.tag_id,
        tag_name=req.tag_name,
        group_id=req.group_id,
        ai_rule=req.ai_rule,
    )
    if not success:
        raise HTTPException(status_code=500, detail="创建标签失败")
    return {"success": True, "message": "标签创建成功"}


@router.put("/tags/{tag_id}")
async def update_tag(
    tag_id: str,
    req: TagUpdateRequest,
    current_admin: dict = Depends(get_admin_session),
):
    """更新标签定义"""
    if not TagService.get_tag_by_id(tag_id):
        raise HTTPException(status_code=404, detail="标签不存在")

    success = TagService.update_tag(
        tag_id=tag_id,
        tag_name=req.tag_name,
        group_id=req.group_id,
        ai_rule=req.ai_rule,
        sop_template_id=req.sop_template_id,
    )
    if not success:
        raise HTTPException(status_code=500, detail="更新标签失败")
    return {"success": True, "message": "标签更新成功"}


@router.delete("/tags/{tag_id}")
async def delete_tag(
    tag_id: str,
    current_admin: dict = Depends(get_admin_session),
):
    """软删除标签"""
    if not TagService.get_tag_by_id(tag_id):
        raise HTTPException(status_code=404, detail="标签不存在")

    success = TagService.delete_tag(tag_id, soft=True)
    if not success:
        raise HTTPException(status_code=500, detail="删除标签失败")
    return {"success": True, "message": "标签删除成功"}


@router.get("/sop_templates")
async def get_sop_templates(current_admin: dict = Depends(get_admin_session)):
    """获取 SOP 模板列表"""
    templates = TagService.get_sop_templates()
    return {"success": True, "data": templates}


@router.get("/tags/{tag_id}/customers")
async def get_tag_customers(
    tag_id: str,
    current_admin: dict = Depends(get_admin_session),
):
    """按标签查询关联客户列表（按权限范围过滤）"""
    customers = TagService.get_customers_by_tag(
        tag_id=tag_id,
        user_id=current_admin["user_id"],
        data_scope=current_admin["data_scope"],
        wework_account_id=current_admin.get("wework_account_id"),
    )
    return {"success": True, "data": customers}


@router.get("/tag_stats")
async def get_tag_stats(current_admin: dict = Depends(get_admin_session)):
    """标签使用统计报表（各标签关联客户数、已确认数，按权限范围过滤）"""
    stats = TagService.get_tag_stats(
        user_id=current_admin["user_id"],
        data_scope=current_admin["data_scope"],
        wework_account_id=current_admin.get("wework_account_id"),
    )
    return {"success": True, "data": stats}


@router.post("/tags/{tag_id}/customers/{external_id}")
async def add_tag_customer(
    tag_id: str,
    external_id: str,
    current_admin: dict = Depends(get_admin_session),
):
    """给客户手动添加标签（已确认，来源=手动）"""
    if not TagService.get_tag_by_id(tag_id):
        raise HTTPException(status_code=404, detail="标签不存在")

    cust = CustomerService.get_by_external_id(
        external_id=external_id,
        user_id=current_admin["user_id"],
        data_scope=current_admin["data_scope"],
        wework_account_id=current_admin.get("wework_account_id"),
    )
    if not cust:
        raise HTTPException(status_code=404, detail="客户不存在或无访问权限")

    success = CustomerService.add_tag(
        external_id=external_id,
        tag_id=tag_id,
        source="手动",
        confirmed=True,
        confirmed_by=current_admin["user_id"],
    )
    if not success:
        raise HTTPException(status_code=500, detail="添加标签失败")
    return {"success": True, "message": "标签已添加"}


@router.delete("/tags/{tag_id}/customers/{external_id}")
async def remove_tag_customer(
    tag_id: str,
    external_id: str,
    current_admin: dict = Depends(get_admin_session),
):
    """从标签中移除指定客户"""
    success = CustomerService.remove_tag(external_id=external_id, tag_id=tag_id)
    if not success:
        raise HTTPException(status_code=404, detail="该客户未关联此标签")
    return {"success": True, "message": "已移除该客户"}
