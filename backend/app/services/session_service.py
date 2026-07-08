"""Сервис для работы с сессиями чатов."""
from typing import Optional, List
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete as sa_delete
from app.models.session import ChatSession
from app.models.message import ChatMessage


class SessionService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_session(self, user_id: int, title: str = "New Chat") -> ChatSession:
        chat_session = ChatSession(user_id=user_id, name=title)
        self.session.add(chat_session)
        await self.session.commit()
        await self.session.refresh(chat_session)
        return chat_session

    async def get_user_sessions(self, user_id: int) -> List[ChatSession]:
        result = await self.session.execute(
            select(ChatSession)
            .where(ChatSession.user_id == user_id)
            .order_by(ChatSession.created_at.desc())
        )
        return list(result.scalars().all())

    async def add_message(self, session_id: int, role: str, content: str,
                          metadata: Optional[dict] = None) -> ChatMessage:
        msg = ChatMessage(
            session_id=session_id, role=role, content=content, metadata=metadata
        )
        self.session.add(msg)
        await self.session.commit()
        await self.session.refresh(msg)
        return msg

    async def get_session_messages(self, session_id: int) -> List[ChatMessage]:
        result = await self.session.execute(
            select(ChatMessage)
            .where(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.created_at)
        )
        return list(result.scalars().all())

    async def clear_history(self, user_id: int) -> bool:
        sessions_result = await self.session.execute(
            select(ChatSession).where(ChatSession.user_id == user_id)
        )
        sessions = list(sessions_result.scalars().all())
        for s in sessions:
            await self.session.execute(
                sa_delete(ChatMessage).where(ChatMessage.session_id == s.id)
            )
            await self.session.delete(s)
        await self.session.commit()
        return True
