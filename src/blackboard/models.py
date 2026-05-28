from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Task(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    session_id: str
    target_agent: str
    role: str
    prompt: str
    operation_type: str = "chat"
    context: str | None = None
    created_at: datetime = Field(default_factory=_now)


class TaskResult(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    task_id: str
    session_id: str
    agent_name: str
    content: str
    success: bool
    error: str | None = None
    token_usage: dict[str, int] | None = None
    duration_ms: int = 0
    requested_operation: str | None = None
    completed_at: datetime = Field(default_factory=_now)


class ApprovalRequest(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    session_id: str
    task_id: str
    agent_name: str
    operation: str
    context: str
    created_at: datetime = Field(default_factory=_now)


class ApprovalResponse(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    approval_id: str
    session_id: str
    decision: str  # "approved" | "rejected"
    responded_at: datetime = Field(default_factory=_now)


class StreamMessage(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    stream: str
    session_id: str
    payload: dict[str, Any]
    target_channel: str | None = None
    timestamp: datetime = Field(default_factory=_now)
