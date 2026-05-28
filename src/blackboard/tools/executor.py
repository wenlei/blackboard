from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

import yaml

from blackboard.tools.models import ToolCall, ToolDefinition, ToolRegistry, ToolResult

if TYPE_CHECKING:
    from blackboard.logger.session_logger import SessionLogger

logger = logging.getLogger(__name__)


def load_tool_registry(config_dir: str = "config") -> ToolRegistry:
    path = Path(config_dir) / "tools" / "registry.yaml"
    data = yaml.safe_load(path.read_text())
    tools = {}
    for tool_id, tool_data in data["tools"].items():
        tool_data["name"] = tool_data.get("name", tool_id)
        tools[tool_id] = ToolDefinition(**tool_data)
    return ToolRegistry(**{"tools": tools})


class ToolExecutor:
    def __init__(self, registry: ToolRegistry, sandbox_dir: str | None = None):
        self.registry = registry
        self.sandbox_dir = sandbox_dir or "/tmp/blackboard-sandbox"

    async def execute(
        self,
        call: ToolCall,
        session_logger: SessionLogger | None = None,
    ) -> ToolResult:
        tool = self.registry.get(call.tool_name)
        if not tool:
            return ToolResult(tool_name=call.tool_name, success=False, error=f"Unknown tool: {call.tool_name}")

        if session_logger:
            async with session_logger.record_tool_call(call.tool_name, call.parameters) as rec:
                try:
                    handler = self._resolve_handler(tool.handler)
                    raw_result = await handler(tool, call.parameters)
                    rec.result_preview = str(raw_result)[:200]
                    rec.success = True
                    return ToolResult(tool_name=call.tool_name, success=True, result=str(raw_result))
                except Exception as e:
                    rec.success = False
                    rec.error = str(e)
                    logger.exception("Tool %s execution failed", call.tool_name)
                    raise
        else:
            try:
                handler = self._resolve_handler(tool.handler)
                result = await handler(tool, call.parameters)
                return ToolResult(tool_name=call.tool_name, success=True, result=str(result))
            except Exception as e:
                logger.exception("Tool %s execution failed", call.tool_name)
                return ToolResult(tool_name=call.tool_name, success=False, error=str(e))

    def _resolve_handler(self, handler_path: str):
        parts = handler_path.split(".")
        if parts[0] == "filesystem":
            return self._handle_filesystem
        elif parts[0] == "sandbox":
            return self._handle_sandbox
        elif parts[0] == "network":
            return self._handle_network
        elif parts[0] == "search":
            return self._handle_search
        raise ValueError(f"Unknown handler namespace: {handler_path}")

    async def _handle_filesystem(self, tool: ToolDefinition, params: dict) -> str:
        import os

        action = tool.handler.split(".")[-1]
        sandbox_root = os.path.realpath(self.sandbox_dir)
        raw_path = params.get("path", "")
        joined = os.path.realpath(os.path.join(sandbox_root, raw_path))
        if not joined.startswith(sandbox_root + os.sep) and joined != sandbox_root:
            raise ValueError(f"Path traversal denied: {raw_path}")

        if action == "read":
            with open(joined) as f:
                return f.read()
        elif action == "write":
            content = params.get("content", "")
            os.makedirs(os.path.dirname(joined), exist_ok=True)
            with open(joined, "w") as f:
                f.write(content)
            return f"Written {len(content)} bytes to {joined}"
        elif action == "delete":
            if os.path.exists(joined):
                os.remove(joined)
                return f"Deleted: {raw_path}"
            return f"File not found: {raw_path}"
        elif action == "list":
            if os.path.isdir(joined):
                return "\n".join(sorted(os.listdir(joined)))
            return f"Not a directory: {raw_path}"
        raise ValueError(f"Unknown filesystem action: {action}")

    async def _handle_sandbox(self, tool: ToolDefinition, params: dict) -> str:
        import subprocess

        action = tool.handler.split(".")[-1]
        if action == "python":
            code = params.get("code", "")
            result = subprocess.run(
                ["python3", "-c", code], capture_output=True, text=True, timeout=30, cwd=self.sandbox_dir
            )
            return result.stdout or result.stderr
        elif action == "shell":
            command = params.get("command", "")
            result = subprocess.run(
                ["bash", "-c", command], capture_output=True, text=True, timeout=30, cwd=self.sandbox_dir
            )
            return result.stdout or result.stderr
        raise ValueError(f"Unknown sandbox action: {action}")

    async def _handle_network(self, tool: ToolDefinition, params: dict) -> str:
        import httpx

        action = tool.handler.split(".")[-1]
        async with httpx.AsyncClient(timeout=30) as client:
            if action == "http_get":
                resp = await client.get(params["url"])
                return resp.text
            elif action == "http_post":
                resp = await client.post(params["url"], json=params.get("body"))
                return resp.text
        raise ValueError(f"Unknown network action: {action}")

    async def _handle_search(self, tool: ToolDefinition, params: dict) -> str:
        query = params.get("query", "")
        return f"[Search stub] Query ignored: {query} (configure search API in system.yaml)"
