from datetime import datetime

from blackboard.models import (
    ApprovalRequest,
    ApprovalResponse,
    StreamMessage,
    Task,
    TaskResult,
)


class TestTask:
    def test_task_creation(self):
        task = Task(
            session_id="s1",
            target_agent="deepseek",
            role="程序员",
            prompt="写一个排序函数",
        )
        assert task.session_id == "s1"
        assert task.target_agent == "deepseek"
        assert task.role == "程序员"
        assert task.prompt == "写一个排序函数"
        assert task.operation_type == "chat"
        assert task.context is None

    def test_task_defaults(self):
        task = Task(session_id="s1", target_agent="deepseek", role="test", prompt="test")
        assert isinstance(task.id, str)
        assert len(task.id) == 36
        assert isinstance(task.created_at, datetime)
        assert task.operation_type == "chat"

    def test_task_with_operation_type(self):
        task = Task(
            session_id="s1",
            target_agent="deepseek",
            role="tester",
            prompt="执行测试",
            operation_type="execute_code",
        )
        assert task.operation_type == "execute_code"

    def test_task_with_context(self):
        task = Task(
            session_id="s1",
            target_agent="deepseek",
            role="coder",
            prompt="fix bug",
            context="previous output was wrong",
        )
        assert task.context == "previous output was wrong"

    def test_task_json_serialization(self):
        task = Task(
            session_id="s1",
            target_agent="deepseek",
            role="程序员",
            prompt="写代码",
        )
        data = task.model_dump()
        assert data["session_id"] == "s1"
        assert data["target_agent"] == "deepseek"
        assert "id" in data
        assert "created_at" in data

    def test_task_json_deserialization(self):
        data = {
            "session_id": "s1",
            "target_agent": "deepseek",
            "role": "coder",
            "prompt": "write code",
        }
        task = Task(**data)
        assert task.session_id == "s1"


class TestTaskResult:
    def test_task_result_creation(self):
        result = TaskResult(
            task_id="t1",
            session_id="s1",
            agent_name="deepseek",
            content="排序完成",
            success=True,
        )
        assert result.task_id == "t1"
        assert result.agent_name == "deepseek"
        assert result.success is True
        assert result.error is None

    def test_task_result_with_token_usage(self):
        result = TaskResult(
            task_id="t1",
            session_id="s1",
            agent_name="deepseek",
            content="输出",
            success=True,
            token_usage={"input": 100, "output": 50},
        )
        assert result.token_usage == {"input": 100, "output": 50}

    def test_task_result_with_error(self):
        result = TaskResult(
            task_id="t1",
            session_id="s1",
            agent_name="deepseek",
            content="",
            success=False,
            error="API timeout",
        )
        assert result.success is False
        assert result.error == "API timeout"

    def test_task_result_duration(self):
        result = TaskResult(
            task_id="t1",
            session_id="s1",
            agent_name="deepseek",
            content="OK",
            success=True,
            duration_ms=1234,
        )
        assert result.duration_ms == 1234

    def test_task_result_requested_operation(self):
        result = TaskResult(
            task_id="t1",
            session_id="s1",
            agent_name="deepseek",
            content="need to write file",
            success=True,
            requested_operation="file_write",
        )
        assert result.requested_operation == "file_write"

    def test_task_result_json_serialization(self):
        result = TaskResult(
            task_id="t1",
            session_id="s1",
            agent_name="deepseek",
            content="OK",
            success=True,
            token_usage={"input": 10, "output": 5},
            duration_ms=500,
        )
        data = result.model_dump()
        assert data["task_id"] == "t1"
        assert data["token_usage"]["input"] == 10
        assert data["duration_ms"] == 500


class TestApprovalRequest:
    def test_approval_request_creation(self):
        req = ApprovalRequest(
            session_id="s1",
            task_id="t1",
            agent_name="deepseek",
            operation="file_write",
            context="write result to output.txt",
        )
        assert req.session_id == "s1"
        assert req.task_id == "t1"
        assert req.operation == "file_write"

    def test_approval_request_defaults(self):
        req = ApprovalRequest(
            session_id="s1",
            task_id="t1",
            agent_name="claude",
            operation="execute_code",
            context="run python script",
        )
        assert isinstance(req.id, str)
        assert isinstance(req.created_at, datetime)


class TestApprovalResponse:
    def test_approval_response_approve(self):
        resp = ApprovalResponse(approval_id="a1", session_id="s1", decision="approved")
        assert resp.approval_id == "a1"
        assert resp.decision == "approved"

    def test_approval_response_reject(self):
        resp = ApprovalResponse(approval_id="a1", session_id="s1", decision="rejected")
        assert resp.decision == "rejected"

    def test_approval_pair(self):
        req = ApprovalRequest(
            session_id="s1",
            task_id="t1",
            agent_name="deepseek",
            operation="execute_code",
            context="run",
        )
        resp = ApprovalResponse(approval_id=req.id, session_id="s1", decision="approved")
        assert resp.approval_id == req.id
        assert resp.session_id == req.session_id


class TestStreamMessage:
    def test_stream_message_creation(self):
        msg = StreamMessage(
            stream="inbox",
            session_id="s1",
            payload={"type": "chat", "content": "hello"},
        )
        assert msg.stream == "inbox"
        assert msg.session_id == "s1"
        assert msg.payload["type"] == "chat"

    def test_stream_message_with_channel(self):
        msg = StreamMessage(
            stream="outbox",
            session_id="s1",
            payload={"text": "hello"},
            target_channel="telegram",
        )
        assert msg.target_channel == "telegram"

    def test_stream_message_no_channel(self):
        msg = StreamMessage(
            stream="inbox",
            session_id="s1",
            payload={"type": "chat"},
        )
        assert msg.target_channel is None

    def test_stream_message_json_serialization(self):
        msg = StreamMessage(
            stream="outbox",
            session_id="s1",
            payload={"text": "hello", "from": "host"},
            target_channel="web",
        )
        data = msg.model_dump()
        assert data["stream"] == "outbox"
        assert data["payload"]["from"] == "host"
        assert data["target_channel"] == "web"
