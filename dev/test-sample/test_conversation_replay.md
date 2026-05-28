# 测试用例：Session 回放

> 覆盖已关闭 Session 的对话回放、策略查看、消息重放、配置克隆

## 前置条件
- session `test-001` 已完成多轮对话并关闭
- Session 文件夹 `/data/sessions/test-001/` 存在且包含完整文件

## 用例

### 8.1 对话时间线回放
| 字段 | 值 |
|------|-----|
| **输入** | 已关闭 session `test-001` |
| **操作** | `GET /api/sessions/test-001/history` |
| **预期** | 返回完整时间线：时间戳 + 角色（User/Host/Agent 名）+ 消息内容 + 操作类型 |

### 8.2 策略执行路径查看
| 字段 | 值 |
|------|-----|
| **输入** | session `test-001` |
| **操作** | `GET /api/sessions/test-001/strategy` |
| **预期** | 返回策略 JSON，展示每一步：步骤序号 → 目标 Agent → 输入内容 → 结果摘要 → 跳转关系 |

### 8.3 MQ 消息顺序重放
| 字段 | 值 |
|------|-----|
| **输入** | `messages.jsonl` 文件 |
| **操作** | Session Logger 读取逐行重放 |
| **预期** | 按时间戳顺序遍历所有 Stream 消息（inbox/outbox/dispatched/results/approvals），还原完整通信过程 |

### 8.4 基于旧 Session 克隆新建
| 字段 | 值 |
|------|-----|
| **输入** | 历史 session `test-001` 的配置 |
| **操作** | `POST /api/sessions` with `{"clone_from":"test-001"}` |
| **预期** | 新 session 继承所有配置（Agent 列表 + 角色 + 权限设置），但不继承策略和对话记录 |
