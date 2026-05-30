"""Structured logging configuration for GraphRAG platform.

Uses structlog with environment-specific formatters.
Adapted from FastAPI-LangGraph template.
"""

import logging
import sys
from contextvars import ContextVar
from pathlib import Path
from typing import Any, Dict, Optional

import structlog

from app.core.config import Environment, settings

settings.LOG_DIR.mkdir(parents=True, exist_ok=True)

_request_context: ContextVar[Optional[Dict[str, Any]]] = ContextVar("request_context", default=None)


def bind_context(**kwargs: Any) -> None:
    current = _request_context.get() or {}
    _request_context.set({**current, **kwargs})


def clear_context() -> None:
    _request_context.set(None)


def get_context() -> Dict[str, Any]:
    return _request_context.get() or {}


def add_context_to_event_dict(
    logger_: Any, method_name: str, event_dict: Dict[str, Any]
) -> Dict[str, Any]:
    context = get_context()
    if context:
        event_dict.update(context)
    return event_dict


def configure_logging():
    """Configure structlog with environment-appropriate processors."""
    shared_processors = [
        structlog.contextvars.merge_contextvars,
        add_context_to_event_dict,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if settings.LOG_FORMAT == "json" or settings.ENVIRONMENT == Environment.PRODUCTION:
        renderer = structlog.processors.JSONRenderer(ensure_ascii=False)
    else:
        renderer = structlog.dev.ConsoleRenderer()

    structlog.configure(
        processors=[*shared_processors, structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        processors=[structlog.stdlib.ProcessorFormatter.remove_processors_meta, renderer],
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    # File handler
    file_handler = logging.FileHandler(settings.LOG_DIR / "graphrag.log", encoding="utf-8")
    file_handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.addHandler(file_handler)
    root_logger.setLevel(getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO))


configure_logging()
logger = structlog.get_logger("graphrag")
