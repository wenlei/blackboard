# Phase 3 Test Samples

> 覆盖 Phase 3 全部模块：API Server / Session Logger / UI Pages / Health & SSE

---

## 1. Session Logger — 日志读写

### 1.1 确保目录创建
| 字段 | 值 |
|------|-----|
| **操作** | `SessionLogger("test", tmpdir).ensure_dir()` |
| **预期** | `tmpdir/test/` 目录被创建 |

### 1.2 记录会话对话
| 字段 | 值 |
|------|-----|
| **操作** | `log_conversation("user", "hello")` → `read_conversation()` |
| **预期** | 返回含 `[user] hello` 的字符串，带时间戳前缀 |

### 1.3 记录消息 JSONL
| 字段 | 值 |
|------|-----|
| **操作** | `log_message("inbox", {"type":"chat"})` → `read_messages()` |
| **预期** | 返回列表含 1 条，字段含 timestamp/stream/payload |

### 1.4 记录事件 JSONL
| 字段 | 值 |
|------|-----|
| **操作** | `log_event("session_created", {"agent_count":2})` → `read_events()` |
| **预期** | 返回列表含 1 条，type="session_created"，data 含 agent_count |

### 1.5 读取不存在的会话日志
| 字段 | 值 |
|------|-----|
| **操作** | `read_conversation()` / `read_messages()` / `read_events()` — 目录不存在 |
| **预期** | conversation 返回 ""，messages 返回 []，events 返回 [] |

### 1.6 读取 config.json
| 字段 | 值 |
|------|-----|
| **操作** | 创建 config.json 文件 → `read_config()` |
| **预期** | 返回完整 JSON 对象 |

### 1.7 读取 config.json 不存在
| 字段 | 值 |
|------|-----|
| **操作** | `read_config()` — 文件不存在 |
| **预期** | 返回 {} |

### 1.8 读取策略文件
| 字段 | 值 |
|------|-----|
| **操作** | 创建 strategy.psc → `read_strategy()` |
| **预期** | 返回 PSC 文本内容 |

### 1.9 读取策略文件不存在
| 字段 | 值 |
|------|-----|
| **操作** | `read_strategy()` — 文件不存在 |
| **预期** | 返回 "" |

### 1.10 多条目累计
| 字段 | 值 |
|------|-----|
| **操作** | 连续 3 次 `log_event(...)` → `read_events()` |
| **预期** | 返回 3 条事件 |

---

## 2. API — Session 端点

### 2.1 创建 Session — 成功
| 字段 | 值 |
|------|-----|
| **操作** | `POST /api/sessions` body: `{session_id, agents, permissions}` |
| **预期** | 201/200，返回 config 含 session_id，session_mgr.create 被调用 |

### 2.2 创建 Session — 冲突
| 字段 | 值 |
|------|-----|
| **操作** | `POST /api/sessions` — session_id 已存在（session_mgr 抛出 ValueError） |
| **预期** | 409 Conflict |

### 2.3 获取 Session
| 字段 | 值 |
|------|-----|
| **操作** | `GET /api/sessions/{session_id}` |
| **预期** | 200，返回 `{session_id, status, agent_roles}` |

### 2.4 获取不存在的 Session
| 字段 | 值 |
|------|-----|
| **操作** | `GET /api/sessions/ghost` |
| **预期** | 404 Not Found |

### 2.5 暂停 Session
| 字段 | 值 |
|------|-----|
| **操作** | `POST /api/sessions/{session_id}/pause` |
| **预期** | 200，返回 `{"status":"paused"}` |

### 2.6 暂停不存在的 Session
| 字段 | 值 |
|------|-----|
| **操作** | `POST /api/sessions/ghost/pause` |
| **预期** | 404 |

### 2.7 恢复 Session
| 字段 | 值 |
|------|-----|
| **操作** | `POST /api/sessions/{session_id}/resume` |
| **预期** | 200，返回 `{"status":"active"}` |

