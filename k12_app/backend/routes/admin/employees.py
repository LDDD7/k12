"""
管理后台员工管理路由
GET    /api/admin/employees                  — 员工列表（三维度权限过滤）
POST   /api/admin/employees                  — 添加员工（V3.2: password 必填 + roles + wework_account_id 可选）
POST   /api/admin/bind_wework                — 绑定企微账户（V3.2 新增：unbound→bound）
DELETE /api/admin/employees/<user_id>        — 删除员工
GET    /api/admin/employee_customers/<user_id> — 员工名下客户
"""
# k12_app/routes/admin/employees.py
"""管理后台 — 员工管理（含企微绑定 V3.2）"""

from fastapi import APIRouter, Request, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional, List

from k12_app.backend.services.employee_service import EmployeeService

from k12_app.backend.services.auth_service import get_admin_session

router = APIRouter()


# ============================================================
# 请求/响应模型
# ============================================================

class EmployeeCreateRequest(BaseModel):
    user_id: str
    name: str
    password: str
    org_id: Optional[str] = None
    dept: Optional[str] = None
    wework_account_id: Optional[str] = None
    roles: Optional[List[dict]] = None


class EmployeeUpdateRequest(BaseModel):
    name: Optional[str] = None
    org_id: Optional[str] = None
    dept: Optional[str] = None


class BindWeworkRequest(BaseModel):
    user_id: str
    wework_account_id: str


# ============================================================
# 接口
# ============================================================

@router.get("/employees")
async def list_employees(
    page: int = 1,
    page_size: int = 20,
    binding_status: Optional[str] = None,
    keyword: Optional[str] = None,
    dept: Optional[str] = None,
    current_admin: dict = Depends(get_admin_session),
):
    """获取员工列表（三维度权限过滤）"""
    result = EmployeeService.get_list(
        user_id=current_admin["user_id"],
        data_scope=current_admin["data_scope"],
        wework_account_id=current_admin.get("wework_account_id"),
        binding_status=binding_status,
        keyword=keyword,
        dept=dept,
        page=page,
        page_size=page_size,
    )
    return {"success": True, "data": result}


@router.post("/employees")
async def create_employee(
    req: EmployeeCreateRequest,
    current_admin: dict = Depends(get_admin_session),
):
    """添加员工（含密码和角色）"""
    if EmployeeService.exists(req.user_id):
        raise HTTPException(status_code=400, detail="员工 ID 已存在")

    success = EmployeeService.create_employee(
        user_id=req.user_id,
        name=req.name,
        password=req.password,
        org_id=req.org_id,
        dept=req.dept,
        wework_account_id=req.wework_account_id,
        roles=req.roles,
    )
    if not success:
        raise HTTPException(status_code=500, detail="创建员工失败")

    employee = EmployeeService.get_by_user_id(req.user_id)
    return {
        "success": True,
        "data": {
            "user_id": employee["user_id"],
            "name": employee["name"],
            "binding_status": employee.get("binding_status", "unbound"),
            "wework_account_id": employee.get("wework_account_id"),
        }
    }


@router.put("/employees/{user_id}")
async def update_employee(
    user_id: str,
    req: EmployeeUpdateRequest,
    current_admin: dict = Depends(get_admin_session),
):
    """更新员工信息（部门、片区、在线状态等）"""
    if not EmployeeService.exists(user_id):
        raise HTTPException(status_code=404, detail="员工不存在")

    # 权限校验：非超管只能修改自己权限范围内的员工
    if current_admin["data_scope"] == "self" and user_id != current_admin["user_id"]:
        raise HTTPException(status_code=403, detail="无权修改他人信息")

    success = EmployeeService.update_employee(
        user_id=user_id,
        name=req.name,
        org_id=req.org_id,
        dept=req.dept,
    )
    if not success:
        raise HTTPException(status_code=500, detail="更新失败")
    return {"success": True, "message": "员工信息已更新"}


@router.delete("/employees/{user_id}")
async def delete_employee(
    user_id: str,
    current_admin: dict = Depends(get_admin_session),
):
    """删除员工"""
    if not EmployeeService.exists(user_id):
        raise HTTPException(status_code=404, detail="员工不存在")

    success = EmployeeService.delete_employee(user_id)
    if not success:
        raise HTTPException(status_code=500, detail="删除失败")
    return {"success": True, "message": "删除成功"}


@router.post("/bind_wework")
async def bind_wework(
    req: BindWeworkRequest,
    current_admin: dict = Depends(get_admin_session),
):
    """绑定企微账户（V3.2）"""
    try:
        success = EmployeeService.bind_wework(
            user_id=req.user_id,
            wework_account_id=req.wework_account_id,
            current_admin=current_admin,
        )
    except ValueError as e:
        if str(e) == "ALREADY_BOUND":
            return {
                "success": False,
                "error": "该员工已绑定企微账户",
                "code": "ALREADY_BOUND"
            }
        raise HTTPException(status_code=400, detail=str(e))
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))

    if not success:
        raise HTTPException(status_code=500, detail="绑定失败")

    updated = EmployeeService.get_by_user_id(req.user_id)
    return {
        "success": True,
        "data": {
            "user_id": req.user_id,
            "wework_account_id": req.wework_account_id,
            "binding_status": updated["binding_status"],
            "bound_at": updated.get("bound_at"),
        }
    }


@router.get("/employee_customers/{user_id}")
async def get_employee_customers(
    user_id: str,
    current_admin: dict = Depends(get_admin_session),
):
    """获取某员工名下的客户列表"""
    if current_admin["data_scope"] == "self" and user_id != current_admin["user_id"]:
        raise HTTPException(status_code=403, detail="无权查看他人客户")

    try:
        customers = EmployeeService.get_employee_customers(
            user_id=user_id,
            current_admin=current_admin,
        )
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"success": True, "data": customers}
