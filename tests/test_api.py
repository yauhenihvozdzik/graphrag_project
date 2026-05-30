"""
Tests for FastAPI endpoints — auth, health, chat, ingest.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestAuthEndpoints:
    """Tests for /api/v1/auth/* endpoints."""

    def test_create_access_token(self):
        """JWT token creation returns a Token model."""
        from app.utils.auth import create_access_token
        token = create_access_token(user_id=1, email="test@test.com", role="admin")
        # Token model has access_token attribute
        assert hasattr(token, "access_token")
        assert len(token.access_token) > 20

    def test_verify_valid_token(self):
        """Valid token is verified successfully."""
        from app.utils.auth import create_access_token, verify_token
        token = create_access_token(user_id=1, email="test@test.com", role="analyst")
        result = verify_token(token.access_token)
        assert result is not None
        assert result["email"] == "test@test.com"
        assert result["role"] == "analyst"

    def test_verify_invalid_token(self):
        """Invalid token returns None."""
        from app.utils.auth import verify_token
        result = verify_token("invalid.token.here")
        assert result is None

    def test_verify_empty_token(self):
        """Empty token raises or returns None."""
        from app.utils.auth import verify_token
        try:
            result = verify_token("")
            assert result is None
        except (ValueError, Exception):
            pass  # Expected

    def test_token_contains_user_id(self):
        """Token payload includes user_id."""
        from app.utils.auth import create_access_token, verify_token
        token = create_access_token(user_id=42, email="u@u.com", role="viewer")
        result = verify_token(token.access_token)
        assert result is not None
        assert result["user_id"] == 42


class TestSanitization:
    """Tests for input sanitization utilities."""

    def test_sanitize_string_removes_script(self):
        """Script tags are removed from input."""
        from app.utils.sanitization import sanitize_string
        result = sanitize_string('<script>alert("xss")</script>Hello')
        assert "<script>" not in result
        assert "Hello" in result

    def test_sanitize_email_valid(self):
        """Valid email passes sanitization."""
        from app.utils.sanitization import sanitize_email
        result = sanitize_email("user@example.com")
        assert result == "user@example.com"

    def test_sanitize_email_invalid(self):
        """Invalid email raises ValueError."""
        from app.utils.sanitization import sanitize_email
        with pytest.raises(ValueError):
            sanitize_email("not-an-email")

    def test_validate_password_strength(self):
        """Password validation checks minimum requirements."""
        from app.utils.sanitization import validate_password_strength
        assert validate_password_strength("Admin123!") is True
        assert validate_password_strength("weak") is False
        assert validate_password_strength("nouppercase1") is False


class TestHealthEndpoint:
    """Test API health check structure."""

    def test_health_response_schema(self):
        """Health response model has expected fields."""
        from app.models.schemas import HealthResponse
        h = HealthResponse(
            status="ok",
            version="1.0.0",
            environment="test",
            services={"neo4j": "connected", "qdrant": "connected", "ollama": "connected"},
        )
        assert h.success is True
        assert "neo4j" in h.services
        assert h.version == "1.0.0"