### 2.8 关闭 Session
| 字段 | 值 |
|------|-----|
| **操作** | `DELETE /api/sessions/{session_id}` |
| **预期** | 200，返回 `{"status":"closed"}` |

### 2.9 关闭不存在的 Session
| 字段 | 值 |
|------|-----|
| **操作** | `DELETE /api/sessions/ghost` |
| **预期** | 404 |

---

## 3. API — Message 端点

### 3.1 发送消息
| 字段 | 值 |
|------|-----|
| **操作** | `POST /api/sessions/{id}/messages` body: `{"content":"hello"}` |
| **预期** | 200，返回 `{"status":"sent"}`，mq.publish 被调用 |

### 3.2 发送消息到不存在的 Session
| 字段 | 值 |
|------|-----|
| **操作** | `POST /api/sessions/ghost/messages` |
| **预期** | 404 |

### 3.3 执行 Session
| 字段 | 值 |
|------|-----|
| **操作** | `POST /api/sessions/{id}/execute` |
| **预期** | 200，返回 `{"status":"executing"}`，mq.publish 发送 command 消息 |

### 3.4 获取会话历史
| 字段 | 值 |
|------|-----|
| **操作** | `GET /api/sessions/{id}/history` |
| **预期** | 200，返回 `{conversation, messages, events}` |

### 3.5 获取策略
| 字段 | 值 |
|------|-----|
| **操作** | `GET /api/sessions/{id}/strategy` |
| **预期** | 200，返回 `{"psc":"..."}` |

### 3.6 获取策略不存在
| 字段 | 值 |
|------|-----|
| **操作** | `GET /api/sessions/{id}/strategy` — psc 为空 |
| **预期** | 404 |

---

## 4. API — Agent 端点（Session 内）

### 4.1 添加 Agent
| 字段 | 值 |
|------|-----|
| **操作** | `POST /api/sessions/{id}/agents` body: `{name, provider, role}` |
| **预期** | 200，返回 `{"status":"added"}` |

### 4.2 添加 Agent 到不存在的 Session
| 字段 | 值 |
|------|-----|
| **操作** | `POST /api/sessions/ghost/agents` |
| **预期** | 404 |

### 4.3 移除 Agent
| 字段 | 值 |
|------|-----|
| **操作** | `DELETE /api/sessions/{id}/agents/{agent_name}` |
| **预期** | 200，返回 `{"status":"removed"}` |

### 4.4 更新 Agent
| 字段 | 值 |
|------|-----|
| **操作** | `PATCH /api/sessions/{id}/agents/{agent_name}` body: `{"role":"new_role"}` |
| **预期** | 200，返回 `{"status":"updated","changes":{...}}` |

---

## 5. API — Permission 端点

### 5.1 更新权限模式
| 字段 | 值 |
|------|-----|
| **操作** | `PATCH /api/sessions/{id}/permissions` body: `{"mode":"open"}` |
| **预期** | 200，返回 `{"status":"updated"}` |

### 5.2 更新操作权限
| 字段 | 值 |
|------|-----|
| **操作** | `PATCH /api/sessions/{id}/permissions` body: `{"operations":{"chat":"allowed"}}` |
| **预期** | 200 |

### 5.3 更新不存在的 Session 权限
| 字段 | 值 |
|------|-----|
| **操作** | `PATCH /api/sessions/ghost/permissions` |
| **预期** | 404 |

---

## 6. API — Archive 端点

### 6.1 归档 Session
| 字段 | 值 |
|------|-----|
| **操作** | `POST /api/sessions/{id}/archive` body: `{remote_type, remote_path}` |
| **预期** | 200，返回 `{"status":"archived","archive":"..."}` |

### 6.2 归档不存在的 Session
| 字段 | 值 |
|------|-----|
| **操作** | `POST /api/sessions/ghost/archive` |
| **预期** | 404 |

### 6.3 获取归档状态
| 字段 | 值 |
|------|-----|
| **操作** | `GET /api/sessions/{id}/archive` |
| **预期** | 200，返回 `{"status":"ready","path":"..."}` 或 404 |

