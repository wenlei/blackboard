import json

import pytest

from blackboard.models import (
    ApprovalRequest,
    ApprovalResponse,
    StreamMessage,
    Task,
    TaskResult,
)
from blackboard.config.models import (
    AgentRegistryError,
    ApprovalTimeoutError,
    ArchiveFailedError,
    InvalidApiKeyError,
    MissingApiKeyError,
    OperationType,
    PermissionMode,
    SandboxExecutionError,
    StorageQuotaError,
)


class TestTask:
    def test_task_creation(self):
        task = Task(session_id="s1", target_agent="deepseek", role="程序员", prompt="写代码")
        assert task.session_id == "s1"
        assert task.role == "程序员"
        assert task.id != ""
        assert task.created_at is not None

    def test_task_serialization(self):
        task = Task(session_id="s1", target_agent="deepseek", role="architect", prompt="analyze")
        data = task.model_dump_json()
        parsed = json.loads(data)
        assert parsed["session_id"] == "s1"
        assert parsed["operation_type"] == "chat"


class TestTaskResult:
    def test_success_result(self):
        result = TaskResult(
            task_id="t1",
            session_id="s1",
            agent_name="deepseek",
            content="def sort():...",
            success=True,
            token_usage={"input": 100, "output": 50},
            duration_ms=1234,
        )
        assert result.success
        assert result.token_usage == {"input": 100, "output": 50}

    def test_error_result(self):
        result = TaskResult(
            task_id="t1",
            session_id="s1",
            agent_name="claude",
            content="",
            success=False,
            error="API timeout",
        )
        assert not result.success
        assert result.error == "API timeout"


class TestApproval:
    def test_approval_flow(self):
        req = ApprovalRequest(session_id="s1", task_id="t1", agent_name="deepseek", operation="file_write", context="write to test.py")
        assert req.operation == "file_write"

        resp = ApprovalResponse(approval_id=req.id, session_id="s1", decision="approved")
        assert resp.approval_id == req.id
        assert resp.decision == "approved"


class TestStreamMessage:
    def test_with_channel(self):
        msg = StreamMessage(
            stream="outbox",
            session_id="s1",
            payload={"text": "hello"},
            target_channel="telegram",
        )
        assert msg.target_channel == "telegram"

    def test_without_channel(self):
        msg = StreamMessage(stream="inbox", session_id="s1", payload={"text": "hi"})
        assert msg.target_channel is None


class TestEnums:
    def test_permission_modes(self):
        assert PermissionMode.WHITELIST.value == "whitelist"
        assert PermissionMode.APPROVAL_FIRST.value == "approval_first"
        assert PermissionMode.OPEN.value == "open"

    def test_operation_types(self):
        assert OperationType.CHAT.value == "chat"
        assert OperationType.EXECUTE_CODE.value == "execute_code"
        assert OperationType.FILE_DELETE.value == "file_delete"


class TestErrors:
    def test_error_status_codes(self):
        assert AgentRegistryError().status_code == 404
        assert MissingApiKeyError().status_code == 422
        assert InvalidApiKeyError().status_code == 502
        assert SandboxExecutionError().status_code == 500
        assert StorageQuotaError().status_code == 507
        assert ArchiveFailedError().status_code == 500
        assert ApprovalTimeoutError().status_code == 408

    def test_errors_are_exceptions(self):
        with pytest.raises(AgentRegistryError):
            raise AgentRegistryError()
        with pytest.raises(StorageQuotaError):
            raise StorageQuotaError()
