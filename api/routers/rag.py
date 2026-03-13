from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from typing import Any

import structlog
from fastapi import APIRouter, Depends, Request, UploadFile
from pydantic import BaseModel

from api.config import Settings, get_settings
from api.dependencies import get_chroma, get_embedder
from rag.embedder import Embedder
from rag.ingestion import DocumentIngester
from rag.retriever import Retriever

logger = structlog.get_logger()
router = APIRouter()

MAX_UPLOAD_BYTES = 50 * 1024 * 1024  # 50 MB
ALLOWED_EXTENSIONS = {".pdf", ".md", ".markdown", ".txt", ".py", ".ts", ".tsx",
                      ".js", ".go", ".rs", ".html", ".json", ".csv"}


# ── Request / Response Models ────────────────────────────────────────────────

class IngestRequest(BaseModel):
    """Request body for ingesting from a path (git repo, notion export)."""

    source_type: str  # "git" | "notion" | "file"
    path: str
    collection: str = "default"
    include_extensions: list[str] | None = None


class SearchResult(BaseModel):
    """A single search result."""

    content: str
    metadata: dict[str, Any] = {}
    score: float = 0.0


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.post("/ingest")
async def ingest_document(
    request: Request,
    body: IngestRequest | None = None,
    file: UploadFile | None = None,
    collection: str = "default",
    settings: Settings = Depends(get_settings),
) -> dict:
    """Ingest a document or directory into a RAG collection.

    Supports file upload OR a path-based ingest request (git repo, notion export).
    """
    chroma = request.app.state.chroma_client
    embedder = request.app.state.embedder

    ingester = DocumentIngester(
        chroma_client=chroma,
        embedder=embedder,
        chunk_size=settings.rag_chunk_size,
        chunk_overlap=settings.rag_chunk_overlap,
    )

    # Handle file upload
    if file is not None:
        suffix = Path(file.filename or "").suffix.lower()
        if suffix not in ALLOWED_EXTENSIONS:
            return {"data": None, "error": f"File type not supported: {suffix}"}

        # Check file size
        contents = await file.read()
        if len(contents) > MAX_UPLOAD_BYTES:
            return {"data": None, "error": f"File too large. Max {MAX_UPLOAD_BYTES // (1024*1024)} MB"}

        # Save to temp file
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(contents)
            tmp_path = tmp.name

        try:
            result = await ingester.ingest(
                source_type="file",
                path=tmp_path,
                collection=collection,
            )
            return {"data": result, "error": None}
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    # Handle path-based ingest
    if body is not None:
        result = await ingester.ingest(
            source_type=body.source_type,
            path=body.path,
            collection=body.collection,
            include_extensions=body.include_extensions,
        )
        return {"data": result, "error": None}

    return {"data": None, "error": "Provide either a file upload or an ingest request body"}


@router.get("/search")
async def search(
    q: str,
    request: Request,
    collection: str = "default",
    top_k: int = 5,
) -> dict:
    """Semantic search across a RAG collection."""
    if not q.strip():
        return {"data": None, "error": "Query cannot be empty"}

    chroma = request.app.state.chroma_client
    embedder = request.app.state.embedder
    retriever = Retriever(chroma_client=chroma, embedder=embedder)

    results = await retriever.search(query=q, collection=collection, top_k=top_k)

    return {"data": results, "error": None}


@router.get("/collections")
async def list_collections(request: Request) -> dict:
    """List all RAG collections."""
    chroma = request.app.state.chroma_client
    collections = chroma.list_collections()
    return {
        "data": [{"name": c.name, "count": c.count()} for c in collections],
        "error": None,
    }
