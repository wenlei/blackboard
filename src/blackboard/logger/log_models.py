from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field


class LogLevel(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


class LogEntry(BaseModel):
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    session_id: str = ""
    level: LogLevel = LogLevel.INFO
    component: str = ""


class AgentCallEntry(LogEntry):
    agent_name: str
    prompt_preview: str
    response_preview: str = ""
    model: str = ""
    success: bool = True
    error: str = ""
    duration_ms: float = 0.0


class ToolCallEntry(LogEntry):
    tool_name: str
    parameters: dict = Field(default_factory=dict)
    result_preview: str = ""
    success: bool = True
    error: str = ""
    duration_ms: float = 0.0


class WarnErrorEntry(LogEntry):
    message: str
    data: dict = Field(default_factory=dict)
    exc_str: str = ""
