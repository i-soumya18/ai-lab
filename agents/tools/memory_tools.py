from __future__ import annotations

import asyncio
from typing import Any

import structlog
from pydantic import BaseModel

logger = structlog.get_logger()


class MemoryChunk(BaseModel):
    """A chunk from memory search."""

    content: str
    metadata: dict[str, Any] = {}
    distance: float | None = None


async def memory_search(
    query: str,
    chroma_client: Any,
    embedder: Any,
    collection: str = "memory",
    top_k: int = 5,
) -> list[MemoryChunk]:
    """Semantic search across long-term vector memory."""
    try:
        coll = chroma_client.get_or_create_collection(collection)
    except Exception:
        return []

    embedding = await embedder.embed_single(query)

    results = await asyncio.to_thread(
        coll.query,
        query_embeddings=[embedding],
        n_results=top_k,
    )

    chunks = []
    if results and results.get("documents"):
        docs = results["documents"][0]
        metadatas = results.get("metadatas", [[]])[0]
        distances = results.get("distances", [[]])[0]

        for i, doc in enumerate(docs):
            chunks.append(MemoryChunk(
                content=doc,
                metadata=metadatas[i] if i < len(metadatas) else {},
                distance=distances[i] if i < len(distances) else None,
            ))

    return chunks


async def memory_store(
    content: str,
    metadata: dict[str, Any],
    chroma_client: Any,
    embedder: Any,
    collection: str = "memory",
) -> bool:
    """Store a fact or summary in long-term vector memory."""
    import uuid

    try:
        coll = chroma_client.get_or_create_collection(collection)
    except Exception as exc:
        logger.error("memory_tools.store_error", error=str(exc))
        return False

    embedding = await embedder.embed_single(content)
    doc_id = str(uuid.uuid4())

    await asyncio.to_thread(
        coll.upsert,
        ids=[doc_id],
        documents=[content],
        embeddings=[embedding],
        metadatas=[metadata],
    )

    logger.info("memory_tools.stored", doc_id=doc_id, collection=collection)
    return True


async def memory_recall_recent(
    redis_client: Any,
    user_id: str = "default",
    limit: int = 10,
) -> list[dict[str, str]]:
    """Get recent conversation messages from Redis."""
    from memory.short_term import Message, ShortTermMemory

    stm = ShortTermMemory(redis_client)

    # Try to get messages from recent sessions
    # We look for any session keys matching the pattern
    keys = []
    async for key in redis_client.scan_iter(match="session:*:messages", count=100):
        keys.append(key)
        if len(keys) >= limit:
            break

    messages = []
    for key in keys[:5]:  # limit to 5 sessions
        raw = await redis_client.lrange(key, -limit, -1)
        for m in raw:
            msg = Message.model_validate_json(m)
            messages.append(msg.model_dump())

    return messages[-limit:]
