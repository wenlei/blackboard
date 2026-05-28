"""Tests for the structured logging feature."""

from __future__ import annotations

import pytest

from blackboard.logger.log_models import AgentCallEntry, LogLevel, ToolCallEntry
from blackboard.logger.session_logger import SessionLogger, SystemLogger


@pytest.fixture
def sl(tmp_path):
    return SessionLogger("test-session", str(tmp_path))


# ── log_agent_call ────────────────────────────────────────────────────────────

def test_log_agent_call_written(sl):
    entry = AgentCallEntry(
        session_id="test-session",
        component="test",
        agent_name="h1",
        prompt_preview="hello",
        response_preview="world",
        success=True,
        duration_ms=42.0,
    )
    sl.log_agent_call(entry)
    calls = sl.read_agent_calls()
    assert len(calls) == 1
    assert calls[0]["agent_name"] == "h1"
    assert calls[0]["success"] is True
    assert calls[0]["duration_ms"] == 42.0


def test_log_agent_call_multiple(sl):
    for i in range(3):
        sl.log_agent_call(AgentCallEntry(
            session_id="test-session",
            agent_name=f"agent{i}",
            prompt_preview=f"prompt{i}",
        ))
    assert len(sl.read_agent_calls()) == 3


def test_read_agent_calls_limit_offset(sl):
    for i in range(5):
        sl.log_agent_call(AgentCallEntry(session_id="s", agent_name=f"a{i}", prompt_preview="p"))
    page = sl.read_agent_calls(limit=2, offset=1)
    assert len(page) == 2
    assert page[0]["agent_name"] == "a1"


# ── log_tool_call ─────────────────────────────────────────────────────────────

def test_log_tool_call_written(sl):
    entry = ToolCallEntry(
        session_id="test-session",
        component="test",
        tool_name="filesystem.read",
        parameters={"path": "test.txt"},
        result_preview="file content here",
        success=True,
        duration_ms=10.0,
    )
    sl.log_tool_call(entry)
    calls = sl.read_tool_calls()
    assert len(calls) == 1
    assert calls[0]["tool_name"] == "filesystem.read"
    assert calls[0]["parameters"] == {"path": "test.txt"}


# ── log_warn / log_error ──────────────────────────────────────────────────────

def test_log_warn(sl):
    sl.log_warn("executor", "Guard denied", {"op": "execute_code"})
    warnings = sl.read_warnings()
    assert len(warnings) == 1
    assert warnings[0]["level"] == LogLevel.WARNING
    assert warnings[0]["message"] == "Guard denied"
    assert warnings[0]["data"] == {"op": "execute_code"}
    assert warnings[0]["component"] == "executor"


def test_log_error_with_traceback(sl):
    sl.log_error("host", "Agent crashed", {"agent": "h1"}, "Traceback (most recent call last): ...")
    errors = sl.read_errors()
    assert len(errors) == 1
    assert errors[0]["level"] == LogLevel.ERROR
    assert errors[0]["exc_str"].startswith("Traceback")


def test_log_warn_empty_data(sl):
    sl.log_warn("comp", "something happened")
    assert sl.read_warnings()[0]["data"] == {}


# ── record_agent_call context manager ────────────────────────────────────────

@pytest.mark.asyncio
async def test_record_agent_call_success(sl):
    async with sl.record_agent_call("h1", "test prompt " * 20, "gpt-4") as rec:
        rec.response_preview = "response here"
        rec.success = True

    calls = sl.read_agent_calls()
    assert len(calls) == 1
    assert calls[0]["agent_name"] == "h1"
    assert calls[0]["prompt_preview"] == ("test prompt " * 20)[:100]
    assert calls[0]["response_preview"] == "response here"
    assert calls[0]["model"] == "gpt-4"
    assert calls[0]["success"] is True
    assert calls[0]["duration_ms"] >= 0


@pytest.mark.asyncio
async def test_record_agent_call_exception_logs_error(sl):
    with pytest.raises(RuntimeError, match="agent failed"):
        async with sl.record_agent_call("h1", "test") as rec:
            raise RuntimeError("agent failed")

    calls = sl.read_agent_calls()
    assert len(calls) == 1
    assert calls[0]["success"] is False
    assert calls[0]["error"] == "agent failed"
    assert calls[0]["level"] == LogLevel.ERROR


@pytest.mark.asyncio
async def test_record_agent_call_reraises(sl):
    with pytest.raises(ValueError):
        async with sl.record_agent_call("h1", "x"):
            raise ValueError("boom")


@pytest.mark.asyncio
async def test_record_agent_call_cancelled_logs_warning(sl):
    """CancelledError must NOT appear as success=True (was a pre-fix bug)."""
    import asyncio
    with pytest.raises(asyncio.CancelledError):
        async with sl.record_agent_call("h1", "task") as rec:
            raise asyncio.CancelledError()

    calls = sl.read_agent_calls()
    assert len(calls) == 1
    assert calls[0]["success"] is False
    assert calls[0]["error"] == "cancelled"
    assert calls[0]["level"] == LogLevel.WARNING  # not ERROR — it's a deliberate stop


@pytest.mark.asyncio
async def test_record_tool_call_cancelled_logs_warning(sl):
    import asyncio
    with pytest.raises(asyncio.CancelledError):
        async with sl.record_tool_call("sandbox.python", {"code": "pass"}) as rec:
            raise asyncio.CancelledError()

    calls = sl.read_tool_calls()
    assert calls[0]["success"] is False
    assert calls[0]["error"] == "cancelled"
    assert calls[0]["level"] == LogLevel.WARNING


