"""Comprehensive tests for config API endpoints not covered by test_api_config.py."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from blackboard.agents.registry import AgentRegistry
from blackboard.api.routes import router as api_router

# ---------------------------------------------------------------------------
# Sample models.dev payload (minimal, covers key fields)
# ---------------------------------------------------------------------------

MOCK_DEV_DATA = {
    "deepseek": {
        "name": "DeepSeek",
        "api_endpoint": "https://api.deepseek.com/v1",
        "models": {
            "deepseek-chat": {
                "id": "deepseek-chat",
                "name": "DeepSeek Chat",
                "modalities": {"input": ["text"], "output": ["text"]},
                "capabilities": {"tool_call": True, "reasoning": False},
                "limit": {"context": 64000},
            },
            "deepseek-reasoner": {
                "id": "deepseek-reasoner",
                "name": "DeepSeek Reasoner",
                "modalities": {"input": ["text"], "output": ["text"]},
                "capabilities": {"tool_call": False, "reasoning": True},
                "limit": {"context": 64000},
            },
        },
    },
    "openai": {
        "name": "OpenAI",
        "api_endpoint": "https://api.openai.com/v1",
        "models": {
            "gpt-4o": {
                "id": "gpt-4o",
                "name": "GPT-4o",
                "modalities": {"input": ["text", "image"], "output": ["text"]},
                "capabilities": {"tool_call": True, "reasoning": False},
                "limit": {"context": 128000},
            }
        },
    },
}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_cred_mgr():
    mgr = MagicMock()
    mgr.get_api_key.return_value = "sk-test-key"
    mgr.get_base_url_override.return_value = ""
    mgr.get_default_model.return_value = "deepseek-chat"
    mgr.get_model_list.return_value = []
    mgr.save_api_key.return_value = None
    mgr.save_model_list.return_value = None
    mgr.list_credentials.return_value = {"deepseek": {"masked_key": "sk-t****key"}}
    mgr.delete.return_value = None
    mgr.get_overall_status.return_value = {"status": "ok", "ready_providers": ["deepseek"]}
    return mgr


@pytest.fixture
def mock_config_loader_extra():
    loader = MagicMock()
    loader.load_system.return_value = MagicMock(config_agent="deepseek")

    agent_registry_mock = MagicMock()
    agent_registry_mock.agents = {
        "deepseek": MagicMock(
            provider="deepseek",
            display_name="DeepSeek",
            api_key_env="DEEPSEEK_API_KEY",
            base_url="https://api.deepseek.com/v1",
            default_model="deepseek-chat",
            models=["deepseek-chat"],
            api_type=MagicMock(value="openai_compatible"),
        ),
    }
    agent_registry_mock.model_dump.return_value = {"agents": {"deepseek": {}}}
    loader.load_agent_registry.return_value = agent_registry_mock
    loader.save_agent_registry = MagicMock()
    loader.load_tool_registry.return_value = MagicMock(tools={})
    loader.save_system_config = MagicMock()
    return loader


@pytest.fixture
def app_with_creds(mock_cred_mgr, mock_config_loader_extra, tmp_path):
    app = FastAPI()
    app.state.mq = MagicMock()
    app.state.config_loader = mock_config_loader_extra
    app.state.tool_registry = MagicMock(tools={})
    app.state.tool_executor = MagicMock()
    app.state.agent_registry = AgentRegistry()
    app.state.session_mgr = MagicMock(_sessions={})
    app.state.data_dir = str(tmp_path)
    app.state.credential_mgr = mock_cred_mgr
    app.include_router(api_router)
    return app


@pytest.fixture
def client_creds(app_with_creds):
    return TestClient(app_with_creds)


# ---------------------------------------------------------------------------
# GET /config/providers — mocked models.dev
# ---------------------------------------------------------------------------


class TestProviders:
    def test_providers_includes_ollama(self, client_creds):
        with patch("blackboard.api.routes._load_local_catalog", return_value=MOCK_DEV_DATA):
            resp = client_creds.get("/api/config/providers")
        assert resp.status_code == 200
        data = resp.json()
        providers = data["providers"]
        assert "ollama" in providers
        assert providers["ollama"]["auth_type"] == "none"
        assert providers["ollama"]["base_url"] == "http://localhost:11434/v1"

    def test_providers_includes_models_dev_entries(self, client_creds):
        with patch("blackboard.api.routes._load_local_catalog", return_value=MOCK_DEV_DATA):
            resp = client_creds.get("/api/config/providers")
        data = resp.json()["providers"]
        assert "deepseek" in data
        assert data["deepseek"]["display_name"] == "DeepSeek"
        assert data["deepseek"]["base_url"] == "https://api.deepseek.com/v1"
        assert "openai" in data

    def test_providers_empty_models_dev_still_returns_ollama(self, client_creds):
        with patch("blackboard.api.routes._load_local_catalog", return_value={}):
            resp = client_creds.get("/api/config/providers")
        assert resp.status_code == 200
        assert "ollama" in resp.json()["providers"]


# ---------------------------------------------------------------------------
# GET /config/providers/{slug}/catalog
# ---------------------------------------------------------------------------


class TestProviderCatalog:
    def test_catalog_known_slug(self, client_creds):
        with patch("blackboard.api.routes._load_local_catalog", return_value=MOCK_DEV_DATA):
            resp = client_creds.get("/api/config/providers/deepseek/catalog")
        assert resp.status_code == 200
        data = resp.json()
        assert data["source"] == "local_catalog"
        model_ids = [m["model_id"] for m in data["models"]]
        assert "deepseek-chat" in model_ids
        assert "deepseek-reasoner" in model_ids

    def test_catalog_vision_model_type(self, client_creds):
        with patch("blackboard.api.routes._load_local_catalog", return_value=MOCK_DEV_DATA):
            resp = client_creds.get("/api/config/providers/openai/catalog")
        data = resp.json()
        gpt4o = next(m for m in data["models"] if m["model_id"] == "gpt-4o")
        assert gpt4o["model_type"] == "vision"

    def test_catalog_reasoning_flag(self, client_creds):
        with patch("blackboard.api.routes._load_local_catalog", return_value=MOCK_DEV_DATA):
            resp = client_creds.get("/api/config/providers/deepseek/catalog")
        data = resp.json()
        reasoner = next(m for m in data["models"] if m["model_id"] == "deepseek-reasoner")
        assert reasoner.get("reasoning") is True

    def test_catalog_supports_tools_field(self, client_creds):
        with patch("blackboard.api.routes._load_local_catalog", return_value=MOCK_DEV_DATA):
            resp = client_creds.get("/api/config/providers/deepseek/catalog")
        data = resp.json()
        chat = next(m for m in data["models"] if m["model_id"] == "deepseek-chat")
        assert chat["supports_tools"] is True

    def test_catalog_unknown_slug_returns_empty(self, client_creds):
        with patch("blackboard.api.routes._load_local_catalog", return_value=MOCK_DEV_DATA):
            resp = client_creds.get("/api/config/providers/nonexistent-xyz/catalog")
        assert resp.status_code == 200
        data = resp.json()
        assert data["models"] == []
        assert data["source"] == "none"


# ---------------------------------------------------------------------------
# POST /config/test-connection
# ---------------------------------------------------------------------------


class TestConnectionInline:
    def _make_httpx_response(self, status_code: int, body: dict | None = None, text: str = ""):
        resp = MagicMock()
        resp.status_code = status_code
        if body is not None:
            resp.json.return_value = body
        else:
            resp.json.side_effect = Exception("no json")
        resp.text = text
        return resp

    def test_success_200(self, client_creds):
        mock_resp = self._make_httpx_response(200, {"choices": [{"message": {"content": "."}}]})
        with patch("httpx.AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=MagicMock(post=AsyncMock(return_value=mock_resp)))
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            resp = client_creds.post("/api/config/test-connection", json={
                "base_url": "https://api.deepseek.com/v1",
                "api_key": "sk-test",
                "model": "deepseek-chat",
            })
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True

    def test_401_rejected(self, client_creds):
        mock_resp = self._make_httpx_response(401, {}, "Unauthorized")
        with patch("httpx.AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=MagicMock(post=AsyncMock(return_value=mock_resp)))
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            resp = client_creds.post("/api/config/test-connection", json={
                "base_url": "https://api.deepseek.com/v1",
                "api_key": "bad-key",
                "model": "deepseek-chat",
            })
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is False
        assert "401" in data["message"]

    def test_400_model_not_found_treated_as_ok(self, client_creds):
        mock_resp = self._make_httpx_response(
            400,
            {"error": {"message": "model does not exist: bad-model"}},
        )
        with patch("httpx.AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=MagicMock(post=AsyncMock(return_value=mock_resp)))
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            resp = client_creds.post("/api/config/test-connection", json={
                "base_url": "https://api.deepseek.com/v1",
                "api_key": "sk-valid",
                "model": "bad-model",
            })
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True

    def test_404_endpoint_not_found(self, client_creds):
        mock_resp = self._make_httpx_response(404, {})
        with patch("httpx.AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=MagicMock(post=AsyncMock(return_value=mock_resp)))
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            resp = client_creds.post("/api/config/test-connection", json={
                "base_url": "https://wrong.example.com/v99",
                "model": "gpt-4",
            })
        data = resp.json()
        assert data["ok"] is False
        assert "404" in data["message"]

    def test_ollama_success(self, client_creds):
        mock_resp = self._make_httpx_response(200, {"models": [{"name": "llama3"}]})
        with patch("httpx.AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=MagicMock(get=AsyncMock(return_value=mock_resp)))
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            resp = client_creds.post("/api/config/test-connection", json={
                "base_url": "http://localhost:11434/v1",
                "api_type": "ollama",
            })
        data = resp.json()
        assert data["ok"] is True
        assert "Ollama" in data["message"]

    def test_ollama_not_running(self, client_creds):
        mock_resp = self._make_httpx_response(503, {})
        with patch("httpx.AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=MagicMock(get=AsyncMock(return_value=mock_resp)))
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            resp = client_creds.post("/api/config/test-connection", json={
                "base_url": "http://localhost:11434/v1",
                "api_type": "ollama",
            })
        data = resp.json()
        assert data["ok"] is False

    def test_missing_base_url_returns_400(self, client_creds):
        resp = client_creds.post("/api/config/test-connection", json={
            "base_url": "",
            "api_key": "sk-test",
        })
        assert resp.status_code == 400

    def test_timeout_returns_ok_false(self, client_creds):
        import httpx as _httpx
        with patch("httpx.AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(
                return_value=MagicMock(post=AsyncMock(side_effect=_httpx.TimeoutException("timeout")))
            )
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            resp = client_creds.post("/api/config/test-connection", json={
                "base_url": "https://api.deepseek.com/v1",
                "api_key": "sk-test",
                "model": "deepseek-chat",
            })
        data = resp.json()
        assert data["ok"] is False
        assert "timed out" in data["message"].lower()


# ---------------------------------------------------------------------------
# POST /config/agents/{name}/test
# ---------------------------------------------------------------------------


class TestAgentTestConnection:
    def _mock_post_resp(self, status_code=200):
        resp = MagicMock()
        resp.status_code = status_code
        resp.json.return_value = {}
        return resp

    def test_agent_test_success(self, client_creds, mock_config_loader_extra):
        mock_resp = self._mock_post_resp(200)
        with patch("httpx.AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=MagicMock(post=AsyncMock(return_value=mock_resp)))
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            resp = client_creds.post("/api/config/agents/deepseek/test")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True

    def test_agent_test_not_found(self, client_creds):
        resp = client_creds.post("/api/config/agents/nobody/test")
        assert resp.status_code == 404

    def test_agent_test_auth_failure(self, client_creds, mock_cred_mgr):
        mock_resp = self._mock_post_resp(401)
        mock_cred_mgr.get_api_key.return_value = "bad-key"
        with patch("httpx.AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=MagicMock(post=AsyncMock(return_value=mock_resp)))
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            resp = client_creds.post("/api/config/agents/deepseek/test")
        data = resp.json()
        assert data["ok"] is False


# ---------------------------------------------------------------------------
# GET /config/settings  /  PATCH /config/settings
# ---------------------------------------------------------------------------


class TestSettings:
    def test_get_settings(self, client_creds, mock_config_loader_extra):
        resp = client_creds.get("/api/config/settings")
        assert resp.status_code == 200
        data = resp.json()
        assert "config_agent" in data
        assert data["config_agent"] == "deepseek"

    def test_patch_settings_update(self, client_creds, mock_config_loader_extra):
        resp = client_creds.patch("/api/config/settings", json={"config_agent": "openai"})
        assert resp.status_code == 200
        mock_config_loader_extra.save_system_config.assert_called_once()

    def test_patch_settings_null_is_noop(self, client_creds, mock_config_loader_extra):
        resp = client_creds.patch("/api/config/settings", json={"config_agent": None})
        assert resp.status_code == 200
        # save_system_config is still called (with unchanged value)
        mock_config_loader_extra.save_system_config.assert_called_once()


# ---------------------------------------------------------------------------
# POST /config/agents/{name}/set-key
# ---------------------------------------------------------------------------


class TestSetKey:
    def test_set_key_success(self, client_creds, mock_cred_mgr):
        resp = client_creds.post("/api/config/agents/deepseek/set-key", json={
            "api_key": "sk-new-key",
            "base_url_override": "",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "saved"
        assert data["name"] == "deepseek"
        mock_cred_mgr.save_api_key.assert_called_once_with("deepseek", "sk-new-key", base_url_override="")

    def test_set_key_with_base_url_override(self, client_creds, mock_cred_mgr):
        resp = client_creds.post("/api/config/agents/deepseek/set-key", json={
            "api_key": "sk-key",
            "base_url_override": "https://custom.endpoint.com/v1",
        })
        assert resp.status_code == 200
        mock_cred_mgr.save_api_key.assert_called_once_with(
            "deepseek", "sk-key", base_url_override="https://custom.endpoint.com/v1"
        )

    def test_set_key_not_found(self, client_creds):
        resp = client_creds.post("/api/config/agents/ghost/set-key", json={
            "api_key": "sk-x",
        })
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /config/agents/{name}/default-model
# ---------------------------------------------------------------------------


class TestSetDefaultModel:
    def test_set_default_model_success(self, client_creds, mock_cred_mgr):
        mock_cred_mgr.get_model_list.return_value = []
        resp = client_creds.post("/api/config/agents/deepseek/default-model", json={
            "model_id": "deepseek-reasoner",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "saved"
        assert data["default_model"] == "deepseek-reasoner"
        mock_cred_mgr.save_model_list.assert_called_once_with(
            "deepseek", [], default_model="deepseek-reasoner"
        )

    def test_set_default_model_not_found(self, client_creds):
        resp = client_creds.post("/api/config/agents/nobody/default-model", json={
            "model_id": "gpt-4o",
        })
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /config/credentials  /  DELETE /config/credentials/{id}
# ---------------------------------------------------------------------------


class TestCredentials:
    def test_list_credentials(self, client_creds, mock_cred_mgr):
        resp = client_creds.get("/api/config/credentials")
        assert resp.status_code == 200
        data = resp.json()
        assert "credentials" in data
        assert "deepseek" in data["credentials"]
        mock_cred_mgr.list_credentials.assert_called_once()

    def test_delete_credential(self, client_creds, mock_cred_mgr):
        resp = client_creds.delete("/api/config/credentials/deepseek")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "deleted"
        assert data["provider_id"] == "deepseek"
        mock_cred_mgr.delete.assert_called_once_with("deepseek")

    def test_no_cred_mgr_returns_503(self, tmp_path, mock_config_loader_extra):
        app = FastAPI()
        app.state.mq = MagicMock()
        app.state.config_loader = mock_config_loader_extra
        app.state.tool_registry = MagicMock(tools={})
        app.state.tool_executor = MagicMock()
        app.state.agent_registry = AgentRegistry()
        app.state.session_mgr = MagicMock(_sessions={})
        app.state.data_dir = str(tmp_path)
        app.state.credential_mgr = None
        app.include_router(api_router)
        c = TestClient(app)
        resp = c.get("/api/config/credentials")
        assert resp.status_code == 503


# ---------------------------------------------------------------------------
# GET /config/status
# ---------------------------------------------------------------------------


class TestConfigStatus:
    def test_status_with_cred_mgr(self, client_creds, mock_cred_mgr):
        resp = client_creds.get("/api/config/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "deepseek" in data["ready_providers"]

    def test_status_without_cred_mgr(self, tmp_path, mock_config_loader_extra):
        app = FastAPI()
        app.state.mq = MagicMock()
        app.state.config_loader = mock_config_loader_extra
        app.state.tool_registry = MagicMock(tools={})
        app.state.tool_executor = MagicMock()
        app.state.agent_registry = AgentRegistry()
        app.state.session_mgr = MagicMock(_sessions={})
        app.state.data_dir = str(tmp_path)
        app.state.credential_mgr = None
        app.include_router(api_router)
        c = TestClient(app)
        resp = c.get("/api/config/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "not_configured"
        assert data["ready_providers"] == []
