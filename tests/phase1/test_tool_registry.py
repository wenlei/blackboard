from blackboard.tools.models import (
    ToolCall,
    ToolDefinition,
    ToolParameter,
    ToolRegistry,
    ToolResult,
)


class TestToolDefinition:
    def test_create_tool_definition(self):
        tool = ToolDefinition(
            name="read_file",
            description="Read a file",
            operation_type="file_read",
            parameters=[
                ToolParameter(name="path", type="string", description="File path", required=True)
            ],
            handler="filesystem.read",
        )
        assert tool.name == "read_file"
        assert tool.operation_type == "file_read"
        assert len(tool.parameters) == 1
        assert tool.parameters[0].name == "path"

    def test_parameter_defaults(self):
        param = ToolParameter(name="body", type="object")
        assert param.description == ""
        assert param.required is True


class TestToolRegistry:
    def test_registry_get_existing(self):
        tools = {
            "read_file": ToolDefinition(
                name="read_file",
                description="Read",
                operation_type="file_read",
                parameters=[],
                handler="filesystem.read",
            ),
            "write_file": ToolDefinition(
                name="write_file",
                description="Write",
                operation_type="file_write",
                parameters=[],
                handler="filesystem.write",
            ),
        }
        reg = ToolRegistry(tools=tools)
        assert reg.get("read_file") is not None
        assert reg.get("read_file").name == "read_file"

    def test_registry_get_missing(self):
        reg = ToolRegistry(tools={})
        assert reg.get("non_existent") is None

    def test_list_by_operation(self):
        tools = {
            "read": ToolDefinition(
                name="read",
                description="R",
                operation_type="file_read",
                parameters=[],
                handler="f.read",
            ),
            "write": ToolDefinition(
                name="write",
                description="W",
                operation_type="file_write",
                parameters=[],
                handler="f.write",
            ),
            "py": ToolDefinition(
                name="execute_python",
                description="Exec",
                operation_type="execute_code",
                parameters=[],
                handler="s.python",
            ),
            "sh": ToolDefinition(
                name="execute_shell",
                description="Exec",
                operation_type="execute_code",
                parameters=[],
                handler="s.shell",
            ),
        }
        reg = ToolRegistry(tools=tools)
        code_tools = reg.list_by_operation("execute_code")
        assert len(code_tools) == 2
        assert {t.name for t in code_tools} == {"execute_python", "execute_shell"}
        read_tools = reg.list_by_operation("file_read")
        assert len(read_tools) == 1
        assert read_tools[0].name == "read"

    def test_list_all(self):
        tools = {
            "a": ToolDefinition(
                name="a", description="", operation_type="chat", parameters=[], handler="h.a"
            ),
            "b": ToolDefinition(
                name="b", description="", operation_type="chat", parameters=[], handler="h.b"
            ),
        }
        reg = ToolRegistry(tools=tools)
        assert len(reg.list_all()) == 2


class TestToolCall:
    def test_tool_call_creation(self):
        call = ToolCall(tool_name="read_file", parameters={"path": "test.txt"})
        assert call.tool_name == "read_file"
        assert call.parameters == {"path": "test.txt"}


class TestToolResult:
    def test_success_result(self):
        result = ToolResult(tool_name="read_file", success=True, result="file content")
        assert result.success is True
        assert result.result == "file content"
        assert result.error is None

    def test_failure_result(self):
        result = ToolResult(tool_name="read_file", success=False, error="File not found")
        assert result.success is False
        assert result.error == "File not found"

    def test_unknown_tool_result(self):
        result = ToolResult(
            tool_name="non_existent", success=False, error="Unknown tool: non_existent"
        )
        assert result.success is False
        assert result.error == "Unknown tool: non_existent"
