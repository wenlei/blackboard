from abc import ABC, abstractmethod
from pathlib import Path

from blackboard.models import Task, TaskResult


class BaseAgent(ABC):
    """所有 LLM Agent 的基础契约：统一 execute / 健康检查 / 记忆读写"""

    name: str
    provider: str

    def __init__(self, name: str, provider: str, api_key: str, base_url: str, model: str):
        self.name = name
        self.provider = provider
        self.api_key = api_key
        self.base_url = base_url
        self.model = model

    @abstractmethod
    async def execute(self, task: Task, memory: str | None = None) -> TaskResult: ...

    @abstractmethod
    async def health_check(self) -> bool: ...

    def load_memory(self, mem_path: str) -> str | None:
        p = Path(mem_path)
        if p.exists():
            return p.read_text()
        return None

    def save_memory(self, mem_path: str, content: str):
        p = Path(mem_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "a") as f:
            f.write(content + "\n")
