from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def ui_app(tmp_path):
    from blackboard.main import app

    app.state.session_mgr = MagicMock()
    app.state.session_mgr._sessions = {}
    app.state.agent_registry = MagicMock()
    app.state.agent_registry.list = MagicMock(return_value=[])
    app.state.tool_registry = MagicMock()
    app.state.tool_registry.tools = {}

    return app


@pytest.fixture
def ui_client(ui_app):
    return TestClient(ui_app)


class TestUIPages:
    def test_dashboard_page(self, ui_client: TestClient):
        resp = ui_client.get("/")
        assert resp.status_code == 200
        assert "text/html" in resp.headers.get("content-type", "")

    def test_sessions_create_page(self, ui_client: TestClient):
        resp = ui_client.get("/sessions")
        assert resp.status_code == 200
        assert "text/html" in resp.headers.get("content-type", "")

    def test_session_chat_page(self, ui_client: TestClient):
        resp = ui_client.get("/sessions/test-s1")
        assert resp.status_code == 200
        assert "text/html" in resp.headers.get("content-type", "")
