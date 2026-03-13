from __future__ import annotations

from typing import Any

import structlog
from fastapi import APIRouter, Depends, Request

from api.config import Settings, get_settings
from api.dependencies import get_chroma, get_embedder
from memory.conversation_store import ConversationStore
from memory.long_term import LongTermMemory
from memory.memory_manager import MemoryManager
from memory.short_term import ShortTermMemory

logger = structlog.get_logger()
router = APIRouter()


def _build_memory_manager(request: Request) -> MemoryManager:
    """Build a MemoryManager from app state."""
    settings = get_settings()
    stm = ShortTermMemory(request.app.state.redis, ttl=settings.memory_ttl_seconds)
    ltm = LongTermMemory(request.app.state.chroma_client, request.app.state.embedder)
    cs = ConversationStore(request.app.state.db_session_factory)
    return MemoryManager(short_term=stm, long_term=ltm, conversation_store=cs)


@router.get("/recall")
async def recall_memory(
    q: str,
    request: Request,
    top_k: int = 5,
) -> dict:
    """Search across all memory layers."""
    if not q.strip():
        return {"data": None, "error": "Query cannot be empty"}

    mm = _build_memory_manager(request)
    results = await mm.recall(query=q, top_k=top_k)

    return {"data": results, "error": None}


@router.get("/context")
async def get_context(
    q: str,
    request: Request,
    session_id: str = "default",
    user_id: str = "default",
) -> dict:
    """Get full context from all memory layers for a query."""
    mm = _build_memory_manager(request)
    context = await mm.get_context(session_id=session_id, user_id=user_id, query=q)
    return {"data": context, "error": None}
