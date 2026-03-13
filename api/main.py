from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import AsyncIterator

import chromadb
import redis.asyncio as aioredis
import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from api.config import get_settings
from rag.embedder import Embedder

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Initialize and clean up shared resources."""
    settings = get_settings()

    # Database engine
    engine = create_async_engine(settings.postgres_url, echo=False, pool_size=5)
    app.state.db_engine = engine
    app.state.db_session_factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    # Redis
    app.state.redis = aioredis.from_url(
        settings.redis_url, decode_responses=True
    )

    # ChromaDB
    app.state.chroma_client = chromadb.HttpClient(
        host=settings.chroma_host, port=settings.chroma_port
    )

    # Ollama client (needed by Embedder)
    from models.ollama_client import OllamaClient
    ollama_client = OllamaClient(
        base_url=settings.ollama_base_url,
        default_model=settings.default_model,
    )
    app.state.ollama_client = ollama_client

    # Embedder (uses Ollama's embedding endpoint — zero local model loading)
    app.state.embedder = Embedder(
        ollama_client=ollama_client,
        embedding_model=settings.embedding_model,
    )

    # APScheduler (start background jobs)
    from automation.scheduler import get_scheduler
    scheduler = get_scheduler()
    scheduler.start()
    app.state.scheduler = scheduler

    # Orchestrator — shared instance with redis for kill-switch-aware agents
    from agents.orchestrator import Orchestrator
    app.state.orchestrator = Orchestrator(
        ollama_client=ollama_client,
        chroma_client=app.state.chroma_client,
        embedder=app.state.embedder,
        redis=app.state.redis,
    )

    # GoalExecutor — persistent goal execution engine
    from goals.goal_executor import GoalExecutor
    goal_executor = GoalExecutor(
        orchestrator=app.state.orchestrator,
        db_session_factory=app.state.db_session_factory,
        redis=app.state.redis,
        approval_timeout_seconds=settings.approval_timeout_seconds,
        max_concurrent=settings.goal_max_concurrent,
    )
    app.state.goal_executor = goal_executor

    # FileWatcher — filesystem event → goal trigger
    from automation.file_watcher import FileWatcher
    loop = asyncio.get_running_loop()
    file_watcher = FileWatcher(
        loop=loop,
        goal_executor=goal_executor,
        db_factory=app.state.db_session_factory,
    )
    app.state.file_watcher = file_watcher

    # Resume goals that were RUNNING when the system last shut down
    await goal_executor.resume_interrupted_goals()

    # Start filesystem watcher
    await file_watcher.load_and_start()

    logger.info(
        "ai_lab.startup",
        services=["db", "redis", "chromadb", "embedder", "scheduler",
                  "orchestrator", "goal_executor", "file_watcher"],
    )
    yield

    # Shutdown — reverse order
    file_watcher.stop()
    scheduler.shutdown(wait=False)
    await app.state.redis.aclose()
    await engine.dispose()
    logger.info("ai_lab.shutdown")


def create_app() -> FastAPI:
    """Application factory."""
    settings = get_settings()
    app = FastAPI(
        title="AI Lab API",
        description="Personal AI Operating System — fully local, privacy-first",
        version="2.0.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
        allow_headers=["*"],
        expose_headers=["*"],
        max_age=3600,
    )

    # ── Import and register routers ──────────────────────────────────────
    from api.routers import (
        activity,
        agents,
        approvals,
        automation,
        chat,
        goals,
        memory,
        rag,
        system,
        voice,
        watchers,
    )

    app.include_router(chat.router, prefix="/api/v1/chat", tags=["chat"])
    app.include_router(rag.router, prefix="/api/v1/rag", tags=["rag"])
    app.include_router(agents.router, prefix="/api/v1/agents", tags=["agents"])
    app.include_router(memory.router, prefix="/api/v1/memory", tags=["memory"])
    app.include_router(automation.router, prefix="/api/v1/automation", tags=["automation"])
    app.include_router(voice.router, prefix="/api/v1/voice", tags=["voice"])
    # v2 — Goal-Oriented Persistent Assistant OS
    app.include_router(goals.router, prefix="/api/v1/goals", tags=["goals"])
    app.include_router(approvals.router, prefix="/api/v1/approvals", tags=["approvals"])
    app.include_router(system.router, prefix="/api/v1/system", tags=["system"])
    app.include_router(activity.router, prefix="/api/v1/activity", tags=["activity"])
    app.include_router(watchers.router, prefix="/api/v1/watchers", tags=["watchers"])

    @app.get("/api/v1/health")
    async def health() -> dict:
        """Health check endpoint."""
        return {"data": {"status": "ok"}, "error": None}

    return app


app = create_app()
