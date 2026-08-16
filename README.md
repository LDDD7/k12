#  K12 用户画像推荐系统

> AI 智能销售辅助系统 — 面向 K12 教育机构的客户画像与销售支持平台
> 模块化分层单体架构 · FastAPI + LangGraph + LlamaIndex + ChromaDB

---

## 📌 项目简介

**K12 用户画像推荐系统**，帮助教育机构销售顾问：
- 从企微聊天记录、订单、跟进记录中自动提取 **客户画像**
- 基于 AI 生成 **回复建议、智能标签、跟进日程**
- 通过 **人机协同中断机制**（AI 生成 → 人工确认 → 落库）保证数据质量
- 提供 **管理后台** 与 **顾问侧边栏** 双端界面，支持三维数据权限管控

**系统版本**：V3.2（设计文档版本：系统设计 V3.1 / 接口设计 V3.1 / 数据库设计 V3.1）

---

## 🛠 技术栈

| 类别 | 技术 |
|---|---|
| 后端 | Python 3.12 · FastAPI · SQLAlchemy 2.0 (ORM) |
| AI 编排 | LangGraph（人机协同中断闭环） |
| LLM | DeepSeek（对话/生成）· DashScope text-embedding-v3（向量化） |
| 向量检索 | ChromaDB + LlamaIndex（RAG 知识库） |
| 存储 | MySQL 8.0 · Redis 7 · SQLite（LangGraph checkpoint） |
| 前端 | 原生 HTML/CSS/JS 单页应用（管理后台 + 侧边栏） |

---

## 🚀 快速启动

### 前置依赖
- Python 3.12+
- MySQL 8.0（本地或 Docker）
- Redis 7（本地或 Docker）
- 已安装依赖：`pip install -r requirements.txt`（或 `uv sync`）

### 1. 初始化数据库

```bash
mysql -u root -p < k12_app/scripts/init_db.sql
```

> 数据库重建可运行：`python k12_app/scripts/reload_db.py`

### 2. 配置环境变量

复制 `k12_app/backend/.env.example` 为 `k12_app/backend/.env` 并填写：

```
DEEPSEEK_API_KEY=你的DeepSeek密钥
DASHSCOPE_API_KEY=你的DashScope密钥
DB_PASSWORD=数据库密码
JWT_SECRET_KEY=随机字符串（可用 k12_app/scripts/jwt_generate_secret_env.py 生成）
```

> ⚠️ `.env` 含密钥，已在 `.gitignore` 中排除，**切勿提交到仓库**。

### 3. 启动后端

```bash
cd <项目根目录>
python -m uvicorn k12_app.backend.main:app --host 0.0.0.0 --port 8000 --reload
```

Windows 一键启动：运行 `start.ps1`（自动拉起 MySQL/Redis/后端）。

### 4. 访问界面

| 入口 | 地址 | 说明 |
|---|---|---|
| 入口选择页 | `http://localhost:8000/` | 管理后台 / 侧边栏导航 |
| 管理后台 | `http://localhost:8000/admin` | 数据看板、员工/客户/订单/标签管理、权限配置 |
| 顾问侧边栏 | `http://localhost:8000/sidebar` | 客户会话、AI 画像、回复建议、日程 |

---

## 🔑 演示账号

| 用户名 | 密码 | 角色 | 数据范围 |
|---|---|---|---|
| `admin` | `admin123` | 超级管理员 | 全部数据 |
| `hejing` | `hejing123` | 区域主管 | 华北区域 |
| `chenxiaomeng` | `cxm123` | 普通顾问 | 深圳 · 名下客户 |
| `liuyang` | `ly123` | 普通顾问 | 深圳 · 名下客户 |
| `wuqiang` | `wq123` | 普通顾问 | 上海 · 名下客户 |
| `sunyue` | `sy123` | 普通顾问 | 北京 · 名下客户 |
| `zhaoliu` | `zl123` | 未绑定员工 | 演示绑定引导页 |

