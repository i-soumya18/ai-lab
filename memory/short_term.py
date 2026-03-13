from __future__ import annotations

import json
from datetime import datetime, timezone

import redis.asyncio as aioredis
import structlog
from pydantic import BaseModel

logger = structlog.get_logger()


class Message(BaseModel):
    """A single chat message stored in short-term memory."""

    role: str
    content: str
    timestamp: str


class ShortTermMemory:
    """Redis-backed session memory with automatic TTL expiry.

    Stores the last N messages per session in a Redis list.
    Each session key expires after the configured TTL (default 2 hours).
    """

    def __init__(self, redis_client: aioredis.Redis, ttl: int = 7200) -> None:
        self._redis = redis_client
        self._ttl = ttl

    def _key(self, session_id: str) -> str:
        """Build the Redis key for a session."""
        return f"session:{session_id}:messages"

    async def add_message(self, session_id: str, message: Message) -> None:
        """Append a message to the session and refresh TTL."""
        key = self._key(session_id)
        await self._redis.rpush(key, message.model_dump_json())
        await self._redis.expire(key, self._ttl)
        logger.debug("stm.add_message", session_id=session_id, role=message.role)

    async def get_messages(self, session_id: str, limit: int = 20) -> list[Message]:
        """Get the last N messages for a session."""
        key = self._key(session_id)
        raw = await self._redis.lrange(key, -limit, -1)
        return [Message.model_validate_json(m) for m in raw]

    async def clear_session(self, session_id: str) -> None:
        """Delete all messages for a session."""
        await self._redis.delete(self._key(session_id))
        logger.info("stm.clear_session", session_id=session_id)

    async def session_exists(self, session_id: str) -> bool:
        """Check if a session has any messages."""
        return await self._redis.exists(self._key(session_id)) > 0
