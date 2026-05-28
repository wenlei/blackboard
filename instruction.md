# Blackboard — 文档导航

> 本文件是项目文档体系的入口，说明每个文档的用途和使用时机。

## 文档地图

| 文件 | 用途 | 更新频率 |
|------|------|----------|
| instruction.md | 文档体系说明（本文件） | 文档结构变更时 |
| dev/roadmap.md | 开发路线图（5 阶段 + 进度） | 每阶段完成时 |
| dev/background.md | 项目背景、目标、约束 | 项目定义变更时 |
| dev/architecture.md | 系统架构与组件关系 | 架构调整时 |
| dev/rule.md | 开发规范与 AI 协作规则（全局） | 规范变更时 |
| dev/rules/ | 功能块规则（各模块约定，见 README） | 修改对应模块时 |
| dev/log.md | 每日变更记录 | 每次提交后 |
| dev/todo.md | 当前任务 Backlog | 每次计划/完成任务时 |
| dev/decisions.md | 技术决策记录（ADR） | 做出重要决策时 |
| dev/bugs.md | 已发现 bug 记录（含修复状态） | 发现或修复 bug 时 |
| dev/terms.md | 项目术语表 | 引入新术语时 |
| dev/test-sample/ | 测试计划/用例文档 | 新增模块/功能时 |

## 使用原则

- 开始新功能前：先看 `todo.md` 和 `architecture.md`
- 做技术选型时：先在 `decisions.md` 记录候选方案，决策后更新结论
- 每次开发结束：更新 `log.md`，同步 `todo.md` 状态
- 发现架构变化：立即更新 `architecture.md`，同步在 `decisions.md` 写明原因
- 引入新缩写或领域术语：在 `terms.md` 补充定义
- 开发新功能前：查看 `test-sample/` 下的对应测试用例
- 修改某功能块前：先读 `dev/rules/<module>.md`，遵守其中的键名语义和调用顺序约定

## 文档同步指令

在 Claude Code 或支持 AGENTS.md 的工具中，输入以下指令触发自动文档同步：

| 指令 | 动作 |
|------|------|
| `/sync-docs` | 扫描文档健康度 → 更新 log.md → 同步 todo.md → 补全建议 → 输出报告 |

详细执行逻辑见项目根目录的 `AGENTS.md`。
