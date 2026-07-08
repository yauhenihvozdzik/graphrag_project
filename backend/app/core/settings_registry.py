"""In-memory settings registry singleton for dynamic admin configuration.

All runtime components (agent, guardrails, agent_utils) read from this
registry instead of hardcoded constants. Falls back to static values from
:mod:`app.core.constants` and :mod:`app.core.prompts` when the database
is unavailable or the registry hasn't been initialised yet.
"""

from __future__ import annotations

import json
import re
from typing import Any, Optional

from app.core.logging import logger


class SettingsRegistry:
    """Singleton in-memory cache of admin settings.

    Populated from the PostgreSQL ``admin_settings`` table on startup.
    Reloaded on every ``PUT /api/v1/admin/settings`` call so that runtime
    components always use the latest values.

    All typed getters return sensible fallback defaults from
    :mod:`app.core.constants` and :mod:`app.core.prompts` when the
    internal cache is empty or a key is missing.
    """

    _instance: Optional["SettingsRegistry"] = None
    _settings: dict[str, dict[str, Any]] = {}  # {category: {key: parsed_value}}

    # Compiled regex patterns cached after registration
    # NOTE: initialised as None so that reload() can invalidate them
    # via _invalidate_compiled_patterns() and force recompilation.
    _injection_compiled: list[re.Pattern] | None = None
    _pii_compiled: dict[str, tuple[re.Pattern, re.Pattern, str]] | None = None

    def __new__(cls) -> "SettingsRegistry":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    # ── Lifecycle ────────────────────────────────────────────────

    async def initialize(self, db_session: Any = None) -> None:
        """Load all active settings from the database into memory.

        Args:
            db_session: Optional async DB session. If ``None`` a new
                session is created via the global ``database_service``.
        """
        from app.services.database import database_service

        # NOTE: get_all_admin_settings() is a synchronous method (uses
        # sqlmodel.Session, not AsyncSession). Calling it with ``await``
        # would raise ``TypeError`` because a plain list is not awaitable.
        rows = database_service.get_all_admin_settings()
        logger.info("settings_registry_initialize_debug",
                    row_count=len(rows),
                    row_keys=[(r.category, r.key, str(r.value)[:40]) for r in rows[:5]])
        self._rebuild_cache(rows)
        logger.info("settings_registry_initialized",
                    categories=list(self._settings.keys()),
                    settings_preview={cat: list(kv.keys()) for cat, kv in self._settings.items()})

    async def reload(self, db_session: Any = None) -> None:
        """Reload all settings (called after a settings update).

        Args:
            db_session: Optional async DB session (same semantics as
                :meth:`initialize`).
        """
        self._invalidate_compiled_patterns()
        await self.initialize(db_session)
        # Notify guardrails service about potential config changes
        from app.core.security.guardrails import guardrails_service
        guardrails_service.reload_config()
        logger.info("settings_registry_reloaded")

    def _rebuild_cache(self, rows: list[Any]) -> None:
        """Rebuild ``_settings`` dict from a list of ORM rows."""
        self._settings = {}
        for row in rows:
            cat = self._settings.setdefault(row.category, {})
            cat[row.key] = self._parse_value(row.value)

    def _invalidate_compiled_patterns(self) -> None:
        """Invalidate cached compiled regex patterns so they are recompiled
        on the next call to :meth:`get_injection_patterns` or
        :meth:`get_pii_patterns`."""
        self._injection_compiled = None
        self._pii_compiled = None
        logger.info("compiled_patterns_invalidated")

    @staticmethod
    def _parse_value(raw: str) -> Any:
        """Attempt to JSON-parse a value; fall back to the raw string."""
        if not raw:
            return raw
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return raw

    # ── Generic accessors ────────────────────────────────────────

    def get(self, category: str, key: str, default: Any = None) -> Any:
        """Return a single setting value, or *default* if not found."""
        return self._settings.get(category, {}).get(key, default)

    def get_category(self, category: str) -> dict[str, Any]:
        """Return all key-value pairs for a *category*."""
        return self._settings.get(category, {})

    # ── Prompts ──────────────────────────────────────────────────

    def get_system_prompt(self) -> str:
        val = self.get("prompts", "system_prompt")
        if val:
            return val
        from app.core.prompts import SYSTEM_PROMPT

        return SYSTEM_PROMPT

    def get_spelling_prompt(self) -> str:
        val = self.get("prompts", "spelling_correction_prompt")
        if val:
            return val
        from app.core.prompts import SPELLING_CORRECTION_PROMPT

        return SPELLING_CORRECTION_PROMPT

    def get_ner_prompt(self) -> str:
        val = self.get("prompts", "entity_extraction_prompt")
        if val:
            return val
        from app.core.prompts import ENTITY_EXTRACTION_PROMPT

        return ENTITY_EXTRACTION_PROMPT

    def get_no_context_message(self) -> str:
        val = self.get("prompts", "no_context_message")
        if val:
            return val
        from app.core.prompts import NO_CONTEXT_MESSAGE

        return NO_CONTEXT_MESSAGE

    # ── LLM Temperature ──────────────────────────────────────────

    def get_temperature_chat(self) -> float:
        val = self.get("llm_temperature", "temperature_chat")
        if val is not None:
            return float(val)
        from app.core.constants import LLM_TEMPERATURE_CHAT

        return LLM_TEMPERATURE_CHAT

    def get_temperature_spelling(self) -> float:
        val = self.get("llm_temperature", "temperature_spelling")
        if val is not None:
            return float(val)
        from app.core.constants import LLM_TEMPERATURE_SPELLING

        return LLM_TEMPERATURE_SPELLING

    def get_temperature_ner(self) -> float:
        val = self.get("llm_temperature", "temperature_ner")
        if val is not None:
            return float(val)
        from app.core.constants import LLM_TEMPERATURE_NER

        return LLM_TEMPERATURE_NER

    # ── LLM Inference params ─────────────────────────────────────

    def get_max_tokens(self) -> int:
        val = self.get("llm_temperature", "max_tokens")
        if val is not None:
            return int(val)
        return 2048

    def get_num_ctx(self) -> int:
        val = self.get("llm_temperature", "num_ctx")
        if val is not None:
            return int(val)
        return 4096

    # ── Other ────────────────────────────────────────────────────

    def get_allowed_file_extensions(self) -> list:
        val = self.get("other", "allowed_file_extensions")
        if val is not None:
            if isinstance(val, str):
                import json
                return json.loads(val)
            return list(val)
        from app.core.constants import ALLOWED_FILE_EXTENSIONS
        return ALLOWED_FILE_EXTENSIONS

    # ── Guardrails ───────────────────────────────────────────────

    def get_guardrails_enabled(self) -> bool:
        val = self.get("guardrails", "guardrails_enabled")
        if val is not None:
            if isinstance(val, bool):
                return val
            return str(val).lower() in ("true", "1", "yes")
        from app.core.config import settings

        return settings.GUARDRAILS_ENABLED

    def get_injection_threshold(self) -> float:
        val = self.get("guardrails", "injection_threshold")
        if val is not None:
            return float(val)
        from app.core.config import settings

        return settings.PROMPT_INJECTION_THRESHOLD

    def get_max_input_length(self) -> int:
        val = self.get("guardrails", "max_input_length")
        if val is not None:
            return int(val)
        from app.core.config import settings

        return settings.MAX_INPUT_LENGTH

    def get_injection_patterns(self) -> list[re.Pattern]:
        """Return compiled injection regex patterns."""
        if self._injection_compiled is not None:
            return self._injection_compiled
        # Fallback: compile from hardcoded constants
        from app.core.security.guardrails import INJECTION_PATTERNS

        compiled = [re.compile(p) for p in INJECTION_PATTERNS]
        self._injection_compiled = compiled  # кэшируем
        return compiled

    def get_pii_patterns(self) -> dict[str, tuple[re.Pattern, re.Pattern, str]]:
        """Return compiled PII regex patterns."""
        if self._pii_compiled is not None:
            return self._pii_compiled
        # Fallback: use hardcoded constants
        from app.core.security.guardrails import PII_PATTERNS

        compiled = {
            name: (re.compile(strict), re.compile(loose), label)
            for name, (strict, loose, label) in PII_PATTERNS.items()
        }
        self._pii_compiled = compiled  # кэшируем
        return compiled

    def register_injection_patterns(self, patterns: list[str]) -> None:
        """Register and compile injection patterns.

        Args:
            patterns: List of raw regex strings.
        """
        self._injection_compiled = [re.compile(p) for p in patterns]
        logger.info("injection_patterns_registered", count=len(patterns))

    def register_pii_patterns(self, patterns: dict[str, tuple[str, str, str]]) -> None:
        """Register and compile PII patterns.

        Args:
            patterns: Dict mapping pattern name to
                ``(strict_regex, loose_regex, label)`` tuple.
        """
        self._pii_compiled = {
            name: (re.compile(strict), re.compile(loose), label)
            for name, (strict, loose, label) in patterns.items()
        }
        logger.info("pii_patterns_registered", count=len(patterns))

    # ── Off-topic ────────────────────────────────────────────────

    def get_off_topic_keywords(self) -> list[str]:
        val = self.get("off_topic", "keywords")
        if val:
            return val if isinstance(val, list) else [val]
        from app.core.langgraph.agent_utils import BUSINESS_DOMAIN_KEYWORDS

        return BUSINESS_DOMAIN_KEYWORDS

    # ── Stop tokens ──────────────────────────────────────────────

    def get_stop_tokens(self) -> list[str]:
        val = self.get("stop_tokens", "tokens")
        if val:
            return val if isinstance(val, list) else [val]
        from app.core.constants import STOP_TOKENS

        return STOP_TOKENS

    # ── RAG parameters ───────────────────────────────────────────

    def get_rag_min_results(self) -> int:
        val = self.get("rag_parameters", "reranker_min_results")
        if val is not None:
            return int(val)
        from app.core.config import settings

        return settings.RERANKER_MIN_RESULTS

    def get_rag_max_results(self) -> int:
        val = self.get("rag_parameters", "reranker_max_results")
        if val is not None:
            return int(val)
        from app.core.config import settings

        return settings.RERANKER_MAX_RESULTS

    def get_rag_scale_factor(self) -> float:
        val = self.get("rag_parameters", "reranker_scale_factor")
        if val is not None:
            return float(val)
        from app.core.config import settings

        return settings.RERANKER_SCALE_FACTOR

    # ── Ingestion ────────────────────────────────────────────────

    def get_chunk_size(self) -> int:
        val = self.get("ingestion", "chunk_size")
        if val is not None:
            return int(val)
        return 512

    def get_chunk_overlap(self) -> int:
        val = self.get("ingestion", "chunk_overlap")
        if val is not None:
            return int(val)
        return 64

    def get_entity_extraction_batch_size(self) -> int:
        val = self.get("ingestion", "entity_extraction_batch_size")
        if val is not None:
            return int(val)
        return 5

    # ── LLM models ───────────────────────────────────────────────

    def get_ollama_model(self) -> str:
        val = self.get("llm", "ollama_model")
        if val is not None:
            return str(val)
        from app.core.config import settings
        return settings.OLLAMA_MODEL

    def get_ollama_embedding_model(self) -> str:
        val = self.get("llm", "ollama_embedding_model")
        if val is not None:
            return str(val)
        from app.core.config import settings
        return settings.OLLAMA_EMBEDDING_MODEL

    def get_ollama_timeout(self) -> int:
        val = self.get("llm", "ollama_timeout")
        if val is not None:
            return int(val)
        return 120

    # ── Auth ─────────────────────────────────────────────────────

    def get_jwt_access_token_expire_days(self) -> int:
        val = self.get("auth", "jwt_access_token_expire_days")
        if val is not None:
            return int(val)
        return 30

    # ── Logging ──────────────────────────────────────────────────

    def get_log_level(self) -> str:
        val = self.get("logging", "log_level")
        if val is not None:
            return str(val)
        return "INFO"

    def get_log_format(self) -> str:
        val = self.get("logging", "log_format")
        if val is not None:
            return str(val)
        return "json"


# Module-level singleton
settings_registry = SettingsRegistry()
