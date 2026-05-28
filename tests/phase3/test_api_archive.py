from pathlib import Path

from fastapi.testclient import TestClient


class TestApiArchive:
    def test_archive_session(self, client: TestClient, active_session, tmp_path):
        ses_dir = Path(tmp_path) / active_session
        ses_dir.mkdir(parents=True, exist_ok=True)
        (ses_dir / "config.json").write_text('{"test":true}')

        resp = client.post(
            f"/api/sessions/{active_session}/archive",
            json={"remote_type": "local_nas", "remote_path": "/mnt/nas/blackboard/"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "archived"
        assert "archive" in data

    def test_archive_session_not_found(self, client: TestClient):
        resp = client.post(
            "/api/sessions/ghost/archive",
            json={"remote_type": "local_nas", "remote_path": "/mnt/nas/"},
        )
        assert resp.status_code == 404

    def test_get_archive_not_found(self, client: TestClient):
        resp = client.get("/api/sessions/ghost/archive")
        assert resp.status_code == 404
