# Phase 2 Test Samples

> 覆盖 Phase 2 全部模块：Agent Adapters / Session Guard / Host (Compiler+Executor+Strategy) / Session Manager

---

## 1. Agent Adapters — BaseAgent + 3 LLM 适配器

### 1.1 DeepSeek Adapter 构造
| 字段 | 值 |
|------|-----|
| **操作** | `DeepSeekAdapter(name="my-ds", api_key="sk-test", model="deepseek-r1")` |
| **预期** | 实例创建成功，name="my-ds", provider="deepseek", model="deepseek-r1" |

### 1.2 Claude Adapter 构造
| 字段 | 值 |
|------|-----|
| **操作** | `ClaudeAdapter(name="my-claude", api_key="sk-ant-test", model="claude-opus-4-20250514")` |
| **预期** | 实例创建成功，provider="anthropic" |

### 1.3 OpenAI Adapter 构造
| 字段 | 值 |
|------|-----|
| **操作** | `OpenAIAdapter(name="my-gpt", api_key="sk-openai-test", model="gpt-4o-mini")` |
| **预期** | 实例创建成功，provider="openai" |

### 1.4 health_check — 有 API Key
| 字段 | 值 |
|------|-----|
| **操作** | `adapter.health_check()` — api_key 非空 |
| **预期** | 返回 True |

### 1.5 health_check — 无 API Key
| 字段 | 值 |
|------|-----|
| **操作** | `adapter.health_check()` — api_key 为空串 |
| **预期** | 返回 False |

### 1.6 Agent Registry 创建/查询/移除
| 字段 | 值 |
|------|-----|
| **操作** | `reg.create("ds", "deepseek")` → `reg.get("ds")` |
| **预期** | 返回 DeepSeekAdapter 实例，name="ds", provider="deepseek" |

### 1.7 多 Agent 注册
| 字段 | 值 |
|------|-----|
| **操作** | 注册 deepseek + claude + openai 三个 Agent |
| **预期** | `reg.list()` 返回 3 个 Agent |

### 1.8 按 provider 筛选
| 字段 | 值 |
|------|-----|
| **操作** | 注册 ds1, ds2 (deepseek) + cl (claude) → `reg.list_by_provider("deepseek")` |
| **预期** | 返回 2 个 deepseek Agent |

### 1.9 未知 Provider 拒绝
| 字段 | 值 |
|------|-----|
| **操作** | `reg.create("x", "nonexistent")` |
| **预期** | 抛出 AgentRegistryError |

### 1.10 Agent 移除
| 字段 | 值 |
|------|-----|
| **操作** | 注册后 `reg.remove("agent")` |
| **预期** | `reg.list()` 不包含该 Agent |

### 1.11 Memory 写入与读取
| 字段 | 值 |
|------|-----|
| **操作** | `adapter.save_memory(path, "content1")` → `adapter.save_memory(path, "content2")` → `adapter.load_memory(path)` |
| **预期** | 读回内容包含 "content1" 和 "content2" |

### 1.12 Memory 读取不存在文件
| 字段 | 值 |
|------|-----|
| **操作** | `adapter.load_memory("/nonexistent/path.md")` |
| **预期** | 返回 None |

### 1.13 Adapter Provider 映射
| 字段 | 值 |
|------|-----|
| **操作** | 检查 `ADAPTER_MAP` 字典 |
| **预期** | "deepseek"→DeepSeekAdapter, "claude"→ClaudeAdapter, "openai"→OpenAIAdapter |

---

## 2. Session Guard — 权限校验与审批

### 2.1 Whitelist — allowed 放行
| 字段 | 值 |
|------|-----|
| **操作** | `guard.check("chat")` — whitelist 模式，chat=allowed |
| **预期** | 返回 OperationDecision.ALLOWED |

### 2.2 Whitelist — 未声明 denied
| 字段 | 值 |
|------|-----|
| **操作** | `guard.check("unknown_op")` |
| **预期** | 返回 OperationDecision.DENIED |

