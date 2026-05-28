from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from blackboard.agents.registry import AgentRegistry
from blackboard.api.routes import router as api_router
from blackboard.config.loader import ConfigLoader, FallbackModelConfig


@pytest.fixture
def mock_mq():
    mq = MagicMock()
    mq.publish = AsyncMock(return_value="msg-001")
    mq.consume = AsyncMock(return_value=[])
    mq.health_check = AsyncMock(return_value=True)
    mq.init_session_streams = AsyncMock()
    mq.destroy_session_streams = AsyncMock()
    mq.connect = AsyncMock()
    mq.disconnect = AsyncMock()
    return mq


@pytest.fixture
def mock_config_loader():
    loader = MagicMock(spec=ConfigLoader)
    loader.load_system.return_value = MagicMock()

    agent_registry_mock = MagicMock()
    agent_registry_mock.agents = {
        "deepseek": MagicMock(provider="deepseek", display_name="DeepSeek",
                             api_key_env="DEEPSEEK_API_KEY", base_url="https://api.deepseek.com/v1",
                             default_model="deepseek-chat", models=["deepseek-chat"]),
        "openai": MagicMock(provider="openai", display_name="OpenAI",
                           api_key_env="OPENAI_API_KEY", base_url="https://api.openai.com/v1",
                           default_model="gpt-4o", models=["gpt-4o"]),
    }
    agent_registry_mock.model_dump.return_value = {"agents": {"deepseek": {}, "openai": {}}}
    loader.load_agent_registry.return_value = agent_registry_mock
    loader.save_agent_registry = MagicMock()

    tmpl_obj = MagicMock(id="test_tmpl", name="测试模板", match_keywords=[], steps=[])
    tmpl_obj.model_dump.return_value = {"id": "test_tmpl", "name": "测试模板", "match_keywords": [], "steps": []}
    templates_mock = MagicMock()
    templates_mock.templates = [tmpl_obj]
    templates_mock.model_dump.return_value = {"templates": [{"id": "general", "name": "通用"}]}
    loader.load_strategy_templates.return_value = templates_mock
    loader.save_strategy_templates = MagicMock()

    presets_mock = MagicMock()
    presets_mock.model_dump.return_value = {"presets": {"whitelist": {}, "open": {}}}
    loader.load_permission_presets.return_value = presets_mock

    loader.load_tool_registry.return_value = MagicMock(tools={})

    loader.load_fallback_models.return_value = FallbackModelConfig()
    return loader


@pytest.fixture
def mock_tool_registry():
    reg = MagicMock()
    reg.tools = {"read_file": MagicMock(), "write_file": MagicMock()}
    return reg


@pytest.fixture
def mock_session_mgr():
    mgr = MagicMock()
    mgr._sessions = {}
    mgr.create = AsyncMock()
    mgr.pause = AsyncMock()
    mgr.resume = AsyncMock()
    mgr.close = AsyncMock()
    mgr.add_agent = AsyncMock()
    mgr.remove_agent = AsyncMock()
    return mgr


@pytest.fixture
def test_app(mock_mq, mock_config_loader, mock_tool_registry, mock_session_mgr, tmp_path):
    app = FastAPI()
    app.state.mq = mock_mq
    app.state.config_loader = mock_config_loader
    app.state.tool_registry = mock_tool_registry
    app.state.tool_executor = MagicMock()
    app.state.agent_registry = AgentRegistry()
    app.state.agent_registry.list = MagicMock(return_value=[])
    app.state.session_mgr = mock_session_mgr
    app.state.data_dir = str(tmp_path)
    app.include_router(api_router)
    return app


@pytest.fixture
def client(test_app):
    return TestClient(test_app)


@pytest.fixture
def active_session(mock_session_mgr):
    mock_session_mgr._sessions["test-s1"] = {
        "status": "active",
        "agent_roles": {"程序员": "dp", "审查者": "gpt"},
        "guard": MagicMock(),
    }
    mock_session_mgr.create = AsyncMock(return_value={
        "session_id": "test-s1",
        "agents": [
            {"name": "dp", "provider": "deepseek", "role": "程序员"},
            {"name": "gpt", "provider": "openai", "role": "审查者"},
        ],
        "permissions": {"mode": "whitelist", "operations": {}},
    })
    return "test-s1"


@pytest.fixture
def temp_log_dir(tmp_path):
    d = tmp_path / "sessions" / "test-s1"
    d.mkdir(parents=True, exist_ok=True)
    return d
