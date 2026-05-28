"""In-memory MQ — drop-in replacement for MQLayer when Redis is unavailable."""
import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

_ID_COUNTER = 0


def _next_id() -> str:
    global _ID_COUNTER
    _ID_COUNTER += 1
    ts = int(datetime.now(timezone.utc).timestamp() * 1000)
    return f"{ts}-{_ID_COUNTER}"


class InMemoryMQ:
    def __init__(self):
        # stream_key → list of {"id": str, "data": dict}
        self._streams: dict[str, list[dict]] = {}
        # (stream_key, group) → next undelivered index in stream
        self._group_cursors: dict[tuple[str, str], int] = {}
        # asyncio.Event per (stream_key, group) to wake up blocked consumers
        self._group_events: dict[tuple[str, str], asyncio.Event] = {}
        # asyncio.Event per stream_key for read_from() waiters
        self._stream_events: dict[str, asyncio.Event] = {}

    async def connect(self):
        logger.info("InMemoryMQ: using in-memory streams (no Redis)")

    async def disconnect(self):
        pass

    async def health_check(self) -> bool:
        return True

    def _stream_key(self, session_id: str, name: str) -> str:
        return f"session:{session_id}:{name}"

    async def publish(
        self,
        session_id: str,
        stream_name: str,
        payload: dict[str, Any],
        target_channel: str | None = None,
    ) -> str:
        key = self._stream_key(session_id, stream_name)
        if key not in self._streams:
            self._streams[key] = []

        msg_id = _next_id()
        entry = {
            "id": msg_id,
            "data": {
                "session_id": session_id,
                "stream": stream_name,
                "payload": payload,
                "target_channel": target_channel,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        }
        self._streams[key].append(entry)

        # Wake up any consumers waiting on this stream
        ev = self._stream_events.get(key)
        if ev:
            ev.set()
        for (sk, _grp), gev in self._group_events.items():
            if sk == key:
                gev.set()

        return msg_id

    async def consume(
        self,
        session_id: str,
        stream_name: str,
        consumer_group: str,
        consumer_name: str,
        count: int = 1,
        block_ms: int = 5000,
    ) -> list[dict[str, Any]]:
        key = self._stream_key(session_id, stream_name)
        gk = (key, consumer_group)

        if gk not in self._group_cursors:
            self._group_cursors[gk] = 0
        if gk not in self._group_events:
            self._group_events[gk] = asyncio.Event()

        deadline = asyncio.get_event_loop().time() + block_ms / 1000

        while True:
            stream = self._streams.get(key, [])
            cursor = self._group_cursors[gk]
            available = stream[cursor : cursor + count]
            if available:
                self._group_cursors[gk] = cursor + len(available)
                return available

            remaining = deadline - asyncio.get_event_loop().time()
            if remaining <= 0:
                return []

            ev = self._group_events[gk]
            ev.clear()
            try:
                await asyncio.wait_for(ev.wait(), timeout=min(remaining, 5.0))
            except asyncio.TimeoutError:
                pass

    def _index_after(self, stream: list[dict], last_id: str) -> int:
        """Return the index of the first message after last_id."""
        if last_id in ("0", "0-0"):
            return 0
        for i, entry in enumerate(stream):
            if entry["id"] == last_id:
                return i + 1
        # ID not found (e.g. stream was trimmed): start from end
        return len(stream)

    async def read_from(
        self,
        session_id: str,
        stream_name: str,
        last_id: str = "$",
        count: int = 10,
        block_ms: int = 5000,
    ) -> list[dict[str, Any]]:
        key = self._stream_key(session_id, stream_name)
        if key not in self._stream_events:
            self._stream_events[key] = asyncio.Event()

        # "$" means "tail at call time" — convert to the last existing ID
        # so we only return messages published *after* this call.
        if last_id == "$":
            stream = self._streams.get(key, [])
            last_id = stream[-1]["id"] if stream else "__tail__"

        deadline = asyncio.get_event_loop().time() + block_ms / 1000

        while True:
            stream = self._streams.get(key, [])

            if last_id == "__tail__":
                # Was empty at "$" time; return everything published since
                result = stream[:count]
                if result:
                    last_id = result[-1]["id"]  # not used by caller, but consistent
            else:
                idx = self._index_after(stream, last_id)
                result = stream[idx : idx + count]

            if result:
                return result

            remaining = deadline - asyncio.get_event_loop().time()
            if remaining <= 0:
                return []

            ev = self._stream_events[key]
            ev.clear()
            try:
                await asyncio.wait_for(ev.wait(), timeout=min(remaining, 5.0))
            except asyncio.TimeoutError:
                pass

    async def ack(
        self,
        session_id: str,
        stream_name: str,
        consumer_group: str,
        message_ids: list[str],
    ):
        pass  # no-op: cursor already advanced in consume()

    async def pending(
        self, session_id: str, stream_name: str, consumer_group: str
    ) -> list[dict[str, Any]]:
        return []

    async def init_session_streams(self, session_id: str):
        streams = ["inbox", "outbox", "dispatched", "results", "approvals", "events"]
        for name in streams:
            key = self._stream_key(session_id, name)
            if key not in self._streams:
                self._streams[key] = []
        logger.info("InMemoryMQ: session %s streams initialised", session_id)

    async def destroy_session_streams(self, session_id: str):
        streams = ["inbox", "outbox", "dispatched", "results", "approvals", "events"]
        for name in streams:
            key = self._stream_key(session_id, name)
            self._streams.pop(key, None)
            for gk in [k for k in self._group_cursors if k[0] == key]:
                del self._group_cursors[gk]
            self._stream_events.pop(key, None)
        logger.info("InMemoryMQ: session %s streams destroyed", session_id)