### 权限模型
- **all（超级管理员）**：查看全部数据
- **region（区域主管）**：查看本区域所有顾问的数据
- **self（普通顾问）**：仅查看自己名下客户数据
- 未绑定员工无法使用业务功能（引导绑定企微账户）

---

## ✨ 核心功能

### 管理后台（/admin）
- 📊 数据看板：客户阶段分布、线索来源、转化漏斗、AI 采纳率
- 👥 员工管理：员工 CRUD、企微账户绑定、角色分配
- 📇 客户管理：客户列表/详情/编辑、标签管理、触达时间线、订单关联
- 🧾 订单管理：订单列表、状态流转、新增订单
- 📝 跟进记录：电话/试听/面谈等跟进 CRUD
- 🏷️ 标签管理：标签体系、AI 推荐规则、客户标签检索
- 📅 日程管理：日历视图、按日查看日程
- 🔐 权限与组织：三级角色矩阵、组织架构、企微账户

### 顾问侧边栏（/sidebar）
- 💬 客户会话列表与聊天窗口
- 🤖 AI 客户画像生成（基于聊天/订单/跟进自动提取）
- ✍️ 回复建议生成（结合画像与上下文）
- 🏷️ 智能标签推荐与确认
- 📅 日程提取与提醒

### AI 与数据层
- **SSE 流式推送**：AI 生成过程实时返回前端
- **LangGraph 人机协同中断**：AI 生成 → 人工确认 → 落库，全链路可追溯
- **RAG 知识检索**：话术库 / SOP / FAQ / 相似客户 / 聊天记录语义检索
- **登录安全**：Session + JWT 双认证、登录失败锁定、Token 黑名单、限流

---

## 📁 项目结构

```
k12_app/
├── backend/
│   ├── main.py              # FastAPI 入口（统一注册 admin/sidebar/rag 路由）
│   ├── config.py            # 配置（读取 .env）
│   ├── agent/               # AI 编排层（LangGraph 图 / LLM 客户端 / 企微工具）
│   ├── dao/                 # 数据访问层（SQLAlchemy ORM）
│   ├── models/              # ORM 模型（22 张表）
│   ├── rag/                 # RAG 层（Embedding / 索引构建 / 检索器）
│   ├── routes/              # API 路由（admin / sidebar / rag）
│   ├── services/            # 业务逻辑层
│   ├── middleware/          # 中间件（限流等）
│   └── data/                # LangGraph checkpoint（已 gitignore，运行时生成）
├── frontend/
│   └── static/              # 管理后台 + 侧边栏 SPA
├── scripts/                 # 数据库初始化 / 工具脚本
├── knowledge_base/          # RAG 知识库（话术 / SOP / FAQ / 案例）
├── docs/                    # 设计文档
└── Dockerfile               # 容器化构建
```

---

## 🧪 测试

```bash
# 端到端连通性测试（前后端-DB 链路，需 MySQL/Redis 运行）
python tests/test_e2e.py

# 人机协同中断闭环回归测试
python tests/test_interrupt_loop.py
```

---

## 📦 部署

- **Docker**：见 `k12_app/Dockerfile`（应用镜像），`docker-compose.yml` 可编排 MySQL/Redis
- **Nginx**：`nginx.conf` 提供反向代理参考配置
- 生产环境建议：设置 `ENV=production`，配置 `SESSION_SECRET_KEY`、HTTPS

---

## 🤝 贡献 / 版本

- 分支管理：基于 `main` 开发，功能分支合并
- 版本号：遵循语义化版本（如 v1.0.0）
- 提交规范：`feat:` / `fix:` / `chore:` / `docs:` 前缀

---

## ⚠️ 安全须知

1. `.env` 中的 API Key / 数据库密码**严禁提交**（已在 .gitignore 排除）
2. 若密钥曾泄露，请立即到对应控制台轮换
3. 生产环境请使用强随机 `JWT_SECRET_KEY` 与 `SESSION_SECRET_KEY`
4. 本项目企微功能默认 Mock 模式（`USE_MOCK=true`），对接真实企微需自行配置

---

## 📄 License

[BSD-3-Clause](LICENSE)（项目默认许可，可按需调整）
