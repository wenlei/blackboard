import pytest

from blackboard.agents import AgentRegistry


class TestAgentRegistry:
    def test_create_agent(self):
        reg = AgentRegistry()
        agent = reg.create("test-ds", "deepseek")
        assert agent.name == "test-ds"
        assert agent.provider == "deepseek"

    def test_create_multiple(self):
        reg = AgentRegistry()
        reg.create("a", "deepseek")
        reg.create("b", "openai")
        reg.create("c", "groq")
        assert len(reg.list()) == 3

    def test_get_agent(self):
        reg = AgentRegistry()
        reg.create("my-agent", "deepseek")
        a = reg.get("my-agent")
        assert a.name == "my-agent"

    def test_get_missing_raises(self):
        reg = AgentRegistry()
        from blackboard.config.models import AgentRegistryError
        with pytest.raises(AgentRegistryError):
            reg.get("nobody")

    def test_remove_agent(self):
        reg = AgentRegistry()
        reg.create("tmp", "openai")
        reg.remove("tmp")
        assert len(reg.list()) == 0

    def test_unknown_provider_falls_back_to_chat_completions(self):
        from blackboard.agents.chat_completions import ChatCompletionsAdapter
        reg = AgentRegistry()
        agent = reg.create("x", "meta-llama")
        assert isinstance(agent, ChatCompletionsAdapter)

    def test_list_by_provider(self):
        reg = AgentRegistry()
        reg.create("d1", "deepseek")
        reg.create("d2", "deepseek")
        reg.create("o1", "openai")
        assert len(reg.list_by_provider("deepseek")) == 2
