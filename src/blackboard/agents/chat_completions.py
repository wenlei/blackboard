import asyncio
import time
from typing import Any

import httpx

from blackboard.agents.base import BaseAgent
from blackboard.models import Task, TaskResult


class ChatCompletionsAdapter(BaseAgent):
    """OpenAI-compatible Chat Completions adapter.

    Works with OpenAI, DeepSeek, Groq, xAI, Mistral, Qwen, Ollama,
    OpenRouter, Together AI, Fireworks, DeepInfra, Cerebras, and
    any other provider exposing a /chat/completions endpoint.
    """

    # Sensible per-provider default models when none is specified
    _PROVIDER_DEFAULT_MODELS: dict[str, str] = {
        "deepseek": "deepseek-chat",
        "openai": "gpt-4o-mini",
        "groq": "llama-3.1-8b-instant",
        "xai": "grok-beta",
        "mistral": "mistral-small-latest",
        "qwen": "qwen-turbo",
        "google": "gemini-1.5-flash",
        "anthropic": "claude-3-haiku-20240307",
        "claude": "claude-3-haiku-20240307",
        "cerebras": "llama3.1-8b",
        "together": "meta-llama/Llama-3.2-3B-Instruct-Turbo",
        "fireworks": "accounts/fireworks/models/llama-v3p1-8b-instruct",
    }

    # Provider-default base URLs (used when no registry config exists for the agent)
    _PROVIDER_DEFAULT_BASE_URLS: dict[str, str] = {
        "deepseek": "https://api.deepseek.com/v1",
        "openai": "https://api.openai.com/v1",
        "groq": "https://api.groq.com/openai/v1",
        "xai": "https://api.x.ai/v1",
        "mistral": "https://api.mistral.ai/v1",
        "qwen": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "google": "https://generativelanguage.googleapis.com/v1beta/openai",
        "cerebras": "https://api.cerebras.ai/v1",
        "together": "https://api.together.xyz/v1",
        "fireworks": "https://api.fireworks.ai/inference/v1",
        "deepinfra": "https://api.deepinfra.com/v1/openai",
        "openrouter": "https://openrouter.ai/api/v1",
        "anthropic": "https://api.anthropic.com/v1",
        "claude": "https://api.anthropic.com/v1",
        "nvidia": "https://integrate.api.nvidia.com/v1",
    }

    def __init__(self, name: str, provider: str = "openai", api_key: str | None = None, model: str | None = None, base_url: str | None = None, system_prompt: str | None = None):
        api_key = api_key or ""
        model = model or self._PROVIDER_DEFAULT_MODELS.get(provider, provider)
        base_url = base_url or self._PROVIDER_DEFAULT_BASE_URLS.get(provider, "")
        super().__init__(
            name=name,
            provider=provider,
            api_key=api_key,
            base_url=base_url,
            model=model,
        )
        self.system_prompt: str | None = system_prompt

    async def execute(self, task: Task, memory: str | None = None) -> TaskResult:
        start = time.monotonic()
        messages: list[dict[str, Any]] = []
        # 1. Agent identity / soul — highest priority system message
        if self.system_prompt:
            messages.append({"role": "system", "content": self.system_prompt})
        # 2. Per-call context (e.g. previous agent outputs in multi-agent chain)
        if task.context:
            messages.append({"role": "system", "content": task.context})
        # 3. Long-term memory (agent's accumulated notes)
        if memory:
            messages.append({"role": "system", "content": f"Memory:\n{memory}"})
        # 4. User message — omit redundant role prefix when system_prompt already defines identity
        user_content = task.prompt if self.system_prompt else f"[Role: {task.role}]\n{task.prompt}"
        messages.append({"role": "user", "content": user_content})

        async with httpx.AsyncClient(timeout=60) as client:
            for attempt in range(3):
                try:
                    url = f"{self.base_url.rstrip('/')}/chat/completions"
                    headers = {
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    }
                    resp = await client.post(
                        url,
                        headers=headers,
                        json={"model": self.model, "messages": messages},
                    )
                    if resp.status_code == 429:
                        await asyncio.sleep(2**attempt)
                        continue
                    if resp.status_code in (401, 403):
                        return TaskResult(
                            task_id=task.id,
                            session_id=task.session_id,
                            agent_name=self.name,
                            content="",
                            success=False,
                            error=f"API auth error: {resp.status_code}",
                            duration_ms=int((time.monotonic() - start) * 1000),
                        )
                    resp.raise_for_status()
                    data = resp.json()
                    msg_obj = data["choices"][0]["message"]
                    # Some models (deepseek-reasoner, tool-call responses) return
                    # content=null and put the real text in reasoning_content.
                    content = msg_obj.get("content") or msg_obj.get("reasoning_content") or ""
                    usage = data.get("usage", {})
                    return TaskResult(
                        task_id=task.id,
                        session_id=task.session_id,
                        agent_name=self.name,
                        content=content,
                        success=True,
                        token_usage={"input": usage.get("prompt_tokens", 0), "output": usage.get("completion_tokens", 0)},
                        duration_ms=int((time.monotonic() - start) * 1000),
                    )
                except httpx.TimeoutException:
                    if attempt == 2:
                        return TaskResult(
                            task_id=task.id,
                            session_id=task.session_id,
                            agent_name=self.name,
                            content="",
                            success=False,
                            error="API request timed out (60s)",
                            duration_ms=int((time.monotonic() - start) * 1000),
                        )
                except Exception as e:
                    if attempt == 2:
                        return TaskResult(
                            task_id=task.id,
                            session_id=task.session_id,
                            agent_name=self.name,
                            content="",
                            success=False,
                            error=str(e),
                            duration_ms=int((time.monotonic() - start) * 1000),
                        )
                    await asyncio.sleep(1)
        return TaskResult(
            task_id=task.id,
            session_id=task.session_id,
            agent_name=self.name,
            content="",
            success=False,
            error="Max retries exceeded",
            duration_ms=int((time.monotonic() - start) * 1000),
        )

    async def health_check(self) -> bool:
        return bool(self.api_key)
