from __future__ import annotations

import structlog

from models.ollama_client import OllamaClient

logger = structlog.get_logger()


class Embedder:
    """Wrapper for Ollama embedding API.

    Uses Ollama's /api/embed endpoint for embeddings.
    No local model loading — Ollama handles everything.
    """

    def __init__(
        self,
        ollama_client: OllamaClient,
        embedding_model: str = "nomic-embed-text"
    ) -> None:
        """
        Args:
            ollama_client: Initialized OllamaClient instance
            embedding_model: Name of embedding model in Ollama (e.g., "nomic-embed-text")
        """
        self.ollama_client = ollama_client
        self.embedding_model = embedding_model
        logger.info("embedder.initialized", model=embedding_model)

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts via Ollama. Returns list of embedding vectors."""
        logger.debug("embedder.embed.start", count=len(texts), model=self.embedding_model)
        embeddings = await self.ollama_client.embed(self.embedding_model, texts)
        logger.debug("embedder.embed.complete", count=len(embeddings))
        return embeddings

    async def embed_single(self, text: str) -> list[float]:
        """Embed a single text string."""
        results = await self.embed([text])
        if not results:
            raise ValueError("Embedding service returned no vectors")
        return results[0]
