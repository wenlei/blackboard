# Phase 1 测试报告

> 日期: 2026-05-19  
> 状态: ✅ 通过  
> 环境: Python 3.14.3 / pytest 9.0.3 / macOS (darwin)

---

## 测试概览

| 模块 | 文件 | 用例数 | 通过 | 跳过 | 失败 |
|------|------|--------|------|------|------|
| System Config | `test_config.py` | 22 | 22 | 0 | 0 |
| Message Models | `test_models.py` | 21 | 21 | 0 | 0 |
| Error Types | `test_errors.py` | 14 | 14 | 0 | 0 |
| MQ Layer | `test_mq_layer.py` | 11 | 0 | 11 | 0 |
| Tool Registry | `test_tool_registry.py` | 10 | 10 | 0 | 0 |
| Tool Executor | `test_tool_executor.py` | 13 | 13 | 0 | 0 |
| **合计** | **6 files** | **91** | **80** | **11** | **0** |

---

## 运行命令

```bash
pytest tests/phase1/ -v

# 如需运行 MQ Layer 测试:
WITH_REDIS=1 pytest tests/phase1/ -v
```

---

## 各模块详述

### 1. System Config — 22 测试（22 通过）

**文件**: `tests/phase1/test_config.py`

| # | 测试用例 | 状态 | 说明 |
|---|---------|------|------|
| 1.1 | `test_load_system_yaml` | ✅ | 从临时 YAML 加载完整 SystemConfig |
| 1.2 | `test_load_system_from_project_config` | ✅ | 从真实 `config/system.yaml` 加载 |
| 1.3 | `test_system_config_defaults` | ✅ | 默认值校验（redis/max_connections/data/session） |
| 1.4 | `test_invalid_yaml_type_rejected` | ✅ | 字段类型错误时 Pydantic 拒绝 |
| 1.5 | `test_invalid_yaml_syntax_rejected` | ✅ | 非法 YAML 语法时 YAMLError 抛出 |
| 1.6 | `test_invalid_nested_type_rejected` | ✅ | 嵌套字段类型错误时拒绝 |
| 1.7 | `test_all_sub_configs_present` | ✅ | 子配置全量字段存在性检查 |
| 1.8 | `test_load_agent_registry` | ✅ | 加载 3 个 Agent（deepseek/claude/openai） |
| 1.9 | `test_agent_entry_fields` | ✅ | AgentEntry 各字段值验证 |
| 1.10 | `test_agent_registry_from_project` | ✅ | 从项目真实 registry.yaml 加载 |
| 1.11 | `test_claude_has_multiple_models` | ✅ | Claude 含多模型列表 |
| 1.12 | `test_load_templates` | ✅ | 加载 4 套策略模板 |
| 1.13 | `test_template_ids` | ✅ | 模板 ID 集合完整性 |
| 1.14 | `test_template_match_keywords` | ✅ | code_review 模板关键词匹配 |
| 1.15 | `test_template_steps_have_order` | ✅ | write_code 模板步骤排序递增 |
| 1.16 | `test_general_template_no_keywords` | ✅ | general 模板关键词为空 |
| 1.17 | `test_load_templates_from_project` | ✅ | 从项目真实 templates.yaml 加载 |
| 1.18 | `test_load_presets` | ✅ | 加载 3 套权限预设 |
| 1.19 | `test_whitelist_preset_defaults` | ✅ | whitelist 模式各操作默认值 |
| 1.20 | `test_approval_first_all_require` | ✅ | approval_first 模式全权需审批 |
| 1.21 | `test_open_preset` | ✅ | open 模式仅 denied 拦截 |
| 1.22 | `test_load_presets_from_project` | ✅ | 从项目真实 presets.yaml 加载 |

### 2. Message Models — 21 测试（21 通过）

**文件**: `tests/phase1/test_models.py`

