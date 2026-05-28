from __future__ import annotations

import os
from typing import Type

from blackboard.agents.base import BaseAgent
from blackboard.agents.chat_completions import ChatCompletionsAdapter
from blackboard.config.models import AgentRegistryError as AgentRegError


ADAPTER_MAP: dict[str, Type[BaseAgent]] = {
    "deepseek": ChatCompletionsAdapter,
    "openai": ChatCompletionsAdapter,
    "groq": ChatCompletionsAdapter,
    "xai": ChatCompletionsAdapter,
    "ollama": ChatCompletionsAdapter,
    "openrouter": ChatCompletionsAdapter,
    "together": ChatCompletionsAdapter,
    "fireworks": ChatCompletionsAdapter,
    "deepinfra": ChatCompletionsAdapter,
    "cerebras": ChatCompletionsAdapter,
    "mistral": ChatCompletionsAdapter,
    "qwen": ChatCompletionsAdapter,
    "google": ChatCompletionsAdapter,
    "moonshot": ChatCompletionsAdapter,
    "minimax": ChatCompletionsAdapter,
    "nvidia": ChatCompletionsAdapter,
    "huggingface": ChatCompletionsAdapter,
    "custom": ChatCompletionsAdapter,
    "claude": ChatCompletionsAdapter,
    "anthropic": ChatCompletionsAdapter,
}


class AgentRegistry:
    def __init__(self):
        self._agents: dict[str, BaseAgent] = {}

    def create(self, name: str, provider: str, model: str | None = None, api_key: str | None = None, base_url: str | None = None, system_prompt: str | None = None) -> BaseAgent:
        # Unknown providers (e.g. dynamically added from OpenRouter) fall back to the
        # universal OpenAI-compatible adapter — every listed provider uses the same wire format.
        adapter_cls = ADAPTER_MAP.get(provider, ChatCompletionsAdapter)

        kwargs: dict = {"name": name, "provider": provider, "model": model}
        if api_key is not None:
            kwargs["api_key"] = api_key
        if base_url is not None:
            kwargs["base_url"] = base_url
        if system_prompt is not None:
            kwargs["system_prompt"] = system_prompt
        agent = adapter_cls(**kwargs)
        self._agents[name.lower()] = agent
        return agent

    def get(self, name: str) -> BaseAgent:
        agent = self._agents.get(name.lower())
        if not agent:
            raise AgentRegError(f"Agent not found: {name}")
        return agent

    def list(self) -> list[BaseAgent]:
        return list(self._agents.values())

    def all_agents(self) -> list[BaseAgent]:
        return self.list()

    def remove(self, name: str):
        key = name.lower()
        if key in self._agents:
            del self._agents[key]

    def list_by_provider(self, provider: str) -> list[BaseAgent]:
        return [a for a in self._agents.values() if a.provider == provider]
