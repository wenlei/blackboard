from __future__ import annotations

import contextlib
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)


def _read_jsonl(path: Path, limit: int = 0, offset: int = 0) -> list[dict]:
    if not path.exists():
        return []
    lines = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    if offset:
        lines = lines[offset:]
    if limit:
        lines = lines[:limit]
    return lines


def _count_jsonl(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(1 for line in path.read_text().splitlines() if line.strip())


class SystemLogger:
    """Cross-session reader for system-level WARNING/ERROR logs.

    All SessionLogger instances dual-write their warn/error entries here
    so operators can monitor the entire system without opening per-session dirs.
    Each entry carries session_id and timestamp for full traceability.
    """

    SYS_DIR_NAME = "_system"

    def __init__(self, data_dir: str):
        self._dir = Path(data_dir) / self.SYS_DIR_NAME
        self._warnings_path = self._dir / "warnings.jsonl"
        self._errors_path = self._dir / "errors.jsonl"

    def read_warnings(self, limit: int = 0, offset: int = 0) -> list[dict]:
        return _read_jsonl(self._warnings_path, limit, offset)

    def read_errors(self, limit: int = 0, offset: int = 0) -> list[dict]:
        return _read_jsonl(self._errors_path, limit, offset)

    def summary(self) -> dict:
        return {
            "warnings": _count_jsonl(self._warnings_path),
            "errors": _count_jsonl(self._errors_path),
        }


class SessionLogger:
    def __init__(self, session_id: str, data_dir: str = "/data/sessions"):
        self.session_id = session_id
        self._root_dir = Path(data_dir)
        self.dir = self._root_dir / session_id

        # Business data paths (session content)
        self._conversation_path = self.dir / "conversation.log"
        self._messages_path = self.dir / "messages.jsonl"
        self._events_path = self.dir / "events.jsonl"

        # Operational log paths (monitoring / debug) — under logs/ subdir
        self._logs_dir = self.dir / "logs"
        self._agent_calls_path = self._logs_dir / "agent_calls.jsonl"
        self._tool_calls_path = self._logs_dir / "tool_calls.jsonl"
        self._warnings_path = self._logs_dir / "warnings.jsonl"
        self._errors_path = self._logs_dir / "errors.jsonl"

        # System-level paths (shared across all sessions)
        _sys_dir = self._root_dir / SystemLogger.SYS_DIR_NAME
        self._sys_warnings_path = _sys_dir / "warnings.jsonl"
        self._sys_errors_path = _sys_dir / "errors.jsonl"

    def ensure_dir(self):
        self.dir.mkdir(parents=True, exist_ok=True)
        self._logs_dir.mkdir(parents=True, exist_ok=True)

    # ── Original methods ─────────────────────────────────────────────────────

    def log_conversation(self, role: str, content: str):
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        self.dir.mkdir(parents=True, exist_ok=True)
        with open(self._conversation_path, "a") as f:
            f.write(f"[{ts}] [{role}] {content}\n")

    def log_message(self, stream: str, payload: dict):
        self.dir.mkdir(parents=True, exist_ok=True)
        entry = {"timestamp": datetime.now(timezone.utc).isoformat(), "stream": stream, "payload": payload}
        with open(self._messages_path, "a") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def log_event(self, event_type: str, data: dict):
        self.dir.mkdir(parents=True, exist_ok=True)
        entry = {"timestamp": datetime.now(timezone.utc).isoformat(), "type": event_type, "data": data}
        with open(self._events_path, "a") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def read_conversation(self) -> str:
        if self._conversation_path.exists():
            return self._conversation_path.read_text()
        return ""

    def read_messages(self) -> list[dict]:
        return _read_jsonl(self._messages_path)

    def read_events(self) -> list[dict]:
        return _read_jsonl(self._events_path)

    def read_config(self) -> dict:
        p = self.dir / "config.json"
        if p.exists():
            return json.loads(p.read_text())
        return {}

    def read_strategy(self) -> str:
        p = self.dir / "strategy.psc"
        if p.exists():
            return p.read_text()
        return ""

    def write_strategy(self, psc: str):
        self.dir.mkdir(parents=True, exist_ok=True)
        (self.dir / "strategy.psc").write_text(psc)

    # ── Structured log writers ───────────────────────────────────────────────

    def _write_jsonl(self, path: Path, data: dict) -> None:
        """Append one JSON line to path, creating parent directories as needed."""
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a") as f:
            f.write(json.dumps(data, ensure_ascii=False) + "\n")

    def log_agent_call(self, entry: "AgentCallEntry") -> None:  # type: ignore[name-defined]
        self._write_jsonl(self._agent_calls_path, entry.model_dump())

    def log_tool_call(self, entry: "ToolCallEntry") -> None:  # type: ignore[name-defined]
        self._write_jsonl(self._tool_calls_path, entry.model_dump())

    def log_warn(self, component: str, message: str, data: dict | None = None, exc_str: str = "") -> None:
        from blackboard.logger.log_models import LogLevel, WarnErrorEntry
        entry = WarnErrorEntry(
            session_id=self.session_id,
            level=LogLevel.WARNING,
            component=component,
            message=message,
            data=data or {},
            exc_str=exc_str,
        )
        dumped = entry.model_dump()
        self._write_jsonl(self._warnings_path, dumped)
        self._write_jsonl(self._sys_warnings_path, dumped)  # system-level dual-write

    def log_error(self, component: str, message: str, data: dict | None = None, exc_str: str = "") -> None:
        from blackboard.logger.log_models import LogLevel, WarnErrorEntry
        entry = WarnErrorEntry(
            session_id=self.session_id,
            level=LogLevel.ERROR,
            component=component,
            message=message,
            data=data or {},
            exc_str=exc_str,
        )
        dumped = entry.model_dump()
        self._write_jsonl(self._errors_path, dumped)
        self._write_jsonl(self._sys_errors_path, dumped)  # system-level dual-write

    # ── Context managers (auto-timing) ───────────────────────────────────────

    @contextlib.asynccontextmanager
    async def record_agent_call(self, agent_name: str, prompt: str, model: str = ""):
        import asyncio
        from blackboard.logger.log_models import AgentCallEntry, LogLevel
        start = time.monotonic()
        entry = AgentCallEntry(
            session_id=self.session_id,
            component="agent",
            agent_name=agent_name,
            prompt_preview=prompt[:100],
            model=model,
        )
        try:
            yield entry
        except asyncio.CancelledError:
            # CancelledError is BaseException, not Exception — handle separately.
            # A cancellation is not an error; record it as WARNING so the call
            # doesn't silently appear as success=True in agent_calls.jsonl.
            entry.success = False
            entry.error = "cancelled"
            entry.level = LogLevel.WARNING
            raise
        except Exception as e:
            entry.success = False
            entry.error = str(e)
            entry.level = LogLevel.ERROR
            raise
        finally:
            entry.duration_ms = round((time.monotonic() - start) * 1000, 1)
            self._write_jsonl(self._agent_calls_path, entry.model_dump())

    @contextlib.asynccontextmanager
    async def record_tool_call(self, tool_name: str, parameters: dict):
        import asyncio
        from blackboard.logger.log_models import LogLevel, ToolCallEntry
        start = time.monotonic()
        entry = ToolCallEntry(
            session_id=self.session_id,
            component="tool",
            tool_name=tool_name,
            parameters=parameters,
        )
        try:
            yield entry
        except asyncio.CancelledError:
            entry.success = False
            entry.error = "cancelled"
            entry.level = LogLevel.WARNING
            raise
        except Exception as e:
            entry.success = False
            entry.error = str(e)
            entry.level = LogLevel.ERROR
            raise
        finally:
            entry.duration_ms = round((time.monotonic() - start) * 1000, 1)
            self._write_jsonl(self._tool_calls_path, entry.model_dump())

    # ── Readers ──────────────────────────────────────────────────────────────

    def read_agent_calls(self, limit: int = 0, offset: int = 0) -> list[dict]:
        return _read_jsonl(self._agent_calls_path, limit, offset)

    def read_tool_calls(self, limit: int = 0, offset: int = 0) -> list[dict]:
        return _read_jsonl(self._tool_calls_path, limit, offset)

    def read_warnings(self) -> list[dict]:
        return _read_jsonl(self._warnings_path)

    def read_errors(self) -> list[dict]:
        return _read_jsonl(self._errors_path)

    def log_summary(self) -> dict:
        return {
            "session_id": self.session_id,
            "agent_calls": _count_jsonl(self._agent_calls_path),
            "tool_calls": _count_jsonl(self._tool_calls_path),
            "warnings": _count_jsonl(self._warnings_path),
            "errors": _count_jsonl(self._errors_path),
        }
