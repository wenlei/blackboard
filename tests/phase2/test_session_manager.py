import asyncio
import json
import tempfile
from pathlib import Path

import pytest

from blackboard.agents.registry import AgentRegistry
from blackboard.config.loader import ConfigLoader
from blackboard.mq.redis_streams import MQLayer
from blackboard.session.manager import SessionManager


@pytest.fixture
async def session_mgr(redis_available):
    if not redis_available:
        pytest.skip("Redis not available")
    mq = MQLayer()
    await mq.connect()
    loader = ConfigLoader("config")
    reg = AgentRegistry()
    with tempfile.TemporaryDirectory() as tmpdir:
        mgr = SessionManager(mq, loader, reg, data_dir=tmpdir)
        yield mgr
    await mq.disconnect()


class TestSessionManager:
    @pytest.mark.asyncio
    async def test_create_session(self, session_mgr):
        agents = [{"name": "dp", "provider": "deepseek", "role": "程序员"}]
        config = await session_mgr.create("test-s1", agents)
        assert config["session_id"] == "test-s1"
        assert "test-s1" in session_mgr._sessions
        assert session_mgr._sessions["test-s1"]["status"] == "active"

        ses_dir = session_mgr.data_dir / "test-s1"
        assert (ses_dir / "config.json").exists()

        await session_mgr.close("test-s1")

    @pytest.mark.asyncio
    async def test_create_duplicate_rejected(self, session_mgr):
        agents = [{"name": "dp", "provider": "deepseek", "role": "程序员"}]
        await session_mgr.create("test-s2", agents)
        with pytest.raises(ValueError, match="already exists"):
            await session_mgr.create("test-s2", agents)
        await session_mgr.close("test-s2")

    @pytest.mark.asyncio
    async def test_pause_resume(self, session_mgr):
        agents = [{"name": "dp", "provider": "deepseek", "role": "助手"}]
        await session_mgr.create("test-s3", agents)
        assert session_mgr._sessions["test-s3"]["status"] == "active"

        await session_mgr.pause("test-s3")
        assert session_mgr._sessions["test-s3"]["status"] == "paused"

        await session_mgr.resume("test-s3")
        assert session_mgr._sessions["test-s3"]["status"] == "active"

        await session_mgr.close("test-s3")

    @pytest.mark.asyncio
    async def test_close_session(self, session_mgr):
        agents = [{"name": "dp", "provider": "deepseek", "role": "助手"}]
        await session_mgr.create("test-s4", agents)
        await session_mgr.close("test-s4")
        assert "test-s4" not in session_mgr._sessions

    @pytest.mark.asyncio
    async def test_add_remove_agent(self, session_mgr):
        agents = [{"name": "dp", "provider": "deepseek", "role": "程序员"}]
        await session_mgr.create("test-s5", agents)

        await session_mgr.add_agent("test-s5", "cl", "claude", "审查者")
        assert "审查者" in session_mgr._sessions["test-s5"]["agent_roles"]

        await session_mgr.remove_agent("test-s5", "cl")
        assert "审查者" not in session_mgr._sessions["test-s5"]["agent_roles"]

        await session_mgr.close("test-s5")

    @pytest.mark.asyncio
    async def test_config_json_content(self, session_mgr):
        agents = [
            {"name": "dp", "provider": "deepseek", "role": "程序员"},
            {"name": "cl", "provider": "claude", "role": "架构师"},
        ]
        await session_mgr.create("test-s6", agents)

        ses_dir = session_mgr.data_dir / "test-s6"
        with open(ses_dir / "config.json") as f:
            data = json.load(f)
        assert len(data["agents"]) == 2
        assert data["permissions"]["mode"] == "whitelist"

        await session_mgr.close("test-s6")

    @pytest.mark.asyncio
    async def test_pause_nonexistent_raises(self, session_mgr):
        with pytest.raises(ValueError, match="not found"):
            await session_mgr.pause("ghost")

    @pytest.mark.asyncio
    async def test_close_nonexistent_raises(self, session_mgr):
        with pytest.raises(ValueError, match="not found"):
            await session_mgr.close("ghost")
