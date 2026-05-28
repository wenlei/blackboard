import json

import pytest

from blackboard.mq.redis_streams import MQLayer

SESSION_ID = "test-mq-001"


@pytest.fixture
async def mq(redis_available):
    if not redis_available:
        pytest.skip("Redis not available")
    layer = MQLayer()
    await layer.connect()
    await layer.init_session_streams(SESSION_ID)
    yield layer
    await layer.destroy_session_streams(SESSION_ID)
    await layer.disconnect()


class TestMQLayer:
    @pytest.mark.asyncio
    async def test_health_check(self, mq):
        assert await mq.health_check()

    @pytest.mark.asyncio
    async def test_publish(self, mq):
        msg_id = await mq.publish(SESSION_ID, "inbox", {"type": "chat", "content": "hello"})
        assert msg_id is not None

    @pytest.mark.asyncio
    async def test_consume(self, mq):
        await mq.publish(SESSION_ID, "inbox", {"type": "chat", "content": "test-consume"})
        msgs = await mq.consume(SESSION_ID, "inbox", "inbox", "test-consumer-1", count=1, block_ms=2000)
        assert len(msgs) == 1
        assert msgs[0]["data"]["payload"]["content"] == "test-consume"

    @pytest.mark.asyncio
    async def test_ack(self, mq):
        await mq.publish(SESSION_ID, "inbox", {"type": "chat", "content": "ack-me"})
        msgs = await mq.consume(SESSION_ID, "inbox", "inbox", "test-consumer-2", count=1, block_ms=2000)
        assert len(msgs) == 1
        await mq.ack(SESSION_ID, "inbox", "inbox", [msgs[0]["id"]])
        pending = await mq.pending(SESSION_ID, "inbox", "inbox")
        assert len(pending) == 0

    @pytest.mark.asyncio
    async def test_pending_unacked(self, mq):
        await mq.publish(SESSION_ID, "inbox", {"type": "chat", "content": "not-acked"})
        msgs = await mq.consume(SESSION_ID, "inbox", "inbox", "test-consumer-3", count=1, block_ms=2000)
        assert len(msgs) == 1
        pending = await mq.pending(SESSION_ID, "inbox", "inbox")
        assert len(pending) == 1
        await mq.ack(SESSION_ID, "inbox", "inbox", [msgs[0]["id"]])

    @pytest.mark.asyncio
    async def test_session_isolation(self, mq):
        session_a = "test-mq-a"
        session_b = "test-mq-b"
        await mq.init_session_streams(session_a)
        await mq.init_session_streams(session_b)

        await mq.publish(session_a, "inbox", {"session": "a"})
        await mq.publish(session_b, "inbox", {"session": "b"})

        msgs_a = await mq.consume(session_a, "inbox", "inbox", "iso-a", count=1, block_ms=2000)
        msgs_b = await mq.consume(session_b, "inbox", "inbox", "iso-b", count=1, block_ms=2000)

        assert msgs_a[0]["data"]["payload"]["session"] == "a"
        assert msgs_b[0]["data"]["payload"]["session"] == "b"

        await mq.destroy_session_streams(session_a)
        await mq.destroy_session_streams(session_b)

    @pytest.mark.asyncio
    async def test_target_channel(self, mq):
        await mq.publish(SESSION_ID, "outbox", {"text": "hi"}, target_channel="telegram")
        msgs = await mq.consume(SESSION_ID, "outbox", "outbox", "ch-test", count=1, block_ms=2000)
        assert msgs[0]["data"]["target_channel"] == "telegram"
