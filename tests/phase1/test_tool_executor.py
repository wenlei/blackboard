from pathlib import Path

import pytest
import yaml

from blackboard.tools.executor import ToolExecutor, load_tool_registry
from blackboard.tools.models import ToolCall, ToolRegistry


@pytest.fixture
def tool_registry(valid_tools_yaml):
    data = yaml.safe_load((valid_tools_yaml / "tools" / "registry.yaml").read_text())
    from blackboard.tools.models import ToolDefinition

    tools = {}
    for tool_id, tool_data in data["tools"].items():
        tool_data["name"] = tool_data.get("name", tool_id)
        tools[tool_id] = ToolDefinition(**tool_data)
    return ToolRegistry(tools=tools)


@pytest.fixture
def sandbox_dir(tmp_path):
    s = tmp_path / "sandbox"
    s.mkdir()
    return str(s)


@pytest.fixture
def executor(tool_registry, sandbox_dir):
    return ToolExecutor(tool_registry, sandbox_dir)


class TestLoadToolRegistry:
    def test_load_from_config_dir(self, valid_tools_yaml):
        reg = load_tool_registry(config_dir=str(valid_tools_yaml))
        assert isinstance(reg, ToolRegistry)
        assert reg.get("read_file") is not None
        assert reg.get("write_file") is not None
        assert reg.get("execute_python") is not None
        assert reg.get("execute_shell") is not None
        assert reg.get("http_get") is not None
        assert reg.get("http_post") is not None
        assert reg.get("web_search") is not None

    def test_load_from_project_config(self, config_dir):
        reg = load_tool_registry(config_dir=str(config_dir))
        assert len(reg.tools) == 7

    def test_all_operation_types_covered(self, valid_tools_yaml):
        reg = load_tool_registry(config_dir=str(valid_tools_yaml))
        op_types = {t.operation_type for t in reg.list_all()}
        assert "file_read" in op_types
        assert "file_write" in op_types
        assert "execute_code" in op_types
        assert "http_request" in op_types
        assert "search" in op_types


class TestToolExecution:
    @pytest.mark.asyncio
    async def test_read_file(self, executor, sandbox_dir):
        path = Path(sandbox_dir) / "test.txt"
        path.write_text("hello world")
        result = await executor.execute(
            ToolCall(tool_name="read_file", parameters={"path": "test.txt"})
        )
        assert result.success is True
        assert "hello world" in result.result

    @pytest.mark.asyncio
    async def test_write_file(self, executor, sandbox_dir):
        result = await executor.execute(
            ToolCall(
                tool_name="write_file",
                parameters={"path": "output.txt", "content": "hello world"},
            )
        )
        assert result.success is True
        assert (Path(sandbox_dir) / "output.txt").read_text() == "hello world"

    @pytest.mark.asyncio
    async def test_write_file_creates_dirs(self, executor, sandbox_dir):
        result = await executor.execute(
            ToolCall(
                tool_name="write_file",
                parameters={"path": "sub/dir/file.txt", "content": "nested"},
            )
        )
        assert result.success is True
        assert (Path(sandbox_dir) / "sub" / "dir" / "file.txt").read_text() == "nested"

    @pytest.mark.asyncio
    async def test_execute_python(self, executor):
        result = await executor.execute(
            ToolCall(tool_name="execute_python", parameters={"code": "print(1+1)"})
        )
        assert result.success is True
        assert "2" in result.result

    @pytest.mark.asyncio
    async def test_execute_python_error_in_code(self, executor):
        result = await executor.execute(
            ToolCall(tool_name="execute_python", parameters={"code": "raise Exception('test')"})
        )
        assert result.success is True
        assert "Exception" in result.result

    @pytest.mark.asyncio
    async def test_execute_shell(self, executor):
        result = await executor.execute(
            ToolCall(tool_name="execute_shell", parameters={"command": "echo hello"})
        )
        assert result.success is True
        assert "hello" in result.result

    @pytest.mark.asyncio
    async def test_unknown_tool(self, executor):
        result = await executor.execute(ToolCall(tool_name="non_existent", parameters={}))
        assert result.success is False
        assert "Unknown tool" in result.error

    @pytest.mark.asyncio
    async def test_web_search_stub(self, executor):
        result = await executor.execute(
            ToolCall(tool_name="web_search", parameters={"query": "python"})
        )
        assert result.success is True
        assert "Search stub" in result.result

    @pytest.mark.asyncio
    async def test_filesystem_read_missing_file(self, executor):
        result = await executor.execute(
            ToolCall(tool_name="read_file", parameters={"path": "does_not_exist.txt"})
        )
        assert result.success is False

    @pytest.mark.asyncio
    async def test_execute_shell_non_zero_exit(self, executor):
        result = await executor.execute(
            ToolCall(tool_name="execute_shell", parameters={"command": "exit 1"})
        )
        assert result.success is True
        assert result.result is not None
