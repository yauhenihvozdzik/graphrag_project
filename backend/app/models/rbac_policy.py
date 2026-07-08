"""Модель для хранения RBAC-политик."""
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, func
from app.models.base import Base


class RBACPolicy(Base):
    __tablename__ = "rbac_policies"

    id = Column(Integer, primary_key=True, autoincrement=True)
    role = Column(String(50), nullable=False, index=True)  # "admin", "manager", "analyst", "auditor"
    resource = Column(String(100), nullable=False)  # e.g., "document", "user", "department", "settings"
    action = Column(String(50), nullable=False)  # "create", "read", "update", "delete", "*"
    condition = Column(Text, nullable=True)  # JSON с дополнительными условиями
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
