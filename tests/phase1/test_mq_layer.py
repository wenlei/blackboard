import os

import pytest

from blackboard.mq.redis_streams import STREAMS, MQLayer, _stream_key

pytestmark = pytest.mark.skipif(
    not os.environ.get("WITH_REDIS"),
    reason="Set WITH_REDIS=1 and ensure Redis is running on localhost:6379",
)


def _redis_available():
    import asyncio

    async def _check():
        import redis.asyncio as redis

        client = redis.Redis(host="localhost", port=6379, socket_connect_timeout=1)
        try:
            await client.ping()
            return True
        except Exception:
            return False
        finally:
            await client.aclose()

    return asyncio.run(_check())


@pytest.mark.skipif(not _redis_available(), reason="Redis not available on localhost:6379")
@pytest.mark.asyncio
class TestMQLayer:
    async def test_connect_and_health(self):
        mq = MQLayer()
        await mq.connect()
        try:
            assert await mq.health_check() is True
        finally:
            await mq.disconnect()

    async def test_init_session_streams(self):
        mq = MQLayer()
        await mq.connect()
        try:
            await mq.init_session_streams("test-mq-001")
            for name in STREAMS:
                key = _stream_key("test-mq-001", name)
                exists = await mq.client.exists(key)
                assert exists == 1, f"Stream {key} should exist"
            await mq.destroy_session_streams("test-mq-001")
        finally:
            await mq.disconnect()

    async def test_publish_and_consume(self):
        mq = MQLayer()
        await mq.connect()
        try:
            await mq.init_session_streams("test-mq-002")
            msg_id = await mq.publish("test-mq-002", "inbox", {"type": "chat", "content": "hello"})
            assert msg_id is not None

            msgs = await mq.consume(
                "test-mq-002", "inbox", "inbox", "host-1", count=1, block_ms=2000
            )
            assert len(msgs) == 1
            assert msgs[0]["data"]["payload"]["type"] == "chat"
            assert msgs[0]["data"]["payload"]["content"] == "hello"

            await mq.ack("test-mq-002", "inbox", "inbox", [msgs[0]["id"]])
            await mq.destroy_session_streams("test-mq-002")
        finally:
            await mq.disconnect()

    async def test_message_ack_removes_from_pel(self):
        mq = MQLayer()
        await mq.connect()
        try:
            await mq.init_session_streams("test-mq-003")
            await mq.publish("test-mq-003", "inbox", {"type": "test"})

            msgs = await mq.consume(
                "test-mq-003", "inbox", "inbox", "host-1", count=1, block_ms=2000
            )
            assert len(msgs) == 1

            before = await mq.pending("test-mq-003", "inbox", "inbox")
            assert len(before) == 1

            await mq.ack("test-mq-003", "inbox", "inbox", [msgs[0]["id"]])

            after = await mq.pending("test-mq-003", "inbox", "inbox")
            assert len(after) == 0

            await mq.destroy_session_streams("test-mq-003")
        finally:
            await mq.disconnect()

    async def test_consumer_group_contention(self):
        mq = MQLayer()
        await mq.connect()
        try:
            await mq.init_session_streams("test-mq-004")
            await mq.publish("test-mq-004", "inbox", {"type": "test"})

            msgs1 = await mq.consume(
                "test-mq-004", "inbox", "inbox", "host-1", count=1, block_ms=2000
            )
            msgs2 = await mq.consume(
                "test-mq-004", "inbox", "inbox", "host-2", count=1, block_ms=500
            )

            consumed = len(msgs1) + len(msgs2)
            assert consumed == 1, f"Only 1 consumer should get the message, got {consumed}"

            if msgs1:
                await mq.ack("test-mq-004", "inbox", "inbox", [msgs1[0]["id"]])
            if msgs2:
                await mq.ack("test-mq-004", "inbox", "inbox", [msgs2[0]["id"]])

            await mq.destroy_session_streams("test-mq-004")
        finally:
            await mq.disconnect()

    async def test_destroy_session_streams(self):
        mq = MQLayer()
        await mq.connect()
        try:
            await mq.init_session_streams("test-mq-005")
            await mq.destroy_session_streams("test-mq-005")
            for name in STREAMS:
                key = _stream_key("test-mq-005", name)
                exists = await mq.client.exists(key)
                assert exists == 0, f"Stream {key} should be deleted"
        finally:
            await mq.disconnect()

    async def test_multi_session_isolation(self):
        mq = MQLayer()
        await mq.connect()
        try:
            await mq.init_session_streams("test-mq-006")
            await mq.init_session_streams("test-mq-007")

            await mq.publish("test-mq-006", "inbox", {"msg": "session-006"})
            await mq.publish("test-mq-007", "inbox", {"msg": "session-007"})

            msgs_6 = await mq.consume(
                "test-mq-006", "inbox", "inbox", "host-6", count=1, block_ms=2000
            )
            msgs_7 = await mq.consume(
                "test-mq-007", "inbox", "inbox", "host-7", count=1, block_ms=2000
            )

            assert len(msgs_6) == 1
            assert len(msgs_7) == 1
            assert msgs_6[0]["data"]["payload"]["msg"] == "session-006"
            assert msgs_7[0]["data"]["payload"]["msg"] == "session-007"

            await mq.ack("test-mq-006", "inbox", "inbox", [msgs_6[0]["id"]])
            await mq.ack("test-mq-007", "inbox", "inbox", [msgs_7[0]["id"]])
            await mq.destroy_session_streams("test-mq-006")
            await mq.destroy_session_streams("test-mq-007")
        finally:
            await mq.disconnect()

    async def test_publish_with_target_channel(self):
        mq = MQLayer()
        await mq.connect()
        try:
            await mq.init_session_streams("test-mq-008")
            await mq.publish("test-mq-008", "outbox", {"text": "hello"}, target_channel="telegram")
            msgs = await mq.consume(
                "test-mq-008", "outbox", "outbox", "api-1", count=1, block_ms=2000
            )
            assert len(msgs) == 1
            assert msgs[0]["data"]["target_channel"] == "telegram"

            await mq.ack("test-mq-008", "outbox", "outbox", [msgs[0]["id"]])
            await mq.destroy_session_streams("test-mq-008")
        finally:
            await mq.disconnect()

    async def test_consume_empty_stream(self):
        mq = MQLayer()
        await mq.connect()
        try:
            await mq.init_session_streams("test-mq-009")
            msgs = await mq.consume(
                "test-mq-009", "inbox", "inbox", "host-1", count=1, block_ms=500
            )
            assert len(msgs) == 0
            await mq.destroy_session_streams("test-mq-009")
        finally:
            await mq.disconnect()

    async def test_stream_key_format(self):
        key = _stream_key("my-session", "inbox")
        assert key == "session:my-session:inbox"

    async def test_all_six_streams_created(self):
        mq = MQLayer()
        await mq.connect()
        try:
            await mq.init_session_streams("test-mq-010")
            for name in STREAMS:
                key = _stream_key("test-mq-010", name)
                exists = await mq.client.exists(key)
                assert exists == 1, f"Stream {key} should exist"
            await mq.destroy_session_streams("test-mq-010")
        finally:
            await mq.disconnect()
