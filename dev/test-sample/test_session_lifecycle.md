# 测试用例：Session 生命周期

> 覆盖 Session 创建/暂停/恢复/关闭/落盘/回放

## 前置条件
- Redis 已启动，MQ Layer 可用
- Session Manager 已初始化
- 测试目录 `/tmp/blackboard-test/sessions/` 已创建

## 用例

### 1.1 创建 Session
| 字段 | 值 |
|------|-----|
| **输入** | 用户提交 config JSON（2 个 Agent 各配角色，权限模式 whitelist）|
| **操作** | `POST /api/sessions` with body from `fixtures/session_config.json` |
| **预期** | 返回 201 + `session_id`，MQ Stream 组已初始化（6 个 Stream），`config.json` 落盘 |

### 1.2 Host 自动启动
| 字段 | 值 |
|------|-----|
| **输入** | session 创建成功 |
| **操作** | 检查 Host 消费者组状态 |
| **预期** | Host 已注册 `session:{id}:inbox` 消费者组，处于 XREADGROUP BLOCK 等待状态 |

### 1.3 用户发送首条消息
| 字段 | 值 |
|------|-----|
| **输入** | `"帮我分析这段代码的性能问题"` |
| **操作** | `POST /api/sessions/{id}/messages` |
| **预期** | 消息写入 `session:{id}:inbox`，Host 收到并开始生成策略 |

### 1.4 Session 暂停
| 字段 | 值 |
|------|-----|
| **输入** | session 运行中 |
| **操作** | `POST /api/sessions/{id}/pause` |
| **预期** | Host 停止消费新消息，进行中的 Agent 任务正常完成，返回状态 `paused` |

### 1.5 Session 恢复
| 字段 | 值 |
|------|-----|
| **输入** | session 处于 paused 状态 |
| **操作** | `POST /api/sessions/{id}/resume` |
| **预期** | Host 重新开始消费 inbox，状态变为 `active`，PEL 中的未处理消息被重新拾取 |

### 1.6 Session 关闭
| 字段 | 值 |
|------|-----|
| **输入** | session 运行中 |
| **操作** | `DELETE /api/sessions/{id}` |
| **预期** | 返回 200，关闭所有 MQ 消费者组，保留文件不删除，状态标记为 `closed` |

### 1.7 重复创建
| 字段 | 值 |
|------|-----|
| **输入** | 已存在的 session_id |
| **操作** | `POST /api/sessions` 携带相同 id |
| **预期** | 返回 409 Conflict |

### 1.8 文件落盘完整性
| 字段 | 值 |
|------|-----|
| **输入** | 正常流程完成 |
| **操作** | 检查 session 文件夹 |
| **预期** | 确认 `config.json`、`strategy.json`、`conversation.log`、`messages.jsonl`、`events.jsonl` 5 个文件均存在且非空 |
