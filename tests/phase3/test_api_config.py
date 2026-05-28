
from fastapi.testclient import TestClient


class TestApiConfig:
    def test_get_agents(self, client: TestClient, mock_config_loader):
        resp = client.get("/api/config/agents")
        assert resp.status_code == 200
        assert "agents" in resp.json()
        mock_config_loader.load_agent_registry.assert_called_once()

    def test_add_agent(self, client: TestClient):
        resp = client.post(
            "/api/config/agents",
            json={
                "name": "qwen",
                "provider": "qwen",
                "display_name": "Qwen",
                "api_key_env": "QWEN_API_KEY",
                "base_url": "https://api.qwen.example.com/v1",
                "models": ["qwen-max"],
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "added"
        assert data["name"] == "qwen"

    def test_remove_registered_agent(self, client: TestClient):
        resp = client.delete("/api/config/agents/deepseek")
        assert resp.status_code == 200
        assert resp.json()["name"] == "deepseek"

    def test_remove_custom_agent(self, client: TestClient):
        # first add a custom agent
        client.post(
            "/api/config/agents",
            json={
                "name": "my-custom",
                "provider": "custom",
                "display_name": "My Custom",
                "api_key_env": "",
                "base_url": "https://custom.example.com/v1",
                "models": ["custom-model"],
            },
        )
        resp = client.delete("/api/config/agents/my-custom")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "removed"
        assert data["name"] == "my-custom"

    def test_get_templates(self, client: TestClient, mock_config_loader):
        resp = client.get("/api/config/templates")
        assert resp.status_code == 200
        assert "templates" in resp.json()
        mock_config_loader.load_strategy_templates.assert_called_once()

    def test_add_template(self, client: TestClient):
        resp = client.post(
            "/api/config/templates",
            json={
                "id": "new_template",
                "name": "新模板",
                "match_keywords": ["测试"],
                "steps": [{"order": 1, "agent_role": "auto", "action": "自动决策"}],
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "added"
        assert data["id"] == "new_template"

    def test_update_template(self, client: TestClient):
        resp = client.patch(
            "/api/config/templates/test_tmpl",
            json={"name": "更新后的模板"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "updated"
        assert data["id"] == "test_tmpl"

    def test_get_permissions_presets(self, client: TestClient, mock_config_loader):
        resp = client.get("/api/config/permissions/presets")
        assert resp.status_code == 200
        assert "presets" in resp.json()
        mock_config_loader.load_permission_presets.assert_called_once()

    def test_get_providers(self, client: TestClient, mock_config_loader):
        resp = client.get("/api/config/providers")
        assert resp.status_code == 200
        data = resp.json()
        assert "providers" in data
        providers = data["providers"]
        # Ollama is always present (hardcoded local provider)
        assert "ollama" in providers
        assert providers["ollama"]["auth_type"] == "none"
        assert providers["ollama"]["base_url"] == "http://localhost:11434/v1"

    def test_remove_any_registered_agent(self, client: TestClient, mock_config_loader):
        # Any agent in the registry — even one whose name matches a provider preset — is deletable
        agent_registry = mock_config_loader.load_agent_registry.return_value
        agent_registry.agents["openai"] = type("E", (), {
            "provider": "openai", "display_name": "OpenAI"
        })()
        resp = client.delete("/api/config/agents/openai")
        assert resp.status_code == 200

    def test_remove_nonexistent_agent_404(self, client: TestClient):
        resp = client.delete("/api/config/agents/nobody")
        assert resp.status_code == 404
