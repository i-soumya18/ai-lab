from __future__ import annotations

from typing import AsyncIterator

import chromadb
import redis.asyncio as aioredis
from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from api.config import Settings, get_settings
from rag.embedder import Embedder


async def get_db(request: Request) -> AsyncIterator[AsyncSession]:
    """Yield a database session from the app-level session factory."""
    async with request.app.state.db_session_factory() as session:
        yield session


async def get_redis(request: Request) -> aioredis.Redis:
    """Return the shared Redis client."""
    return request.app.state.redis


async def get_chroma(request: Request) -> chromadb.HttpClient:
    """Return the shared ChromaDB client."""
    return request.app.state.chroma_client


async def get_embedder(request: Request) -> Embedder:
    """Return the shared embedding model."""
    return request.app.state.embedder


def get_config() -> Settings:
    """Return cached settings."""
    return get_settings()
