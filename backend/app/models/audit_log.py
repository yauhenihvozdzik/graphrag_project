"""Модель для аудита действий пользователей."""
from sqlalchemy import Column, Integer, String, Text, DateTime, func, ForeignKey
from app.models.base import Base


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("user.id", ondelete="SET NULL"), nullable=True)
    action = Column(String(255), nullable=False, index=True)  # e.g., "user.login", "document.delete"
    entity_type = Column(String(100), nullable=True)  # e.g., "user", "document", "department"
    entity_id = Column(Integer, nullable=True)
    details = Column(Text, nullable=True)  # JSON с деталями действия
    ip_address = Column(String(45), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
