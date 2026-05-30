"""Authentication and authorization endpoints."""

import smtplib
import uuid
from email.message import EmailMessage
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import settings
from app.core.logging import logger
from app.core.metrics import auth_attempts_total
from app.core.security.rbac import AccessContext, ClearanceLevel, Role
from app.models.schemas import (
    LoginRequest, SessionResponse, TokenResponse, UserCreate, UserResponse,
)
from app.services.database import database_service
from app.utils.auth import create_access_token, verify_token
from app.utils.sanitization import sanitize_email, sanitize_string

router = APIRouter()
security = HTTPBearer()

# ── SMTP config ──
SMTP_HOST = getattr(settings, "SMTP_HOST", "localhost")
SMTP_PORT = int(getattr(settings, "SMTP_PORT", "1025"))
SMTP_USER = getattr(settings, "SMTP_USER", "")
SMTP_PASSWORD = getattr(settings, "SMTP_PASSWORD", "")
SMTP_USE_TLS = str(getattr(settings, "SMTP_USE_TLS", "true")).lower() == "true"
SMTP_FROM = SMTP_USER or "graph@rag.by"


def _send_email(to_email: str, subject: str, body: str):
    msg = EmailMessage()
    msg["From"] = SMTP_FROM
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.set_content(body, charset="utf-8")
    try:
        if SMTP_PORT == 465:
            import ssl
            ctx = ssl.create_default_context()
            with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=15, context=ctx) as smtp:
                if SMTP_USER and SMTP_PASSWORD:
                    smtp.login(SMTP_USER, SMTP_PASSWORD)
                smtp.send_message(msg)
        else:
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15) as smtp:
                if SMTP_USE_TLS:
                    smtp.starttls()
                if SMTP_USER and SMTP_PASSWORD:
                    smtp.login(SMTP_USER, SMTP_PASSWORD)
                smtp.send_message(msg)
        logger.info("email_sent", to=to_email, subject=subject, host=SMTP_HOST)
    except Exception as e:
        logger.warning("email_send_failed", to=to_email, error=str(e), host=SMTP_HOST)


async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    """Verify JWT and return user info. Does NOT check is_active — that is done only at login."""
    try:
        token = sanitize_string(credentials.credentials)
        payload = verify_token(token)
        if payload is None:
            raise HTTPException(401, "Недействительные учётные данные")
        user = database_service.get_user_by_id(payload["user_id"])
        if not user:
            raise HTTPException(401, "Пользователь не найден")
        return {
            "user_id": user.id, "email": user.email, "username": user.username,
            "role": user.role, "department": user.department, "clearance_level": user.clearance_level,
        }
    except ValueError as e:
        raise HTTPException(401, str(e))


def get_access_context(user=Depends(get_current_user)) -> AccessContext:
    return AccessContext(user_id=str(user["user_id"]), role=Role(user.get("role", "viewer")), department=user.get("department", "all"), clearance=ClearanceLevel(user.get("clearance_level", 0)))


@router.post("/register", response_model=UserResponse)
async def register(r: Request, data: UserCreate):
    try:
        email = sanitize_email(data.email); pwd = data.password.get_secret_value()
        uname = sanitize_string(data.username) if data.username else None
        user = database_service.create_user(email=email, password=pwd, username=uname)
        auth_attempts_total.labels(status="register_success").inc()
        logger.info("user_registered", user_id=user.id, email=email)
        _send_email(email, "Регистрация в GraphRAG",
            f"Здравствуйте!\n\nВы зарегистрированы в системе GraphRAG.\nВаш аккаунт будет активирован администратором.\nОжидайте письма об активации.")
        return UserResponse(id=user.id, email=user.email, username=user.username, role=user.role, department=user.department, created_at=user.created_at)
    except HTTPException:
        auth_attempts_total.labels(status="register_conflict").inc()
        raise HTTPException(409, "Пользователь с таким email уже зарегистрирован")
    except Exception as e:
        auth_attempts_total.labels(status="register_error").inc()
        logger.exception("registration_failed", error=str(e))
        raise HTTPException(500, "Ошибка регистрации. Попробуйте позже.")


