# Config 模块规则

> 覆盖范围：`src/blackboard/config/`、`src/blackboard/api/routes.py`（config 段）、
> `src/blackboard/templates/config.html`

---

## 0. 凭据文件位置

凭据（API Key + 模型列表）存储在 **`config/agents/credentials.enc`**，与 `registry.yaml` 同级，由 `CredentialManager(config_dir=CONFIG_DIR)` 管理。

```
config/agents/
├── registry.yaml      ← Agent 注册信息（provider、base_url 等）
└── credentials.enc    ← API Key 加密存储（Fernet，实例名为键）
```

**不在** `data/sessions/` 下。Session 数据目录可以安全清理，不影响凭据。

---

## 1. 键名语义：全部按实例名

| 存储层 | 键类型 | 示例 |
|--------|--------|------|
| `registry.yaml` → `agents` dict | **实例名**（用户自定义） | `"DS1"`, `"my-claude"` |
| `CredentialManager._state["credentials"]` | **实例名** | `"DS1"`, `"my-claude"` |
| `CredentialManager._state["model_lists"]` | **实例名** | `"DS1"`, `"my-claude"` |

**规则**：注册表、凭据、模型列表三者均以实例名为键，实例间数据完全独立，不共享。
`entry.provider`（provider slug）仅用于 API 调用（base_url 推断、openrouter enrich），不用于存储键。

```
agentConfig["DS1"]           →  agentCredentials["DS1"]
agentConfig["my-claude"]     →  agentCredentials["my-claude"]
```

---

## 2. 凭据查找（前端）

```javascript
// ✅ 正确：直接用实例名（表格 key / editKey）
const cred = agentCredentials[instanceName];

// ❌ 错误：用 provider slug 查凭据
const cred = agentCredentials[a.provider];  // 永远 undefined（provider slug 不是存储键）
```

受影响函数：`openAgentModal`、`selectModel`、`syncAgentModels`、表格渲染 `loadAgents`。

---

## 3. 同一 Provider 多实例

同一 provider slug 可对应多个注册实例（如 DS1、DS2 都 provider="deepseek"）。
凭据（api_key、model_list）按**实例名**独立存储，互不影响。

影响点：
- **删除实例**：直接删除该实例名的凭据，无需检查 provider 引用计数。
- **Sync Models**：只更新当前实例名下的 model_list，其他实例不受影响。
- **API key**：DS1 和 DS2 可以配置不同的 API key，互相独立。

---

## 4. Agent 删除：原子清理

**后端** `DELETE /api/config/agents/{name}` 负责完整清理：

```python
del reg.agents[name]
loader.save_agent_registry(reg)
cred_mgr.delete(name)   # 直接删除实例名对应的 api_key + model_list
```

**前端** `deleteAgent` 只调用一次 `DELETE /api/config/agents/{key}`，
不单独调用 `DELETE /api/config/credentials/{key}`（后端已统一处理）。

---

## 5. Agent 保存顺序（saveAgent）

必须严格按以下顺序调用，否则后续步骤因找不到注册表条目而报 404：

```
1. POST /api/config/agents               → 写入 registry.yaml（实例名为键）
2. POST /api/config/agents/{name}/set-key       → 写入凭据（仅 apiKey 非空时执行）
3. POST /api/config/agents/{name}/sync-models   → 自动同步模型列表（始终执行）
4. POST /api/config/agents/{name}/default-model → 优先用户选择，其次取 sync 结果第一项
```

步骤 3（sync）始终执行，无需用户手动触发。步骤 4 仅在有可用 model 时执行。
模态框中不再有独立的 "Sync Models" 按钮；表格行的 Sync 按钮用于事后手动重同步。

---

## 6. Add 模式限制（前端弹窗）

`agent-edit-key` hidden field 为空 → 处于 Add 模式。

| 操作 | Add 模式行为 |
|------|-------------|
| "Test Connection" 按钮 | 允许（用表单输入值直接调 `/api/config/test-connection`，无需注册表） |
| 模型列表展示 | `selectProvider` 调用 `GET /api/config/providers/{slug}/catalog`，从 OpenRouter 公开 API 实时拉取 |
| `autoSyncModels` | **已删除**，不再存在 |
| `fallback_models.yaml` | **已删除**，静态列表维护成本高且会过时 |

**禁止**在 Add 模式下调用 `ensureAgentExists`——它会用 provider slug 创建幽灵注册条目，
导致表格中出现两个 Agent（实例名 + provider slug 各一条）。

**`selectProvider` 不读取 API Key**：选择 Provider 时 API key 字段必须清空（`value = ""`），
placeholder 恢复为 `sk-...`。不得从任何已存凭据读取 key 回填，避免"全局 key"假象。

---

## 7. renderModelDropdown 传参

```javascript
// ✅ 正确：第一参数用实例名，agentConfig[key] 才能查到 fallback models
renderModelDropdown(instanceKey, cred);

// ❌ 错误：用 provider slug，agentConfig["deepseek"] 在实例名注册表中查不到
renderModelDropdown(providerSlug, cred);
```

Add 模式下 `instanceKey = editKey || providerKey`，此时 `editKey` 为空，
降级为 `providerKey`（fallback section 不显示，属预期行为）。

---

## 8. API Key 显示规范

`list_credentials()` 返回的 `api_key` 字段是 **masked 值**（`sk-1234****5678`），永远不能回填到输入框并直接提交给 `set-key`。

规则：
- Edit 模式打开弹窗时，`modal-apikey` 字段必须保持**空值**，placeholder 显示"API key saved — leave blank to keep"
- `saveAgent()` 的 `set-key` 步骤：仅当字段非空时执行（空 = 用户没改 key = 保留现有）
- 不要在任何地方把 `cred.api_key`（masked）写入输入框

---

## 10. Test Connection 端点选择

| 场景 | 端点 | 说明 |
|------|------|------|
| Add 模式（editKey 为空）或用户输入了新 API key | `POST /api/config/test-connection` | body 携带 `{api_key, base_url}`，不查注册表 |
| Edit 模式且 API key 字段为空（保留已存 key） | `POST /api/config/agents/{name}/test` | 从 CredentialManager 读取真实 key |

新端点 `/api/config/test-connection` 的响应包含 `endpoint` 字段，前端应展示实际请求的 URL 以便排查。

---

## 11. set-key 端点语义

`POST /api/config/agents/{name}/set-key` 接收实例名，直接以**实例名**为键存储凭据：

```python
cred_mgr.save_api_key(name, req.api_key)  # 存储键 = 实例名
```

因此 set-key 要求 registry 中已存在该实例，调用前必须先完成步骤 5.1。

---

## 12. sync-models 端点行为

`POST /api/config/agents/{name}/sync-models`：

- **name 在注册表中**：以**实例名**查凭据（api_key、base_url_override），拉模型，写 `cred_mgr.save_model_list(name)`
- **name 不在注册表中**（bare provider slug）：不查凭据，仅用 preset base_url 拉模型，不写任何持久化数据，不创建注册条目

**Add 模式不调用此端点**：前端改为调用 `GET /api/config/providers/{slug}/catalog`（OpenRouter 公开 API，无需 key），仅拿模型属性数据（model_id、display_name、context_window、model_type），不含 pricing 或 OpenRouter 路由配置。`autoSyncModels()` 函数已从 `config.html` 删除，`fallback_models.yaml` 已删除。

Save 流程中的 sync（步骤 3）使用已注册的实例名路径，从 Provider 原生 `/models` 端点拉取真实列表，是唯一触发持久化同步的时机。
