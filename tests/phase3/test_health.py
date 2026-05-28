from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient


@pytest.fixture
def health_app(mock_mq, mock_tool_registry):
    app = FastAPI()
    mock_session_mgr = MagicMock()
    mock_session_mgr._sessions = {}

    app.state.mq = mock_mq
    app.state.tool_registry = mock_tool_registry
    app.state.session_mgr = mock_session_mgr

    @app.get("/health")
    async def health(request: Request):
        redis_ok = await request.app.state.mq.health_check()
        tool_count = (
            len(request.app.state.tool_registry.tools)
            if request.app.state.tool_registry
            else 0
        )
        sessions = len(request.app.state.session_mgr._sessions)
        return {
            "status": "ok" if redis_ok else "degraded",
            "redis": "connected" if redis_ok else "disconnected",
            "tools_loaded": tool_count,
            "active_sessions": sessions,
        }

    return app


@pytest.fixture
def health_client(health_app):
    return TestClient(health_app)


class TestHealth:
    def test_health_all_ok(self, health_client: TestClient):
        resp = health_client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["redis"] == "connected"
        assert data["tools_loaded"] == 2
        assert data["active_sessions"] == 0

    def test_health_redis_down(self, health_client: TestClient, mock_mq):
        mock_mq.health_check = AsyncMock(return_value=False)
        resp = health_client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "degraded"
        assert data["redis"] == "disconnected"
