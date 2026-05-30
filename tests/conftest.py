"""
Shared pytest fixtures for GraphRAG Platform tests.
"""

import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Ensure backend app is on the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

# ── Mock heavy dependencies before importing app ──────────

# Mock neo4j driver
mock_neo4j = MagicMock()
sys.modules["neo4j"] = mock_neo4j

# Mock qdrant_client
mock_qdrant = MagicMock()
sys.modules["qdrant_client"] = mock_qdrant
sys.modules["qdrant_client.http"] = MagicMock()
sys.modules["qdrant_client.http.models"] = MagicMock()
sys.modules["qdrant_client.models"] = MagicMock()

# Mock optional modules
for mod in [
    "langgraph", "langgraph.graph", "langgraph.graph.state",
    "langchain_core", "langchain_core.tools",
    "opentelemetry", "opentelemetry.trace", "opentelemetry.sdk",
    "opentelemetry.sdk.trace", "opentelemetry.sdk.trace.export",
    "opentelemetry.exporter.otlp", "opentelemetry.exporter.otlp.proto.grpc.trace_exporter",
    "opentelemetry.instrumentation.fastapi",
    "psycopg", "psycopg_pool", "langgraph.checkpoint.postgres.aio",
    "pymupdf", "fitz", "docx",
    "structlog",
    "prometheus_client",
    "sqlmodel",
    "httpx",
]:
    if mod not in sys.modules:
        sys.modules[mod] = MagicMock()

# Set env vars before importing app
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key")
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("DEBUG", "false")
os.environ.setdefault("NEO4J_URI", "bolt://localhost:7687")
os.environ.setdefault("NEO4J_PASSWORD", "test")
os.environ.setdefault("POSTGRES_HOST", "localhost")
os.environ.setdefault("POSTGRES_PASSWORD", "test")
os.environ.setdefault("QDRANT_HOST", "localhost")
os.environ.setdefault("OLLAMA_BASE_URL", "http://localhost:11434")
os.environ.setdefault("OTEL_ENABLED", "false")
os.environ.setdefault("GUARDRAILS_ENABLED", "true")


@pytest.fixture
def auth_token():
    """Generate a test JWT token."""
    from app.utils.auth import create_access_token
    token = create_access_token(user_id=1, email="test@example.com", role="admin")
    return token.access_token


@pytest.fixture
def viewer_token():
    """Generate a viewer JWT token."""
    from app.utils.auth import create_access_token
    token = create_access_token(user_id=2, email="viewer@example.com", role="viewer")
    return token.access_token


@pytest.fixture
def analyst_token():
    """Generate an analyst JWT token."""
    from app.utils.auth import create_access_token
    token = create_access_token(user_id=3, email="analyst@example.com", role="analyst")
    return token.access_token
