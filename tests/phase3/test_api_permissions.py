
from fastapi.testclient import TestClient


class TestApiPermissions:
    def test_update_permission_mode(self, client: TestClient, active_session, mock_session_mgr):
        resp = client.patch(
            f"/api/sessions/{active_session}/permissions",
            json={"mode": "open"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "updated"

    def test_update_permission_operations(
        self, client: TestClient, active_session, mock_session_mgr
    ):
        resp = client.patch(
            f"/api/sessions/{active_session}/permissions",
            json={"operations": {"chat": "allowed", "file_write": "denied"}},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "updated"

    def test_update_permissions_session_not_found(self, client: TestClient):
        resp = client.patch(
            "/api/sessions/ghost/permissions",
            json={"mode": "open"},
        )
        assert resp.status_code == 404
