from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Central configuration loaded from environment variables."""

    # Ollama (running locally on host machine)
    ollama_base_url: str = "http://host.docker.internal:11434"
    default_model: str = "nemotron-3-super:cloud"
    coder_model: str = "nemotron-3-super:cloud"
    embedding_model: str = "nomic-embed-text"

    # PostgreSQL
    postgres_url: str = "postgresql+asyncpg://ailab:ailab@postgres:5432/ailab"

    # Redis
    redis_url: str = "redis://redis:6379/0"

    # ChromaDB
    chroma_host: str = "chromadb"
    chroma_port: int = 8000

    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    log_level: str = "info"
    cors_allowed_origins: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]

    # Limits
    max_upload_size_mb: int = 50
    agent_timeout_seconds: int = 120
    memory_ttl_seconds: int = 7200
    rag_default_top_k: int = 5
    rag_chunk_size: int = 512
    rag_chunk_overlap: int = 64

    # Goal-Oriented OS (v2)
    approval_timeout_seconds: int = 300
    goal_max_concurrent: int = 3
    watched_paths_root: str = "/app/watched"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


@lru_cache
def get_settings() -> Settings:
    """Return cached settings instance."""
    return Settings()
