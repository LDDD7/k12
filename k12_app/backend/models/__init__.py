"""
ORM 数据模型 — SQLAlchemy 2.0 声明式映射
对应 MySQL 数据库 k12_agent_db 全部 22 张表（V3.2 数据库设计）。

列类型与 init_db.sql 一一对应：
- TINYINT(1) → Boolean
- JSON      → sqlalchemy.JSON（读写自动序列化/反序列化）
- DECIMAL   → Numeric
- DATETIME(3) → DateTime(fsp=3)
- DATE      → Date
"""

from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    Date,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.mysql import DATETIME as MySQLDateTime

from k12_app.backend.dao.db import Base


def _datetime3() -> MySQLDateTime:
    """DATETIME(3) 列类型（毫秒精度）"""
    return MySQLDateTime(fsp=3)


# ============================================================
# 一、sys_ 系统管理类
# ============================================================


class SysWeworkAccount(Base):
    """企微账户表 3.1"""

    __tablename__ = "sys_wework_account"

    id = Column(Integer, primary_key=True, autoincrement=True)
    account_id = Column(String(32), nullable=False, unique=True)
    account_name = Column(String(128), nullable=False)
    corp_id = Column(String(64), nullable=False)
    corp_secret = Column(String(256), nullable=False)
    region = Column(String(64), nullable=False)
    agent_id = Column(String(64))
    is_active = Column(Boolean, default=True)
    created_at = Column(_datetime3(), default=datetime.now)
    updated_at = Column(_datetime3(), default=datetime.now, onupdate=datetime.now)


class SysOrganization(Base):
    """组织架构表 3.2"""

    __tablename__ = "sys_organization"

    id = Column(Integer, primary_key=True, autoincrement=True)
    org_id = Column(String(32), nullable=False, unique=True)
    org_name = Column(String(128), nullable=False)
    parent_org_id = Column(String(32))
    org_type = Column(String(16), nullable=False)
    wework_account_id = Column(String(32), nullable=False)
    sort_order = Column(Integer, default=0)
    created_at = Column(_datetime3(), default=datetime.now)
    updated_at = Column(_datetime3(), default=datetime.now, onupdate=datetime.now)


class SysRole(Base):
    """角色定义表 3.3"""

    __tablename__ = "sys_role"

    id = Column(Integer, primary_key=True, autoincrement=True)
    role_code = Column(String(32), nullable=False, unique=True)
    role_name = Column(String(64), nullable=False)
    description = Column(String(256))
    data_scope = Column(String(32), nullable=False)
    module_permissions = Column(JSON)
    created_at = Column(_datetime3(), default=datetime.now)
    updated_at = Column(_datetime3(), default=datetime.now, onupdate=datetime.now)


class SysEmployee(Base):
    """员工表 3.4 (V3.2: wework_account_id 可空)"""

    __tablename__ = "sys_employee"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(64), nullable=False, unique=True)
    name = Column(String(64), nullable=False)
    org_id = Column(String(32))
    dept = Column(String(128))
    wework_account_id = Column(String(32))
    password_hash = Column(String(256), nullable=False)
    binding_status = Column(String(16), nullable=False, default="unbound")
    bound_at = Column(_datetime3())
    created_at = Column(_datetime3(), default=datetime.now)
    updated_at = Column(_datetime3(), default=datetime.now, onupdate=datetime.now)


class SysRemindPreference(Base):
    """用户提醒偏好表 3.4.1 (V3.3)"""

    __tablename__ = "sys_remind_preference"

    user_id = Column(String(64), primary_key=True, nullable=False)
    remind_pref = Column(String(8), nullable=False, default="mid")
    updated_at = Column(_datetime3(), default=datetime.now, onupdate=datetime.now)


