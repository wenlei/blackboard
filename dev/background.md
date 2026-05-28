# 项目背景

## 项目名称
Blackboard

## 创建日期
2026-05-19

## 问题陈述
在复杂的 AI 任务场景中，单一 LLM 往往难以胜任。用户需要同时调用多个 LLM（如 DeepSeek、Claude、GPT-4），并对它们的协作进行统一编排。现有方案缺乏一个轻量、可自部署的调度框架来：
- 解耦任务分发与 LLM 调用
- 让用户在任务执行过程中随时介入（取消、重定向、修改 prompt）
- 以插件化的方式新增或替换 LLM provider

Blackboard 通过 Redis Streams 消息队列实现松耦合的 Agent 编排，提供 REST API + Web UI 让用户全程掌控任务流转。

## 目标用户
- AI 开发者：需要同时使用多个 LLM，希望统一调度和切换
- 个人/小团队：需要一个轻量、Docker 一键部署的调度框架
- 研究者：需要对比不同 LLM 的输出质量，灵活切换 provider

## 核心功能
1. **多 LLM Agent 编排**：统一管理 DeepSeek、Claude、OpenAI 等 provider，Host 按策略模板 + LLM 动态生成执行计划，分发任务给各 Agent
2. **Redis Streams 消息队列**：基于消费者组的 Pub/Sub 通信，Session 级 Stream 隔离，解耦调度与执行
3. **REST API 接口**：Session 创建与管理、Agent 动态增减、权限管理、归档操作、SSE 事件推送
4. **用户实时介入**：任务执行中可随时暂停/恢复、修改策略、调整权限、归档会话
5. **工具链/技能调用**：7 个内置工具（文件读写/代码执行/HTTP 请求/搜索），统一 ToolCall → ToolResult 接口，与 Guard 权限联动
6. **Docker 容器化部署**：一条 `docker compose up` 即可启动完整服务（Redis + API）

## 已知约束
- 无既有系统需对接
- 无技术栈锁定，自由选择
- 个人/小团队使用，成本敏感
- 会 Docker，具备基本容器运维能力

## 成功标准

| 阶段 | 达成标准 |
|------|---------|
| Phase 1 — 地基 | `docker compose up` 能跑；Redis 可读写；29 tests pass |
| Phase 2 — 核心 | 能创建 Session；Host 生成 .psc 并执行多 Agent 协作任务；190 tests pass |
| Phase 3 — 接口 | 浏览器打开 → 创建 Session → 发消息 → 实时看 Agent 执行 → 审批危险操作；290 tests pass |
| Phase 4 — 运维 | Agent 执行代码不污染宿主机；历史 Session 可归档推到 NAS；316 tests pass |
| **整体** | 单用户 `docker compose up` 一键启动；全链路（消息 → Host 编排 → Agent 执行 → 回复）可用；无硬编码 API Key |

## 项目范围
### 包含
- Redis Streams 消息队列层
- Host 策略生成与会话调度（规则模板 + LLM 动态补充，用户确认后执行）
- Session Manager 生命周期管理（创建/暂停/恢复/关闭/动态增减 Agent）
- Session Guard 权限守卫（whitelist / approval_first / open + 审批流程）
- LLM Agent 适配器（DeepSeek、Claude、OpenAI）+ 统一 BaseAgent 接口
- REST API 服务 + SSE 实时事件推送
- Web UI（Jinja2 模板 + Animal Island 设计风格）
- 可视化 DAG / 工作流编辑器（拖拽 Agent 节点、连线、语义化编排执行流程）— 后期阶段
- IM Bridge 多渠道适配（Telegram/Discord/Slack）
- Session Logger 全量操作落盘与会话回放
- System Config 全局配置管理（注册表、模板库、权限预设）
- Tool Registry 工具/技能注册表（7 个内置工具，与 Guard 权限联动）
- Docker Compose 一键部署
- 沙箱执行环境（初期 subprocess + 白名单目录，后期 Docker 子容器）
- 会话归档与远端存储（local_nas / s3 / sftp）

### 不包含（Out of Scope）
- 多租户组织架构与 RBAC 权限系统
- LLM 训练/微调/模型托管
- 商业级 SLA 保障与计费系统
