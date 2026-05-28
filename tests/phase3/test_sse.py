
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def sse_app(mock_mq):
    app = FastAPI()
    app.state.mq = mock_mq
    from blackboard.api.routes import router as api_router
    app.include_router(api_router)
    return app


@pytest.fixture
def sse_client(sse_app):
    return TestClient(sse_app)


class TestSSE:
    def test_events_stream_route_exists(self, sse_app):
        route_paths = [r.path for r in sse_app.routes]
        assert "/api/events/stream" in route_paths

    def test_events_stream_resolves(self, sse_app):
        for route in sse_app.routes:
            if route.path == "/api/events/stream":
                assert "GET" in route.methods
                return
        pytest.fail("SSE route not found")
