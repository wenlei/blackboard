# Bug 记录

## BUG-004 — getAllProviders() 把实例名当 provider slug 污染下拉列表

**发现日期**：2026-05-23
**状态**：已修复

### 根因

设计演进未同步更新同一处代码，导致两次变更叠加出 bug：

1. **早期设计**：实例名 = provider slug（一对一）。`getAllProviders()` 把 `agentConfig`（以实例名为 key）merge 进 provider 列表——因为两者相同，碰巧正确。
2. **ADR-013（实例名与 provider 解耦）**：实例名改为用户自定义（如 "myHost"、"DS1"），同一 Provider 可建多个实例。凭证存储键、保存逻辑等处都同步更新，**但 `getAllProviders()` 遗漏**，仍用实例名做 key merge，从此实例名开始污染 provider 下拉列表。

结果：用户在 Add/Edit modal 的 Provider 下拉里看到其他实例名（如 "myHost"）作为 provider 选项，选中后错误地把实例名存为 `agent.provider` 字段。

### 修复

`config.html` `getAllProviders()`：遍历 `agentConfig` 时改为取 `val.provider`（provider slug），而非 `key`（实例名）。自定义 provider（不在 OpenRouter 列表中）仍可通过此路径补充进下拉，但不再混入实例名。

### 影响文件
- `src/blackboard/templates/config.html`：`getAllProviders()` 逻辑修正

---

## BUG-003 — SSE 端点两处崩溃

**发现日期**：2026-05-22
**状态**：已修复

### 根因

`_event_stream` 调用 `mq.consume("system", "events", "sse-listener", block_ms=5000)` — 缺少必需的 `consumer_name` 位置参数，运行时直接 TypeError。

`_session_event_stream` 使用 `consumer_group="outbox"`（XREADGROUP），多个 SSE 客户端连接同一 session 时，Redis 将消息"竞争分发"给各消费者，每条事件只有一个客户端能收到。

### 修复

在 `MQLayer` 新增 `read_from(session_id, stream_name, last_id, count, block_ms)` 方法，改用 `XREAD`（非 XREADGROUP）。每个 SSE 连接持有独立的 `last_id` 游标，实现真正的广播语义。

两个 SSE 生成器均改为调用 `read_from()`，消除对消费者组的依赖。

### 影响文件
- `src/blackboard/mq/redis_streams.py`：新增 `read_from()` 方法
- `src/blackboard/api/routes.py`：`_event_stream` 和 `_session_event_stream` 改为 `read_from()`

---

## BUG-002 — Provider / Fallback 数据三处硬编码

**发现日期**：2026-05-22
**状态**：已修复

### 根因

同一份数据分散在三处：
- `routes.py`：`BUILTIN_AGENTS`（7 项）、`FALLBACK_MODELS`（40+ 项）、`preset_base_urls`（23 项，局部变量）
- `config.html`：`PROVIDER_PRESETS`（25 项 JS 常量）、`PINNED_MODELS`（9 项 JS 常量）

新增或修改 Provider 必须同时改 Python 和 HTML，且两份列表极易不同步。

### 修复

新增两个 YAML 配置文件：
- `config/agents/provider_presets.yaml` — 25 个 Provider 预设，含 `protected` 字段替代 `BUILTIN_AGENTS`
- `config/agents/fallback_models.yaml` — Fallback 模型 + Pinned Model IDs

`ConfigLoader` 新增 `load_provider_presets()` / `load_fallback_models()`。

`GET /api/config/provider-presets` 端点供前端动态加载。

前端移除所有硬编码 JS 常量，改为页面初始化时从 API 拉取。

### 影响文件
- `config/agents/provider_presets.yaml`（新增，保留）
- `config/agents/fallback_models.yaml`（新增；**2026-05-22 后续已删除**，改为 `GET /api/config/providers/{slug}/catalog` 实时查 OpenRouter 公开 API 替代静态列表）
- `src/blackboard/config/loader.py`：新增 4 个模型类 + 2 个加载方法
- `src/blackboard/api/routes.py`：删除 3 个硬编码结构，新增端点
- `src/blackboard/templates/config.html`：删除 2 个 JS 常量，改为 API 加载

---


## BUG-001 — Model 同步永远 404 / 500

**发现日期**: 2026-05-21
**状态**: 已修复

### 根因

**预存的 import 路径错误**。`config_sync_models` 的 auto-create 块中：

```python
from blackboard.config.models import AgentEntry  # ImportError
```

`AgentEntry` 定义在 `blackboard.config.loader`，不在 `.models`。

当 `registry.yaml` 非空时，`deepseek` 已在注册表中，auto-create 跳过，import 不执行——所以这个 bug 从未暴露。
当文件被清空后，auto-create 触发 → ImportError → 500，文件保持为空，后续一切崩溃。

### 修复

`routes.py:724`: `from blackboard.config.models` → `from blackboard.config.loader`

### 连锁反应

1. registry.yaml 被清空 → agents API 返回空
2. Sync Models 触发 auto-create → ImportError 500
3. 文件保持空 → 所有后续操作崩
4. 前端 JSON.parse 报错（API 返回非 JSON）

### 其他修复

- `loader.py`: load_agent_registry 处理空 YAML (None → 空注册表)
- `routes.py`: sync-models 不依赖 credential_mgr（FERNET_KEY 未设时也能工作）
- `routes.py`: _fetch_from_openrouter 加 logger、加 FALLBACK_MODELS
- `config.html`: selectProvider 自动 sync；cred reload 失败时用响应数据
- `config/agents/registry.yaml`: 恢复被清空的文件，补全 DeepSeek / Anthropic / OpenAI 三条 Agent 条目（2026-05-22）
