# 测试用例：Session Guard 权限守卫

> 覆盖 whitelist / approval_first / open 三种模式 + 审批流程 + 动态修改

## 前置条件
- Session 已创建，Host 运行中
- Session Guard 已加载权限配置
- 3 个 Agent 均已注册

## 用例

### 3.1 Whitelist — 允许的操作
| 字段 | 值 |
|------|-----|
| **输入** | Agent 要执行 `chat`（whitelist 中标记 allowed）|
| **操作** | Host 调用 Guard 校验 |
| **预期** | Guard 返回 `allowed` → Host 正常分发到 Agent |

### 3.2 Whitelist — 禁止的操作
| 字段 | 值 |
|------|-----|
| **输入** | Agent 要执行 `execute_code`（未在 whitelist 中声明）|
| **操作** | Host 调用 Guard 校验 |
| **预期** | Guard 返回 `denied` → Host 不分发 → 写入 events log："[Guard] execute_code denied for agent:{name}" |

### 3.3 require_approval — 发起审批
| 字段 | 值 |
|------|-----|
| **输入** | Agent 要执行 `file_write`（标记 require_approval）|
| **操作** | Host 调用 Guard 校验 |
| **预期** | Guard 挂起任务 → outbox Stream 推送审批请求 → 消息内容："Agent XX 请求写入文件 `path/file.py`，是否批准？" + 任务进入 pending 状态 |

### 3.4 require_approval — 用户批准
| 字段 | 值 |
|------|-----|
| **输入** | 用户回复 "yes"（或 TG 点击「批准」按钮）|
| **操作** | 批准消息写入 `approvals` Stream |
| **预期** | Guard 收到 → 任务状态变更为 allowed → Host 分发 Agent 执行 |

### 3.5 require_approval — 用户拒绝
| 字段 | 值 |
|------|-----|
| **输入** | 用户回复 "no" |
| **操作** | 拒绝消息写入 `approvals` Stream |
| **预期** | Guard 收到 → 任务状态 = denied → Host 通知 Agent → events log 记录："[Guard] file_write rejected by user" |

### 3.6 require_approval — 超时自动拒绝
| 字段 | 值 |
|------|-----|
| **输入** | 审批请求发出后 5 分钟无响应 |
| **操作** | Guard 超时检查 |
| **预期** | 超时回调 → 自动拒绝 → events log 记录 "[Guard] approval timeout → auto-deny for file_write" |

### 3.7 Approval First 模式
| 字段 | 值 |
|------|-----|
| **输入** | 权限模式设为 `approval_first`，操作 `chat`（未单独标记 allowed）|
| **操作** | Host 调用 Guard 校验 |
| **预期** | 所有未明确 allowed 的操作 → 进入审批流程（同 3.3）|

### 3.8 Open 模式
| 字段 | 值 |
|------|-----|
| **输入** | 权限模式设为 `open`，操作 `file_write`（默认 require_approval）|
| **操作** | Host 调用 Guard 校验 |
| **预期** | open 模式下仅 `denied` 列表拦截 → `file_write` 不在 denied 列表 → 直接放行 |

### 3.9 运行时修改权限
| 字段 | 值 |
|------|-----|
| **输入** | `PATCH /api/sessions/{id}/permissions` 将 `execute_code` 从 denied 改为 require_approval |
| **操作** | 调用 API 更新权限 |
| **预期** | 权限配置即时生效，下一次校验使用新规则 |

### 3.10 按 Agent 单独设权限（可选扩展）
| 字段 | 值 |
|------|-----|
| **输入** | Agent A 可以 `file_write`，Agent B 不可以 |
| **操作** | Host 调用 Guard 校验时携带 agent_id |
| **预期** | Guard 按 Agent 身份分别校验 → Agent A 放行 / Agent B 拦截 |
