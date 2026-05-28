# 测试用例：IM Bridge 消息渠道适配

> 覆盖 Telegram/Discord 等外部 IM 渠道的收发、审批交互、断线恢复

## 前置条件
- Telegram Bot Token 已配置
- IM Bridge 模块已加载
- MQ Layer 正常

## 用例

### 6.1 Telegram 消息进入
| 字段 | 值 |
|------|-----|
| **输入** | Telegram 用户 @session → 发消息 `"帮我写代码"` |
| **操作** | Webhook 接收 → IM Bridge 处理 |
| **预期** | IM Bridge 解析消息 → 映射到 session_id → 写入 `session:{id}:inbox`，格式：`{"source":"telegram","user_id":"123","content":"帮我写代码"}` |

### 6.2 Host 回复 → Telegram 回传
| 字段 | 值 |
|------|-----|
| **输入** | Host 写入 outbox：`{"target":"telegram","user_id":"123","content":"好的，开始分析..."}` |
| **操作** | IM Bridge 消费 outbox |
| **预期** | 通过 Telegram Bot API `sendMessage` 发送给用户 |

### 6.3 审批请求 → Telegram 按钮
| 字段 | 值 |
|------|-----|
| **输入** | Guard 触发审批 → outbox 推送 |
| **操作** | IM Bridge 收到审批消息 |
| **预期** | Telegram 推送带 InlineKeyboard 的消息：「Agent XX 请求执行文件写入，是否批准？」+ [批准] [拒绝] 按钮 |

### 6.4 用户 TG 点击"批准"
| 字段 | 值 |
|------|-----|
| **输入** | Telegram callback_query: "approve:task_id" |
| **操作** | IM Bridge 接收 callback → 写入 approvals Stream |
| **预期** | Guard 收到 `{"decision":"approved","task_id":"..."}` → 放行 Agent 执行 |

### 6.5 多渠道同时接入
| 字段 | 值 |
|------|-----|
| **输入** | Telegram 用户和 Discord 用户同时发消息到同一个 session |
| **操作** | 两条消息先后写入 inbox |
| **预期** | 消息按时间戳排序 → Host 按序消费 → 回复通过 outbox 分别回传给各自渠道 |

### 6.6 IM 断线重连
| 字段 | 值 |
|------|-----|
| **输入** | Telegram Bot 临时离线 30 秒 |
| **操作** | 重连后恢复 |
| **预期** | 重连后 IM Bridge 调用 `XPENDING` 获取 outbox 消费者的 PEL → 重放未成功发送的消息 → 不会丢消息 |
