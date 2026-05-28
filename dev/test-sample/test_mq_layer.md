# 测试用例：MQ Layer

> 覆盖 Redis Streams 的生产/消费/ACK/PEL/隔离/清理

## 前置条件
- Redis 已启动
- MQ Layer 封装已初始化

## 用例

### 4.1 Session 初始化 Stream 组
| 字段 | 值 |
|------|-----|
| **输入** | 创建 session `test-001` |
| **操作** | `mq_layer.init_session_streams("test-001")` |
| **预期** | 6 个 Stream（inbox/outbox/dispatched/results/approvals/events）+ 对应消费者组全部创建成功 |

### 4.2 消息生产
| 字段 | 值 |
|------|-----|
| **输入** | `{"type": "chat", "content": "hello"}` |
| **操作** | `mq_layer.publish("session:test-001:inbox", msg)` |
| **预期** | XADD 成功，返回 message_id 格式 `{timestamp}-{sequence}` |

### 4.3 消息消费
| 字段 | 值 |
|------|-----|
| **输入** | inbox 中有待消费消息 |
| **操作** | `mq_layer.consume("session:test-001:inbox", "host", count=1, block=5000)` |
| **预期** | XREADGROUP 返回一条消息，内容与生产的一致 |

### 4.4 消息 ACK
| 字段 | 值 |
|------|-----|
| **输入** | 已消费但未确认的消息 |
| **操作** | `mq_layer.ack("session:test-001:inbox", "host", [message_id])` |
| **预期** | XACK 成功，从 PEL 移除 |

### 4.5 消费者组内竞争
| 字段 | 值 |
|------|-----|
| **输入** | dispatched Stream 有 1 条消息，2 个 Agent（deepseek, claude）共用 `agents` 消费者组 |
| **操作** | 两个 Agent 同时 consume |
| **预期** | 同一条消息只被一个消费者拿到（另一个拿到 None） |

### 4.6 异常恢复（PEL）
| 字段 | 值 |
|------|-----|
| **输入** | 消费者 crash 前消费了 3 条消息但未 ACK |
| **操作** | 模拟 crash → 重启同一个消费者组 |
| **预期** | XPENDING 显示 3 条未确认消息 → 使用 `XREADGROUP ... IDLE 0` 重新分发给组内其他消费者 |

### 4.7 Session 销毁 — Stream 清理
| 字段 | 值 |
|------|-----|
| **输入** | session 关闭 |
| **操作** | `mq_layer.destroy_session_streams("test-001")` |
| **预期** | 6 个 Stream 和消费者组全部删除 → `KEYS session:test-001:*` 返回空 |

### 4.8 多 Session 隔离
| 字段 | 值 |
|------|-----|
| **输入** | 同时存在 session-001 和 session-002 |
| **操作** | 分别写入 inbox → 分别 consume |
| **预期** | `session:test-001:*` 和 `session:test-002:*` 的 Stream 互不干扰 |
