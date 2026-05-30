"""Input sanitization utilities.

Adapted from FastAPI-LangGraph template.
"""

import html
import re
from typing import Any, Dict, List


def sanitize_string(value: str) -> str:
    """Sanitize a string to prevent XSS and injection attacks."""
    if not isinstance(value, str):
        value = str(value)
    value = html.escape(value)
    value = re.sub(r"&lt;script.*?&gt;.*?&lt;/script&gt;", "", value, flags=re.DOTALL)
    value = value.replace("\0", "")
    return value


def sanitize_email(email: str) -> str:
    """Sanitize an email address."""
    email = sanitize_string(email)
    if not re.match(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$", email):
        raise ValueError("Некорректный формат email")
    return email.lower()


def sanitize_dict(data: Dict[str, Any]) -> Dict[str, Any]:
    """Recursively sanitize all string values in a dictionary."""
    sanitized = {}
    for key, value in data.items():
        if isinstance(value, str):
            sanitized[key] = sanitize_string(value)
        elif isinstance(value, dict):
            sanitized[key] = sanitize_dict(value)
        elif isinstance(value, list):
            sanitized[key] = sanitize_list(value)
        else:
            sanitized[key] = value
    return sanitized


def sanitize_list(data: List[Any]) -> List[Any]:
    """Recursively sanitize all string values in a list."""
    return [
        sanitize_string(item) if isinstance(item, str)
        else sanitize_dict(item) if isinstance(item, dict)
        else sanitize_list(item) if isinstance(item, list)
        else item
        for item in data
    ]


def validate_password_strength(password: str) -> bool:
    """Validate password meets minimum strength requirements."""
    if len(password) < 8:
        return False
    if not re.search(r"[A-Z]", password):
        return False
    if not re.search(r"\d", password):
        return False
    return True
