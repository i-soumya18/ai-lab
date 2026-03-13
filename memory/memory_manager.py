from __future__ import annotations

from typing import Any

import structlog

from memory.conversation_store import ConversationStore
from memory.long_term import LongTermMemory
from memory.short_term import Message, ShortTermMemory

logger = structlog.get_logger()


class MemoryManager:
    """Unified interface to all memory layers.

    Transparently queries short-term (Redis), conversation history (PostgreSQL),
    and long-term semantic memory (ChromaDB) to build context for each request.
    """

    def __init__(
        self,
        short_term: ShortTermMemory,
        long_term: LongTermMemory,
        conversation_store: ConversationStore,
    ) -> None:
        self.short_term = short_term
        self.long_term = long_term
        self.conversation_store = conversation_store

    async def get_context(
        self, session_id: str, user_id: str, query: str
    ) -> dict[str, Any]:
        """Gather context from all memory layers for a query."""
        stm_messages = await self.short_term.get_messages(session_id)
        semantic_memories = await self.long_term.search(query, top_k=3)
        recent_conversations = await self.conversation_store.get_recent(
            user_id, limit=5
        )

        return {
            "session_messages": [m.model_dump() for m in stm_messages],
            "semantic_memories": semantic_memories,
            "recent_conversations": recent_conversations,
        }

    async def save_message(
        self,
        session_id: str,
        conversation_id: str,
        role: str,
        content: str,
    ) -> None:
        """Save a message to both short-term memory and conversation store."""
        from datetime import datetime, timezone

        msg = Message(
            role=role,
            content=content,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        await self.short_term.add_message(session_id, msg)
        await self.conversation_store.add_message(conversation_id, role, content)
        logger.debug("memory.saved", session_id=session_id, role=role)

    async def commit_to_long_term(
        self, conversation_id: str, ollama_client: Any, model: str
    ) -> None:
        """Summarize a conversation and store it in long-term memory."""
        conversation_text = await self.conversation_store.get_full_text(
            conversation_id
        )
        await self.long_term.summarize_and_store(
            conversation_text, ollama_client, model
        )
        logger.info("memory.committed_to_ltm", conversation_id=conversation_id)

    async def recall(self, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        """Search long-term semantic memory."""
        return await self.long_term.search(query, top_k=top_k)
