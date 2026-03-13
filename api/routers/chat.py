from __future__ import annotations

import json
import uuid
from typing import Any

import structlog
from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from api.config import Settings, get_settings
from api.dependencies import get_chroma, get_db, get_embedder, get_redis
from memory.conversation_store import ConversationStore
from memory.long_term import LongTermMemory
from memory.memory_manager import MemoryManager
from memory.short_term import ShortTermMemory
from models.ollama_client import OllamaClient
from models.router import ModelRouter

logger = structlog.get_logger()

logger = structlog.get_logger()
router = APIRouter()


# ── Request / Response Models ────────────────────────────────────────────────

class ChatMessageRequest(BaseModel):
    """Request body for sending a chat message."""

    message: str
    session_id: str | None = None
    conversation_id: str | None = None
    model: str | None = None
    stream: bool = True


class ChatMessageResponse(BaseModel):
    """Non-streaming chat response."""

    data: dict[str, Any] | None = None
    error: str | None = None


class SessionListResponse(BaseModel):
    """Response for listing sessions."""

    data: list[dict[str, Any]] | None = None
    error: str | None = None


# ── Helpers ──────────────────────────────────────────────────────────────────

def _build_memory_manager(request: Request) -> MemoryManager:
    """Build a MemoryManager from app state."""
    settings = get_settings()
    stm = ShortTermMemory(request.app.state.redis, ttl=settings.memory_ttl_seconds)
    ltm = LongTermMemory(request.app.state.chroma_client, request.app.state.embedder)
    cs = ConversationStore(request.app.state.db_session_factory)
    return MemoryManager(short_term=stm, long_term=ltm, conversation_store=cs)


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.post("/message", response_model=None)
async def send_message(
    body: ChatMessageRequest,
    request: Request,
    settings: Settings = Depends(get_settings),
):
    """Send a chat message. Supports streaming (SSE) and non-streaming responses."""
    from fastapi import HTTPException
    
    mm = _build_memory_manager(request)
    model_router = ModelRouter()
    model = model_router.get_model("general", override=body.model)
    ollama = OllamaClient(base_url=settings.ollama_base_url)
    
    # Check Ollama connectivity
    try:
        await ollama.list_models()
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail=f"Ollama service unavailable. Please start Ollama with: ollama serve. Error: {str(e)}"
        )

    # Resolve or create session/conversation
    session_id = body.session_id or str(uuid.uuid4())
    conversation_id = body.conversation_id

    if not conversation_id:
        conversation_id = await mm.conversation_store.create_conversation(
            title=body.message[:100]
        )

    # Save user message
    await mm.save_message(session_id, conversation_id, "user", body.message)

    # Build context from memory
    try:
        context = await mm.get_context(session_id, "default", body.message)
    except Exception as e:
        # Fallback if embeddings not available
        logger.warning("memory.context_failed", error=str(e))
        conversation = await mm.conversation_store.get_conversation(conversation_id)
        session_messages = conversation.get("messages", []) if conversation else []
        context = {
            "session_messages": session_messages,
            "semantic_memories": [],
        }

    # Build messages list for Ollama chat
    messages: list[dict[str, str]] = []

    # Add semantic memory context as system message
    if context["semantic_memories"]:
        memory_text = "\n".join(
            m["content"] for m in context["semantic_memories"] if m.get("content")
        )
        messages.append({
            "role": "system",
            "content": f"Relevant context from memory:\n{memory_text}",
        })

    # Add session messages
    for msg in context["session_messages"]:
        messages.append({"role": msg["role"], "content": msg["content"]})

    # Add current message (if not already last)
    if not messages or messages[-1].get("content") != body.message:
        messages.append({"role": "user", "content": body.message})

    if body.stream:
        return StreamingResponse(
            _stream_response(ollama, model, messages, mm, session_id, conversation_id),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Session-Id": session_id,
                      "X-Conversation-Id": conversation_id},
        )

    # Non-streaming
    response_text = await ollama.chat(model=model, messages=messages, stream=False)
    await mm.save_message(session_id, conversation_id, "assistant", response_text)
    await ollama.close()

    return {
        "data": {
            "response": response_text,
            "session_id": session_id,
            "conversation_id": conversation_id,
            "model": model,
        },
        "error": None,
    }


async def _stream_response(
    ollama: OllamaClient,
    model: str,
    messages: list[dict[str, str]],
    mm: MemoryManager,
    session_id: str,
    conversation_id: str,
):
    """Stream SSE events from Ollama chat."""
    full_response = []

    # Send metadata event
    yield f"data: {json.dumps({'type': 'meta', 'session_id': session_id, 'conversation_id': conversation_id})}\n\n"

    try:
        token_stream = await ollama.chat(model=model, messages=messages, stream=True)
        async for token in token_stream:
            full_response.append(token)
            yield f"data: {json.dumps({'type': 'token', 'content': token})}\n\n"

        # Save assistant response
        response_text = "".join(full_response)
        await mm.save_message(session_id, conversation_id, "assistant", response_text)

        yield f"data: {json.dumps({'type': 'done', 'content': response_text})}\n\n"

    except Exception as exc:
        logger.error("chat.stream_error", error=str(exc))
        yield f"data: {json.dumps({'type': 'error', 'content': str(exc)})}\n\n"
    finally:
        await ollama.close()


@router.get("/sessions")
async def list_sessions(
    request: Request,
    user_id: str = "default",
    limit: int = 20,
    offset: int = 0,
) -> dict:
    """List chat sessions for a user."""
    mm = _build_memory_manager(request)
    sessions = await mm.conversation_store.list_conversations(
        user_id=user_id, limit=limit, offset=offset
    )
    return {"data": sessions, "error": None}


@router.get("/sessions/{conversation_id}")
async def get_session(
    conversation_id: str,
    request: Request,
) -> dict:
    """Get a specific conversation with all messages."""
    mm = _build_memory_manager(request)
    conv = await mm.conversation_store.get_conversation(conversation_id)
    if conv is None:
        return {"data": None, "error": "Conversation not found"}
    return {"data": conv, "error": None}
