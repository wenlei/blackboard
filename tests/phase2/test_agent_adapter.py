import asyncio
import os
from pathlib import Path
import tempfile

import pytest

from blackboard.agents.chat_completions import ChatCompletionsAdapter
from blackboard.agents.registry import AgentRegistry, ADAPTER_MAP
from blackboard.config.models import AgentRegistryError
from blackboard.models import Task


class TestChatCompletionsAdapter:
    def test_create_with_defaults(self):
        adapter = ChatCompletionsAdapter(name="deepseek", provider="deepseek")
        assert adapter.name == "deepseek"
        assert adapter.provider == "deepseek"
        # No model specified → provider default is used
        assert adapter.model == "deepseek-chat"

    def test_create_custom(self):
        adapter = ChatCompletionsAdapter(name="my-ds", provider="deepseek", api_key="sk-test", model="deepseek-r1", base_url="https://api.deepseek.com/v1")
        assert adapter.name == "my-ds"
        assert adapter.provider == "deepseek"
        assert adapter.api_key == "sk-test"
        assert adapter.model == "deepseek-r1"
        assert adapter.base_url == "https://api.deepseek.com/v1"

    def test_health_check_with_api_key(self):
        adapter = ChatCompletionsAdapter(name="test", provider="openai", api_key="sk-xxx")
        assert asyncio.run(adapter.health_check()) is True

    def test_health_check_without_api_key(self):
        adapter = ChatCompletionsAdapter(name="test", provider="openai")
        assert asyncio.run(adapter.health_check()) is False

    def test_memory_save_and_load(self):
        adapter = ChatCompletionsAdapter(name="my-ds", provider="deepseek", api_key="sk-test")
        with tempfile.TemporaryDirectory() as tmpdir:
            mem_path = Path(tmpdir) / "agents" / "my-ds" / "agent_mem.md"
            adapter.save_memory(str(mem_path), "Task: wrote bubble sort")
            adapter.save_memory(str(mem_path), "Task: wrote quick sort")
            content = adapter.load_memory(str(mem_path))
            assert "bubble sort" in (content or "")
            assert "quick sort" in (content or "")

    def test_memory_load_nonexistent(self):
        adapter = ChatCompletionsAdapter(name="test", provider="openai", api_key="sk-test")
        assert adapter.load_memory("/nonexistent/path/mem.md") is None

    def test_base_url_strips_trailing_slash(self):
        adapter = ChatCompletionsAdapter(name="test", provider="groq", base_url="https://api.groq.com/openai/v1/")
        assert adapter.base_url == "https://api.groq.com/openai/v1/"


class TestAgentRegistry:
    def test_create_and_get_deepseek(self):
        reg = AgentRegistry()
        agent = reg.create("ds", "deepseek")
        assert agent.name == "ds"
        assert agent.provider == "deepseek"
        assert reg.get("ds") is agent

    def test_create_and_get_openai(self):
        reg = AgentRegistry()
        agent = reg.create("gpt", "openai")
        assert agent.name == "gpt"
        assert agent.provider == "openai"

    def test_create_multiple_and_list(self):
        reg = AgentRegistry()
        reg.create("ds", "deepseek")
        reg.create("gpt", "openai")
        reg.create("grq", "groq")
        assert len(reg.list()) == 3

    def test_list_by_provider(self):
        reg = AgentRegistry()
        reg.create("ds1", "deepseek")
        reg.create("ds2", "deepseek")
        reg.create("gpt", "openai")
        deepseek_agents = reg.list_by_provider("deepseek")
        assert len(deepseek_agents) == 2
        openai_agents = reg.list_by_provider("openai")
        assert len(openai_agents) == 1

    def test_remove_agent(self):
        reg = AgentRegistry()
        reg.create("tmp", "openai")
        assert len(reg.list()) == 1
        reg.remove("tmp")
        assert len(reg.list()) == 0

    def test_remove_nonexistent_no_error(self):
        reg = AgentRegistry()
        reg.remove("nobody")
        assert len(reg.list()) == 0

    def test_get_nonexistent_raises(self):
        reg = AgentRegistry()
        with pytest.raises(AgentRegistryError, match="Agent not found"):
            reg.get("nobody")

    def test_unknown_provider_falls_back_to_chat_completions(self):
        # Unknown providers (e.g. dynamically added from OpenRouter) use the universal adapter
        from blackboard.agents.chat_completions import ChatCompletionsAdapter
        reg = AgentRegistry()
        agent = reg.create("x", "meta-llama")
        assert isinstance(agent, ChatCompletionsAdapter)
        assert agent.provider == "meta-llama"

    def test_duplicate_create_overwrites(self):
        reg = AgentRegistry()
        a1 = reg.create("agent", "deepseek")
        a2 = reg.create("agent", "openai")
        assert reg.get("agent").provider == "openai"
        assert len(reg.list()) == 1

    def test_create_with_api_key_and_base_url(self):
        reg = AgentRegistry()
        agent = reg.create("test", "groq", api_key="sk-groq-test", base_url="https://api.groq.com/openai/v1")
        assert agent.api_key == "sk-groq-test"
        assert agent.base_url == "https://api.groq.com/openai/v1"


class TestAdapterProviderMapping:
    def test_provider_map_contains_keys(self):
        assert "deepseek" in ADAPTER_MAP
        assert "openai" in ADAPTER_MAP
        assert "groq" in ADAPTER_MAP
        assert "xai" in ADAPTER_MAP
        assert "ollama" in ADAPTER_MAP
        assert "custom" in ADAPTER_MAP

    def test_all_providers_use_chat_completions(self):
        for provider, adapter_cls in ADAPTER_MAP.items():
            assert adapter_cls is ChatCompletionsAdapter