| # | 测试用例 | 状态 | 说明 |
|---|---------|------|------|
| 2.1 | `test_task_creation` | ✅ | Task 基本创建与字段 |
| 2.2 | `test_task_defaults` | ✅ | UUID id 自生成 / 默认 operation_type=chat |
| 2.3 | `test_task_with_operation_type` | ✅ | 指定 operation_type=execute_code |
| 2.4 | `test_task_with_context` | ✅ | context 字段传递 |
| 2.5 | `test_task_json_serialization` | ✅ | model_dump() 序列化 |
| 2.6 | `test_task_json_deserialization` | ✅ | 反序列化创建 |
| 2.7 | `test_task_result_creation` | ✅ | TaskResult 基本字段 |
| 2.8 | `test_task_result_with_token_usage` | ✅ | token_usage dict 序列化 |
| 2.9 | `test_task_result_with_error` | ✅ | 失败状态的 error 字段 |
| 2.10 | `test_task_result_duration` | ✅ | duration_ms 精度 |
| 2.11 | `test_task_result_requested_operation` | ✅ | 执行中回调操作字段 |
| 2.12 | `test_task_result_json_serialization` | ✅ | 全量字段序列化 |
| 2.13 | `test_approval_request_creation` | ✅ | ApprovalRequest 创建 |
| 2.14 | `test_approval_request_defaults` | ✅ | id / created_at 自动生成 |
| 2.15 | `test_approval_response_approve` | ✅ | 批准决策 |
| 2.16 | `test_approval_response_reject` | ✅ | 拒绝决策 |
| 2.17 | `test_approval_pair` | ✅ | 请求-响应 approval_id 配对 |
| 2.18 | `test_stream_message_creation` | ✅ | StreamMessage 基本创建 |
| 2.19 | `test_stream_message_with_channel` | ✅ | target_channel 路由字段 |
| 2.20 | `test_stream_message_no_channel` | ✅ | target_channel=None 默认 |
| 2.21 | `test_stream_message_json_serialization` | ✅ | 全量字段序列化 |

### 3. Error Types — 14 测试（14 通过）

**文件**: `tests/phase1/test_errors.py`

| # | 测试用例 | 状态 | 说明 |
|---|---------|------|------|
| 3.1 | `test_agent_registry_error` | ✅ | 404 + 继承 BlackboardError |
| 3.2 | `test_missing_api_key_error` | ✅ | HTTP 500 |
| 3.3 | `test_invalid_api_key_error` | ✅ | HTTP 502 |
| 3.4 | `test_sandbox_execution_error` | ✅ | HTTP 500 |
| 3.5 | `test_storage_quota_error` | ✅ | HTTP 507 |
| 3.6 | `test_archive_failed_error` | ✅ | HTTP 500 |
| 3.7 | `test_approval_timeout_error` | ✅ | HTTP 408 |
| 3.8 | `test_all_errors_inherit_from_blackboard_error` | ✅ | 7 个错误类继承链 |
| 3.9 | `test_error_status_codes_match_architecture_doc` | ✅ | 状态码与 architecture.md 一致 |
| 3.10 | `test_permission_mode_values` | ✅ | PermissionMode 枚举值 |
| 3.11 | `test_operation_type_values` | ✅ | 8 种操作类型完整 |
| 3.12 | `test_operation_decision_values` | ✅ | allowed/require_approval/denied |
| 3.13 | `test_session_status_values` | ✅ | 5 种会话状态 |
| 3.14 | `test_remote_type_values` | ✅ | 3 种远端存储类型 |

### 4. MQ Layer — 11 测试（11 跳过）

**文件**: `tests/phase1/test_mq_layer.py`  
**状态**: ⏭️ 跳过 — Redis 未运行。设置 `WITH_REDIS=1` 并启动 Redis 后执行。

| # | 测试用例 | 状态 | 说明 |
|---|---------|------|------|
| 4.1 | `test_connect_and_health` | ⏭️ | 连接 + 健康检查 |
| 4.2 | `test_init_session_streams` | ⏭️ | 6 个 Stream 创建 + 消费者组 |
| 4.3 | `test_publish_and_consume` | ⏭️ | 发布 + 消费 + ACK |
| 4.4 | `test_message_ack_removes_from_pel` | ⏭️ | ACK 后 PEL 清空 |
| 4.5 | `test_consumer_group_contention` | ⏭️ | 多消费者争用互斥 |
| 4.6 | `test_destroy_session_streams` | ⏭️ | Stream 全量清理 |
| 4.7 | `test_multi_session_isolation` | ⏭️ | session 隔离不干扰 |
| 4.8 | `test_publish_with_target_channel` | ⏭️ | outbox target_channel |
| 4.9 | `test_consume_empty_stream` | ⏭️ | 空 Stream 返回空 |
| 4.10 | `test_stream_key_format` | ⏭️ | `session:{id}:stream` 格式 |
| 4.11 | `test_all_six_streams_created` | ⏭️ | 6 个 Stream 全部存在 |

