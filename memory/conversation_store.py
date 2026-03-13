from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

import structlog
from sqlalchemy import Column, DateTime, ForeignKey, String, Text, select
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase, relationship

logger = structlog.get_logger()


# ── SQLAlchemy Models ────────────────────────────────────────────────────────

class Base(DeclarativeBase):
    pass


class Conversation(Base):
    """A conversation session."""

    __tablename__ = "conversations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(String, nullable=False, default="default")
    title = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))

    messages = relationship("ConversationMessage", back_populates="conversation",
                            cascade="all, delete-orphan", order_by="ConversationMessage.timestamp")


class ConversationMessage(Base):
    """A single message within a conversation."""

    __tablename__ = "conversation_messages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id = Column(UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"),
                             nullable=False)
    role = Column(String, nullable=False)
    content = Column(Text, nullable=False)
    timestamp = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    conversation = relationship("Conversation", back_populates="messages")


# ── Conversation Store ───────────────────────────────────────────────────────

class ConversationStore:
    """PostgreSQL-backed conversation history with full CRUD."""

    def __init__(self, session_factory: Any) -> None:
        self._session_factory = session_factory

    async def create_conversation(
        self, user_id: str = "default", title: str | None = None
    ) -> str:
        """Create a new conversation and return its ID."""
        async with self._session_factory() as session:
            conv = Conversation(user_id=user_id, title=title)
            session.add(conv)
            await session.commit()
            await session.refresh(conv)
            logger.info("conversation.created", id=str(conv.id), user_id=user_id)
            return str(conv.id)

    async def add_message(
        self, conversation_id: str, role: str, content: str
    ) -> str:
        """Add a message to a conversation and return the message ID."""
        async with self._session_factory() as session:
            msg = ConversationMessage(
                conversation_id=uuid.UUID(conversation_id),
                role=role,
                content=content,
            )
            session.add(msg)
            await session.commit()
            await session.refresh(msg)
            return str(msg.id)

    async def get_conversation(self, conversation_id: str) -> dict | None:
        """Fetch a conversation with all its messages."""
        async with self._session_factory() as session:
            stmt = select(Conversation).where(
                Conversation.id == uuid.UUID(conversation_id)
            )
            result = await session.execute(stmt)
            conv = result.scalar_one_or_none()
            if conv is None:
                return None

            msg_stmt = (
                select(ConversationMessage)
                .where(ConversationMessage.conversation_id == conv.id)
                .order_by(ConversationMessage.timestamp)
            )
            msg_result = await session.execute(msg_stmt)
            messages = msg_result.scalars().all()

            return {
                "id": str(conv.id),
                "user_id": conv.user_id,
                "title": conv.title,
                "created_at": conv.created_at.isoformat() if conv.created_at else None,
                "messages": [
                    {
                        "id": str(m.id),
                        "role": m.role,
                        "content": m.content,
                        "timestamp": m.timestamp.isoformat() if m.timestamp else None,
                    }
                    for m in messages
                ],
            }

    async def list_conversations(
        self, user_id: str = "default", limit: int = 20, offset: int = 0
    ) -> list[dict]:
        """List conversations for a user, newest first."""
        async with self._session_factory() as session:
            stmt = (
                select(Conversation)
                .where(Conversation.user_id == user_id)
                .order_by(Conversation.updated_at.desc())
                .limit(limit)
                .offset(offset)
            )
            result = await session.execute(stmt)
            convs = result.scalars().all()

            return [
                {
                    "id": str(c.id),
                    "title": c.title,
                    "created_at": c.created_at.isoformat() if c.created_at else None,
                    "updated_at": c.updated_at.isoformat() if c.updated_at else None,
                }
                for c in convs
            ]

    async def get_recent(self, user_id: str, limit: int = 5) -> list[dict]:
        """Get recent conversations with their last message."""
        return await self.list_conversations(user_id=user_id, limit=limit)

    async def get_full_text(self, conversation_id: str) -> str:
        """Get the full conversation as plain text (for summarization)."""
        conv = await self.get_conversation(conversation_id)
        if conv is None:
            return ""
        lines = []
        for msg in conv.get("messages", []):
            lines.append(f"{msg['role']}: {msg['content']}")
        return "\n".join(lines)

    async def update_title(self, conversation_id: str, title: str) -> None:
        """Update a conversation's title."""
        async with self._session_factory() as session:
            stmt = select(Conversation).where(
                Conversation.id == uuid.UUID(conversation_id)
            )
            result = await session.execute(stmt)
            conv = result.scalar_one_or_none()
            if conv:
                conv.title = title
                await session.commit()