### 2.3 Approval First — 默认需审批
| 字段 | 值 |
|------|-----|
| **操作** | `guard.check("execute_code")` — approval_first 模式 |
| **预期** | 返回 OperationDecision.REQUIRE_APPROVAL，_pending_approvals 中有记录 |

### 2.4 Open — 仅 denied 拦截
| 字段 | 值 |
|------|-----|
| **操作** | open 模式，file_delete=denied |
| **预期** | chat→ALLOWED, file_delete→DENIED |

### 2.5 Agent 级别覆写
| 字段 | 值 |
|------|-----|
| **操作** | whitelist 模式，file_write=require_approval，per_agent_overrides: {programmer: {file_write: allowed}} |
| **预期** | `guard.check("file_write")` → REQUIRE_APPROVAL, `guard.check("file_write","programmer")` → ALLOWED |

### 2.6 多 Agent 不同覆写
| 字段 | 值 |
|------|-----|
| **操作** | programmer→file_write:allowed, reviewer→file_write:denied |
| **预期** | programmer→ALLOWED, reviewer→DENIED, 无 agent→REQUIRE_APPROVAL |

### 2.7 审批通过/拒绝
| 字段 | 值 |
|------|-----|
| **操作** | check → approve(approval_id) / reject(approval_id) |
| **预期** | 通过/拒绝后 _pending_approvals 为空 |

### 2.8 审批不存在的 ID
| 字段 | 值 |
|------|-----|
| **操作** | `guard.approve("fake-id")` / `guard.reject("fake-id")` |
| **预期** | 返回 False |

### 2.9 审批超时检测
| 字段 | 值 |
|------|-----|
| **操作** | 设置 approval_timeout=1 秒 → check → sleep 1.1s → check_timeouts() |
| **预期** | 返回过期审批 ID 列表，_pending_approvals 清空 |

### 2.10 运行时改模式/权限
| 字段 | 值 |
|------|-----|
| **操作** | `guard.update_mode(OPEN)` / `guard.update_operations({...})` |
| **预期** | 后续 check 使用新规则 |

### 2.11 超时后 approve/reject 失败
| 字段 | 值 |
|------|-----|
| **操作** | check → 超时 → check_timeouts → approve |
| **预期** | approve 返回 False（审批已过期） |

### 2.12 重复同一操作需新审批
| 字段 | 值 |
|------|-----|
| **操作** | check("chat") → approve → check("chat") 第二次 |
| **预期** | 第二次仍需审批，_pending_approvals 有新记录 |

---

## 3. Host — PSC 编译/执行/策略

### 3.1 编译 Agent 节点
| 字段 | 值 |
|------|-----|
| **输入** | `AGENT: 写代码` |
| **操作** | `compile_psc(psc)` |
| **预期** | AST node_type=AGENT, agent="AGENT", action="写代码" |

### 3.2 编译多 Agent 链
| 字段 | 值 |
|------|-----|
| **输入** | `ARCHITECT: 设计\nPROGRAMMER: 实现` |
| **预期** | ARCHITECT.next_node = PROGRAMMER |

### 3.3 编译 IF/ELSE 分支
| 字段 | 值 |
|------|-----|
| **输入** | 完整代码审查 PSC（含 IF 通过 → RETURN / ELSE → PROGRAMMER → REVIEWER） |
| **预期** | BRANCH.next_true = RETURN, BRANCH.next_false = PROGRAMMER → REVIEWER |

### 3.4 策略生成 — 模板匹配
| 字段 | 值 |
|------|-----|
| **输入** | "帮我审查一下这段代码" |
| **预期** | 匹配 code_review 模板，生成含 ARCHITECT/PROGRAMMER/REVIEWER 的 PSC |

### 3.5 策略生成 — 关键词匹配
| 字段 | 值 |
|------|-----|
| **输入** | "写一个排序函数" |
| **预期** | 匹配 write_code 模板（协作编码） |

