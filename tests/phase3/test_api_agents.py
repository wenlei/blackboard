
from fastapi.testclient import TestClient


class TestApiAgents:
    def test_add_agent(self, client: TestClient, active_session, mock_session_mgr):
        resp = client.post(
            f"/api/sessions/{active_session}/agents",
            json={"name": "gp", "provider": "openai", "role": "测试者"},
        )
        assert resp.status_code == 200
        assert resp.json() == {"status": "added"}
        mock_session_mgr.add_agent.assert_called_once()

    def test_add_agent_session_not_found(self, client: TestClient, mock_session_mgr):
        mock_session_mgr.add_agent.side_effect = ValueError("ghost not found")
        resp = client.post(
            "/api/sessions/ghost/agents",
            json={"name": "gp", "provider": "openai", "role": "测试者"},
        )
        assert resp.status_code == 404

    def test_remove_agent(self, client: TestClient, active_session, mock_session_mgr):
        resp = client.delete(f"/api/sessions/{active_session}/agents/cl")
        assert resp.status_code == 200
        assert resp.json() == {"status": "removed"}
        mock_session_mgr.remove_agent.assert_called_once_with(active_session, "cl")

    def test_update_agent(self, client: TestClient, active_session):
        resp = client.patch(
            f"/api/sessions/{active_session}/agents/dp",
            json={"role": "新角色"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "updated"
        assert data["changes"] == {"role": "新角色"}

    def test_update_agent_session_not_found(self, client: TestClient):
        resp = client.patch(
            "/api/sessions/ghost/agents/dp",
            json={"role": "新角色"},
        )
        assert resp.status_code == 404
