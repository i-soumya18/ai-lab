from __future__ import annotations

import asyncio
import uuid
from typing import Any

import structlog

logger = structlog.get_logger()


class LongTermMemory:
    """ChromaDB-backed semantic memory for persistent knowledge.

    Stores summarized facts, user preferences, and decisions.
    Uses asyncio.to_thread() to wrap synchronous ChromaDB calls.
    """

    def __init__(self, chroma_client: Any, embedder: Any) -> None:
        self._client = chroma_client
        self._embedder = embedder
        self._collection = self._client.get_or_create_collection("memory")

    async def store(
        self, content: str, metadata: dict[str, Any], doc_id: str | None = None
    ) -> None:
        """Store a summarized fact in long-term memory."""
        if doc_id is None:
            doc_id = str(uuid.uuid4())

        embedding = await self._embedder.embed_single(content)

        await asyncio.to_thread(
            self._collection.upsert,
            ids=[doc_id],
            documents=[content],
            embeddings=[embedding],
            metadatas=[metadata],
        )
        logger.info("ltm.stored", doc_id=doc_id)

    async def search(self, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        """Semantic search across long-term memory."""
        query_embedding = await self._embedder.embed_single(query)

        results = await asyncio.to_thread(
            self._collection.query,
            query_embeddings=[query_embedding],
            n_results=top_k,
        )

        output: list[dict[str, Any]] = []
        if results and results.get("documents"):
            docs = results["documents"][0]
            metadatas = results.get("metadatas", [[]])[0]
            distances = results.get("distances", [[]])[0]
            ids = results.get("ids", [[]])[0]

            for i, doc in enumerate(docs):
                output.append({
                    "id": ids[i] if i < len(ids) else None,
                    "content": doc,
                    "metadata": metadatas[i] if i < len(metadatas) else {},
                    "distance": distances[i] if i < len(distances) else None,
                })

        return output

    async def summarize_and_store(
        self, conversation: str, ollama_client: Any, model: str
    ) -> None:
        """Summarize a conversation using LLM, then embed and store the summary."""
        if not conversation.strip():
            return

        summary = await ollama_client.generate(
            model=model,
            prompt=f"Summarize the key facts, preferences, and decisions from this conversation:\n\n{conversation}",
            system="Extract only factual information, user preferences, project details, and decisions. Be concise.",
            temperature=0.3,
        )

        await self.store(
            content=summary,
            metadata={"type": "conversation_summary"},
        )
        logger.info("ltm.conversation_summarized")

    async def delete(self, doc_id: str) -> None:
        """Delete a specific memory entry."""
        await asyncio.to_thread(
            self._collection.delete,
            ids=[doc_id],
        )