### 3.6 策略生成 — 通用回退
| 字段 | 值 |
|------|-----|
| **输入** | "今天天气怎么样" |
| **预期** | 匹配 general 通用模板 |

### 3.7 操作类型推断
| 字段 | 值 |
|------|-----|
| **输入** | 写→chat, 生成→chat, 分析→analyze, 搜索→search, 执行→execute_code, 你好→chat |
| **预期** | `_infer_operation` 返回正确的操作类型 |

### 3.8 条件求值
| 字段 | 值 |
|------|-----|
| **输入** | "通过"/"pass"/"成功"→True, "失败"/"失败"/"不通过"/"fail"→False, 未知→True |
| **预期** | `_evaluate_condition` 返回正确的布尔值 |

### 3.9 Executor 被 Guard 拒绝
| 字段 | 值 |
|------|-----|
| **操作** | WHITELIST 模式，无任何 allowed 操作 → execute(code_review PSC) |
| **预期** | 所有 Agent 节点返回 "[DENIED] ..." |

### 3.10 Executor 审批超时
| 字段 | 值 |
|------|-----|
| **操作** | APPROVAL_FIRST 模式 → execute（MQ 不可用导致审批超时 300s 但实际走 timeout 路径） |
| **预期** | 返回 "[TIMEOUT] ..." |

---

## 4. Session Manager — 生命周期

### 4.1 创建 Session
| 字段 | 值 |
|------|-----|
| **操作** | `session_mgr.create("s1", [{"name":"dp","provider":"deepseek","role":"程序员"}])` |
| **预期** | 初始化 Stream 组 → 创建 SessionGuard → 创建 Host → 启动 Host.run() → 落盘 config.json |

### 4.2 创建重复 Session 拒绝
| 字段 | 值 |
|------|-----|
| **操作** | 同一 session_id 重复 create |
| **预期** | 抛出 ValueError |

### 4.3 暂停/恢复
| 字段 | 值 |
|------|-----|
| **操作** | `pause("s1")` → `resume("s1")` |
| **预期** | 状态标记 flipped（active↔paused） |

### 4.4 关闭 Session
| 字段 | 值 |
|------|-----|
| **操作** | `close("s1")` |
| **预期** | 销毁 Stream 组，从 _sessions 移除 |

### 4.5 动态增减 Agent
| 字段 | 值 |
|------|-----|
| **操作** | `add_agent("s1", "cl","claude","审查者")` → `remove_agent("s1","cl")` |
| **预期** | agent_roles 更新，Agent Registry 同步 |

### 4.6 操作不存在的 Session
| 字段 | 值 |
|------|-----|
| **操作** | `pause("ghost")` / `close("ghost")` |
| **预期** | 抛出 ValueError |

### 4.7 config.json 内容校验
| 字段 | 值 |
|------|-----|
| **操作** | 创建含 2 个 Agent 的 session → 检查 config.json |
| **预期** | agents 数组含 2 项，permissions.mode="whitelist" |

---

## 测试文件映射

| 测试文件 | 覆盖模块 | 用例数 |
|----------|----------|--------|
| `tests/phase2/test_agent_adapter.py` | Agent Adapters (DeepSeek/Claude/OpenAI) | 24 |
| `tests/phase2/test_guard_advanced.py` | Session Guard (审批超时/边界) | 15 |
| `tests/phase2/test_executor_flow.py` | Executor (操作推断/条件求值/Guard 集成) | 12 |
| `tests/phase2/test_session_manager.py` | Session Manager (生命周期) | 8 |
| `tests/test_agents.py` | Agent Registry (基础) | 7 |
| `tests/test_guard.py` | Session Guard (基础) | 10 |
| `tests/test_host.py` | Compiler + StrategyGenerator | 9 |

**总计**: 85 个 Phase 2 测试用例
