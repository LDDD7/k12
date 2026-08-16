-- ============================================================
-- 擎天学智 K12 用户画像推荐系统 — 数据库初始化脚本
-- 数据库：k12_agent_db (MySQL 8.0)
-- 设计依据：数据库设计文档 V3.2
-- 共 21 张表 + 初始化数据
-- 使用方法：docker exec -i k12-mysql mysql -u root -proot < init_db.sql
-- ============================================================

CREATE DATABASE IF NOT EXISTS k12_agent_db
  DEFAULT CHARACTER SET utf8mb4
  DEFAULT COLLATE utf8mb4_unicode_ci;

USE k12_agent_db;

-- ============================================================
-- 一、sys_ 系统管理类 (5 张表)
-- ============================================================

-- 3.1 企微账户表
CREATE TABLE sys_wework_account (
    id           BIGINT AUTO_INCREMENT PRIMARY KEY,
    account_id   VARCHAR(32) NOT NULL,
    account_name VARCHAR(128) NOT NULL,
    corp_id      VARCHAR(64) NOT NULL,
    corp_secret  VARCHAR(256) NOT NULL,
    region       VARCHAR(64) NOT NULL,
    agent_id     VARCHAR(64),
    is_active    TINYINT(1) DEFAULT 1,
    created_at   DATETIME(3) DEFAULT CURRENT_TIMESTAMP(3),
    updated_at   DATETIME(3) DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
    CONSTRAINT uk_wework_account_id UNIQUE (account_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX idx_wework_account_region ON sys_wework_account (region);

-- 3.2 组织架构表
CREATE TABLE sys_organization (
    id                BIGINT AUTO_INCREMENT PRIMARY KEY,
    org_id            VARCHAR(32) NOT NULL,
    org_name          VARCHAR(128) NOT NULL,
    parent_org_id     VARCHAR(32),
    org_type          VARCHAR(16) NOT NULL,
    wework_account_id VARCHAR(32) NOT NULL,
    sort_order        INT DEFAULT 0,
    created_at        DATETIME(3) DEFAULT CURRENT_TIMESTAMP(3),
    updated_at        DATETIME(3) DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
    CONSTRAINT uk_org_id UNIQUE (org_id),
    CONSTRAINT fk_org_account FOREIGN KEY (wework_account_id)
        REFERENCES sys_wework_account(account_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX idx_org_parent ON sys_organization (parent_org_id);
CREATE INDEX idx_org_account ON sys_organization (wework_account_id);

-- 3.3 角色定义表
CREATE TABLE sys_role (
    id                 BIGINT AUTO_INCREMENT PRIMARY KEY,
    role_code          VARCHAR(32) NOT NULL,
    role_name          VARCHAR(64) NOT NULL,
    description        VARCHAR(256),
    data_scope         VARCHAR(32) NOT NULL,
    module_permissions JSON,
    created_at         DATETIME(3) DEFAULT CURRENT_TIMESTAMP(3),
    updated_at         DATETIME(3) DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
    CONSTRAINT uk_role_code UNIQUE (role_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 3.4 员工表 (V3.2: wework_account_id 可空 + binding_status/bound_at)
CREATE TABLE sys_employee (
    id                BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id           VARCHAR(64) NOT NULL,
    name              VARCHAR(64) NOT NULL,
    org_id            VARCHAR(32),
    dept              VARCHAR(128),
    wework_account_id VARCHAR(32),
    password_hash     VARCHAR(256) NOT NULL,
    binding_status    VARCHAR(16) NOT NULL DEFAULT 'unbound',
    bound_at          DATETIME(3),
    created_at        DATETIME(3) DEFAULT CURRENT_TIMESTAMP(3),
    updated_at        DATETIME(3) DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
    CONSTRAINT uk_employee_user_id UNIQUE (user_id),
    -- wework_account_id 允许 NULL（未绑定状态），外键校验在应用层执行
    -- MySQL 行为：外键列含 NULL 时不检查引用完整性
    CONSTRAINT fk_employee_account FOREIGN KEY (wework_account_id)
        REFERENCES sys_wework_account(account_id),
    CONSTRAINT fk_employee_org FOREIGN KEY (org_id)
        REFERENCES sys_organization(org_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX idx_employee_org ON sys_employee (org_id);
CREATE INDEX idx_employee_account ON sys_employee (wework_account_id);
CREATE INDEX idx_employee_binding_status ON sys_employee (binding_status);

-- 3.4.1 用户提醒偏好表 (V3.3 新增, 需求 4.5)
CREATE TABLE sys_remind_preference (
    user_id     VARCHAR(64) NOT NULL PRIMARY KEY,
    remind_pref VARCHAR(8) NOT NULL DEFAULT 'mid',
    updated_at  DATETIME(3) DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
    CONSTRAINT fk_remind_pref_user FOREIGN KEY (user_id)
        REFERENCES sys_employee(user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 3.5 用户角色关联表
CREATE TABLE sys_user_role (
    id                BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id           VARCHAR(64) NOT NULL,
    role_code         VARCHAR(32) NOT NULL,
    wework_account_id VARCHAR(32) NOT NULL,
    created_at        DATETIME(3) DEFAULT CURRENT_TIMESTAMP(3),
    updated_at        DATETIME(3) DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
    CONSTRAINT uk_user_role_account UNIQUE (user_id, role_code, wework_account_id),
    CONSTRAINT fk_user_role_user FOREIGN KEY (user_id)
        REFERENCES sys_employee(user_id),
    CONSTRAINT fk_user_role_role FOREIGN KEY (role_code)
        REFERENCES sys_role(role_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================
-- 二、biz_ 业务数据类 (5 张表)
-- ============================================================

-- 3.6 客户表
CREATE TABLE biz_customer (
    id                BIGINT AUTO_INCREMENT PRIMARY KEY,
    external_id       VARCHAR(64) NOT NULL,
    union_id          VARCHAR(64),
    wework_account_id VARCHAR(32) NOT NULL,
    follow_user_id    VARCHAR(64) NOT NULL,
    name              VARCHAR(64),
    child_name        VARCHAR(64),
    school            VARCHAR(128),
    grade             VARCHAR(16),
    focus_subject     VARCHAR(64),
    remark            VARCHAR(128),
    stage             VARCHAR(16),
    lead_source       VARCHAR(32),
    created_at        DATETIME(3) DEFAULT CURRENT_TIMESTAMP(3),
    updated_at        DATETIME(3) DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
    CONSTRAINT uk_customer_external_id UNIQUE (external_id),
    CONSTRAINT fk_customer_account FOREIGN KEY (wework_account_id)
        REFERENCES sys_wework_account(account_id),
    CONSTRAINT fk_customer_follow_user FOREIGN KEY (follow_user_id)
        REFERENCES sys_employee(user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX idx_customer_follow_user ON biz_customer (follow_user_id);
CREATE INDEX idx_customer_union_id ON biz_customer (union_id);
CREATE INDEX idx_customer_account ON biz_customer (wework_account_id);
CREATE INDEX idx_customer_lead_source ON biz_customer (lead_source);

-- 3.10 客户标签关联表
CREATE TABLE biz_customer_tag (
    id            BIGINT AUTO_INCREMENT PRIMARY KEY,
    external_id   VARCHAR(64) NOT NULL,
    tag_id        VARCHAR(32) NOT NULL,
    source        VARCHAR(16) NOT NULL,
    confirmed     TINYINT(1) DEFAULT 0,
    confirmed_by  VARCHAR(64),
    confirmed_at  DATETIME(3),
    created_at    DATETIME(3) DEFAULT CURRENT_TIMESTAMP(3),
    updated_at    DATETIME(3) DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
    CONSTRAINT uk_customer_tag UNIQUE (external_id, tag_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX idx_customer_tag_external ON biz_customer_tag (external_id);
CREATE INDEX idx_customer_tag_tag ON biz_customer_tag (tag_id);

-- 3.16 订单表
CREATE TABLE biz_order (
    id                BIGINT AUTO_INCREMENT PRIMARY KEY,
    order_id          VARCHAR(32) NOT NULL,
    union_id          VARCHAR(64) NOT NULL,
    wework_account_id VARCHAR(32) NOT NULL,
    product_names     JSON,
    amount            DECIMAL(10,2),
    status            VARCHAR(16) NOT NULL,
    order_time        DATETIME(3),
    order_date        DATE,
    created_at        DATETIME(3) DEFAULT CURRENT_TIMESTAMP(3),
    updated_at        DATETIME(3) DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
    CONSTRAINT uk_order_order_id UNIQUE (order_id),
    CONSTRAINT fk_order_account FOREIGN KEY (wework_account_id)
        REFERENCES sys_wework_account(account_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX idx_order_union ON biz_order (union_id);
CREATE INDEX idx_order_status ON biz_order (status);
CREATE INDEX idx_order_account ON biz_order (wework_account_id);

-- 3.17 日程表
CREATE TABLE biz_schedule (
    id                   BIGINT AUTO_INCREMENT PRIMARY KEY,
    external_id          VARCHAR(64) NOT NULL,
    user_id              VARCHAR(64) NOT NULL,
    wework_account_id    VARCHAR(32) NOT NULL,
    title                VARCHAR(128) NOT NULL,
    start_time           DATETIME(3) NOT NULL,
    end_time             DATETIME(3),
    priority             VARCHAR(8) NOT NULL DEFAULT '中',
    source               VARCHAR(16) NOT NULL,
    status               VARCHAR(16) NOT NULL DEFAULT '待确认',
    wx_calendar_event_id VARCHAR(64),
    created_at           DATETIME(3) DEFAULT CURRENT_TIMESTAMP(3),
    updated_at           DATETIME(3) DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
    CONSTRAINT fk_schedule_account FOREIGN KEY (wework_account_id)
        REFERENCES sys_wework_account(account_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX idx_schedule_user ON biz_schedule (user_id, start_time);
CREATE INDEX idx_schedule_external ON biz_schedule (external_id);
CREATE INDEX idx_schedule_account ON biz_schedule (wework_account_id);

-- 3.17.1 CRM 跟进记录表 (V3.1 新增)
CREATE TABLE biz_follow_up (
    id                BIGINT AUTO_INCREMENT PRIMARY KEY,
    external_id       VARCHAR(64) NOT NULL,
    user_id           VARCHAR(64) NOT NULL,
    wework_account_id VARCHAR(32) NOT NULL,
    follow_up_type    VARCHAR(16) NOT NULL,
    content           TEXT,
    result            VARCHAR(16),
    follow_up_time    DATETIME(3) NOT NULL,
    next_action       VARCHAR(128),
    created_at        DATETIME(3) DEFAULT CURRENT_TIMESTAMP(3),
    updated_at        DATETIME(3) DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
    CONSTRAINT fk_follow_up_account FOREIGN KEY (wework_account_id)
        REFERENCES sys_wework_account(account_id),
    CONSTRAINT fk_follow_up_external FOREIGN KEY (external_id)
        REFERENCES biz_customer(external_id),
    CONSTRAINT fk_follow_up_user FOREIGN KEY (user_id)
        REFERENCES sys_employee(user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX idx_follow_up_external_time ON biz_follow_up (external_id, follow_up_time);
CREATE INDEX idx_follow_up_user_time ON biz_follow_up (user_id, follow_up_time);
CREATE INDEX idx_follow_up_account ON biz_follow_up (wework_account_id);
CREATE INDEX idx_follow_up_type ON biz_follow_up (follow_up_type);

-- ============================================================
-- 三、cfg_ 配置数据类 (3 张表)
-- ============================================================

-- 3.7 标签分组表
CREATE TABLE cfg_tag_group (
    id           BIGINT AUTO_INCREMENT PRIMARY KEY,
    group_id     VARCHAR(32) NOT NULL,
    group_name   VARCHAR(64) NOT NULL,
    strategy_id  INT DEFAULT 0,
    created_at   DATETIME(3) DEFAULT CURRENT_TIMESTAMP(3),
    updated_at   DATETIME(3) DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
    CONSTRAINT uk_tag_group_id UNIQUE (group_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 3.9 SOP 模板表（必须在 3.8 cfg_tag_definition 之前创建，因为后者引用此表）
CREATE TABLE cfg_sop_template (
    id            BIGINT AUTO_INCREMENT PRIMARY KEY,
    template_name VARCHAR(64) NOT NULL,
    steps         JSON NOT NULL,
    created_at    DATETIME(3) DEFAULT CURRENT_TIMESTAMP(3),
    updated_at    DATETIME(3) DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 3.8 标签定义表
CREATE TABLE cfg_tag_definition (
    id               BIGINT AUTO_INCREMENT PRIMARY KEY,
    tag_id           VARCHAR(32) NOT NULL,
    tag_name         VARCHAR(64) NOT NULL,
    group_id         VARCHAR(32) NOT NULL,
    sop_template_id  BIGINT,
    ai_rule          TEXT,
    deleted          TINYINT(1) DEFAULT 0,
    created_at       DATETIME(3) DEFAULT CURRENT_TIMESTAMP(3),
    updated_at       DATETIME(3) DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
    CONSTRAINT uk_tag_definition_id UNIQUE (tag_id),
    CONSTRAINT fk_tag_definition_group FOREIGN KEY (group_id)
        REFERENCES cfg_tag_group(group_id),
    CONSTRAINT fk_tag_definition_sop FOREIGN KEY (sop_template_id)
        REFERENCES cfg_sop_template(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX idx_tag_definition_group_id ON cfg_tag_definition (group_id);

-- ============================================================
-- 四、ai_ AI 产出类 (4 张表)
-- ============================================================

-- 3.11 客户画像表
CREATE TABLE ai_customer_profile (
    id                BIGINT AUTO_INCREMENT PRIMARY KEY,
    external_id       VARCHAR(64) NOT NULL,
    wework_account_id VARCHAR(32) NOT NULL,
    follow_user_id    VARCHAR(64) NOT NULL,
    status            VARCHAR(16) NOT NULL DEFAULT '草稿',
    confirmed_by      VARCHAR(64),
    confirmed_at      DATETIME(3),
    embedding_status  VARCHAR(16) DEFAULT 'pending',
    created_at        DATETIME(3) DEFAULT CURRENT_TIMESTAMP(3),
    updated_at        DATETIME(3) DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
    CONSTRAINT fk_profile_account FOREIGN KEY (wework_account_id)
        REFERENCES sys_wework_account(account_id),
    CONSTRAINT fk_profile_external FOREIGN KEY (external_id)
        REFERENCES biz_customer(external_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX idx_profile_external ON ai_customer_profile (external_id);
CREATE INDEX idx_profile_follow_user ON ai_customer_profile (follow_user_id);
CREATE INDEX idx_profile_account ON ai_customer_profile (wework_account_id);
CREATE INDEX idx_profile_embedding_status ON ai_customer_profile (embedding_status);

-- 3.12 画像字段项表
CREATE TABLE ai_profile_item (
    id               BIGINT AUTO_INCREMENT PRIMARY KEY,
    profile_id       BIGINT NOT NULL,
    item_name        VARCHAR(64) NOT NULL,
    item_value       TEXT,
    confidence       DECIMAL(3,2),
    confidence_level VARCHAR(8),
    source_type      VARCHAR(16),
    source_ref       VARCHAR(128),
    created_at       DATETIME(3) DEFAULT CURRENT_TIMESTAMP(3),
    updated_at       DATETIME(3) DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
    CONSTRAINT fk_profile_item_profile FOREIGN KEY (profile_id)
        REFERENCES ai_customer_profile(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX idx_profile_item_profile ON ai_profile_item (profile_id);
CREATE INDEX idx_profile_item_name ON ai_profile_item (item_name);

-- 3.18 AI 任务日志表 (埋点)
CREATE TABLE ai_task_log (
    id                BIGINT AUTO_INCREMENT PRIMARY KEY,
    task_type         VARCHAR(32) NOT NULL,
    user_id           VARCHAR(64) NOT NULL,
    external_id       VARCHAR(64) NOT NULL,
    wework_account_id VARCHAR(32) NOT NULL,
    action            VARCHAR(16) NOT NULL,
    action_detail     JSON,
    duration_ms       INT,
    created_at        DATETIME(3) DEFAULT CURRENT_TIMESTAMP(3),
    updated_at        DATETIME(3) DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX idx_task_log_user_action ON ai_task_log (user_id, action, created_at);
CREATE INDEX idx_task_log_type ON ai_task_log (task_type, created_at);
CREATE INDEX idx_task_log_account ON ai_task_log (wework_account_id);

-- 3.19 反馈信号表
CREATE TABLE ai_feedback_signal (
    id                BIGINT AUTO_INCREMENT PRIMARY KEY,
    task_log_id       BIGINT NOT NULL,
    wework_account_id VARCHAR(32) NOT NULL,
    signal_type       VARCHAR(16) NOT NULL,
    snapshot          JSON,
    created_at        DATETIME(3) DEFAULT CURRENT_TIMESTAMP(3),
    updated_at        DATETIME(3) DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
    CONSTRAINT fk_feedback_task_log FOREIGN KEY (task_log_id)
        REFERENCES ai_task_log(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX idx_feedback_signal_type ON ai_feedback_signal (signal_type);
CREATE INDEX idx_feedback_account ON ai_feedback_signal (wework_account_id);

-- ============================================================
-- 五、msg_ 消息数据类 (2 张表)
-- ============================================================

-- 3.13 企微聊天消息表 (按月分区)
CREATE TABLE msg_wxqy_chat (
    id                BIGINT AUTO_INCREMENT,
    msg_id            VARCHAR(64) NOT NULL,
    sorted_key        VARCHAR(128) NOT NULL,
    user_id           VARCHAR(64) NOT NULL,
    external_id       VARCHAR(64) NOT NULL,
    wework_account_id VARCHAR(32) NOT NULL,
    sender            VARCHAR(64),
    receiver          VARCHAR(64),
    sender_name       VARCHAR(64),
    receiver_name     VARCHAR(64),
    msg_type          VARCHAR(16) NOT NULL,
    content           TEXT,
    msg_date          DATE NOT NULL,
    send_time         DATETIME(3) NOT NULL,
    created_at        DATETIME(3) DEFAULT CURRENT_TIMESTAMP(3),
    PRIMARY KEY (id, msg_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
PARTITION BY RANGE (TO_DAYS(msg_date)) (
    PARTITION p202607 VALUES LESS THAN (TO_DAYS('2026-08-01')),
    PARTITION p202608 VALUES LESS THAN (TO_DAYS('2026-09-01')),
    PARTITION p202609 VALUES LESS THAN (TO_DAYS('2026-10-01')),
    PARTITION p_future VALUES LESS THAN MAXVALUE
);

CREATE UNIQUE INDEX uk_wxqy_chat_msg_id ON msg_wxqy_chat (msg_id, msg_date);
CREATE INDEX idx_wxqy_chat_sorted_date ON msg_wxqy_chat (sorted_key, msg_date);
CREATE INDEX idx_wxqy_chat_account ON msg_wxqy_chat (wework_account_id);
CREATE INDEX idx_wxqy_chat_account_date ON msg_wxqy_chat (wework_account_id, msg_date);

-- 3.14 客服消息表 (按月分区)
CREATE TABLE msg_wxkf_chat (
    id                BIGINT AUTO_INCREMENT,
    msg_id            VARCHAR(64) NOT NULL,
    external_id       VARCHAR(64) NOT NULL,
    wework_account_id VARCHAR(32) NOT NULL,
    kf_account        VARCHAR(64),
    sender            VARCHAR(64),
    sender_role       VARCHAR(16) NOT NULL,
    sender_name       VARCHAR(64),
    msg_type          VARCHAR(16) NOT NULL,
    content           TEXT,
    msg_date          DATE NOT NULL,
    send_time         DATETIME(3) NOT NULL,
    created_at        DATETIME(3) DEFAULT CURRENT_TIMESTAMP(3),
    PRIMARY KEY (id, msg_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
PARTITION BY RANGE (TO_DAYS(msg_date)) (
    PARTITION p202607 VALUES LESS THAN (TO_DAYS('2026-08-01')),
    PARTITION p202608 VALUES LESS THAN (TO_DAYS('2026-09-01')),
    PARTITION p202609 VALUES LESS THAN (TO_DAYS('2026-10-01')),
    PARTITION p_future VALUES LESS THAN MAXVALUE
);

CREATE UNIQUE INDEX uk_wxkf_chat_msg_id ON msg_wxkf_chat (msg_id, msg_date);
CREATE INDEX idx_wxkf_chat_external ON msg_wxkf_chat (external_id, msg_date);
CREATE INDEX idx_wxkf_chat_account ON msg_wxkf_chat (wework_account_id);
CREATE INDEX idx_wxkf_chat_account_date ON msg_wxkf_chat (wework_account_id, msg_date);

-- ============================================================
-- 六、rag_ AI 知识检索类 (2 张表, V3.0 新增)
-- ============================================================

-- 3.20 RAG 知识库文档表
CREATE TABLE rag_kb_document (
    id                BIGINT AUTO_INCREMENT PRIMARY KEY,
    doc_id            VARCHAR(64) NOT NULL,
    kb_name           VARCHAR(32) NOT NULL,
    file_path         VARCHAR(256) NOT NULL,
    title             VARCHAR(128),
    chunk_count       INT DEFAULT 0,
    char_count        INT DEFAULT 0,
    chroma_collection VARCHAR(64) NOT NULL,
    status            VARCHAR(16) DEFAULT 'active',
    last_indexed_at   DATETIME(3),
    indexed_by        VARCHAR(64),
    created_at        DATETIME(3) DEFAULT CURRENT_TIMESTAMP(3),
    updated_at        DATETIME(3) DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
    CONSTRAINT uk_rag_doc_id UNIQUE (doc_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX idx_rag_doc_kb ON rag_kb_document (kb_name, status);

-- 3.21 RAG 索引构建日志表
CREATE TABLE rag_kb_index_log (
    id             BIGINT AUTO_INCREMENT PRIMARY KEY,
    kb_name        VARCHAR(32) NOT NULL,
    doc_count      INT,
    chunk_count    INT,
    elapsed_ms     INT,
    status         VARCHAR(16) NOT NULL,
    error_message  TEXT,
    triggered_by   VARCHAR(64) NOT NULL,
    created_at     DATETIME(3) DEFAULT CURRENT_TIMESTAMP(3)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX idx_rag_log_kb ON rag_kb_index_log (kb_name, created_at);

-- ============================================================
-- 初始化数据
-- ============================================================

-- 企微账户 (3 行)
INSERT INTO sys_wework_account (account_id, account_name, corp_id, corp_secret, region, agent_id) VALUES
('sz', '擎天学智·深圳(华南区)', 'wx_corp_sz_0001', 'secret_sz_encrypted', '华南区', '1000001'),
('sh', '擎天学智·上海(华东区)', 'wx_corp_sh_0002', 'secret_sh_encrypted', '华东区', '1000002'),
('bj', '擎天学智·北京(华北区)', 'wx_corp_bj_0003', 'secret_bj_encrypted', '华北区', '1000003');

-- 组织架构 (10 行)
INSERT INTO sys_organization (org_id, org_name, parent_org_id, org_type, wework_account_id, sort_order) VALUES
('region_sz',    '华南区',      NULL,             '区域', 'sz', 1),
('region_sh',    '华东区',      NULL,             '区域', 'sh', 2),
('region_bj',    '华北区',      NULL,             '区域', 'bj', 3),
('dept_sz_1',    '深圳一组',    'region_sz',      '组',   'sz', 1),
('dept_sz_2',    '深圳二组',    'region_sz',      '组',   'sz', 2),
('dept_sh_1',    '上海一组',    'region_sh',      '组',   'sh', 1),
('dept_sh_2',    '上海二组',    'region_sh',      '组',   'sh', 2),
('dept_bj_1',    '北京一组',    'region_bj',      '组',   'bj', 1),
('dept_bj_2',    '北京二组',    'region_bj',      '组',   'bj', 2),
('dept_hq',      '总部',        NULL,             '部门', 'sz', 0);

-- 角色定义 (3 行)
INSERT INTO sys_role (role_code, role_name, description, data_scope, module_permissions) VALUES
('super_admin', '超级管理员',
 '全集团数据查看、权限配置、标签体系管理',
 'all',
 '["dashboard_all","employee_manage","customer_view_all","order_view_all","tag_manage","permission_config"]'),
('region_manager', '区域主管',
 '本区域人效数据查看、客户画像复核、标签配置',
 'region',
 '["dashboard_region","employee_view","customer_view_region","tag_config_region"]'),
('normal_advisor', '普通顾问',
 '本人名下客户的AI辅助、画像确认',
 'self',
 '["sidebar_ai","profile_confirm","customer_view_self","tag_confirm"]');

-- 员工 (7 行，V3.2: 含 1 名未绑定员工 zhaoliu)
-- 密码均为 bcrypt 哈希。明文见注释（对齐原型.html 登录提示）：
--   admin/admin123   hejing/hejing123   chenxiaomeng/cxm123
--   liuyang/ly123     wuqiang/wq123       sunyue/sy123
--   zhaoliu/zl123 (未绑定，演示 V3.2 引导绑定页)
INSERT INTO sys_employee (user_id, name, org_id, dept, wework_account_id, password_hash, binding_status, bound_at) VALUES
('admin',        '黄珊',  'dept_hq',   '总部',              'sz', '$2b$12$1Gk/AoE4GhvOhbGP1PmbFerftfcQnPD.slVVWyvDVt602ym2XF/O6', 'bound', '2026-07-01 09:00:00'),
('hejing',       '何静',  'dept_bj_1', '华北区·北京一组',   'bj', '$2b$12$tfLtLaeUkg.8rdMe.robAeBY6I3WKCAS6egBkKDhYQTBu2FnXuVQe', 'bound', '2026-07-01 09:00:00'),
('chenxiaomeng', '陈晓萌','dept_sz_1', '华南区·深圳一组',   'sz', '$2b$12$YW.Oclz1xdcxfNzplWysYOxyetpsyKb70Dh3dVNsv8eJjdlGPPmAW', 'bound', '2026-07-01 09:00:00'),
('liuyang',      '刘洋',  'dept_sz_1', '华南区·深圳一组',   'sz', '$2b$12$IPWsemN7cdhF1CmQFLLAP.D7kAqbPlkLyvZu2xi5DV8N4cvvmG1bC', 'bound', '2026-07-01 09:00:00'),
('wuqiang',      '吴强',  'dept_sh_1', '华东区·上海一组',   'sh', '$2b$12$U1oIjhCM5ezMgB5DKfDZUOEh3xD6n3lQ4Nb1gZ98.cHVrNQbddJaK', 'bound', '2026-07-01 09:00:00'),
('sunyue',       '孙悦',  'dept_bj_1', '华北区·北京一组',   'bj', '$2b$12$zHMTBtRPBA1Ns6T.38h8JuzJ0ZvS2LNFO6C0Cgy8vRSjsAl2Xu.xq', 'bound', '2026-07-01 09:00:00'),
('zhaoliu',      '赵六',  NULL,        '待分配',             NULL, '$2b$12$TV52B4REHkJKW1kQO2Vni.V7R4QobPT.HP1iB0I/lNm87o8Tigw5C', 'unbound', NULL);

-- 用户角色分配 (6 行)
-- wework_account_id 为 '*' 表示适用全部账户（超级管理员）
INSERT INTO sys_user_role (user_id, role_code, wework_account_id) VALUES
('admin',        'super_admin',    '*'),
('hejing',       'region_manager', 'bj'),
('chenxiaomeng', 'normal_advisor', 'sz'),
('liuyang',      'normal_advisor', 'sz'),
('wuqiang',      'normal_advisor', 'sh'),
('sunyue',       'normal_advisor', 'bj');

-- 标签分组 (4 行)
INSERT INTO cfg_tag_group (group_id, group_name, strategy_id) VALUES
('group_basic',    '基础属性', 0),
('group_consume',  '消费行为', 1),
('group_social',   '社交关系', 1),
('group_service',  '服务敏感度', 1);

-- 标签定义 (33 行)
INSERT INTO cfg_tag_definition (tag_id, tag_name, group_id, ai_rule) VALUES
-- 基础属性 (10)
('tag_gaoyixiang',  '高意向',     'group_consume', '连续≥3天咨询同科目/试听后7天内主动联系'),
('tag_shuxueruo',   '数学薄弱',   'group_basic',   '聊天提及数学成绩不理想/几何薄弱/应用题不会做'),
('tag_yingyuruo',   '英语薄弱',   'group_basic',   '聊天提及英语成绩差/单词记不住/语法不会'),
('tag_yuwenruo',    '语文薄弱',   'group_basic',   '聊天提及语文阅读理解差/作文不会写'),
('tag_zhongkaocj',  '中考冲刺',   'group_basic',   '初三在读+明确表达中考冲刺需求'),
('tag_gaokaocj',    '高考冲刺',   'group_basic',   '高三在读+明确表达高考冲刺需求'),
('tag_xiaoshengchu','小升初衔接', 'group_basic',   '六年级在读+咨询初中课程'),
('tag_chuyisheng',  '新初一',     'group_basic',   '刚升入初一+适应性问题'),
('tag_jiguan',      '籍贯信息',   'group_basic',   '聊天中透露籍贯或老家所在地'),
('tag_zhiyebj',     '职业背景',   'group_basic',   '聊天中透露职业/工作单位信息'),

-- 消费行为 (10)
('tag_zaixueyuan',  '在读学员',   'group_consume', '存在有效未完结订单'),
('tag_jiagesmg',    '价格敏感',   'group_consume', '主动询问价格/优惠/折扣/多次比价'),
('tag_kedanjia',    '高客单价',   'group_consume', '历史订单均价高于平均值 1.5 倍'),
('tag_xufeiyx',     '续费意向',   'group_consume', '在读学员家长表达续费意愿/询问下学期课程'),
('tag_shiting',     '已试听',     'group_consume', '已完成试听课但未报名'),
('tag_tuifeifx',    '退费风险',   'group_consume', '表达不满意/要求退款/投诉倾向'),
('tag_goumaipp',    '购买频次高', 'group_consume', '一年内购买≥2个课程包'),
('tag_tuijianyy',   '推荐意愿',   'group_consume', '主动表示会推荐给朋友/已有转介绍行为'),
('tag_duokemu',     '多科目需求', 'group_consume', '咨询≥2个科目课程'),
('tag_hanjiab',     '寒暑假需求', 'group_consume', '寒暑假前集中咨询短期班/集训营'),

-- 社交关系 (7)
('tag_zjsnl',       '转介绍能力强','group_social',  '已成功转介绍≥2名客户/主动表示认识很多家长'),
('tag_jwhcy',       '家委会成员',  'group_social',  '聊天中表明是家委会成员/班级群管理员'),
('tag_shejiao',     '社交影响力',  'group_social',  '社群活跃/朋友圈经常分享教育内容'),
('tag_qundao',      '渠道引荐',   'group_social',  '通过其他家长/老师介绍而来'),
('tag_qinzi',       '亲子关系',   'group_social',  '聊天中透露亲子关系紧张/教育理念冲突'),
('tag_danzhaod',    '单照家庭',   'group_social',  '暗示单亲/一方在外地/老人带娃'),
('tag_ertong',      '多子女家庭', 'group_social',  '聊天中提及有多个孩子/希望一起报名'),

-- 服务敏感度 (6)
('tag_tousuqx',     '投诉倾向',   'group_service', '历史有过投诉记录/表达极度不满'),
('tag_fuwumyd',     '服务满意度高','group_service', '多次表达对老师/课程的肯定和感谢'),
('tag_minxing',     '明星学员',   'group_service', '成绩显著提升/获得竞赛奖项/家长特别满意'),
('tag_chuqin',      '出勤率低',   'group_service', '请假频繁/迟到次数多/缺课 > 3 次'),
('tag_hudong',      '互动活跃',   'group_service', '群内积极互动/作业按时提交/主动反馈'),
('tag_qianzai',     '潜在流失',   'group_service', '连续 2 周无互动/未回复消息/不接电话');

-- SOP 模板 (2 行)
INSERT INTO cfg_sop_template (template_name, steps) VALUES
('高意向跟进 SOP', '[
    {"step": 1, "action": "当天电话确认意向"},
    {"step": 2, "action": "安排试听"},
    {"step": 3, "action": "3天内跟进报名转化"}
]'),
('在读学员跟进 SOP', '[
    {"step": 1, "action": "每月回访一次（课程满意度+学习效果）"},
    {"step": 2, "action": "续费前30天发送续费提醒"},
    {"step": 3, "action": "学期末发送学习报告+下学期课程推荐"}
]');

-- 更新标签与 SOP 关联
UPDATE cfg_tag_definition SET sop_template_id = 1 WHERE tag_id = 'tag_gaoyixiang';
UPDATE cfg_tag_definition SET sop_template_id = 2 WHERE tag_id = 'tag_zaixueyuan';

-- ============================================================
-- 九、演示业务种子数据（V3.2 演示环境）
-- 仅用于开发/演示，未上线、未连接企业微信。
-- 权限聊天对象矩阵：
--   普通顾问   chenxiaomeng(3)  liuyang(2)  wuqiang(2)  sunyue(3)  = 10
--   区域主管   hejing：华北全部(本区域=华北，覆盖 sunyue 的3个) + 自己的2个 = 5
--   超级管理员 admin：全部 12 个，自己 0 个
-- ============================================================

-- 9.1 客户 (12 行)
INSERT INTO biz_customer (external_id, union_id, wework_account_id, follow_user_id, name, child_name, school, grade, focus_subject, remark, stage, lead_source, created_at) VALUES
('C10001','U10001','sz','chenxiaomeng','王芳','李明浩','市一中','初一','数学','高意向·连续3天咨询初一数学','高意向','企微会话','2026-07-25 10:12:00'),
('C10002','U10002','sz','chenxiaomeng','张静','刘雨欣','实验小学','五年级','英语','在读·关注师资','在读','客服会话','2026-05-02 15:10:00'),
('C10003','U10003','sz','chenxiaomeng','周敏','周子睿','育才中学','初二','物理','试听邀约已发送','试听','企微会话','2026-07-28 09:30:00'),
('C10004','U10004','sz','liuyang','李娟','李明宇','城南小学','三年级','语文','潜在·家长咨询中','潜在','企微会话','2026-07-20 20:10:00'),
('C10005','U10005','sz','liuyang','杨帆','杨子涵','文澜中学','初一','数学','高意向·价格关注','高意向','企微会话','2026-07-18 21:40:00'),
('C10006','U10006','sh','wuqiang','李雪','王紫涵','上海实验','四年级','数学','潜在·数学薄弱','潜在','企微会话','2026-07-22 19:00:00'),
('C10007','U10007','sh','wuqiang','赵刚','赵一鸣','格致中学','初二','物理','试听后待跟进','试听','企微会话','2026-07-15 14:30:00'),
('C10008','U10008','bj','sunyue','孙鹏','孙嘉怡','北京小学','六年级','小升初衔接','在读·小升初冲刺','在读','企微会话','2026-06-10 11:00:00'),
('C10009','U10009','bj','sunyue','周兰','周雨彤','北京四中','初三','中考冲刺','高意向·临近中考','高意向','企微会话','2026-07-12 16:20:00'),
('C10010','U10010','bj','sunyue','罗静','罗子轩','朝阳小学','五年级','英语','试听·英语衔接','试听','企微会话','2026-07-30 10:15:00'),
('C10011','U10011','bj','hejing','胡敏','胡天宇','北京二中','初一','数学','潜在·主管自己名下','潜在','企微会话','2026-07-08 09:00:00'),
('C10012','U10012','bj','hejing','何丽','何思睿','八十中','初三','语文','在读·主管自己名下','在读','客服会话','2026-06-25 13:30:00');

-- 9.2 客户标签 (混合 AI 推荐待确认 + 已确认)
INSERT INTO biz_customer_tag (external_id, tag_id, source, confirmed, confirmed_by, confirmed_at) VALUES
('C10001','tag_gaoyixiang','ai',0,NULL,NULL),
('C10001','tag_shuxueruo','ai',0,NULL,NULL),
('C10001','tag_jiagesmg','manual',1,'chenxiaomeng','2026-07-26 10:00:00'),
('C10002','tag_zaixueyuan','manual',1,'chenxiaomeng','2026-05-03 09:00:00'),
('C10002','tag_fuwumyd','ai',0,NULL,NULL),
('C10003','tag_shiting','manual',1,'chenxiaomeng','2026-07-29 14:00:00'),
('C10005','tag_gaoyixiang','ai',0,NULL,NULL),
('C10005','tag_jiagesmg','ai',0,NULL,NULL),
('C10006','tag_shuxueruo','ai',0,NULL,NULL),
('C10007','tag_gaoyixiang','ai',0,NULL,NULL),
('C10008','tag_zaixueyuan','manual',1,'sunyue','2026-06-11 10:00:00'),
('C10008','tag_xiaoshengchu','ai',0,NULL,NULL),
('C10009','tag_zhongkaocj','ai',0,NULL,NULL),
('C10010','tag_yingyuruo','ai',0,NULL,NULL),
('C10012','tag_zaixueyuan','manual',1,'hejing','2026-06-26 09:00:00');

-- 9.3 企微聊天消息 (按月分区 p202607/p202608)
INSERT INTO msg_wxqy_chat (msg_id, sorted_key, user_id, external_id, wework_account_id, sender, receiver, sender_name, receiver_name, msg_type, content, msg_date, send_time) VALUES
-- C10001 王芳 (chenxiaomeng)
('Q10001_1','C10001_chenxiaomeng','chenxiaomeng','C10001','sz','C10001','chenxiaomeng','王芳','陈晓萌','text','老师您好，我家孩子现在初一，数学成绩一直在及格线徘徊，想问问你们有没有合适的班？','2026-08-08','2026-08-08 10:12:00'),
('Q10001_2','C10001_chenxiaomeng','chenxiaomeng','C10001','sz','chenxiaomeng','C10001','陈晓萌','王芳','text','王妈妈您好，我们周中有同步班也有周末专题班，孩子主要是哪块比较薄弱呀？','2026-08-08','2026-08-08 10:20:00'),
('Q10001_3','C10001_chenxiaomeng','chenxiaomeng','C10001','sz','C10001','chenxiaomeng','王芳','陈晓萌','text','我们这周六下午有空，想带孩子去看看。主要是应用题和几何，一到大题就不会做了。另外想问下价格方面怎么收费？','2026-08-08','2026-08-08 21:05:00'),
('Q10001_4','C10001_chenxiaomeng','chenxiaomeng','C10001','sz','chenxiaomeng','C10001','陈晓萌','王芳','text','好的王妈妈，周六下午2点到4点都有老师值班，我提前给您约好。可以先带孩子来免费摸底，看看失分点在哪。','2026-08-08','2026-08-08 21:10:00'),
-- C10002 张静 (chenxiaomeng)
('Q10002_1','C10002_chenxiaomeng','chenxiaomeng','C10002','sz','C10002','chenxiaomeng','张静','陈晓萌','text','老师，孩子上次英语试听感觉还行，但我想问下现在班级的授课老师是固定的吗？','2026-08-05','2026-08-05 09:30:00'),
('Q10002_2','C10002_chenxiaomeng','chenxiaomeng','C10002','sz','chenxiaomeng','C10002','陈晓萌','张静','text','张妈妈您好，我们同步班的老师是固定的，主讲老师带完整学期，中途不更换。','2026-08-05','2026-08-05 09:35:00'),
('Q10002_3','C10002_chenxiaomeng','chenxiaomeng','C10002','sz','C10002','chenxiaomeng','张静','陈晓萌','text','那就好。最近一次课孩子说有点跟不上，是不是要换班型？','2026-08-05','2026-08-05 21:10:00'),
-- C10003 周敏 (chenxiaomeng)
('Q10003_1','C10003_chenxiaomeng','chenxiaomeng','C10003','sz','C10003','chenxiaomeng','周敏','陈晓萌','text','老师，孩子初二物理一直跟不上，能不能安排老师补一下？','2026-08-07','2026-08-07 19:20:00'),
('Q10003_2','C10003_chenxiaomeng','chenxiaomeng','C10003','sz','chenxiaomeng','C10003','陈晓萌','周敏','text','可以的周妈妈，我们物理周末专题班正合适，周日下午2点有一节试听课，您方便带孩子来吗？','2026-08-07','2026-08-07 19:30:00'),
('Q10003_3','C10003_chenxiaomeng','chenxiaomeng','C10003','sz','C10003','chenxiaomeng','周敏','陈晓萌','text','周日下午可以，谢谢老师。','2026-08-07','2026-08-07 19:32:00'),
-- C10004 李娟 (liuyang)
('Q10004_1','C10004_liuyang','liuyang','C10004','sz','C10004','liuyang','李娟','刘洋','text','老师好，孩子三年级，想咨询语文阅读理解辅导。','2026-08-06','2026-08-06 20:10:00'),
('Q10004_2','C10004_liuyang','liuyang','C10004','sz','liuyang','C10004','刘洋','李娟','text','您好李妈妈，我们三年级语文阅读专题课周三晚7点开班，可以试听一次看看效果。','2026-08-06','2026-08-06 20:15:00'),
-- C10005 杨帆 (liuyang)
('Q10005_1','C10005_liuyang','liuyang','C10005','sz','C10005','liuyang','杨帆','刘洋','text','孩子刚上初一，数学应用题不行，费用多少？','2026-08-09','2026-08-09 21:40:00'),
('Q10005_2','C10005_liuyang','liuyang','C10005','sz','liuyang','C10005','刘洋','杨帆','text','杨妈妈您好，初一数学同步班约 220 元/课时，首次试听免费，现在报名有早鸟 9 折。','2026-08-09','2026-08-09 21:48:00'),
('Q10005_3','C10005_liuyang','liuyang','C10005','sz','C10005','liuyang','杨帆','刘洋','text','那先安排孩子试听一下吧。','2026-08-09','2026-08-09 21:52:00'),
-- C10006 李雪 (wuqiang)
('Q10006_1','C10006_wuqiang','wuqiang','C10006','sh','C10006','wuqiang','李雪','吴强','text','老师，孩子四年级数学一直不太行，几何应用题都不太会。','2026-08-04','2026-08-04 19:00:00'),
('Q10006_2','C10006_wuqiang','wuqiang','C10006','sh','wuqiang','C10006','吴强','李雪','text','李妈妈好，我们四年级数学专题班针对应用题和几何很有效，可以约一次免费测评。','2026-08-04','2026-08-04 19:08:00'),
-- C10007 赵刚 (wuqiang)
('Q10007_1','C10007_wuqiang','wuqiang','C10007','sh','C10007','wuqiang','赵刚','吴强','text','上次试听完物理，孩子觉得节奏有点快。','2026-08-03','2026-08-03 14:30:00'),
('Q10007_2','C10007_wuqiang','wuqiang','C10007','sh','wuqiang','C10007','吴强','赵刚','text','赵爸爸，节奏可以调，我们也有稍慢的同步班，可以再观察一周看是否需要调班。','2026-08-03','2026-08-03 14:40:00'),
-- C10008 孙鹏 (sunyue)
('Q10008_1','C10008_sunyue','sunyue','C10008','bj','C10008','sunyue','孙鹏','孙悦','text','老师，孩子明年小升初，想冲刺一所好初中，有什么班型推荐？','2026-08-02','2026-08-02 11:00:00'),
('Q10008_2','C10008_sunyue','sunyue','C10008','bj','sunyue','C10008','孙悦','孙鹏','text','孙爸爸好，我们小升初冲刺班周末全天制，语数英各 2 小时，九月开课。','2026-08-02','2026-08-02 11:10:00'),
('Q10008_3','C10008_sunyue','sunyue','C10008','bj','C10008','sunyue','孙鹏','孙悦','text','好的，那我们准时到。','2026-08-02','2026-08-02 11:12:00'),
-- C10009 周兰 (sunyue)
('Q10009_1','C10009_sunyue','sunyue','C10009','bj','C10009','sunyue','周兰','孙悦','text','孩子马上中考了，想重点突击物理和化学，冲刺班怎么安排？','2026-08-10','2026-08-10 16:20:00'),
('Q10009_2','C10009_sunyue','sunyue','C10009','bj','sunyue','C10009','孙悦','周兰','text','周妈妈好，中考冲刺班是周末全天制，物化各2小时配一对一答疑，还能加周中晚自习。','2026-08-10','2026-08-10 16:28:00'),
('Q10009_3','C10009_sunyue','sunyue','C10009','bj','C10009','sunyue','周兰','孙悦','text','周中能加课吗？孩子学校那边查得比较严。','2026-08-10','2026-08-10 21:00:00'),
-- C10010 罗静 (sunyue)
('Q10010_1','C10010_sunyue','sunyue','C10010','bj','C10010','sunyue','罗静','孙悦','text','老师，孩子五年级英语口语还行但语法弱，能补一下吗？','2026-08-01','2026-08-01 10:15:00'),
('Q10010_2','C10010_sunyue','sunyue','C10010','bj','sunyue','C10010','孙悦','罗静','text','可以的罗妈妈，英语语法专题班周三晚7点有一节试听课。','2026-08-01','2026-08-01 10:20:00'),
-- C10011 胡敏 (hejing - 主管自己)
('Q10011_1','C10011_hejing','hejing','C10011','bj','C10011','hejing','胡敏','何静','text','何老师，孩子初一数学计算一直失分，能安排辅导吗？','2026-07-30','2026-07-30 09:00:00'),
('Q10011_2','C10011_hejing','hejing','C10011','bj','hejing','C10011','何静','胡敏','text','胡妈妈好，我帮您约一次免费测评，先把计算薄弱点定位清楚。','2026-07-30','2026-07-30 09:05:00'),
-- C10012 何丽 (hejing - 主管自己)
('Q10012_1','C10012_hejing','hejing','C10012','bj','C10012','hejing','何丽','何静','text','何老师，孩子语文阅读理解失分严重，有针对性的班吗？','2026-07-28','2026-07-28 13:30:00'),
('Q10012_2','C10012_hejing','hejing','C10012','bj','hejing','C10012','何静','何丽','text','何妈妈好，我们初三语文阅读专题班周五晚7点开课，可以试听一次看看。','2026-07-28','2026-07-28 13:38:00');

-- 9.4 订单 (5 行)
INSERT INTO biz_order (order_id, union_id, wework_account_id, product_names, amount, status, order_time, order_date) VALUES
('O88012','U10001','sz', JSON_OBJECT('name','试听券'), 0.00, '待使用', '2026-08-09 10:00:00', '2026-08-09'),
('O87123','U10002','sz', JSON_OBJECT('name','英语同步班半年'), 12800.00, '进行中', '2026-07-05 15:00:00', '2026-07-05'),
('O86501','U10008','bj', JSON_OBJECT('name','小升初冲刺班'), 9600.00, '已完结', '2026-07-15 11:00:00', '2026-07-15'),
('O86077','U10007','sh', JSON_OBJECT('name','物理一对一10次'), 6500.00, '已退款', '2026-07-20 14:00:00', '2026-07-20'),
('O85410','U10009','bj', JSON_OBJECT('name','中考冲刺班'), 15800.00, '进行中', '2026-07-12 16:00:00', '2026-07-12');

-- 9.5 日程 (每客户按需)
INSERT INTO biz_schedule (external_id, user_id, wework_account_id, title, start_time, end_time, priority, source, status, wx_calendar_event_id) VALUES
('C10001','chenxiaomeng','sz','试听邀约跟进','2026-08-15 14:00:00','2026-08-15 16:00:00','高','ai','待确认',NULL),
('C10001','chenxiaomeng','sz','续费节点提醒','2026-08-20 10:00:00',NULL,'高','ai','待确认',NULL),
('C10002','chenxiaomeng','sz','课程回访','2026-08-18 11:00:00',NULL,'中','manual','已确认',NULL),
('C10003','chenxiaomeng','sz','周日下午物理试听','2026-08-17 14:00:00','2026-08-17 16:00:00','高','ai','待确认',NULL),
('C10005','liuyang','sz','初一数学试听','2026-08-14 19:00:00','2026-08-14 20:00:00','中','ai','已确认','wxcal_5'),
('C10008','sunyue','bj','小升初冲刺班开课','2026-09-06 09:00:00','2026-09-06 17:00:00','高','manual','已确认','wxcal_9'),
('C10009','sunyue','bj','中考冲刺班跟进','2026-08-16 16:00:00',NULL,'高','ai','待确认',NULL),
('C10011','hejing','bj','计算测评安排','2026-08-13 09:30:00','2026-08-13 10:30:00','中','ai','待确认',NULL),
('C10012','hejing','bj','语文阅读专题开课','2026-08-22 19:00:00','2026-08-22 21:00:00','中','manual','已确认','wxcal_12');

-- 9.6 跟进记录 (biz_follow_up)
INSERT INTO biz_follow_up (external_id, user_id, wework_account_id, follow_up_type, content, result, follow_up_time, next_action) VALUES
('C10001','chenxiaomeng','sz','电话','电话确认意向，家长表示周中可加课','意向强','2026-08-09 20:00:00','试听邀约'),
('C10002','chenxiaomeng','sz','线下面谈','到店沟通师资固定问题','已安抚','2026-08-06 11:00:00','续费回访'),
('C10005','liuyang','sz','试听','安排初一数学试听','待跟进','2026-08-11 19:00:00','试听后回访'),
('C10008','sunyue','bj','电话','确认小升初冲刺意向','已报名','2026-07-15 11:00:00','开课提醒'),
('C10011','hejing','bj','外勤','到校与家长面谈计算辅导方案','待跟进','2026-07-30 09:30:00','测评安排'),
('C10012','hejing','bj','电话','跟进语文专题意向','已约试听','2026-07-28 14:00:00','试听前电话');

-- 9.7 客户画像草稿 + 字段项 (已确认部分+草稿部分)
-- 假设：前 2 个客户画像已确认；其余为草稿
INSERT INTO ai_customer_profile (external_id, wework_account_id, follow_user_id, status, confirmed_by, confirmed_at, embedding_status) VALUES
('C10001','sz','chenxiaomeng','草稿',NULL,NULL,'pending'),
('C10002','sz','chenxiaomeng','已确认','chenxiaomeng','2026-05-04 09:00:00','indexed'),
('C10003','sz','chenxiaomeng','草稿',NULL,NULL,'pending'),
('C10005','sz','liuyang','草稿',NULL,NULL,'pending'),
('C10008','bj','sunyue','已确认','sunyue','2026-06-12 10:00:00','indexed'),
('C10009','bj','sunyue','草稿',NULL,NULL,'pending'),
('C10011','bj','hejing','草稿',NULL,NULL,'pending');

-- 画像字段项（每个画像 6 项：基础 2 + 学情 2 + 沟通偏好 2）
INSERT INTO ai_profile_item (profile_id, item_name, item_value, confidence, confidence_level, source_type, source_ref) VALUES
(1,'学生','李明浩',1.00,'高','chat','企微会话存档 I3'),
(1,'年级','初一',1.00,'高','chat','企微会话存档 I3'),
(1,'强弱科目','数学弱（几何/应用题）',0.88,'高','llm','AI 语义分析'),
(1,'学习目标','期末提升至 85 分',0.76,'中','llm','AI 语义分析'),
(1,'价格敏感度','高（关注性价比）',0.72,'中','llm','AI 行为分析'),
(1,'决策风格','谨慎比价型',0.74,'中','llm','AI 行为分析'),
(2,'学生','刘雨欣',1.00,'高','chat','企微会话存档 I3'),
(2,'年级','五年级',1.00,'高','chat','企微会话存档 I3'),
(2,'强弱科目','英语口语强·语法弱',0.82,'高','llm','AI 语义分析'),
(2,'学习目标','小升初英语衔接',0.71,'中','llm','AI 语义分析'),
(2,'价格敏感度','中（已购正价课）',0.66,'中','llm','AI 行为分析'),
(2,'决策风格','信任关系型',0.69,'中','llm','AI 行为分析'),
(3,'学生','周子睿',1.00,'高','chat','企微会话存档 I3'),
(3,'年级','初二',1.00,'高','chat','企微会话存档 I3'),
(3,'强弱科目','物理薄弱',0.85,'高','llm','AI 语义分析'),
(3,'学习目标','物理提升至及格以上',0.73,'中','llm','AI 语义分析'),
(3,'价格敏感度','中',0.62,'中','llm','AI 行为分析'),
(3,'决策风格','目标导向',0.70,'中','llm','AI 行为分析'),
(4,'学生','杨子涵',1.00,'高','chat','企微会话存档 I3'),
(4,'年级','初一',1.00,'高','chat','企微会话存档 I3'),
(4,'强弱科目','数学应用题薄弱',0.84,'高','llm','AI 语义分析'),
(4,'学习目标','期末数学提升',0.75,'中','llm','AI 语义分析'),
(4,'价格敏感度','高',0.78,'高','llm','AI 行为分析'),
(4,'决策风格','谨慎比价型',0.71,'中','llm','AI 行为分析'),
(5,'学生','孙嘉怡',1.00,'高','chat','企微会话存档 I3'),
(5,'年级','六年级',1.00,'高','chat','企微会话存档 I3'),
(5,'强弱科目','小升初冲刺衔接',0.86,'高','llm','AI 语义分析'),
(5,'学习目标','冲刺重点初中',0.82,'高','llm','AI 语义分析'),
(5,'价格敏感度','低（已报冲刺班）',0.62,'中','llm','AI 行为分析'),
(5,'决策风格','目标结果导向',0.77,'中','llm','AI 行为分析'),
(6,'学生','周雨彤',1.00,'高','chat','企微会话存档 I3'),
(6,'年级','初三',1.00,'高','chat','企微会话存档 I3'),
(6,'强弱科目','物化冲刺',0.90,'高','llm','AI 语义分析'),
(6,'学习目标','中考冲刺重点高中',0.88,'高','llm','AI 语义分析'),
(6,'价格敏感度','低（愿为冲刺投入）',0.71,'中','llm','AI 行为分析'),
(6,'决策风格','目标结果导向',0.85,'高','llm','AI 行为分析'),
(7,'学生','胡天宇',1.00,'高','chat','企微会话存档 I3'),
(7,'年级','初一',1.00,'高','chat','企微会话存档 I3'),
(7,'强弱科目','数学计算失分',0.80,'高','llm','AI 语义分析'),
(7,'学习目标','计算基础巩固',0.74,'中','llm','AI 语义分析'),
(7,'价格敏感度','中',0.60,'中','llm','AI 行为分析'),
(7,'决策风格','信任关系型',0.68,'中','llm','AI 行为分析');

-- ============================================================
-- 验证查询（更新计数）
-- ============================================================
-- SELECT COUNT(*) FROM sys_employee;    -- 期望: 7
-- SELECT COUNT(*) FROM sys_user_role;   -- 期望: 6
-- SELECT COUNT(*) FROM biz_customer;    -- 期望: 12
-- SELECT COUNT(*) FROM biz_customer_tag;-- 期望: 15
-- SELECT COUNT(*) FROM msg_wxqy_chat;   -- 期望: 33
-- SELECT COUNT(*) FROM biz_order;       -- 期望: 5
-- SELECT COUNT(*) FROM biz_schedule;    -- 期望: 9
-- SELECT COUNT(*) FROM biz_follow_up;   -- 期望: 6
-- SELECT COUNT(*) FROM ai_customer_profile; -- 期望: 7
-- SELECT COUNT(*) FROM ai_profile_item;     -- 期望: 42
--
-- 演示登录（密码见 sys_employee 注释）：
--   超级管理员 admin / admin123
--   区域主管   hejing / hejing123  （华北区）
--   普通顾问   chenxiaomeng / cxm123（华南·深圳）
--               liuyang / ly123     （华南·深圳）
--               wuqiang  / wq123    （华东·上海）
--               sunyue   / sy123    （华北·北京）
--   未绑定     zhaoliu / zl123（演示 V3.2 引导绑定页）
