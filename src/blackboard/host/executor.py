from __future__ import annotations

import logging
import traceback
from typing import TYPE_CHECKING

from blackboard.config.models import OperationDecision
from blackboard.guard.guard import SessionGuard
from blackboard.host.compiler import ASTNode, NodeType
from blackboard.models import Task
from blackboard.mq.redis_streams import MQLayer

if TYPE_CHECKING:
    from blackboard.logger.session_logger import SessionLogger

logger = logging.getLogger(__name__)


class Executor:
    def __init__(
        self,
        mq: MQLayer,
        guard: SessionGuard,
        session_id: str,
        session_logger: SessionLogger | None = None,
    ):
        self.mq = mq
        self.guard = guard
        self.session_id = session_id
        self.session_logger = session_logger

    async def execute(self, ast: ASTNode, agent_registry) -> list[str]:
        results: list[str] = []
        await self._execute_node(ast, agent_registry, results)
        return results

    async def _execute_node(self, node: ASTNode, agent_registry, results: list[str]):
        if node.node_type == NodeType.AGENT:
            result = await self._dispatch_agent(node, agent_registry, prior_results=results)
            results.append(result)
            if node.next_node:
                await self._execute_node(node.next_node, agent_registry, results)

        elif node.node_type == NodeType.BRANCH:
            if node.condition:
                condition_met = self._evaluate_condition(node.condition, results)
                if condition_met and node.next_true:
                    await self._execute_node(node.next_true, agent_registry, results)
                elif node.next_false:
                    await self._execute_node(node.next_false, agent_registry, results)

        elif node.node_type == NodeType.RETURN:
            logger.info("Executor: strategy complete for session %s", self.session_id)
            return

    async def _dispatch_agent(self, node: ASTNode, agent_registry, prior_results: list[str] | None = None) -> str:
        agent_name = node.agent.lower()
        operation = self._infer_operation(node.action)

        decision = self.guard.check(operation, agent_name)
        if decision == OperationDecision.DENIED:
            logger.warning("Executor: Guard denied %s for %s", operation, agent_name)
            if self.session_logger:
                self.session_logger.log_warn(
                    "executor._dispatch_agent",
                    f"Guard denied operation '{operation}' for agent '{agent_name}'",
                    {"operation": operation, "agent": agent_name, "action": node.action},
                )
            return f"[DENIED] {node.action}"

        if decision == OperationDecision.REQUIRE_APPROVAL:
            await self.mq.publish(
                self.session_id, "outbox",
                {"type": "approval_request", "operation": operation, "agent": agent_name, "action": node.action},
                target_channel="web_ui",
            )
            approvals = await self.mq.consume(
                self.session_id, "approvals", "approvals", "executor", count=1, block_ms=300000,
            )
            if approvals:
                data = approvals[0]["data"]["payload"]
                if data.get("decision") == "approved":
                    self.guard.approve(data.get("approval_id", ""))
                else:
                    if self.session_logger:
                        self.session_logger.log_warn(
                            "executor._dispatch_agent",
                            f"Operation '{operation}' rejected by user for agent '{agent_name}'",
                            {"operation": operation, "agent": agent_name},
                        )
                    return f"[REJECTED] {node.action}"
            else:
                if self.session_logger:
                    self.session_logger.log_warn(
                        "executor._dispatch_agent",
                        f"Approval timeout for operation '{operation}' on agent '{agent_name}'",
                        {"operation": operation, "agent": agent_name},
                    )
                return f"[TIMEOUT] {node.action}"

        context: str | None = None
        if prior_results:
            context = "\n\n".join(
                f"[Step {i+1}] {r}" for i, r in enumerate(prior_results) if r
            )

        task = Task(
            session_id=self.session_id,
            target_agent=agent_name,
            role=node.agent,
            prompt=node.action,
            operation_type=operation,
            context=context,
        )

        await self.mq.publish(
            self.session_id, "dispatched",
            {"task_id": task.id, "prompt": task.prompt, "role": task.role},
        )

        try:
            agent = agent_registry.get(agent_name)
        except Exception as e:
            logger.error("Agent not found: %s — %s", agent_name, e)
            if self.session_logger:
                self.session_logger.log_error(
                    "executor._dispatch_agent",
                    f"Agent not found: {agent_name}",
                    {"agent": agent_name},
                    traceback.format_exc(),
                )
            return f"[Agent not found: {agent_name}]"

        if self.session_logger:
            async with self.session_logger.record_agent_call(agent_name, node.action, agent.model) as rec:
                result = await agent.execute(task)
                rec.success = result.success
                rec.response_preview = (result.content or "")[:200]
                rec.error = result.error or ""
        else:
            result = await agent.execute(task)

        await self.mq.publish(
            self.session_id, "results",
            {
                "task_id": task.id,
                "content": result.content,
                "agent_name": agent_name,
                "success": result.success,
                "error": result.error or "",
            },
        )

        if not result.success:
            logger.warning("Agent %s failed: %s", agent_name, result.error)
            if self.session_logger:
                self.session_logger.log_warn(
                    "executor._dispatch_agent",
                    f"Agent {agent_name} returned failure: {result.error}",
                    {"agent": agent_name, "operation": operation, "error": result.error},
                )
            await self.mq.publish(
                self.session_id, "outbox",
                {"type": "progress", "message": f"[{agent_name}] 执行失败: {result.error}"},
                target_channel="web_ui",
            )
            return f"[Agent error: {result.error}]"

        content = result.content or "[Agent returned empty response]"
        await self.mq.publish(
            self.session_id, "outbox",
            {"type": "reply", "content": content, "agent_name": agent_name},
            target_channel="web_ui",
        )
        return content

    def _infer_operation(self, action: str) -> str:
        action_lower = action.lower()
        if any(kw in action_lower for kw in ["写", "write", "生成", "generate", "create", "build"]):
            return "chat"
        if any(kw in action_lower for kw in ["分析", "analyze", "审查", "review", "检查", "check", "解释", "explain"]):
            return "analyze"
        if any(kw in action_lower for kw in ["搜索", "search", "查找", "find"]):
            return "search"
        if any(kw in action_lower for kw in ["执行", "execute", "运行", "run"]):
            return "execute_code"
        return "chat"

    def _evaluate_condition(self, condition: str, results: list[str]) -> bool:
        cond_lower = condition.lower()
        if "通过" in cond_lower or "pass" in cond_lower or "成功" in cond_lower:
            return True
        if "失败" in cond_lower or "不通过" in cond_lower or "fail" in cond_lower:
            return False
        return True
