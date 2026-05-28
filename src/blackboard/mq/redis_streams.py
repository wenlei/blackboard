import json
import logging
from datetime import datetime, timezone
from typing import Any

import redis.asyncio as redis
from redis.asyncio import Redis

logger = logging.getLogger(__name__)

STREAMS = ["inbox", "outbox", "dispatched", "results", "approvals", "events"]


def _stream_key(session_id: str, name: str) -> str:
    return f"session:{session_id}:{name}"


class MQLayer:
    def __init__(self, redis_url: str = "redis://localhost:6379", max_connections: int = 10):
        self.redis_url = redis_url
        self._pool: redis.ConnectionPool | None = None
        self._client: Redis | None = None
        self._max_connections = max_connections

    async def connect(self):
        self._pool = redis.ConnectionPool.from_url(
            self.redis_url, max_connections=self._max_connections
        )
        self._client = Redis(connection_pool=self._pool)
        await self._client.ping()
        logger.info("MQ Layer connected to Redis (%s)", self.redis_url)

    async def disconnect(self):
        if self._client:
            await self._client.aclose()
        if self._pool:
            await self._pool.disconnect()
        logger.info("MQ Layer disconnected")

    @property
    def client(self) -> Redis:
        if not self._client:
            raise RuntimeError("MQ Layer not connected. Call connect() first.")
        return self._client

    async def publish(
        self, session_id: str, stream_name: str, payload: dict[str, Any], target_channel: str | None = None
    ) -> str:
        key = _stream_key(session_id, stream_name)
        msg = {
            "session_id": session_id,
            "stream": stream_name,
            "payload": payload,
            "target_channel": target_channel,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        return await self.client.xadd(key, {"data": json.dumps(msg)})

    async def consume(
        self,
        session_id: str,
        stream_name: str,
        consumer_group: str,
        consumer_name: str,
        count: int = 1,
        block_ms: int = 5000,
    ) -> list[dict[str, Any]]:
        key = _stream_key(session_id, stream_name)
        try:
            result = await self.client.xreadgroup(
                consumer_group, consumer_name, {key: ">"}, count=count, block=block_ms
            )
        except redis.ResponseError as e:
            if "NOGROUP" in str(e):
                logger.warning("Consumer group %s not found for %s", consumer_group, key)
                return []
            raise

        messages = []
        for stream_key, entries in result:
            for msg_id, fields in entries:
                messages.append({
                    "id": msg_id,
                    "stream": stream_key.decode(),
                    "data": json.loads(fields[b"data"]),
                })
        return messages

    async def read_from(
        self,
        session_id: str,
        stream_name: str,
        last_id: str = "$",
        count: int = 10,
        block_ms: int = 5000,
    ) -> list[dict[str, Any]]:
        """Fan-out read using XREAD. Each caller tracks its own last_id cursor."""
        key = _stream_key(session_id, stream_name)
        try:
            result = await self.client.xread({key: last_id}, count=count, block=block_ms)
        except Exception:
            return []

        messages = []
        for stream_key, entries in (result or []):
            for msg_id, fields in entries:
                messages.append({
                    "id": msg_id.decode() if isinstance(msg_id, bytes) else msg_id,
                    "stream": stream_key.decode() if isinstance(stream_key, bytes) else stream_key,
                    "data": json.loads(fields[b"data"]),
                })
        return messages

    async def ack(self, session_id: str, stream_name: str, consumer_group: str, message_ids: list[str]):
        key = _stream_key(session_id, stream_name)
        await self.client.xack(key, consumer_group, *message_ids)

    async def pending(
        self, session_id: str, stream_name: str, consumer_group: str
    ) -> list[dict[str, Any]]:
        key = _stream_key(session_id, stream_name)
        result = await self.client.xpending_range(key, consumer_group, min="-", max="+", count=100)
        return [
            {"id": item["message_id"], "consumer": item["consumer"], "idle_ms": item["time_since_delivered"]}
            for item in result
        ]

    async def ack_all_pending(self, session_id: str, stream_name: str, consumer_group: str) -> int:
        """ACK (discard) all pending messages in a stream that were delivered but never acked.

        Called on session restore so stale inbox messages from a previous process
        are dropped instead of being re-dispatched to the new host.
        """
        key = _stream_key(session_id, stream_name)
        try:
            pending = await self.client.xpending_range(key, consumer_group, min="-", max="+", count=200)
        except Exception:
            return 0
        if not pending:
            return 0
        ids = [item["message_id"] for item in pending]
        await self.client.xack(key, consumer_group, *ids)
        logger.info("Discarded %d stale pending message(s) in %s/%s", len(ids), session_id, stream_name)
        return len(ids)

    async def init_session_streams(self, session_id: str):
        for name in STREAMS:
            key = _stream_key(session_id, name)
            try:
                await self.client.xgroup_create(key, name, id="0", mkstream=True)
            except redis.ResponseError as e:
                if "BUSYGROUP" in str(e):
                    logger.info("Consumer group %s already exists for %s", name, key)
                else:
                    raise
        logger.info("Session %s streams initialized (%d streams)", session_id, len(STREAMS))

    async def destroy_session_streams(self, session_id: str):
        for name in STREAMS:
            key = _stream_key(session_id, name)
            await self.client.xtrim(key, maxlen=0)
            await self.client.delete(key)
        logger.info("Session %s streams destroyed", session_id)

    async def health_check(self) -> bool:
        try:
            await self.client.ping()
            return True
        except Exception:
            return False
