"""Database service - фасад для обратной совместимости.

NOTE: Этот класс сохранён для обратной совместимости.
Новый код должен использовать специализированные сервисы напрямую:
- UserService
- DepartmentService
- SessionService
- AdminSettingsService
- FileService
"""
from typing import Any, AsyncGenerator, List, Optional
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.pool import QueuePool, NullPool
from sqlalchemy import create_engine, func
from sqlmodel import select
from sqlmodel import Session as SQLModelSession
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

import json
from datetime import datetime, timezone

from app.core.constants import Environment
from app.core.config import settings
from app.core.logging import logger
from app.models.admin import AdminSetting, AdminSettingsAudit, AdminSettingsVersion
from app.models.user import User
from app.models.session import ChatSession
from app.models.message import ChatMessage
from app.models.department import Department
from app.models.file_metadata import FileMetadata

from app.services.user_service import UserService
from app.services.department_service import DepartmentService
from app.services.session_service import SessionService
from app.services.admin_settings_service import AdminSettingsService
from app.services.file_service import FileService


class DatabaseService:
    """Фасад, делегирующий вызовы специализированным сервисам.

    Сохраняет полную обратную совместимость с существующим кодом.
    """

    def __init__(self):
        try:
            # Async engine (основной для приложения)
            self.engine = create_async_engine(
                settings.DATABASE_URL,
                echo=settings.DEBUG,
                pool_size=settings.POSTGRES_POOL_SIZE,
                max_overflow=settings.POSTGRES_MAX_OVERFLOW,
                pool_pre_ping=True,
                pool_recycle=1800,
            )
            self.async_session = async_sessionmaker(
                self.engine, class_=AsyncSession, expire_on_commit=False
            )

            # Sync engine (для Alembic и обратной совместимости)
            self.sync_engine = create_engine(
                settings.SYNC_DATABASE_URL,
                pool_pre_ping=True,
                poolclass=QueuePool,
                pool_size=settings.POSTGRES_POOL_SIZE,
                max_overflow=settings.POSTGRES_MAX_OVERFLOW,
                pool_timeout=30,
                pool_recycle=1800,
            )
            logger.info(
                "database_initialized",
                environment=settings.ENVIRONMENT.value,
                pool_size=settings.POSTGRES_POOL_SIZE,
            )
        except SQLAlchemyError as e:
            logger.error("database_initialization_error", error=str(e))
            if settings.ENVIRONMENT != Environment.PRODUCTION:
                raise

    async def get_session(self) -> AsyncGenerator[AsyncSession, None]:
        """Async context manager for database sessions."""
        async with self.async_session() as session:
            yield session

    # ── Sync helpers for backward compatibility ──────────────────────────

    def _get_sync_session(self) -> SQLModelSession:
        return SQLModelSession(self.sync_engine)

    def _get_sync_session_context(self):
        """Context manager for sync sessions (legacy code path)."""
        return SQLModelSession(self.sync_engine)

    def run_migrations(self) -> None:
        """Run Alembic migrations programmatically at startup.

        Falls back to SQLModel.metadata.create_all if Alembic is not installed
        or the config file is missing. This guarantees tables exist in all
        environments (dev, CI, production).
        """
        try:
            from alembic.config import Config
            from alembic import command
            import os
            # Path relative to this file: services/ -> app/ -> backend/
            alembic_ini = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "alembic.ini")
            if os.path.exists(alembic_ini):
                alembic_cfg = Config(alembic_ini)
                alembic_cfg.set_main_option("sqlalchemy.url", settings.SYNC_DATABASE_URL)
                command.upgrade(alembic_cfg, "head")
                logger.info("alembic_migrations_applied")
                return
            else:
                logger.warning("alembic_ini_not_found_fallback", path=alembic_ini)
        except ImportError:
            logger.info("alembic_not_installed_fallback_to_create_all")
        except Exception as e:
            logger.warning("alembic_migration_failed_fallback", error=str(e))

        # Fallback: create tables via SQLModel metadata
        try:
            from sqlmodel import SQLModel
            SQLModel.metadata.create_all(self.sync_engine)
            logger.info("sqlmodel_create_all_fallback_applied")
        except Exception as e:
            logger.exception("db_table_creation_failed", error=str(e))

    # ─── Users ──────────────────────────────────────────────────────────────

    def create_user(self, email: str, password: str, username: Optional[str] = None,
                    role: str = "viewer", department: str = "all") -> User:
        with self._get_sync_session() as s:
            u = User(
                email=email,
                hashed_password=User.hash_password(password),
                username=username,
                role=role,
                department=department,
                is_active=True,
            )
            s.add(u)
            try:
                s.commit()
                s.refresh(u)
                logger.info("user_created", user_id=u.id, email=email)
                return u
            except IntegrityError:
                s.rollback()
                raise HTTPException(status_code=409, detail="Пользователь с таким email уже существует")

    def get_user_by_email(self, email: str) -> Optional[User]:
        with self._get_sync_session() as s:
            return s.exec(select(User).where(User.email == email)).first()

    def get_user_by_id(self, user_id: int) -> Optional[User]:
        with self._get_sync_session() as s:
            return s.get(User, user_id)

    def get_all_users(self) -> List[User]:
        with self._get_sync_session() as s:
            return list(s.exec(select(User).order_by(User.id)).all())

    def get_users_paginated(
        self, page: int = 1, page_size: int = 15, sort: str = "id",
        order: str = "asc", role: str = "", department: str = "",
        clearance: int = -1, email: str = "",
    ) -> dict:
        try:
            with self._get_sync_session() as s:
                q = select(User)
                if role and role != "all":
                    q = q.where(User.role == role)
                if department and department != "all":
                    q = q.where(User.department == department)
                if clearance >= 0:
                    q = q.where(User.clearance_level == clearance)
                if email:
                    q = q.where(User.email.contains(email))
                sort_col = getattr(User, sort, User.id)
                q = q.order_by(sort_col.desc() if order == "desc" else sort_col.asc())
                # Используем execute() + scalar_one() вместо exec() для func.count()
                total = s.execute(select(func.count()).select_from(q.subquery())).scalar_one()
                # Используем execute() + scalars() вместо exec() для получения моделей
                result = s.execute(q.offset((page - 1) * page_size).limit(page_size))
                users = result.scalars().all()
                return {
                    "users": [
                        {
                            "id": u.id, "email": u.email, "username": u.username,
                            "role": u.role, "department": u.department,
                            "clearance_level": u.clearance_level, "is_active": u.is_active,
                        }
                        for u in users
                    ],
                    "total": total,
                }
        except Exception as e:
            logger.exception("get_users_paginated_failed", error=str(e), page=page, page_size=page_size, sort=sort, order=order)
            raise

    def update_user(self, user_id: int, updates: dict) -> Optional[User]:
        with self._get_sync_session() as s:
            u = s.get(User, user_id)
            if not u:
                return None
            for k, v in updates.items():
                if k in {"role", "department", "clearance_level", "is_active"} and hasattr(u, k):
                    setattr(u, k, v)
            s.commit()
            s.refresh(u)
            logger.info("user_updated", user_id=user_id, updates=updates)
            return u

    def delete_user(self, user_id: int) -> bool:
        with self._get_sync_session() as s:
            u = s.get(User, user_id)
            if not u:
                return False
            s.delete(u)
            s.commit()
            logger.info("user_deleted", user_id=user_id)
            return True

    # ─── Departments ────────────────────────────────────────────────────────


    def get_departments(self) -> list[dict]:
        try:
            with self._get_sync_session() as s:
                result = s.execute(select(Department).order_by(Department.name))
                deps = result.scalars().all()
                return [
                    {"id": d.id, "name": d.name, "code": d.code, "description": d.description}
                    for d in deps
                ]
        except Exception as e:
            logger.exception("get_departments_failed", error=str(e))
            raise

    def create_department(self, name: str, code: str, description: Optional[str] = None) -> Department:
        with self._get_sync_session() as s:
            if s.exec(select(Department).where(Department.code == code)).first():
                raise HTTPException(409, f"Отдел с кодом '{code}' уже существует")
            d = Department(name=name, code=code, description=description)
            s.add(d)
            s.commit()
            s.refresh(d)
            logger.info("department_created", id=d.id, name=name, code=code)
            return d

    def update_department(
        self, dep_id: int, name: str, code: str, description: Optional[str] = None
    ) -> Optional[Department]:
        with self._get_sync_session() as s:
            d = s.get(Department, dep_id)
            if not d:
                return None
            if code != d.code and s.exec(select(Department).where(Department.code == code)).first():
                raise HTTPException(409, f"Отдел с кодом '{code}' уже существует")
            d.name = name
            d.code = code
            d.description = description
            s.commit()
            s.refresh(d)
            logger.info("department_updated", id=dep_id)
            return d

    def delete_department(self, dep_id: int) -> bool:
        with self._get_sync_session() as s:
            d = s.get(Department, dep_id)
            if not d:
                return False
            users = s.exec(select(User).where(User.department == d.code)).all()
            if users:
                raise HTTPException(
                    409,
                    f"Невозможно удалить: отдел '{d.name}' содержит {len(users)} пользователей",
                )
            s.delete(d)
            s.commit()
            logger.info("department_deleted", id=dep_id, name=d.name)
            return True

    # ─── File Metadata (duplicate detection) ────────────────────────────────

    def file_exists(
        self, filename: str, file_size: int, file_modified: Optional[str] = None
    ) -> Optional[dict]:
        """Check if a file with same name + size + modified date already exists."""
        with self._get_sync_session() as s:
            q = select(FileMetadata).where(
                FileMetadata.filename == filename,
                FileMetadata.file_size == file_size,
            )
            if file_modified:
                try:
                    dt = datetime.fromisoformat(file_modified.replace("Z", "+00:00"))
                    q = q.where(FileMetadata.file_modified == dt)
                except (ValueError, TypeError):
                    pass
            existing = s.exec(q).first()
            if existing:
                return {
                    "id": existing.id,
                    "filename": existing.filename,
                    "document_id": existing.document_id,
                    "status": existing.status,
                }
            return None

    def create_file_metadata(
        self, filename: str, file_size: int, file_modified: Optional[str] = None
    ) -> FileMetadata:
        """Record a new file upload attempt."""
        with self._get_sync_session() as s:
            r = FileMetadata(filename=filename, file_size=file_size, file_modified=None, status="pending")
            if file_modified:
                try:
                    r.file_modified = datetime.fromisoformat(file_modified.replace("Z", "+00:00"))
                except (ValueError, TypeError):
                    pass
            s.add(r)
            s.commit()
            s.refresh(r)
            logger.info("file_metadata_created", id=r.id, filename=filename)
            return r

    def update_file_metadata(self, meta_id: int, document_id: str, status: str) -> None:
        """Link file metadata to document_id after successful ingestion."""
        with self._get_sync_session() as s:
            r = s.get(FileMetadata, meta_id)
            if r:
                r.document_id = document_id
                r.status = status
                s.commit()
                logger.info("file_metadata_updated", id=meta_id, document_id=document_id, status=status)

    def delete_file_metadata_by_document(self, document_id: str) -> None:
        """Remove file metadata when document is deleted."""
        with self._get_sync_session() as s:
            rows = s.exec(select(FileMetadata).where(FileMetadata.document_id == document_id)).all()
            for r in rows:
                s.delete(r)
            if rows:
                s.commit()
                logger.info("file_metadata_deleted", document_id=document_id, count=len(rows))

    def clear_all_file_metadata(self) -> int:
        """Remove ALL file_metadata records. Used by 'clear all' operation."""
        with self._get_sync_session() as s:
            rows = s.exec(select(FileMetadata)).all()
            count = len(rows)
            for r in rows:
                s.delete(r)
            if rows:
                s.commit()
            logger.info("file_metadata_cleared_all", count=count)
            return count

    # ─── Sessions & Messages ────────────────────────────────────────────────

    def create_session(
        self, session_id: str, user_id: int, username: Optional[str] = None
    ) -> ChatSession:
        with self._get_sync_session() as s:
            cs = ChatSession(id=session_id, user_id=user_id, username=username)
            s.add(cs)
            s.commit()
            s.refresh(cs)
            return cs

    def get_session(self, session_id: str) -> Optional[ChatSession]:
        with self._get_sync_session() as s:
            return s.get(ChatSession, session_id)

    def get_user_sessions(self, user_id: int) -> List[ChatSession]:
        with self._get_sync_session() as s:
            return list(
                s.exec(
                    select(ChatSession)
                    .where(ChatSession.user_id == user_id)
                    .order_by(ChatSession.created_at.desc())
                ).all()
            )

    def delete_session(self, session_id: str) -> bool:
        with self._get_sync_session() as s:
            cs = s.get(ChatSession, session_id)
            if cs:
                s.delete(cs)
                s.commit()
                return True
            return False

    def save_message(
        self, user_id: int, role: str, content: str,
        session_id: str = "default", sources: Optional[str] = None,
    ) -> ChatMessage:
        with self._get_sync_session() as s:
            m = ChatMessage(
                user_id=user_id, role=role, content=content,
                session_id=session_id, sources=sources,
            )
            s.add(m)
            s.commit()
            s.refresh(m)
            return m

    def get_chat_history(self, user_id: int, limit: int = 100) -> list[ChatMessage]:
        with self._get_sync_session() as s:
            return list(
                s.exec(
                    select(ChatMessage)
                    .where(ChatMessage.user_id == user_id)
                    .order_by(ChatMessage.created_at.asc())
                    .limit(limit)
                ).all()
            )

    def clear_chat_history(self, user_id: int) -> int:
        with self._get_sync_session() as s:
            ms = s.exec(select(ChatMessage).where(ChatMessage.user_id == user_id)).all()
            for m in ms:
                s.delete(m)
            s.commit()
            return len(ms)

    # ─── Admin Settings ─────────────────────────────────────────────────────

    def get_all_admin_settings(self) -> list[AdminSetting]:
        with self._get_sync_session() as s:
            return list(
                s.exec(
                    select(AdminSetting).where(AdminSetting.is_active == True)  # noqa: E712
                ).all()
            )

    def get_admin_settings_by_category(self, category: str) -> list[AdminSetting]:
        with self._get_sync_session() as s:
            return list(
                s.exec(
                    select(AdminSetting).where(
                        AdminSetting.category == category,
                        AdminSetting.is_active == True,  # noqa: E712
                    )
                ).all()
            )

    def update_admin_setting(
        self, setting_id: int, value: Any, updated_by: int,
    ) -> Optional[AdminSetting]:
        with self._get_sync_session() as s:
            setting = s.get(AdminSetting, setting_id)
            if not setting:
                return None

            old_value = setting.value
            new_value_str = json.dumps(value, ensure_ascii=False) if not isinstance(value, str) else value

            setting.value = new_value_str
            setting.updated_by = updated_by
            setting.updated_at = datetime.now(timezone.utc)

            audit = AdminSettingsAudit(
                setting_id=setting.id,
                old_value=old_value,
                new_value=new_value_str,
                changed_by=updated_by,
                changed_at=datetime.now(timezone.utc),
            )
            s.add(audit)
            s.commit()
            s.refresh(setting)
            logger.info(
                "admin_setting_updated",
                setting_id=setting_id,
                category=setting.category,
                key=setting.key,
            )
            return setting

    def create_admin_setting(
        self, category: str, key: str, value: Any, description: str = "",
    ) -> AdminSetting:
        value_str = json.dumps(value, ensure_ascii=False) if not isinstance(value, str) else value
        with self._get_sync_session() as s:
            setting = AdminSetting(
                category=category,
                key=key,
                value=value_str,
                description=description or None,
            )
            s.add(setting)
            s.commit()
            s.refresh(setting)
            logger.info(
                "admin_setting_created",
                id=setting.id,
                category=category,
                key=key,
            )
            return setting

    def get_admin_settings_history(
        self, limit: int = 50, offset: int = 0,
    ) -> list[AdminSettingsAudit]:
        with self._get_sync_session() as s:
            return list(
                s.exec(
                    select(AdminSettingsAudit)
                    .order_by(AdminSettingsAudit.changed_at.desc())
                    .offset(offset)
                    .limit(limit)
                ).all()
            )


database_service = DatabaseService()
