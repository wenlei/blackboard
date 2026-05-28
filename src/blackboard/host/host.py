from __future__ import annotations

import asyncio
import json
import logging
import re
import traceback
from pathlib import Path
from typing import TYPE_CHECKING

from blackboard.agents.registry import AgentRegistry
from blackboard.guard.guard import SessionGuard
from blackboard.host.compiler import compile_psc
from blackboard.host.executor import Executor
from blackboard.host.strategy import StrategyGenerator
from blackboard.models import Task
from blackboard.mq.redis_streams import MQLayer

if TYPE_CHECKING:
    from blackboard.logger.session_logger import SessionLogger

logger = logging.getLogger(__name__)


class Host:
    def __init__(
        self,
        session_id: str,
        mq: MQLayer,
        guard: SessionGuard,
        agent_registry: AgentRegistry,
        strategy_generator: StrategyGenerator,
        data_dir: str = "/data/sessions",
        default_agent: str | None = None,
        session_logger: SessionLogger | None = None,
    ):
        self.session_id = session_id
        self.mq = mq
        self.guard = guard
        self.agent_registry = agent_registry
        self.strategy_generator = strategy_generator
        self.data_dir = Path(data_dir) / session_id
        self.session_logger = session_logger
        self.executor = Executor(mq, guard, session_id, session_logger=session_logger)
        self._psc_path = self.data_dir / "strategy.psc"
        self._stop_event = asyncio.Event()
        self._paused = False
        self.default_agent = default_agent
        self._current_task: asyncio.Task | None = None  # currently running agent subtask

    def pause(self):
        self._paused = True

    def resume(self):
        self._paused = False

    def stop(self):
        self._stop_event.set()

    def cancel_tasks(self):
        """Cancel the currently executing agent call without stopping the host loop."""
        if self._current_task and not self._current_task.done():
            self._current_task.cancel()

    async def run(self, agent_roles: dict[str, str]):
        logger.info("Host started for session %s (default_agent=%s)", self.session_id, self.default_agent)

        while not self._stop_event.is_set():
            if self._paused:
                await asyncio.sleep(1)
                continue

            try:
                msgs = await self.mq.consume(
                    self.session_id, "inbox", "inbox", f"host-{self.session_id}", count=1, block_ms=5000,
                )
            except asyncio.CancelledError:
                raise  # propagate stop() cancellation
            except Exception as e:
                logger.warning(
                    "Host consume error for session %s (%s) — retrying in 3s",
                    self.session_id, e,
                )
                await asyncio.sleep(3)
                continue

            if not msgs:
                continue

            for msg in msgs:
                payload = msg["data"]["payload"]
                msg_type = payload.get("type", "")
                user_input = payload.get("content", payload.get("text", "")).strip()
                await self.mq.ack(self.session_id, "inbox", "inbox", [msg["id"]])

                if not user_input:
                    continue

                # ── Execute command: run the pre-saved strategy PSC ──────────
                if msg_type == "command" and user_input.lower() == "execute":
                    await self._run_as_task(self._run_strategy())
                    continue

                if msg_type == "command":
                    continue  # ignore other unknown commands

                # ── /template <id>: set strategy from template, notify UI ───
                explicit_tmpl = self._parse_template_request(user_input)
                if explicit_tmpl:
                    await self._set_strategy_from_template(explicit_tmpl, agent_roles)
                    continue

                # ── @AgentName routing ──────────────────────────────────────
                multi = self._parse_multi_mention(user_input)
                if multi:
                    await self._run_as_task(self._multi_agent_chat(multi))
                    continue

                mention = self._parse_mention(user_input)
                if mention:
                    agent_name, clean_text = mention
                    await self._run_as_task(self._direct_chat(agent_name, clean_text))
                    continue

                # ── Default: direct chat with 主持人 ──────────────────────
                target = self.default_agent or (list(agent_roles.values())[0] if agent_roles else None)
                if target:
                    logger.info("Direct chat → %s: %r", target, user_input[:80])
                    await self._run_as_task(self._direct_chat(target, user_input))
                else:
                    await self.mq.publish(
                        self.session_id, "outbox",
                        {"type": "progress", "message": "No agent available. Add an agent to this session first."},
                        target_channel="web_ui",
                    )

    # ── Cancellable subtask runner ───────────────────────────────────────────

    async def _run_as_task(self, coro) -> None:
        """Wrap a coroutine in a Task so cancel_tasks() can interrupt it without
        killing the entire host loop."""
        self._current_task = asyncio.create_task(coro)
        try:
            await self._current_task
        except asyncio.CancelledError:
            pass  # UI already notified inside the coro
        finally:
            self._current_task = None

    # ── Direct chat ─────────────────────────────────────────────────────────

    async def _direct_chat(self, agent_name: str, text: str):
        try:
            agent = self.agent_registry.get(agent_name)
        except Exception:
            await self.mq.publish(
                self.session_id, "outbox",
                {"type": "progress", "message": f"Agent '{agent_name}' not found in this session."},
                target_channel="web_ui",
            )
            return

        task = Task(
            session_id=self.session_id,
            target_agent=agent_name,
            role=agent_name,
            prompt=text,
            operation_type="chat",
        )
        try:
            if self.session_logger:
                async with self.session_logger.record_agent_call(agent_name, text, agent.model) as rec:
                    result = await agent.execute(task)
                    rec.success = result.success
                    rec.response_preview = (result.content or "")[:200]
                    rec.error = result.error or ""
            else:
                result = await agent.execute(task)

            if not result.success:
                err = result.error or "unknown error"
                logger.warning("Agent %s failed: %s", agent_name, err)
                if self.session_logger:
                    self.session_logger.log_warn(
                        "host._direct_chat",
                        f"Agent {agent_name} returned failure: {err}",
                        {"agent": agent_name, "error": err},
                    )
                await self.mq.publish(
                    self.session_id, "outbox",
                    {"type": "progress", "message": f"[{agent_name}] ⚠ {err}"},
                    target_channel="web_ui",
                )
                return
            content = result.content or "(no response)"
            await self.mq.publish(
                self.session_id, "outbox",
                {"type": "reply", "content": content, "agent_name": agent_name},
                target_channel="web_ui",
            )
            self._log_reply(agent_name, content)
        except asyncio.CancelledError:
            # Notify UI then re-raise so _run_as_task knows the task was cancelled
            asyncio.create_task(self.mq.publish(
                self.session_id, "outbox",
                {"type": "progress", "message": f"⛔ [{agent_name}] 已停止"},
                target_channel="web_ui",
            ))
            raise
        except Exception as e:
            logger.exception("Direct chat error with %s in session %s", agent_name, self.session_id)
            if self.session_logger:
                self.session_logger.log_error(
                    "host._direct_chat",
                    f"Unhandled error calling agent {agent_name}: {e}",
                    {"agent": agent_name},
                    traceback.format_exc(),
                )
            await self.mq.publish(
                self.session_id, "outbox",
                {"type": "progress", "message": f"[{agent_name}] 出错: {e}"},
                target_channel="web_ui",
            )

    # ── Multi-agent sequential dispatch ─────────────────────────────────────

    def _parse_multi_mention(self, text: str) -> list[tuple[str, str]] | None:
        """Parse multiple @AgentName segments from a message.

        E.g. "@h1 summarise this  @t1 then translate" →
             [("h1", "summarise this"), ("t1", "then translate")]

        Returns None (not a list!) when there is fewer than 2 @mentions,
        so single-mention flow stays on the fast path.
        """
        pattern = re.compile(r"@(\w+)")
        matches = list(pattern.finditer(text))
        if len(matches) < 2:
            return None
        segments: list[tuple[str, str]] = []
        for i, m in enumerate(matches):
            agent_name = m.group(1).lower()
            start = m.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            task_text = text[start:end].strip()
            if not task_text:
                task_text = text
            segments.append((agent_name, task_text))
        return segments

    async def _multi_agent_chat(self, segments: list[tuple[str, str]]):
        """Execute a chain of @mentions sequentially, each agent receiving
        the accumulated replies of the previous agents as context."""
        context_parts: list[tuple[str, str]] = []

        for agent_name, task_text in segments:
            try:
                agent = self.agent_registry.get(agent_name)
            except Exception:
                await self.mq.publish(
                    self.session_id, "outbox",
                    {"type": "progress", "message": f"Agent '{agent_name}' not found — skipping."},
                    target_channel="web_ui",
                )
                continue

            context: str | None = None
            if context_parts:
                context = "\n\n".join(f"[{n}]: {r}" for n, r in context_parts)

            task = Task(
                session_id=self.session_id,
                target_agent=agent_name,
                role=agent_name,
                prompt=task_text,
                context=context,
                operation_type="chat",
            )
            try:
                if self.session_logger:
                    async with self.session_logger.record_agent_call(agent_name, task_text, agent.model) as rec:
                        result = await agent.execute(task)
                        rec.success = result.success
                        rec.response_preview = (result.content or "")[:200]
                        rec.error = result.error or ""
                else:
                    result = await agent.execute(task)

                if not result.success:
                    err = result.error or "unknown error"
                    logger.warning("Agent %s failed (multi-chat): %s", agent_name, err)
                    if self.session_logger:
                        self.session_logger.log_warn(
                            "host._multi_agent_chat",
                            f"Agent {agent_name} returned failure: {err}",
                            {"agent": agent_name, "error": err},
                        )
                    await self.mq.publish(
                        self.session_id, "outbox",
                        {"type": "progress", "message": f"[{agent_name}] ⚠ {err}"},
                        target_channel="web_ui",
                    )
                    context_parts.append((agent_name, f"(error: {err})"))
                    continue

                content = result.content or "(no response)"
                await self.mq.publish(
                    self.session_id, "outbox",
                    {"type": "reply", "content": content, "agent_name": agent_name},
                    target_channel="web_ui",
                )
                self._log_reply(agent_name, content)
                context_parts.append((agent_name, content))

            except asyncio.CancelledError:
                asyncio.create_task(self.mq.publish(
                    self.session_id, "outbox",
                    {"type": "progress", "message": f"⛔ [{agent_name}] 已停止"},
                    target_channel="web_ui",
                ))
                raise
            except Exception as e:
                logger.exception("Multi-chat error with %s in session %s", agent_name, self.session_id)
                if self.session_logger:
                    self.session_logger.log_error(
                        "host._multi_agent_chat",
                        f"Unhandled error calling agent {agent_name}: {e}",
                        {"agent": agent_name},
                        traceback.format_exc(),
                    )
                await self.mq.publish(
                    self.session_id, "outbox",
                    {"type": "progress", "message": f"[{agent_name}] 出错: {e}"},
                    target_channel="web_ui",
                )
                context_parts.append((agent_name, f"(error: {e})"))

    # ── Strategy execution ───────────────────────────────────────────────────

    async def _run_strategy(self):
        if not self._psc_path.exists():
            await self.mq.publish(
                self.session_id, "outbox",
                {"type": "progress", "message": "没有预设策略。请先在侧边栏选择模板并点击 Apply Strategy。"},
                target_channel="web_ui",
            )
            return
        psc = self._psc_path.read_text().strip()
        if not psc:
            await self.mq.publish(
                self.session_id, "outbox",
                {"type": "progress", "message": "策略为空，请先在侧边栏设置策略。"},
                target_channel="web_ui",
            )
            return
        try:
            ast = compile_psc(psc)
            await self.executor.execute(ast, self.agent_registry)
            await self.mq.publish(
                self.session_id, "outbox",
                {"type": "progress", "message": "✅ 所有任务完成"},
                target_channel="web_ui",
            )
        except Exception as e:
            logger.exception("Executor error in session %s", self.session_id)
            if self.session_logger:
                self.session_logger.log_error(
                    "host._run_strategy",
                    f"Strategy execution failed: {e}",
                    {},
                    traceback.format_exc(),
                )
            await self.mq.publish(
                self.session_id, "outbox",
                {"type": "progress", "message": f"执行出错: {e}"},
                target_channel="web_ui",
            )

    async def _set_strategy_from_template(self, template_id: str, agent_roles: dict[str, str]):
        psc = self.strategy_generator.generate_from_template_id(template_id, agent_roles)
        if not psc:
            await self.mq.publish(
                self.session_id, "outbox",
                {"type": "progress", "message": f"未找到模板 '{template_id}'，可用模板: code_review, write_code, analyze, general"},
                target_channel="web_ui",
            )
            return
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._psc_path.write_text(psc)
        (self.data_dir / "strategy.json").write_text(json.dumps({"source": psc, "compiled_at": ""}, ensure_ascii=False, indent=2))
        await self.mq.publish(
            self.session_id, "outbox",
            {"type": "strategy_ready", "psc": psc, "message": f"已加载模板 '{template_id}'，点击 Execute 执行"},
            target_channel="web_ui",
        )

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _log_reply(self, agent_name: str, content: str):
        if self.session_logger:
            self.session_logger.log_conversation(agent_name, content)
            return
        try:
            from datetime import datetime, timezone
            ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            log_path = self.data_dir / "conversation.log"
            self.data_dir.mkdir(parents=True, exist_ok=True)
            with log_path.open("a") as f:
                f.write(f"[{ts}] [{agent_name}] {content}\n")
        except Exception:
            pass

    def _parse_mention(self, text: str) -> tuple[str, str] | None:
        if not text.startswith("@"):
            return None
        parts = text.split(None, 1)
        agent_name = parts[0][1:]
        remaining = parts[1].strip() if len(parts) > 1 else ""
        if not agent_name:
            return None
        return (agent_name.lower(), remaining)

    def _parse_template_request(self, text: str) -> str | None:
        if text.startswith("/template "):
            return text[len("/template "):].strip()
        lower = text.lower()
        for prefix in ("用模板:", "用模板：", "template:", "template："):
            if lower.startswith(prefix):
                return text[len(prefix):].strip()
        return None

    async def _wait_confirm(self):
        await self.mq.publish(
            self.session_id, "outbox",
            {"type": "progress", "message": "Waiting for strategy confirmation..."},
            target_channel="web_ui",
        )
        for i in range(60):
            msgs = await self.mq.consume(
                self.session_id, "inbox", "inbox", f"host-confirm-{self.session_id}", count=1, block_ms=5000,
            )
            if msgs:
                payload = msgs[0]["data"]["payload"]
                msg_type = payload.get("type", "")
                text = payload.get("content", payload.get("text", "")).strip().lower()
                await self.mq.ack(self.session_id, "inbox", "inbox", [msgs[0]["id"]])
                if msg_type == "command" and text == "execute":
                    return
                if text in ("确认", "yes", "ok", "执行", "y", "execute", "confirm"):
                    return
                if text in ("取消", "no", "cancel", "n"):
                    raise RuntimeError("Strategy cancelled by user")
            if i > 0 and i % 10 == 0:
                await self.mq.publish(
                    self.session_id, "outbox",
                    {"type": "progress", "message": f"Still waiting for confirmation... ({i * 5}s elapsed)"},
                    target_channel="web_ui",
                )
        raise RuntimeError("Strategy confirmation timeout")
