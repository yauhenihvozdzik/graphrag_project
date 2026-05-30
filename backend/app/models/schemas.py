"""Pydantic schemas for API request/response models.

Covers auth, chat, ingestion, and graph visualization endpoints.
"""

import re
from datetime import datetime
from typing import Any, List, Literal, Optional

from pydantic import BaseModel, Field, SecretStr, field_validator, model_validator


# ── Base ──

class BaseResponse(BaseModel):
    """Base response with success flag."""

    success: bool = True


# ── Auth Schemas ──

class Token(BaseModel):
    access_token: str = Field(..., description="JWT access token")
    token_type: str = Field(default="bearer")
    expires_at: datetime


class TokenResponse(BaseResponse):
    access_token: str
    token_type: str = "bearer"
    expires_at: datetime


class UserCreate(BaseModel):
    email: str = Field(..., description="Email (e.g. admin@graphrag.local)")
    password: SecretStr = Field(..., min_length=8, max_length=64)
    username: Optional[str] = Field(default=None, max_length=50)
    role: str = Field(default="viewer")
    department: str = Field(default="all")

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]{2,}$", v):
            raise ValueError("Некорректный email адрес")
        return v.lower()

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: SecretStr) -> SecretStr:
        password = v.get_secret_value()
        if len(password) < 8:
            raise ValueError("Пароль должен быть не менее 8 символов")
        if not re.search(r"[A-Z]", password):
            raise ValueError("Пароль должен содержать заглавную букву")
        if not re.search(r"\d", password):
            raise ValueError("Пароль должен содержать цифру")
        return v


class UserResponse(BaseResponse):
    id: int
    email: str
    username: Optional[str]
    role: str
    department: str
    created_at: datetime


class LoginRequest(BaseModel):
    email: str = Field(..., description="Email")
    password: SecretStr

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]{2,}$", v):
            raise ValueError("Некорректный email адрес")
        return v.lower()


class SessionResponse(BaseResponse):
    session_id: str
    name: str
    created_at: datetime


# ── Chat Schemas ──

class Message(BaseModel):
    """Chat message."""

    model_config = {"extra": "ignore"}

    role: Literal["user", "assistant", "system"] = Field(..., description="Роль отправителя")
    content: str = Field(..., min_length=1, max_length=10000)

    @field_validator("content")
    @classmethod
    def validate_content(cls, v: str) -> str:
        if re.search(r"<script.*?>.*?</script>", v, re.IGNORECASE | re.DOTALL):
            raise ValueError("Обнаружены потенциально опасные теги")
        if "\0" in v:
            raise ValueError("Текст содержит недопустимые символы")
        return v


class ChatRequest(BaseModel):
    """Chat request — accepts both {message} and {messages} formats."""
    messages: List[Message] = Field(default_factory=list, min_length=1)
    session_id: Optional[str] = None
    # Legacy flat fields (converted in model_validator)
    message: Optional[str] = Field(default=None, max_length=10000, exclude=True)

    @model_validator(mode="before")
    @classmethod
    def normalize_format(cls, data: Any) -> Any:
        if isinstance(data, dict):
            # Convert {message: "..."} → {messages: [{role: "user", content: "..."}]}
            if "message" in data and not data.get("messages"):
                data["messages"] = [{"role": "user", "content": data.pop("message")}]
            # Ensure messages is always present for validation
            if "messages" not in data and "message" not in data:
                pass  # Will fail on field validation
        return data


class ChatResponse(BaseResponse):
    messages: List[Message]
    sources: List[dict] = Field(default_factory=list, description="Источники из графа знаний")


class StreamResponse(BaseResponse):
    event: str = "token"
    data: str = ""


# ── Ingestion Schemas ──

class IngestUrlRequest(BaseModel):
    """URL ingestion request."""
    url: str = Field(..., description="URL to ingest")
    title: str = Field(default="", description="Optional title")
    clearance_level: int = Field(default=0, ge=0, le=3)
    department: str = Field(default="all")

class IngestRequest(BaseModel):
    """Document ingestion request."""

    title: str = Field(..., max_length=500)
    source: str = Field(default="upload", description="Источник документа")
    content: Optional[str] = Field(default=None, description="Текст документа (альтернатива файлу)")
    metadata: dict[str, Any] = Field(default_factory=dict)
    clearance_level: int = Field(default=0, ge=0, le=3)
    department: str = Field(default="all")


class IngestResponse(BaseResponse):
    document_id: str
    chunks_count: int
    entities_count: int
    message: str


class IngestStatusResponse(BaseModel):
    success: bool = False
    document_id: str
    status: str  # processing, completed, failed
    step: int = 0
    step_name: str = ""
    total_steps: int = 4
    message: str = ""
    chunks_count: int = 0
    entities_count: int = 0
    vectors_count: int = 0
    error: Optional[str] = None

    @model_validator(mode="after")
    def set_success(self):
        self.success = self.status not in ("failed",)
        return self


# ── Graph Schemas ──

class GraphNode(BaseModel):
    id: str
    name: str
    type: str = "entity"
    properties: dict[str, Any] = Field(default_factory=dict)


class GraphEdge(BaseModel):
    source: str
    target: str
    type: str
    properties: dict[str, Any] = Field(default_factory=dict)


class GraphVisualizationResponse(BaseResponse):
    nodes: List[GraphNode]
    edges: List[GraphEdge]
    stats: dict[str, int] = Field(default_factory=dict)


class GraphSearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=500)
    entity_type: Optional[str] = None
    depth: int = Field(default=2, ge=1, le=5)
    limit: int = Field(default=50, ge=1, le=500)


# ── LangGraph State ──

class GraphState(BaseModel):
    """State definition for the LangGraph agent workflow."""

    messages: list = Field(default_factory=list, description="Conversation messages")
    context: str = Field(default="", description="Retrieved GraphRAG context")
    entities: list[str] = Field(default_factory=list, description="Extracted entities from query")
    sources: list[dict] = Field(default_factory=list, description="Source references")
    requires_graph: bool = Field(default=False, description="Whether graph traversal is needed")


# ── Health ──

class HealthResponse(BaseResponse):
    version: str
    environment: str
    services: dict[str, str] = Field(default_factory=dict)


# ── Department Schemas ──

class DepartmentCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    code: str = Field(..., min_length=1, max_length=50)
    description: Optional[str] = Field(default=None, max_length=500)


class DepartmentUpdate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    code: str = Field(..., min_length=1, max_length=50)
    description: Optional[str] = Field(default=None, max_length=500)


class DepartmentResponse(BaseResponse):
    id: int
    name: str
    code: str
    description: Optional[str] = None
