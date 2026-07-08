"""Seed default admin settings into the database.

Run after Alembic migrations to populate the admin_settings table
with sensible defaults from current codebase constants.
"""

import json
from datetime import datetime, timezone

from sqlmodel import Session, select

from app.core.prompts import (
    SYSTEM_PROMPT,
    SPELLING_CORRECTION_PROMPT,
    ENTITY_EXTRACTION_PROMPT,
    NO_CONTEXT_MESSAGE,
    CONTEXT_HEADER,
)
from app.core.constants import (
    ALLOWED_FILE_EXTENSIONS,
    LLM_TEMPERATURE_CHAT,
    LLM_TEMPERATURE_NER,
    LLM_TEMPERATURE_SPELLING,
    STOP_TOKENS,
)
from app.core.config import settings
from app.core.langgraph.agent_utils import BUSINESS_DOMAIN_KEYWORDS
from app.core.security.guardrails import INJECTION_PATTERNS, PII_PATTERNS
from app.models.admin import AdminSetting


DEFAULTS: list[tuple[str, str, str, str]] = [
    # ── prompts ──
    ("prompts", "system_prompt", SYSTEM_PROMPT, "Системный промпт для RAG-агента"),
    ("prompts", "spelling_correction_prompt", SPELLING_CORRECTION_PROMPT, "Промпт коррекции опечаток"),
    ("prompts", "entity_extraction_prompt", ENTITY_EXTRACTION_PROMPT, "NER промпт для извлечения сущностей"),
    ("prompts", "no_context_message", NO_CONTEXT_MESSAGE, "Сообщение при отсутствии контекста"),
    ("prompts", "context_header", CONTEXT_HEADER, "Заголовок секции контекста"),
    # ── llm_temperature ──
    ("llm_temperature", "temperature_chat", str(LLM_TEMPERATURE_CHAT), "Температура генерации ответа в чате"),
    ("llm_temperature", "temperature_spelling", str(LLM_TEMPERATURE_SPELLING), "Температура коррекции опечаток"),
    ("llm_temperature", "temperature_ner", str(LLM_TEMPERATURE_NER), "Температура NER"),
    ("llm_temperature", "max_tokens", str(settings.MAX_TOKENS), "Максимум токенов генерации"),
    ("llm_temperature", "num_ctx", str(settings.OLLAMA_NUM_CTX), "Контекстное окно Ollama"),
    # ── guardrails ──
    ("guardrails", "guardrails_enabled", "true", "Включение/отключение guardrails"),
    ("guardrails", "injection_threshold", str(settings.PROMPT_INJECTION_THRESHOLD), "Порог срабатывания prompt injection"),
    ("guardrails", "max_input_length", str(settings.MAX_INPUT_LENGTH), "Максимальная длина ввода пользователя"),
    ("guardrails", "injection_patterns", json.dumps(INJECTION_PATTERNS, ensure_ascii=False), "Массив regex-паттернов для обнаружения injection"),
    (
        "guardrails",
        "pii_patterns",
        json.dumps({name: [strict, loose, label] for name, (strict, loose, label) in PII_PATTERNS.items()}, ensure_ascii=False),
        "Словарь PII-паттернов (strict, loose, label)",
    ),
    # ── off_topic ──
    ("off_topic", "keywords", json.dumps(BUSINESS_DOMAIN_KEYWORDS, ensure_ascii=False), "Ключевые слова бизнес-домена для фильтрации off-topic"),
    # ── stop_tokens ──
    ("stop_tokens", "tokens", json.dumps(STOP_TOKENS, ensure_ascii=False), "Стоп-токены для LLM"),
    # ── rag_parameters ──
    ("rag_parameters", "reranker_min_results", str(settings.RERANKER_MIN_RESULTS), "Минимальное количество результатов реранкера"),
    ("rag_parameters", "reranker_max_results", str(settings.RERANKER_MAX_RESULTS), "Максимальное количество результатов реранкера"),
    ("rag_parameters", "reranker_scale_factor", str(settings.RERANKER_SCALE_FACTOR), "Масштабирующий коэффициент реранкера"),
    # ── other ──
    ("other", "allowed_file_extensions", json.dumps(list(ALLOWED_FILE_EXTENSIONS), ensure_ascii=False), "Допустимые расширения файлов для загрузки"),
]


def seed_admin_settings(db_service=None) -> int:
    """Insert default admin settings if they don't exist.

    Args:
        db_service: Optional DatabaseService instance. Creates one if None.

    Returns:
        Number of settings inserted.
    """
    if db_service is None:
        from app.services.database import DatabaseService
        db_service = DatabaseService()

    now = datetime.now(timezone.utc)
    inserted = 0

    with Session(db_service.engine) as s:
        for category, key, value, description in DEFAULTS:
            existing = s.exec(
                select(AdminSetting).where(
                    AdminSetting.category == category,
                    AdminSetting.key == key,
                )
            ).first()
            if existing:
                continue

            setting = AdminSetting(
                category=category,
                key=key,
                value=value,
                description=description,
                created_at=now,
                updated_at=now,
            )
            s.add(setting)
            inserted += 1

        s.commit()

    from app.core.logging import logger
    logger.info("admin_settings_seeded", count=inserted)
    return inserted


if __name__ == "__main__":
    count = seed_admin_settings()
    print(f"Seeded {count} admin settings.")