# ── record_tool_call context manager ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_record_tool_call_success(sl):
    async with sl.record_tool_call("filesystem.read", {"path": "x.txt"}) as rec:
        rec.result_preview = "contents"
        rec.success = True

    calls = sl.read_tool_calls()
    assert calls[0]["tool_name"] == "filesystem.read"
    assert calls[0]["result_preview"] == "contents"
    assert calls[0]["duration_ms"] >= 0


@pytest.mark.asyncio
async def test_record_tool_call_failure(sl):
    with pytest.raises(IOError):
        async with sl.record_tool_call("filesystem.read", {"path": "missing"}) as rec:
            raise IOError("file not found")

    calls = sl.read_tool_calls()
    assert calls[0]["success"] is False
    assert calls[0]["level"] == LogLevel.ERROR


# ── log_summary ───────────────────────────────────────────────────────────────

def test_log_summary(sl):
    sl.log_warn("c", "w1", {})
    sl.log_warn("c", "w2", {})
    sl.log_error("c", "e1", {})
    sl.log_agent_call(AgentCallEntry(session_id="s", agent_name="a", prompt_preview="p"))
    sl.log_tool_call(ToolCallEntry(session_id="s", tool_name="t", parameters={}))

    summary = sl.log_summary()
    assert summary["session_id"] == "test-session"
    assert summary["agent_calls"] == 1
    assert summary["tool_calls"] == 1
    assert summary["warnings"] == 2
    assert summary["errors"] == 1
    assert "events" not in summary


def test_log_summary_empty(sl):
    summary = sl.log_summary()
    assert all(v == 0 for k, v in summary.items() if k != "session_id")


# ── SystemLogger: cross-session dual-write ────────────────────────────────────

def test_warn_dual_writes_to_system_log(tmp_path):
    sl = SessionLogger("sess-A", str(tmp_path))
    sl.log_warn("comp", "cross-session warning", {"k": "v"})

    sys_log = SystemLogger(str(tmp_path))
    warnings = sys_log.read_warnings()
    assert len(warnings) == 1
    assert warnings[0]["session_id"] == "sess-A"
    assert warnings[0]["message"] == "cross-session warning"
    assert warnings[0]["level"] == LogLevel.WARNING


def test_error_dual_writes_to_system_log(tmp_path):
    sl = SessionLogger("sess-B", str(tmp_path))
    sl.log_error("comp", "critical failure", {}, "Traceback: ...")

    sys_log = SystemLogger(str(tmp_path))
    errors = sys_log.read_errors()
    assert len(errors) == 1
    assert errors[0]["session_id"] == "sess-B"
    assert errors[0]["exc_str"] == "Traceback: ..."
    assert errors[0]["level"] == LogLevel.ERROR


def test_multiple_sessions_warnings_aggregated(tmp_path):
    """Warnings from session A and B both appear in the system log, ordered by insertion."""
    sl_a = SessionLogger("sess-A", str(tmp_path))
    sl_b = SessionLogger("sess-B", str(tmp_path))

    sl_a.log_warn("host", "A's problem", {})
    sl_b.log_warn("executor", "B's problem", {})
    sl_a.log_warn("host", "A again", {})

    sys_log = SystemLogger(str(tmp_path))
    warnings = sys_log.read_warnings()
    assert len(warnings) == 3
    # session_ids alternate as inserted
    assert warnings[0]["session_id"] == "sess-A"
    assert warnings[1]["session_id"] == "sess-B"
    assert warnings[2]["session_id"] == "sess-A"
    # timestamps present and non-empty
    for w in warnings:
        assert w["timestamp"]


def test_system_log_summary(tmp_path):
    sl_a = SessionLogger("sess-A", str(tmp_path))
    sl_b = SessionLogger("sess-B", str(tmp_path))
    sl_a.log_warn("c", "w1", {})
    sl_b.log_error("c", "e1", {})
    sl_a.log_error("c", "e2", {})

    summary = SystemLogger(str(tmp_path)).summary()
    assert summary["warnings"] == 1
    assert summary["errors"] == 2


def test_system_log_empty(tmp_path):
    summary = SystemLogger(str(tmp_path)).summary()
    assert summary["warnings"] == 0
    assert summary["errors"] == 0


def test_system_log_pagination(tmp_path):
    sl = SessionLogger("sess-X", str(tmp_path))
    for i in range(5):
        sl.log_warn("c", f"warn {i}", {})

    sys_log = SystemLogger(str(tmp_path))
    page = sys_log.read_warnings(limit=2, offset=1)
    assert len(page) == 2
    assert page[0]["message"] == "warn 1"


def test_session_log_unaffected_by_other_session(tmp_path):
    """Per-session warnings.jsonl only contains that session's entries."""
    sl_a = SessionLogger("sess-A", str(tmp_path))
    sl_b = SessionLogger("sess-B", str(tmp_path))
    sl_a.log_warn("c", "only A", {})
    sl_b.log_warn("c", "only B", {})

    assert len(sl_a.read_warnings()) == 1
    assert sl_a.read_warnings()[0]["session_id"] == "sess-A"
    assert len(sl_b.read_warnings()) == 1
    assert sl_b.read_warnings()[0]["session_id"] == "sess-B"
