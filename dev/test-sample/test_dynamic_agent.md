# 测试用例：运行时动态增减 Agent

> 覆盖 Session 运行中 Agent 的新增/移除/角色修改/API 切换

## 前置条件
- Session 已创建，初始含 DeepSeek Agent（角色：程序员）
- Host 运行中

## 用例

### 7.1 运行时新增 Agent
| 字段 | 值 |
|------|-----|
| **输入** | `POST /api/sessions/{id}/agents` 加入 Claude Agent（角色：审查者，api_key + model）|
| **操作** | Session Manager 处理 |
| **预期** | Claude 注册 → 创建消费者组 `session:{id}:dispatched` → `config.json` 更新 → Host 策略动态更新，后续步骤可通过 Guard 分发给 Claude |

### 7.2 运行时移除 Agent
| 字段 | 值 |
|------|-----|
| **输入** | `DELETE /api/sessions/{id}/agents/deepseek` |
| **操作** | Session Manager 处理 |
| **预期** | DeepSeek 完成当前任务 → 关闭消费者组 → 从 `config.json` 移除 → Host 策略更新，不再包含该 Agent |

### 7.3 运行时修改 Agent 角色
| 字段 | 值 |
|------|-----|
| **输入** | 将 DeepSeek 角色从"程序员"改为"测试员" |
| **操作** | `PATCH /api/sessions/{id}/agents/deepseek` with `{"role":"测试员"}` |
| **预期** | `config.json` 更新 → Host 策略即时生效 → 后续分发使用新角色 prompt |

### 7.4 运行时切换 Agent API 模型
| 字段 | 值 |
|------|-----|
| **输入** | DeepSeek model 从 `deepseek-chat` 切换到 `deepseek-r1` |
| **操作** | `PATCH /api/sessions/{id}/agents/deepseek` with `{"model":"deepseek-r1"}` |
| **预期** | `config.json` 更新 → 后续 LLM 调用使用新的 model 参数 |
