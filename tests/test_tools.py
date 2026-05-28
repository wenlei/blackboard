import os
import tempfile

import pytest

from blackboard.tools.executor import ToolExecutor, load_tool_registry
from blackboard.tools.models import ToolCall


@pytest.fixture
def registry():
    return load_tool_registry()


@pytest.fixture
def temp_sandbox():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def executor(registry, temp_sandbox):
    return ToolExecutor(registry, sandbox_dir=temp_sandbox)


class TestToolRegistry:
    def test_load_tools(self, registry):
        assert len(registry.tools) == 7

    def test_filter_by_operation(self, registry):
        http_tools = registry.list_by_operation("http_request")
        assert len(http_tools) == 2
        names = {t.name for t in http_tools}
        assert "HTTP GET 请求" in names
        assert "HTTP POST 请求" in names

    def test_get_tool(self, registry):
        tool = registry.get("read_file")
        assert tool.operation_type == "file_read"
        assert len(tool.parameters) == 1

    def test_unknown_tool(self, registry):
        assert registry.get("non_existent") is None

    def test_tool_parameter_metadata(self, registry):
        tool = registry.get("write_file")
        params = {p.name: p for p in tool.parameters}
        assert params["path"].required
        assert params["content"].required
        assert params["path"].type == "string"


class TestToolExecutor:
    @pytest.mark.asyncio
    async def test_read_file(self, executor, temp_sandbox):
        filepath = os.path.join(temp_sandbox, "test.txt")
        with open(filepath, "w") as f:
            f.write("hello world")

        result = await executor.execute(ToolCall(tool_name="read_file", parameters={"path": "test.txt"}))
        assert result.success
        assert result.result == "hello world"

    @pytest.mark.asyncio
    async def test_write_file(self, executor, temp_sandbox):
        result = await executor.execute(ToolCall(tool_name="write_file", parameters={"path": "out.txt", "content": "你好"}))
        assert result.success

        filepath = os.path.join(temp_sandbox, "out.txt")
        with open(filepath) as f:
            assert f.read() == "你好"

    @pytest.mark.asyncio
    async def test_execute_python(self, executor):
        result = await executor.execute(ToolCall(tool_name="execute_python", parameters={"code": "print(1+1)"}))
        assert result.success
        assert "2" in result.result

    @pytest.mark.asyncio
    async def test_execute_shell(self, executor):
        result = await executor.execute(ToolCall(tool_name="execute_shell", parameters={"command": "echo 'ok'"}))
        assert result.success
        assert "ok" in result.result

    @pytest.mark.asyncio
    async def test_unknown_tool(self, executor):
        result = await executor.execute(ToolCall(tool_name="ghost_tool", parameters={}))
        assert not result.success
        assert "Unknown tool" in result.error

    @pytest.mark.asyncio
    async def test_tool_to_operation_mapping(self, registry):
        for name, tool in registry.tools.items():
            valid_ops = {"chat", "analyze", "search", "execute_code", "http_request", "file_read", "file_write", "file_delete"}
            assert tool.operation_type in valid_ops, f"{name}: {tool.operation_type} not in valid operations"
