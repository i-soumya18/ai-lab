from __future__ import annotations

from typing import Any, AsyncIterator

import structlog

from models.ollama_client import OllamaClient
from rag.retriever import Retriever

logger = structlog.get_logger()

RAG_SYSTEM_PROMPT = """You are a helpful assistant. Use the following context to answer the question.
If the context doesn't help, say so clearly.

Context:
{context}

Question: {question}"""


class RAGPipeline:
    """End-to-end RAG chain: retrieve → inject context → generate answer.

    Combines the Retriever for semantic search with the Ollama client
    for LLM-based answer generation.
    """

    def __init__(
        self,
        retriever: Retriever,
        ollama_client: OllamaClient,
    ) -> None:
        self._retriever = retriever
        self._ollama = ollama_client

    async def query(
        self,
        question: str,
        collection: str = "default",
        model: str = "nemotron-3-super:cloud",
        top_k: int = 5,
        stream: bool = False,
    ) -> dict[str, Any] | AsyncIterator[str]:
        """Run the full RAG pipeline.

        1. Retrieve relevant chunks from ChromaDB
        2. Build context from retrieved chunks
        3. Generate an answer using the LLM

        Returns a dict with answer and sources, or an async iterator if streaming.
        """
        # Step 1: Retrieve
        chunks = await self._retriever.search(
            query=question,
            collection=collection,
            top_k=top_k,
        )

        # Step 2: Build context
        context_parts = []
        sources = []
        for chunk in chunks:
            context_parts.append(chunk["content"])
            meta = chunk.get("metadata", {})
            source = meta.get("file_path", meta.get("title", "unknown"))
            if source not in sources:
                sources.append(source)

        context = "\n\n---\n\n".join(context_parts) if context_parts else "No relevant context found."

        # Step 3: Generate
        system_prompt = RAG_SYSTEM_PROMPT.format(context=context, question=question)

        if stream:
            return self._stream_answer(model, system_prompt, question, sources)

        answer = await self._ollama.generate(
            model=model,
            prompt=question,
            system=system_prompt,
            stream=False,
        )

        logger.info("rag.query", collection=collection, chunks=len(chunks), sources=len(sources))

        return {
            "answer": answer,
            "sources": sources,
            "chunks_used": len(chunks),
        }

    async def _stream_answer(
        self,
        model: str,
        system_prompt: str,
        question: str,
        sources: list[str],
    ) -> AsyncIterator[str]:
        """Stream the RAG answer token by token."""
        token_stream = await self._ollama.generate(
            model=model,
            prompt=question,
            system=system_prompt,
            stream=True,
        )
        async for token in token_stream:
            yield token