class SysUserRole(Base):
    """用户角色关联表 3.5"""

    __tablename__ = "sys_user_role"
    __table_args__ = (
        UniqueConstraint("user_id", "role_code", "wework_account_id", name="uk_user_role_account"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(64), nullable=False)
    role_code = Column(String(32), nullable=False)
    wework_account_id = Column(String(32), nullable=False)
    created_at = Column(_datetime3(), default=datetime.now)
    updated_at = Column(_datetime3(), default=datetime.now, onupdate=datetime.now)


# ============================================================
# 二、biz_ 业务数据类
# ============================================================


class BizCustomer(Base):
    """客户表 3.6"""

    __tablename__ = "biz_customer"

    id = Column(Integer, primary_key=True, autoincrement=True)
    external_id = Column(String(64), nullable=False, unique=True)
    union_id = Column(String(64))
    wework_account_id = Column(String(32), nullable=False)
    follow_user_id = Column(String(64), nullable=False)
    name = Column(String(64))
    child_name = Column(String(64))
    school = Column(String(128))
    grade = Column(String(16))
    focus_subject = Column(String(64))
    remark = Column(String(128))
    stage = Column(String(16))
    lead_source = Column(String(32))
    created_at = Column(_datetime3(), default=datetime.now)
    updated_at = Column(_datetime3(), default=datetime.now, onupdate=datetime.now)


class BizCustomerTag(Base):
    """客户标签关联表 3.10"""

    __tablename__ = "biz_customer_tag"
    __table_args__ = (
        UniqueConstraint("external_id", "tag_id", name="uk_customer_tag"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    external_id = Column(String(64), nullable=False)
    tag_id = Column(String(32), nullable=False)
    source = Column(String(16), nullable=False)
    confirmed = Column(Boolean, default=False)
    confirmed_by = Column(String(64))
    confirmed_at = Column(_datetime3())
    created_at = Column(_datetime3(), default=datetime.now)
    updated_at = Column(_datetime3(), default=datetime.now, onupdate=datetime.now)


class BizOrder(Base):
    """订单表 3.16"""

    __tablename__ = "biz_order"

    id = Column(Integer, primary_key=True, autoincrement=True)
    order_id = Column(String(32), nullable=False, unique=True)
    union_id = Column(String(64), nullable=False)
    wework_account_id = Column(String(32), nullable=False)
    product_names = Column(JSON)
    amount = Column(Numeric(10, 2))
    status = Column(String(16), nullable=False)
    order_time = Column(_datetime3())
    order_date = Column(Date)
    created_at = Column(_datetime3(), default=datetime.now)
    updated_at = Column(_datetime3(), default=datetime.now, onupdate=datetime.now)


class BizSchedule(Base):
    """日程表 3.17"""

    __tablename__ = "biz_schedule"

    id = Column(Integer, primary_key=True, autoincrement=True)
    external_id = Column(String(64), nullable=False)
    user_id = Column(String(64), nullable=False)
    wework_account_id = Column(String(32), nullable=False)
    title = Column(String(128), nullable=False)
    start_time = Column(_datetime3(), nullable=False)
    end_time = Column(_datetime3())
    priority = Column(String(8), nullable=False, default="中")
    source = Column(String(16), nullable=False)
    status = Column(String(16), nullable=False, default="待确认")
    wx_calendar_event_id = Column(String(64))
    created_at = Column(_datetime3(), default=datetime.now)
    updated_at = Column(_datetime3(), default=datetime.now, onupdate=datetime.now)


class BizFollowUp(Base):
    """CRM 跟进记录表 3.17.1 (V3.1)"""

    __tablename__ = "biz_follow_up"

    id = Column(Integer, primary_key=True, autoincrement=True)
    external_id = Column(String(64), nullable=False)
    user_id = Column(String(64), nullable=False)
    wework_account_id = Column(String(32), nullable=False)
    follow_up_type = Column(String(16), nullable=False)
    content = Column(Text)
    result = Column(String(16))
    follow_up_time = Column(_datetime3(), nullable=False)
    next_action = Column(String(128))
    created_at = Column(_datetime3(), default=datetime.now)
    updated_at = Column(_datetime3(), default=datetime.now, onupdate=datetime.now)


# ============================================================
# 三、cfg_ 配置数据类
# ============================================================


class CfgTagGroup(Base):
    """标签分组表 3.7"""

    __tablename__ = "cfg_tag_group"

    id = Column(Integer, primary_key=True, autoincrement=True)
    group_id = Column(String(32), nullable=False, unique=True)
    group_name = Column(String(64), nullable=False)
    strategy_id = Column(Integer, default=0)
    created_at = Column(_datetime3(), default=datetime.now)
    updated_at = Column(_datetime3(), default=datetime.now, onupdate=datetime.now)


class CfgSopTemplate(Base):
    """SOP 模板表 3.9"""

    __tablename__ = "cfg_sop_template"

    id = Column(Integer, primary_key=True, autoincrement=True)
    template_name = Column(String(64), nullable=False)
    steps = Column(JSON, nullable=False)
    created_at = Column(_datetime3(), default=datetime.now)
    updated_at = Column(_datetime3(), default=datetime.now, onupdate=datetime.now)


class CfgTagDefinition(Base):
    """标签定义表 3.8"""

    __tablename__ = "cfg_tag_definition"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tag_id = Column(String(32), nullable=False, unique=True)
    tag_name = Column(String(64), nullable=False)
    group_id = Column(String(32), nullable=False)
    sop_template_id = Column(Integer)
    ai_rule = Column(Text)
    deleted = Column(Boolean, default=False)
    created_at = Column(_datetime3(), default=datetime.now)
    updated_at = Column(_datetime3(), default=datetime.now, onupdate=datetime.now)


# ============================================================
# 四、ai_ AI 产出类
# ============================================================


class AiCustomerProfile(Base):
    """客户画像表 3.11"""

    __tablename__ = "ai_customer_profile"

    id = Column(Integer, primary_key=True, autoincrement=True)
    external_id = Column(String(64), nullable=False)
    wework_account_id = Column(String(32), nullable=False)
    follow_user_id = Column(String(64), nullable=False)
    status = Column(String(16), nullable=False, default="草稿")
    confirmed_by = Column(String(64))
    confirmed_at = Column(_datetime3())
    embedding_status = Column(String(16), default="pending")
    created_at = Column(_datetime3(), default=datetime.now)
    updated_at = Column(_datetime3(), default=datetime.now, onupdate=datetime.now)


class AiProfileItem(Base):
    """画像字段项表 3.12"""

    __tablename__ = "ai_profile_item"

    id = Column(Integer, primary_key=True, autoincrement=True)
    profile_id = Column(Integer, nullable=False)
    item_name = Column(String(64), nullable=False)
    item_value = Column(Text)
    confidence = Column(Numeric(3, 2))
    confidence_level = Column(String(8))
    source_type = Column(String(16))
    source_ref = Column(String(128))
    created_at = Column(_datetime3(), default=datetime.now)
    updated_at = Column(_datetime3(), default=datetime.now, onupdate=datetime.now)


class AiTaskLog(Base):
    """AI 任务日志表 3.18"""

    __tablename__ = "ai_task_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_type = Column(String(32), nullable=False)
    user_id = Column(String(64), nullable=False)
    external_id = Column(String(64), nullable=False)
    wework_account_id = Column(String(32), nullable=False)
    action = Column(String(16), nullable=False)
    action_detail = Column(JSON)
    duration_ms = Column(Integer)
    created_at = Column(_datetime3(), default=datetime.now)
    updated_at = Column(_datetime3(), default=datetime.now, onupdate=datetime.now)


class AiFeedbackSignal(Base):
    """反馈信号表 3.19"""

    __tablename__ = "ai_feedback_signal"

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_log_id = Column(Integer, nullable=False)
    wework_account_id = Column(String(32), nullable=False)
    signal_type = Column(String(16), nullable=False)
    snapshot = Column(JSON)
    created_at = Column(_datetime3(), default=datetime.now)
    updated_at = Column(_datetime3(), default=datetime.now, onupdate=datetime.now)


# ============================================================
# 五、msg_ 消息数据类（按月分区表）
# ============================================================


class MsgWxqyChat(Base):
    """企微聊天消息表 3.13（按月分区，主键 id + msg_date）"""

    __tablename__ = "msg_wxqy_chat"
    __table_args__ = (
        UniqueConstraint("msg_id", "msg_date", name="uk_wxqy_chat_msg_id"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    msg_id = Column(String(64), nullable=False)
    sorted_key = Column(String(128), nullable=False)
    user_id = Column(String(64), nullable=False)
    external_id = Column(String(64), nullable=False)
    wework_account_id = Column(String(32), nullable=False)
    sender = Column(String(64))
    receiver = Column(String(64))
    sender_name = Column(String(64))
    receiver_name = Column(String(64))
    msg_type = Column(String(16), nullable=False)
    content = Column(Text)
    msg_date = Column(Date, primary_key=True, nullable=False)
    send_time = Column(_datetime3(), nullable=False)
    created_at = Column(_datetime3(), default=datetime.now)


class MsgWxkfChat(Base):
    """客服消息表 3.14（按月分区，主键 id + msg_date）"""

    __tablename__ = "msg_wxkf_chat"
    __table_args__ = (
        UniqueConstraint("msg_id", "msg_date", name="uk_wxkf_chat_msg_id"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    msg_id = Column(String(64), nullable=False)
    external_id = Column(String(64), nullable=False)
    wework_account_id = Column(String(32), nullable=False)
    kf_account = Column(String(64))
    sender = Column(String(64))
    sender_role = Column(String(16), nullable=False)
    sender_name = Column(String(64))
    msg_type = Column(String(16), nullable=False)
    content = Column(Text)
    msg_date = Column(Date, primary_key=True, nullable=False)
    send_time = Column(_datetime3(), nullable=False)
    created_at = Column(_datetime3(), default=datetime.now)


# ============================================================
# 六、rag_ AI 知识检索类
# ============================================================


class RagKbDocument(Base):
    """RAG 知识库文档表 3.20 (V3.0)"""

    __tablename__ = "rag_kb_document"

    id = Column(Integer, primary_key=True, autoincrement=True)
    doc_id = Column(String(64), nullable=False, unique=True)
    kb_name = Column(String(32), nullable=False)
    file_path = Column(String(256), nullable=False)
    title = Column(String(128))
    chunk_count = Column(Integer, default=0)
    char_count = Column(Integer, default=0)
    chroma_collection = Column(String(64), nullable=False)
    status = Column(String(16), default="active")
    last_indexed_at = Column(_datetime3())
    indexed_by = Column(String(64))
    created_at = Column(_datetime3(), default=datetime.now)
    updated_at = Column(_datetime3(), default=datetime.now, onupdate=datetime.now)


class RagKbIndexLog(Base):
    """RAG 索引构建日志表 3.21 (V3.0)"""

    __tablename__ = "rag_kb_index_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    kb_name = Column(String(32), nullable=False)
    doc_count = Column(Integer)
    chunk_count = Column(Integer)
    elapsed_ms = Column(Integer)
    status = Column(String(16), nullable=False)
    error_message = Column(Text)
    triggered_by = Column(String(64), nullable=False)
    created_at = Column(_datetime3(), default=datetime.now)


__all__ = [
    "Base",
    "SysWeworkAccount",
    "SysOrganization",
    "SysRole",
    "SysEmployee",
    "SysRemindPreference",
    "SysUserRole",
    "BizCustomer",
    "BizCustomerTag",
    "BizOrder",
    "BizSchedule",
    "BizFollowUp",
    "CfgTagGroup",
    "CfgSopTemplate",
    "CfgTagDefinition",
    "AiCustomerProfile",
    "AiProfileItem",
    "AiTaskLog",
    "AiFeedbackSignal",
    "MsgWxqyChat",
    "MsgWxkfChat",
    "RagKbDocument",
    "RagKbIndexLog",
]
