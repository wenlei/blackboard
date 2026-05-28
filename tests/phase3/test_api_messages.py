
from fastapi.testclient import TestClient


class TestApiMessages:
    def test_send_message(self, client: TestClient, active_session, mock_mq):
        resp = client.post(
            f"/api/sessions/{active_session}/messages",
            json={"content": "hello world"},
        )
        assert resp.status_code == 200
        assert resp.json() == {"status": "sent"}
        mock_mq.publish.assert_called_once()

    def test_send_message_session_not_found(self, client: TestClient):
        resp = client.post(
            "/api/sessions/ghost/messages",
            json={"content": "hello"},
        )
        assert resp.status_code == 404

    def test_execute_session(self, client: TestClient, active_session, mock_mq):
        resp = client.post(f"/api/sessions/{active_session}/execute")
        assert resp.status_code == 200
        assert resp.json() == {"status": "executing"}
        mock_mq.publish.assert_called_once()

    def test_execute_session_not_found(self, client: TestClient):
        resp = client.post("/api/sessions/ghost/execute")
        assert resp.status_code == 404

    def test_session_history(self, client: TestClient, active_session, tmp_path):
        from blackboard.logger.session_logger import SessionLogger

        sl = SessionLogger(active_session, str(tmp_path))
        sl.log_conversation("user", "hello")
        sl.log_event("session_created", {})

        resp = client.get(f"/api/sessions/{active_session}/history")
        assert resp.status_code == 200
        data = resp.json()
        assert "conversation" in data
        assert "messages" in data
        assert "events" in data

    def test_session_strategy(self, client: TestClient, active_session, tmp_path):
        from blackboard.logger.session_logger import SessionLogger

        sl = SessionLogger(active_session, str(tmp_path))
        sl.ensure_dir()
        (sl.dir / "strategy.psc").write_text("ARCHITECT: 设计方案")

        resp = client.get(f"/api/sessions/{active_session}/strategy")
        assert resp.status_code == 200
        assert resp.json()["psc"] == "ARCHITECT: 设计方案"

    def test_session_strategy_not_found(self, client: TestClient, active_session):
        resp = client.get(f"/api/sessions/{active_session}/strategy")
        assert resp.status_code == 404
