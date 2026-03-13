from __future__ import annotations

import asyncio
import uuid
from pathlib import Path
from typing import Any

import structlog
from langchain_text_splitters import RecursiveCharacterTextSplitter

from rag.embedder import Embedder
from rag.loaders.git_loader import Document, load_git_repo
from rag.loaders.markdown_loader import load_markdown
from rag.loaders.notion_loader import load_notion_export
from rag.loaders.pdf_loader import load_pdf

logger = structlog.get_logger()


class DocumentIngester:
    """Chunks documents and stores them in ChromaDB.

    Supports multiple source types: file (PDF/markdown/text),
    git (repository), and notion (exported directory).
    """

    def __init__(
        self,
        chroma_client: Any,
        embedder: Embedder,
        chunk_size: int = 512,
        chunk_overlap: int = 64,
    ) -> None:
        self._chroma = chroma_client
        self._embedder = embedder
        self._splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            length_function=len,
            separators=["\n\n", "\n", ". ", " ", ""],
        )

    async def ingest(
        self,
        source_type: str,
        path: str,
        collection: str = "default",
        include_extensions: list[str] | None = None,
    ) -> dict[str, Any]:
        """Ingest documents from a source into a ChromaDB collection.

        Returns a summary of what was ingested.
        """
        logger.info("ingester.start", source_type=source_type, path=path, collection=collection)

        # Load documents
        documents = await self._load_documents(source_type, path, include_extensions)

        if not documents:
            return {"source": path, "collection": collection, "chunks": 0, "documents": 0}

        # Chunk all documents
        all_chunks: list[str] = []
        all_metadatas: list[dict[str, Any]] = []

        for doc in documents:
            chunks = self._splitter.split_text(doc.content)
            for i, chunk in enumerate(chunks):
                all_chunks.append(chunk)
                all_metadatas.append({
                    **doc.metadata,
                    "chunk_index": i,
                    "total_chunks": len(chunks),
                })

        # Embed all chunks
        embeddings = await self._embedder.embed(all_chunks)

        # Store in ChromaDB
        chroma_collection = self._chroma.get_or_create_collection(collection)
        ids = [str(uuid.uuid4()) for _ in all_chunks]

        # Upsert in batches to avoid memory issues
        batch_size = 100
        for i in range(0, len(all_chunks), batch_size):
            end = min(i + batch_size, len(all_chunks))
            await asyncio.to_thread(
                chroma_collection.upsert,
                ids=ids[i:end],
                documents=all_chunks[i:end],
                embeddings=embeddings[i:end],
                metadatas=all_metadatas[i:end],
            )

        result = {
            "source": path,
            "collection": collection,
            "documents": len(documents),
            "chunks": len(all_chunks),
        }
        logger.info("ingester.complete", **result)
        return result

    async def _load_documents(
        self,
        source_type: str,
        path: str,
        include_extensions: list[str] | None,
    ) -> list[Document]:
        """Load documents based on source type."""
        if source_type == "git":
            return await load_git_repo(path, extensions=include_extensions)

        if source_type == "notion":
            return await load_notion_export(path)

        if source_type == "file":
            file_path = Path(path)
            if not file_path.exists():
                raise FileNotFoundError(f"File not found: {path}")

            ext = file_path.suffix.lower()

            if ext == ".pdf":
                pages = await load_pdf(path)
                return [
                    Document(
                        content=page,
                        metadata={"file_path": path, "page": i + 1, "source_type": "pdf"},
                    )
                    for i, page in enumerate(pages)
                ]

            if ext in (".md", ".markdown"):
                content = await load_markdown(path)
                return [Document(
                    content=content,
                    metadata={"file_path": path, "source_type": "markdown"},
                )]

            # Plain text fallback
            content = file_path.read_text(encoding="utf-8", errors="replace")
            return [Document(
                content=content,
                metadata={"file_path": path, "source_type": "text"},
            )]

        raise ValueError(f"Unknown source type: {source_type}")


async def ingest_file(
    path: str,
    collection_name: str,
    chroma_client: Any,
    embedder: Any,
) -> int:
    """Convenience wrapper: ingest a single file into a ChromaDB collection.

    Returns the number of chunks stored.
    """
    ingester = DocumentIngester(chroma_client=chroma_client, embedder=embedder)
    result = await ingester.ingest(source_type="file", path=path, collection=collection_name)
    return result.get("chunks", 0)