---

## 7. API — Config 端点

### 7.1 获取 Agent 配置
| 字段 | 值 |
|------|-----|
| **操作** | `GET /api/config/agents` |
| **预期** | 200，返回 `{agents: {...}}`，config_loader.load_agent_registry 被调用 |

### 7.2 添加 Agent 配置
| 字段 | 值 |
|------|-----|
| **操作** | `POST /api/config/agents` body: `{name, provider, ...}` |
| **预期** | 200，返回 `{"status":"added","name":"..."}` |

### 7.3 删除 Agent 配置
| 字段 | 值 |
|------|-----|
| **操作** | `DELETE /api/config/agents/{name}` |
| **预期** | 200，返回 `{"status":"removed","name":"..."}` |

### 7.4 获取模板配置
| 字段 | 值 |
|------|-----|
| **操作** | `GET /api/config/templates` |
| **预期** | 200，返回 `{templates: [...]}` |

### 7.5 添加模板配置
| 字段 | 值 |
|------|-----|
| **操作** | `POST /api/config/templates` |
| **预期** | 200，返回 `{"status":"added","id":"..."}` |

### 7.6 更新模板配置
| 字段 | 值 |
|------|-----|
| **操作** | `PATCH /api/config/templates/{id}` |
| **预期** | 200，返回 `{"status":"updated","id":"..."}` |

### 7.7 获取权限预设
| 字段 | 值 |
|------|-----|
| **操作** | `GET /api/config/permissions/presets` |
| **预期** | 200，返回 `{presets: {...}}` |

---

## 8. Health 端点

### 8.1 健康检查 — 全部正常
| 字段 | 值 |
|------|-----|
| **操作** | `GET /health` — Redis 可用、工具已加载、有活跃 Session |
| **预期** | 200，status="ok"，redis="connected"，tools_loaded > 0 |

### 8.2 健康检查 — Redis 不可用
| 字段 | 值 |
|------|-----|
| **操作** | `GET /health` — Redis 断开 |
| **预期** | 200，status="degraded"，redis="disconnected" |

---

## 9. SSE 端点

### 9.1 事件流 SSE
| 字段 | 值 |
|------|-----|
| **操作** | `GET /api/events/stream` — Accept: text/event-stream |
| **预期** | 200，Content-Type=text/event-stream，返回 `data: ...` 格式 |

---

## 10. UI Pages

### 10.1 Dashboard 页面
| 字段 | 值 |
|------|-----|
| **操作** | `GET /` |
| **预期** | 200，Content-Type=text/html，内容含 Blackboard 相关元素 |

### 10.2 Session 创建页面
| 字段 | 值 |
|------|-----|
| **操作** | `GET /sessions` |
| **预期** | 200，Content-Type=text/html |

### 10.3 Session 聊天页面
| 字段 | 值 |
|------|-----|
| **操作** | `GET /sessions/{session_id}` |
| **预期** | 200，Content-Type=text/html |

---

## 测试文件映射

| 测试文件 | 覆盖模块 | 用例数 |
|----------|----------|--------|
| `tests/phase3/test_logger.py` | SessionLogger (日志读写/配置/策略) | 10 |
| `tests/phase3/test_api_sessions.py` | Session 端点 (CRUD) | 9 |
| `tests/phase3/test_api_messages.py` | Message/Execute/History/Strategy | 6 |
| `tests/phase3/test_api_agents.py` | Session 内 Agent 端点 | 4 |
| `tests/phase3/test_api_permissions.py` | Permission 端点 | 3 |
| `tests/phase3/test_api_archive.py` | Archive 端点 | 3 |
| `tests/phase3/test_api_config.py` | Config 端点 | 7 |
| `tests/phase3/test_health.py` | Health 端点 | 2 |
| `tests/phase3/test_sse.py` | SSE Streaming | 1 |
| `tests/phase3/test_ui.py` | UI Pages (Dashboard/Create/Chat) | 3 |

**总计**: 48 个 Phase 3 测试用例
