# 测试用例：Agent 适配器

> 覆盖 Agent 注册/执行/并行/错误处理/动态增减

## 前置条件
- MQ Layer 正常
- LLM API mock server 已配置（返回可控响应）

## 用例

### 5.1 Agent 注册
| 字段 | 值 |
|------|-----|
| **输入** | 注册 DeepSeek Agent（api_key + model: deepseek-chat）|
| **操作** | `AgentRegistry.register("deepseek", DeepSeekAdapter(config))` |
| **预期** | Agent 写入注册表 → 创建对应消费者组 `session:{id}:dispatched` → health_check 返回 True |

### 5.2 Agent 执行
| 字段 | 值 |
|------|-----|
| **输入** | Host 分发任务到 DeepSeek（prompt:"写一个排序函数", role:"程序员"）|
| **操作** | Agent 消费 `dispatched` → 调用 LLM API → 写 `results` |
| **预期** | results 中包含代码 + token 用量 + 耗时 |

### 5.3 不同 Agent 并行
| 字段 | 值 |
|------|-----|
| **输入** | 同时分发 2 个任务到 DeepSeek 和 Claude |
| **操作** | 两个 Adapter 各自消费 |
| **预期** | 独立消费、并行执行、各自写 results，互不阻塞 |

### 5.4 API 错误处理 — 429 限流
| 字段 | 值 |
|------|-----|
| **输入** | LLM API 返回 429 Too Many Requests |
| **操作** | Adapter 接收 429 响应 |
| **预期** | 指数退避重试（1s → 2s → 4s）→ 最多 3 次 → 超限后返回 error 结果 |

### 5.5 API 超时处理
| 字段 | 值 |
|------|-----|
| **输入** | LLM API 60s 无响应 |
| **操作** | Adapter 设置 httpx timeout=60 |
| **预期** | TimeoutException → 返回 error 结果（不重试，超时通常不是瞬时的） |

### 5.6 Agent 暂停
| 字段 | 值 |
|------|-----|
| **输入** | `POST /api/agents/{id}/pause` |
| **操作** | 停止消费新消息 |
| **预期** | 进行中任务完成 → 不再拉取新消息 → PEL 中消息留给组内其他消费者 |

### 5.7 运行时新增 Agent
| 字段 | 值 |
|------|-----|
| **输入** | session 运行中 → `POST /api/sessions/{id}/agents` 加入 Claude |
| **操作** | Session Manager 执行新增 |
| **预期** | 注册 + 创建消费者组 + 立即可被 Host 分发 + `config.json` 更新 |

### 5.8 运行时移除 Agent
| 字段 | 值 |
|------|-----|
| **输入** | session 运行中移除 DeepSeek |
| **操作** | `DELETE /api/sessions/{id}/agents/deepseek` |
| **预期** | 完成当前任务 → 关闭消费者组 → 从注册表移除 → `config.json` 更新 → Host 策略不再包含该 Agent |