@router.post("/login", response_model=TokenResponse)
async def login(r: Request, data: LoginRequest):
    email = sanitize_email(data.email); pwd = data.password.get_secret_value()
    user = database_service.get_user_by_email(email)
    if not user:
        auth_attempts_total.labels(status="login_failed").inc()
        raise HTTPException(401, "Пользователь с таким email не найден")
    if not user.verify_password(pwd):
        auth_attempts_total.labels(status="login_failed").inc()
        raise HTTPException(401, "Неверный пароль")
    if not user.is_active and user.role != "admin":
        auth_attempts_total.labels(status="login_inactive").inc()
        raise HTTPException(403, "Аккаунт ещё не активирован. Ожидайте подтверждения администратора.")
    token = create_access_token(user_id=user.id, email=user.email, role=user.role)
    auth_attempts_total.labels(status="login_success").inc()
    logger.info("user_logged_in", user_id=user.id)
    return TokenResponse(access_token=token.access_token, token_type=token.token_type, expires_at=token.expires_at)


@router.get("/me", response_model=UserResponse)
async def get_me(user=Depends(get_current_user)):
    u = database_service.get_user_by_id(user["user_id"])
    if not u: raise HTTPException(404, "Пользователь не найден")
    return UserResponse(id=u.id, email=u.email, username=u.username, role=u.role, department=u.department, created_at=u.created_at)


@router.post("/sessions", response_model=SessionResponse)
async def create_session(user=Depends(get_current_user)):
    sid = str(uuid.uuid4())
    s = database_service.create_session(session_id=sid, user_id=user["user_id"], username=user.get("username"))
    return SessionResponse(session_id=s.id, name=s.name, created_at=s.created_at)

@router.get("/sessions")
async def list_sessions(user=Depends(get_current_user)):
    sessions = database_service.get_user_sessions(user["user_id"])
    return {"success": True, "sessions": [{"session_id": s.id, "name": s.name, "created_at": s.created_at.isoformat()} for s in sessions]}


@router.get("/users")
async def list_users(
    user=Depends(get_current_user),
    page: int = Query(default=1, ge=1), page_size: int = Query(default=15, ge=1, le=100),
    sort: str = Query(default="id"), order: str = Query(default="asc"),
    role: str = Query(default=""), department: str = Query(default=""),
    clearance: int = Query(default=-1), email: str = Query(default=""),
):
    if user.get("role") != "admin": raise HTTPException(403, "Только администратор")
    data = database_service.get_users_paginated(page=page, page_size=page_size, sort=sort, order=order, role=role, department=department, clearance=clearance, email=email)
    return {"success": True, "users": data["users"], "total": data["total"], "page": page, "page_size": page_size}


@router.put("/users/{user_id}")
async def update_user(user_id: int, updates: dict, user=Depends(get_current_user)):
    if user.get("role") != "admin": raise HTTPException(403, "Только администратор")
    old = database_service.get_user_by_id(user_id)
    if not old: raise HTTPException(404, "Пользователь не найден")
    u = database_service.update_user(user_id, updates)
    if not u: raise HTTPException(404, "Пользователь не найден")
    if "is_active" in updates:
        admin_email = user.get("email", "admin@graphrag.local")
        if updates["is_active"]:
            _send_email(u.email, "Аккаунт активирован — GraphRAG",
                f"Здравствуйте!\n\nВаш аккаунт активирован администратором.\nМожете войти в систему: {settings.ALLOWED_ORIGINS[0] if settings.ALLOWED_ORIGINS else 'http://localhost:3000'}\n\nПо вопросам: {admin_email}")
        else:
            _send_email(u.email, "Аккаунт деактивирован — GraphRAG",
                f"Здравствуйте!\n\nВаш аккаунт деактивирован администратором.\nПо вопросам обращайтесь: {admin_email}")
    return {"success": True, "user": {"id": u.id, "email": u.email, "role": u.role, "department": u.department, "clearance_level": u.clearance_level, "is_active": u.is_active}}

@router.delete("/users/{user_id}")
async def delete_user(user_id: int, user=Depends(get_current_user)):
    if user.get("role") != "admin": raise HTTPException(403, "Только администратор")
    if int(user["user_id"]) == user_id: raise HTTPException(400, "Нельзя удалить самого себя")
    ok = database_service.delete_user(user_id)
    if not ok: raise HTTPException(404, "Пользователь не найден")
    return {"success": True}


@router.post("/users/{user_id}/impersonate", response_model=TokenResponse)
async def impersonate(user_id: int, user=Depends(get_current_user)):
    if user.get("role") != "admin": raise HTTPException(403, "Только администратор")
    target = database_service.get_user_by_id(user_id)
    if not target: raise HTTPException(404, "Пользователь не найден")
    token = create_access_token(user_id=target.id, email=target.email, role=target.role)
    logger.info("impersonate", admin_id=user["user_id"], target_id=user_id)
    return TokenResponse(access_token=token.access_token, token_type=token.token_type, expires_at=token.expires_at)