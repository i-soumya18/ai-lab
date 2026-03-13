from __future__ import annotations

import asyncio
from typing import Any

import structlog

from rag.embedder import Embedder

logger = structlog.get_logger()


class Retriever:
    """Semantic search over ChromaDB collections.

    Retrieves the most relevant document chunks for a given query.
    """

    def __init__(self, chroma_client: Any, embedder: Embedder) -> None:
        self._chroma = chroma_client
        self._embedder = embedder

    async def search(
        self,
        query: str,
        collection: str = "default",
        top_k: int = 5,
    ) -> list[dict[str, Any]]:
        """Search a ChromaDB collection for relevant chunks.

        Returns a list of results with content, metadata, and relevance score.
        """
        try:
            chroma_collection = self._chroma.get_or_create_collection(collection)
        except Exception as exc:
            logger.error("retriever.collection_error", collection=collection, error=str(exc))
            return []

        query_embedding = await self._embedder.embed_single(query)

        results = await asyncio.to_thread(
            chroma_collection.query,
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
                    "score": 1.0 - (distances[i] if i < len(distances) else 0),
                })

        logger.info("retriever.search", collection=collection, query_len=len(query), results=len(output))
        return output
