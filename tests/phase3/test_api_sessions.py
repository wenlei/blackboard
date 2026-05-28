
from fastapi.testclient import TestClient


class TestApiSessions:
    def test_create_session(self, client: TestClient, mock_session_mgr):
        body = {
            "session_id": "test-s1",
            "agents": [
                {"name": "dp", "provider": "deepseek", "role": "程序员"}
            ],
            "permissions": {"mode": "whitelist"},
        }
        mock_session_mgr.create.return_value = {
            "session_id": "test-s1",
            "agents": [{"name": "dp", "provider": "deepseek", "role": "程序员"}],
            "permissions": {"mode": "whitelist", "operations": {}},
        }

        resp = client.post("/api/sessions", json=body)
        assert resp.status_code == 200
        data = resp.json()
        assert data["session_id"] == "test-s1"
        mock_session_mgr.create.assert_called_once()

    def test_create_session_conflict(self, client: TestClient, mock_session_mgr):
        mock_session_mgr.create.side_effect = ValueError("test-s1 already exists")

        resp = client.post(
            "/api/sessions",
            json={
                "session_id": "test-s1",
                "agents": [{"name": "dp", "provider": "deepseek", "role": "程序员"}],
            },
        )
        assert resp.status_code == 409

    def test_get_session(self, client: TestClient, active_session, mock_session_mgr):
        resp = client.get(f"/api/sessions/{active_session}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["session_id"] == "test-s1"
        assert data["status"] == "active"
        assert "agent_roles" in data

    def test_get_session_not_found(self, client: TestClient):
        resp = client.get("/api/sessions/ghost")
        assert resp.status_code == 404

    def test_pause_session(self, client: TestClient, active_session, mock_session_mgr):
        resp = client.post(f"/api/sessions/{active_session}/pause")
        assert resp.status_code == 200
        assert resp.json() == {"status": "paused"}
        mock_session_mgr.pause.assert_called_once_with(active_session)

    def test_pause_session_not_found(self, client: TestClient, mock_session_mgr):
        mock_session_mgr.pause.side_effect = ValueError("ghost not found")
        resp = client.post("/api/sessions/ghost/pause")
        assert resp.status_code == 404

    def test_resume_session(self, client: TestClient, active_session, mock_session_mgr):
        resp = client.post(f"/api/sessions/{active_session}/resume")
        assert resp.status_code == 200
        assert resp.json() == {"status": "active"}
        mock_session_mgr.resume.assert_called_once_with(active_session)

    def test_close_session(self, client: TestClient, active_session, mock_session_mgr):
        resp = client.delete(f"/api/sessions/{active_session}")
        assert resp.status_code == 200
        assert resp.json() == {"status": "closed"}
        mock_session_mgr.close.assert_called_once_with(active_session)

    def test_close_session_not_found(self, client: TestClient, mock_session_mgr):
        mock_session_mgr.close.side_effect = ValueError("ghost not found")
        resp = client.delete("/api/sessions/ghost")
        assert resp.status_code == 404
