from pydantic import BaseModel


class ToolParameter(BaseModel):
    name: str
    type: str
    description: str = ""
    required: bool = True


class ToolDefinition(BaseModel):
    name: str
    description: str
    operation_type: str
    parameters: list[ToolParameter]
    handler: str


class ToolRegistry(BaseModel):
    tools: dict[str, ToolDefinition]

    def get(self, tool_name: str) -> ToolDefinition | None:
        return self.tools.get(tool_name)

    def list_by_operation(self, operation_type: str) -> list[ToolDefinition]:
        return [t for t in self.tools.values() if t.operation_type == operation_type]

    def list_all(self) -> list[ToolDefinition]:
        return list(self.tools.values())


class ToolCall(BaseModel):
    tool_name: str
    parameters: dict[str, object]


class ToolResult(BaseModel):
    tool_name: str
    success: bool
    result: str | None = None
    error: str | None = None