### 5. Tool Registry — 10 测试（10 通过）

**文件**: `tests/phase1/test_tool_registry.py`

| # | 测试用例 | 状态 | 说明 |
|---|---------|------|------|
| 5.1 | `test_create_tool_definition` | ✅ | ToolDefinition 创建 |
| 5.2 | `test_parameter_defaults` | ✅ | ToolParameter 默认值 |
| 5.3 | `test_registry_get_existing` | ✅ | get() 命中 |
| 5.4 | `test_registry_get_missing` | ✅ | get() 返回 None |
| 5.5 | `test_list_by_operation` | ✅ | 按 operation_type 筛选 |
| 5.6 | `test_list_all` | ✅ | 全量列举 |
| 5.7 | `test_tool_call_creation` | ✅ | ToolCall 创建 |
| 5.8 | `test_success_result` | ✅ | 成功状态 ToolResult |
| 5.9 | `test_failure_result` | ✅ | 失败状态 ToolResult |
| 5.10 | `test_unknown_tool_result` | ✅ | 未知工具错误 |

### 6. Tool Executor — 13 测试（13 通过）

**文件**: `tests/phase1/test_tool_executor.py`

| # | 测试用例 | 状态 | 说明 |
|---|---------|------|------|
| 6.1 | `test_load_from_config_dir` | ✅ | 从 YAML 加载 7 个工具 |
| 6.2 | `test_load_from_project_config` | ✅ | 从项目真实 registry.yaml 加载 |
| 6.3 | `test_all_operation_types_covered` | ✅ | 5 种 operation_type 全覆蓋 |
| 6.4 | `test_read_file` | ✅ | 文件读取（沙箱内） |
| 6.5 | `test_write_file` | ✅ | 文件写入 |
| 6.6 | `test_write_file_creates_dirs` | ✅ | 写文件自动创建父目录 |
| 6.7 | `test_execute_python` | ✅ | Python 代码执行 |
| 6.8 | `test_execute_python_error_in_code` | ✅ | 代码内错误 → stderr 捕获 |
| 6.9 | `test_execute_shell` | ✅ | Shell 命令执行 |
| 6.10 | `test_unknown_tool` | ✅ | 不存在的工具 → error |
| 6.11 | `test_web_search_stub` | ✅ | 搜索桩返回提示 |
| 6.12 | `test_filesystem_read_missing_file` | ✅ | 读取不存在的文件 → error |
| 6.13 | `test_execute_shell_non_zero_exit` | ✅ | 命令以非零退出码结束 |

---

## 代码质量

```
ruff check tests/phase1/ — All checks passed!
```

---

## 测试文件结构

```
tests/phase1/
├── __init__.py            # 包声明
├── conftest.py            # 共享 fixtures (config/tools/tmp YAML)
├── test_config.py         # System Config 加载与校验 (22 tests)
├── test_models.py         # Pydantic 消息模型 (21 tests)
├── test_errors.py         # 异常类型与枚举 (14 tests)
├── test_mq_layer.py       # MQ Layer Redis Streams (11 tests, 需 Redis)
├── test_tool_registry.py  # 工具模型定义 (10 tests)
└── test_tool_executor.py  # 工具加载与执行 (13 tests)
```

---

## 备注

- MQ Layer 测试需要本地 Redis 运行（`redis://localhost:6379`），当前环境未启动 Redis 故跳过
- 可通过 `docker compose up -d redis` 启动 Redis 后再运行 `WITH_REDIS=1 pytest tests/phase1/`
- `test_execute_python_error_in_code` 验证了代码内异常被捕获到 stderr 并返回，这是当前设计的预期行为
- 配置 `test_invalid_yaml_*` 测试已调整为校验 Pydantic 类型校验能力（非空 YAML）
