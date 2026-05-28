"""Tests for config endpoints and logic not covered by test_api_config_extra.py."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from blackboard.agents.registry import AgentRegistry
from blackboard.api.routes import (
    _dev_base_url, _execute_probe_url, _repair_truncated_json,
    _load_local_catalog, router as api_router,
)

# ---------------------------------------------------------------------------
# Minimal local-catalog payload (uses api_endpoint field, same as bundled JSON)
# ---------------------------------------------------------------------------

MOCK_DEV_DATA = {
    "deepseek": {
        "name": "DeepSeek",
        "api_endpoint": "https://api.deepseek.com/v1",
        "models": {
            "deepseek-chat": {"id": "deepseek-chat", "name": "DeepSeek Chat"},
        },
    },
    "openai": {
        "name": "OpenAI",
        "api_endpoint": "https://api.openai.com/v1",
        "models": {
            "gpt-4o": {"id": "gpt-4o", "name": "GPT-4o"},
        },
    },
}


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_cred_mgr():
    mgr = MagicMock()
    mgr.get_api_key.return_value = "sk-test"
    mgr.get_base_url_override.return_value = ""
    mgr.get_default_model.return_value = "deepseek-chat"
    mgr.get_model_list.return_value = []
    mgr.save_api_key.return_value = None
    mgr.save_model_list.return_value = None
    mgr.list_credentials.return_value = {}
    mgr.delete.return_value = None
    return mgr


@pytest.fixture
def mock_loader():
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
            model_dump=lambda: {"provider": "deepseek"},
        ),
    }
    agent_registry_mock.model_dump.return_value = {"agents": {"deepseek": {}}}
    loader.load_agent_registry.return_value = agent_registry_mock
    loader.save_agent_registry = MagicMock()

    tmpl_obj = MagicMock(id="tpl1", name="模板1", match_keywords=[], steps=[])
    tmpl_obj.model_dump.return_value = {"id": "tpl1", "name": "模板1", "match_keywords": [], "steps": []}
    templates_mock = MagicMock()
    templates_mock.templates = [tmpl_obj]
    templates_mock.model_dump.return_value = {"templates": [tmpl_obj.model_dump()]}
    loader.load_strategy_templates.return_value = templates_mock
    loader.save_strategy_templates = MagicMock()
    loader.save_system_config = MagicMock()

    tool_reg = MagicMock()
    tool_reg.tools = {"read_file": MagicMock(description="read"), "write_file": MagicMock(description="write")}
    tool_reg.model_dump.return_value = {"tools": {"read_file": {}, "write_file": {}}}
    loader.load_tool_registry.return_value = tool_reg

    return loader


@pytest.fixture
def app_gap(mock_cred_mgr, mock_loader, tmp_path):
    app = FastAPI()
    app.state.mq = MagicMock()
    app.state.config_loader = mock_loader
    app.state.tool_registry = mock_loader.load_tool_registry()
    app.state.tool_executor = MagicMock()
    app.state.agent_registry = AgentRegistry()
    app.state.session_mgr = MagicMock(_sessions={})
    app.state.data_dir = str(tmp_path)
    app.state.credential_mgr = mock_cred_mgr
    app.include_router(api_router)
    return app


@pytest.fixture
def client(app_gap):
    return TestClient(app_gap)


def _mock_post(status_code=200, body=None, text=""):
    resp = MagicMock()
    resp.status_code = status_code
    if body is not None:
        resp.json.return_value = body
        resp.text = json.dumps(body)
    else:
        resp.json.side_effect = Exception("not json")
        resp.text = text
    return resp


# ===========================================================================
# 1. _dev_base_url() unit tests
# ===========================================================================


class TestDevBaseUrl:
    def test_catalog_field_wins(self):
        assert _dev_base_url("deepseek", MOCK_DEV_DATA) == "https://api.deepseek.com/v1"

    def test_known_provider_returns_url(self):
        url = _dev_base_url("openai", MOCK_DEV_DATA)
        assert url == "https://api.openai.com/v1"

    def test_unknown_slug_returns_empty(self):
        assert _dev_base_url("completely-unknown-xyz", MOCK_DEV_DATA) == ""

    def test_local_catalog_covers_major_providers(self):
        catalog = _load_local_catalog()
        for slug in ["openai", "anthropic", "groq", "mistral", "xai", "deepseek", "togetherai", "cohere", "cerebras"]:
            url = _dev_base_url(slug, catalog)
            assert url, f"Local catalog missing api_endpoint for {slug}"

    def test_catalog_url_strips_trailing_slash(self):
        data = {"prov": {"api_endpoint": "https://api.example.com/v1/"}}
        assert _dev_base_url("prov", data) == "https://api.example.com/v1"

    def test_empty_api_endpoint_returns_empty(self):
        data = {"openai": {"api_endpoint": ""}}
        url = _dev_base_url("openai", data)
        assert url == ""


# ===========================================================================
# 1b. _repair_truncated_json() unit tests
# ===========================================================================


class TestRepairTruncatedJson:
    def test_closes_open_string(self):
        s = '{"base_url": "https://api.example.com/v1", "notes": "Some long note that was cut'
        repaired = _repair_truncated_json(s)
        result = json.loads(repaired)
        assert result["base_url"] == "https://api.example.com/v1"
        assert "cut" in result["notes"]

    def test_closes_open_brace(self):
        s = '{"base_url": "https://api.example.com/v1", "openai_compatible": true'
        repaired = _repair_truncated_json(s)
        result = json.loads(repaired)
        assert result["openai_compatible"] is True

    def test_handles_trailing_comma_after_truncation(self):
        s = '{"base_url": "https://x.com/v1", "openai_compatible": true,'
        repaired = _repair_truncated_json(s)
        result = json.loads(repaired)
        assert result["base_url"] == "https://x.com/v1"

    def test_complete_json_unchanged_in_meaning(self):
        s = '{"base_url": "https://x.com/v1", "openai_compatible": true}'
        repaired = _repair_truncated_json(s)
        assert json.loads(repaired) == json.loads(s)

    def test_escaped_quote_not_mistaken_for_string_end(self):
        s = '{"notes": "Use \\"x-api-key\\" header"}'
        repaired = _repair_truncated_json(s)
        result = json.loads(repaired)
        assert 'x-api-key' in result["notes"]


# ===========================================================================
# 2. PATCH /config/agents/{name}
# ===========================================================================


class TestPatchAgent:
    def test_patch_display_name(self, client, mock_loader):
        resp = client.patch("/api/config/agents/deepseek", json={"display_name": "DS-Pro"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "updated"
        assert data["name"] == "deepseek"
        mock_loader.save_agent_registry.assert_called_once()

    def test_patch_base_url(self, client, mock_loader):
        resp = client.patch("/api/config/agents/deepseek", json={"base_url": "https://custom.deepseek.com/v1"})
        assert resp.status_code == 200
        assert mock_loader.save_agent_registry.called

    def test_patch_not_found(self, client):
        resp = client.patch("/api/config/agents/nobody", json={"display_name": "X"})
        assert resp.status_code == 404


# ===========================================================================
# 3. DELETE /config/templates/{id}
# ===========================================================================


class TestDeleteTemplate:
    def test_delete_existing_template(self, client, mock_loader):
        resp = client.delete("/api/config/templates/tpl1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "removed"
        assert data["id"] == "tpl1"
        mock_loader.save_strategy_templates.assert_called_once()

    def test_delete_nonexistent_template_still_200(self, client):
        # endpoint removes by filter — non-existent id is a no-op, not 404
        resp = client.delete("/api/config/templates/ghost")
        assert resp.status_code == 200


# ===========================================================================
# 4. GET /config/tools
# ===========================================================================


class TestConfigTools:
    def test_returns_tool_list(self, client):
        resp = client.get("/api/config/tools")
        assert resp.status_code == 200
        data = resp.json()
        assert "tools" in data
        assert "read_file" in data["tools"]

    def test_tool_registry_none_falls_back_to_loader(self, app_gap, mock_loader):
        app_gap.state.tool_registry = None
        c = TestClient(app_gap)
        resp = c.get("/api/config/tools")
        assert resp.status_code == 200
        assert "tools" in resp.json()


# ===========================================================================
# 5. POST /config/agents/{name}/sync-models
# ===========================================================================


class TestSyncModels:
    def _make_models_response(self):
        return MagicMock(
            status_code=200,
            json=MagicMock(return_value={
                "data": [
                    {"id": "deepseek-chat", "name": "DeepSeek Chat"},
                    {"id": "deepseek-coder", "name": "DeepSeek Coder"},
                ]
            }),
        )

    def test_sync_returns_model_list(self, client, mock_cred_mgr):
        # Patch both _discover_models and _enrich_from_openrouter
        models_mock = [
            MagicMock(model_id="deepseek-chat", provider_id="", model_dump=lambda: {"model_id": "deepseek-chat"}),
        ]
        with patch("blackboard.api.routes._discover_models", new=AsyncMock(return_value=models_mock)), \
             patch("blackboard.api.routes._enrich_from_openrouter", new=AsyncMock(side_effect=lambda m, _: m)):
            resp = client.post("/api/config/agents/deepseek/sync-models")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) == 1
        mock_cred_mgr.save_model_list.assert_called_once()

    def test_sync_unknown_agent_returns_empty_list(self, client):
        resp = client.post("/api/config/agents/nobody/sync-models")
        assert resp.status_code == 200
        assert resp.json() == []


# ===========================================================================
# 6. POST /config/providers/{slug}/ask-config  (tool-calling version)
# ===========================================================================


def _llm_direct_body(content: str) -> dict:
    """Simulate LLM directly returning JSON without tool calls."""
    return {
        "choices": [{
            "finish_reason": "stop",
            "message": {"role": "assistant", "content": content, "tool_calls": None},
        }]
    }


def _llm_tool_call_body(url: str, call_id: str = "tc1") -> dict:
    """Simulate LLM requesting a probe_url tool call."""
    return {
        "choices": [{
            "finish_reason": "tool_calls",
            "message": {
                "role": "assistant",
                "content": None,
                "tool_calls": [{
                    "id": call_id,
                    "type": "function",
                    "function": {"name": "probe_url", "arguments": json.dumps({"url": url})},
                }],
            },
        }]
    }


class TestAskConfigAgent:
    GOOD_JSON = '{"base_url":"https://api.alibaba.com/v1","openai_compatible":true,"auth_header":"Authorization","notes":""}'

    def _mock_llm(self, *responses):
        """Build a mock httpx.AsyncClient whose .post() returns responses in sequence."""
        resp_mocks = [_mock_post(200, body=b) for b in responses]
        mc = MagicMock()
        mc.post = AsyncMock(side_effect=resp_mocks)
        mc.__aenter__ = AsyncMock(return_value=mc)
        mc.__aexit__ = AsyncMock(return_value=False)
        return mc

    def _run(self, client, llm_mock, probe_result=None):
        probe_mock = AsyncMock(return_value=probe_result or {"url": "x", "reachable": True, "status_code": 401})
        with patch("blackboard.api.routes._load_local_catalog", return_value=MOCK_DEV_DATA), \
             patch("httpx.AsyncClient", return_value=llm_mock), \
             patch("blackboard.api.routes._execute_probe_url", probe_mock):
            return client.post("/api/config/providers/alibaba/ask-config")

    # --- Precondition failures (unchanged) ---

    def test_no_api_key_returns_422(self, app_gap, mock_cred_mgr):
        mock_cred_mgr.get_api_key.return_value = None
        c = TestClient(app_gap)
        with patch("blackboard.api.routes._load_local_catalog", return_value=MOCK_DEV_DATA):
            resp = c.post("/api/config/providers/alibaba/ask-config")
        assert resp.status_code == 422
        assert "API key" in resp.json()["detail"]
        assert "Save" in resp.json()["detail"]

    def test_no_config_agent_returns_404(self, app_gap, mock_loader):
        mock_loader.load_system.return_value = MagicMock(config_agent="")
        c = TestClient(app_gap)
        with patch("blackboard.api.routes._load_local_catalog", return_value=MOCK_DEV_DATA):
            resp = c.post("/api/config/providers/alibaba/ask-config")
        assert resp.status_code == 404

    def test_no_cred_mgr_returns_503(self, app_gap):
        app_gap.state.credential_mgr = None
        c = TestClient(app_gap)
        with patch("blackboard.api.routes._load_local_catalog", return_value=MOCK_DEV_DATA):
            resp = c.post("/api/config/providers/alibaba/ask-config")
        assert resp.status_code == 503

    def test_config_agent_not_in_registry_returns_404(self, app_gap, mock_loader):
        mock_loader.load_system.return_value = MagicMock(config_agent="ghost-agent")
        c = TestClient(app_gap)
        with patch("blackboard.api.routes._load_local_catalog", return_value=MOCK_DEV_DATA):
            resp = c.post("/api/config/providers/alibaba/ask-config")
        assert resp.status_code == 404

    # --- Direct reply (no tool calls) ---

    def test_success_direct_json(self, client):
        mc = self._mock_llm(_llm_direct_body(self.GOOD_JSON))
        resp = self._run(client, mc)
        assert resp.status_code == 200
        data = resp.json()
        assert data["base_url"] == "https://api.alibaba.com/v1"
        assert data["openai_compatible"] is True
        assert data["agent"] == "deepseek"

    def test_success_python_literals_repaired(self, client):
        content = '{"base_url":"https://example.com/v1","openai_compatible":True,"auth_header":"Authorization","notes":None}'
        mc = self._mock_llm(_llm_direct_body(content))
        resp = self._run(client, mc)
        assert resp.status_code == 200
        assert resp.json()["openai_compatible"] is True

    def test_success_trailing_comma_repaired(self, client):
        content = '{"base_url":"https://example.com/v1","openai_compatible":true,"auth_header":"Authorization","notes":"ok",}'
        mc = self._mock_llm(_llm_direct_body(content))
        resp = self._run(client, mc)
        assert resp.status_code == 200

    def test_success_markdown_fence_stripped(self, client):
        content = '```json\n' + self.GOOD_JSON + '\n```'
        mc = self._mock_llm(_llm_direct_body(content))
        resp = self._run(client, mc)
        assert resp.status_code == 200
        assert resp.json()["base_url"] == "https://api.alibaba.com/v1"

    def test_success_truncated_string_repaired(self, client):
        truncated = '{"base_url":"https://api.alibaba.com/v1","openai_compatible":true,"auth_header":"Authorization","notes":"Rate limits apply'
        mc = self._mock_llm(_llm_direct_body(truncated))
        resp = self._run(client, mc)
        assert resp.status_code == 200
        assert resp.json()["base_url"] == "https://api.alibaba.com/v1"

    def test_success_truncated_missing_brace(self, client):
        truncated = '{"base_url":"https://api.alibaba.com/v1","openai_compatible":true,"auth_header":"Authorization","notes":"ok"'
        mc = self._mock_llm(_llm_direct_body(truncated))
        resp = self._run(client, mc)
        assert resp.status_code == 200

    # --- Tool-calling flow ---

    def test_tool_call_then_direct_answer(self, client):
        """LLM probes one URL, then returns the final JSON."""
        probe_url = "https://api.alibaba.com/v1"
        mc = self._mock_llm(
            _llm_tool_call_body(probe_url),       # turn 1: call probe_url
            _llm_direct_body(self.GOOD_JSON),     # turn 2: return answer
        )
        probe_result = {"url": probe_url, "reachable": True, "status_code": 401}
        resp = self._run(client, mc, probe_result=probe_result)
        assert resp.status_code == 200
        assert resp.json()["base_url"] == "https://api.alibaba.com/v1"

    def test_tool_call_probe_unreachable_llm_tries_another(self, client):
        """LLM probes a bad URL (unreachable), probes a second, then answers."""
        mc = self._mock_llm(
            _llm_tool_call_body("https://wrong.url.example.com/v1", "tc1"),
            _llm_tool_call_body("https://api.alibaba.com/v1", "tc2"),
            _llm_direct_body(self.GOOD_JSON),
        )
        probe_results = [
            {"url": "https://wrong.url.example.com/v1", "reachable": False, "error": "connection refused"},
            {"url": "https://api.alibaba.com/v1", "reachable": True, "status_code": 401},
        ]
        probe_mock = AsyncMock(side_effect=probe_results)
        with patch("blackboard.api.routes._load_local_catalog", return_value=MOCK_DEV_DATA), \
             patch("httpx.AsyncClient", return_value=mc), \
             patch("blackboard.api.routes._execute_probe_url", probe_mock):
            resp = client.post("/api/config/providers/alibaba/ask-config")
        assert resp.status_code == 200
        assert probe_mock.call_count == 2

    def test_request_includes_tools_and_stream_false(self, client):
        mc = self._mock_llm(_llm_direct_body(self.GOOD_JSON))
        self._run(client, mc)
        call_kwargs = mc.post.call_args
        payload = call_kwargs[1].get("json") or call_kwargs[0][1]
        assert payload.get("stream") is False
        assert "max_tokens" not in payload
        assert "tools" in payload
        assert payload["tools"][0]["function"]["name"] == "probe_url"

    # --- Failure paths ---

    def test_http_500_returns_502(self, client):
        bad = MagicMock()
        bad.post = AsyncMock(return_value=_mock_post(500, text="Server Error"))
        bad.__aenter__ = AsyncMock(return_value=bad)
        bad.__aexit__ = AsyncMock(return_value=False)
        with patch("blackboard.api.routes._load_local_catalog", return_value=MOCK_DEV_DATA), \
             patch("blackboard.api.routes._execute_probe_url", AsyncMock()), \
             patch("httpx.AsyncClient", return_value=bad):
            resp = client.post("/api/config/providers/alibaba/ask-config")
        assert resp.status_code == 502

    def test_empty_content_returns_502(self, client):
        mc = self._mock_llm(_llm_direct_body(""))
        resp = self._run(client, mc)
        assert resp.status_code == 502
        assert "empty" in resp.json()["detail"].lower()

    def test_no_json_object_returns_502(self, client):
        # First turn: prose reply → triggers json-only retry
        # Second turn: still no JSON → final 502
        mc = self._mock_llm(
            _llm_direct_body("I don't know this provider."),
            _llm_direct_body("Still no JSON here."),
        )
        resp = self._run(client, mc)
        assert resp.status_code == 502
        assert "JSON" in resp.json()["detail"]

    def test_non_json_response_body_returns_502(self, client):
        bad = MagicMock()
        resp_mock = MagicMock(status_code=200)
        resp_mock.json.side_effect = Exception("not json")
        resp_mock.text = "data: event\n\n"
        bad.post = AsyncMock(return_value=resp_mock)
        bad.__aenter__ = AsyncMock(return_value=bad)
        bad.__aexit__ = AsyncMock(return_value=False)
        with patch("blackboard.api.routes._load_local_catalog", return_value=MOCK_DEV_DATA), \
             patch("blackboard.api.routes._execute_probe_url", AsyncMock()), \
             patch("httpx.AsyncClient", return_value=bad):
            resp = client.post("/api/config/providers/alibaba/ask-config")
        assert resp.status_code == 502
        assert "non-JSON" in resp.json()["detail"]


# ===========================================================================
# 7. _execute_probe_url unit tests
# ===========================================================================


class TestExecuteProbeUrl:
    @pytest.mark.asyncio
    async def test_401_is_reachable(self):
        mock_resp = MagicMock(status_code=401)
        with patch("httpx.AsyncClient") as mc:
            mc.return_value.__aenter__ = AsyncMock(return_value=MagicMock(get=AsyncMock(return_value=mock_resp)))
            mc.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await _execute_probe_url("https://api.example.com/v1")
        assert result["reachable"] is True
        assert result["status_code"] == 401

    @pytest.mark.asyncio
    async def test_connection_error_not_reachable(self):
        import httpx as _httpx
        with patch("httpx.AsyncClient") as mc:
            mc.return_value.__aenter__ = AsyncMock(
                return_value=MagicMock(get=AsyncMock(side_effect=_httpx.ConnectError("refused")))
            )
            mc.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await _execute_probe_url("https://bad.example.com/v1")
        assert result["reachable"] is False
        assert "connection refused" in result["error"]
