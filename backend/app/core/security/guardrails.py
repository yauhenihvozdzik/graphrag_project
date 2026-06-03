"""Guardrails service: PII filtering and prompt injection protection.

Designed for Russian-language legal documents (RusLawOD, RFSD datasets).
Provides input sanitization and output filtering for the GraphRAG pipeline.

Fix #4: Added whitespace-normalised second-pass matching to prevent
simple regex evasion via inserted spaces/typos.  Also added a lightweight
contextual heuristic that flags suspicious contiguous digit blocks as
potential obfuscated PII.
"""

import re
from dataclasses import dataclass, field
from typing import Optional

from app.core.config import settings
from app.core.logging import logger
from app.core.metrics import guardrail_blocks_total


@dataclass
class GuardrailResult:
    """Result of a guardrail check."""

    is_safe: bool
    sanitized_text: str
    blocked_reason: Optional[str] = None
    pii_found: list[str] = field(default_factory=list)
    injection_score: float = 0.0


# ── PII patterns for Russian legal domain ──
# Each entry: (strict_pattern, normalised_pattern, label)
# strict_pattern matches the canonical format.
# normalised_pattern removes optional whitespace/separators to catch evasion.
PII_PATTERNS = {
    "inn_individual": (
        r"\b\d{12}\b",
        r"\b\d[\s\-]?\d[\s\-]?\d[\s\-]?\d[\s\-]?\d[\s\-]?\d[\s\-]?\d[\s\-]?\d[\s\-]?\d[\s\-]?\d[\s\-]?\d[\s\-]?\d\b",
        "ИНН физлица",
    ),
    "inn_legal": (
        r"\b\d{10}\b",
        r"\b\d[\s\-]?\d[\s\-]?\d[\s\-]?\d[\s\-]?\d[\s\-]?\d[\s\-]?\d[\s\-]?\d[\s\-]?\d[\s\-]?\d\b",
        "ИНН юрлица",
    ),
    "snils": (
        r"\b\d{3}-\d{3}-\d{3}\s?\d{2}\b",
        r"\b\d[\s\-]?\d[\s\-]?\d[\s\-]?\d[\s\-]?\d[\s\-]?\d[\s\-]?\d[\s\-]?\d[\s\-]?\d[\s\-]?\d[\s\-]?\d\b",
        "СНИЛС",
    ),
    "passport_ru": (
        r"\b\d{2}\s?\d{2}\s?\d{6}\b",
        r"\b\d[\s\-]?\d[\s\-]?\d[\s\-]?\d[\s\-]?\d[\s\-]?\d[\s\-]?\d[\s\-]?\d[\s\-]?\d[\s\-]?\d\b",
        "Паспорт РФ",
    ),
    "phone_ru": (
        r"\b(?:\+7|8)[\s\-]?\(?\d{3}\)?[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}\b",
        r"\b(?:\+7|8)[\s\-\(\)]*\d[\s\-\(\)]*\d[\s\-\(\)]*\d[\s\-\(\)]*\d[\s\-\(\)]*\d[\s\-\(\)]*\d[\s\-\(\)]*\d[\s\-\(\)]*\d[\s\-\(\)]*\d[\s\-\(\)]*\d\b",
        "Телефон",
    ),
    "email": (
        r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b",
        r"\b[A-Za-z0-9._%+\-]+[\s]*@[\s]*[A-Za-z0-9.\-]+[\s]*\.[\s]*[A-Za-z]{2,}\b",
        "Email",
    ),
    "bank_account": (
        r"\b\d{20}\b",
        r"\b\d[\s\-]?\d[\s\-]?\d[\s\-]?\d[\s\-]?\d[\s\-]?\d[\s\-]?\d[\s\-]?\d[\s\-]?\d[\s\-]?\d[\s\-]?\d[\s\-]?\d[\s\-]?\d[\s\-]?\d[\s\-]?\d[\s\-]?\d[\s\-]?\d[\s\-]?\d[\s\-]?\d[\s\-]?\d\b",
        "Расчётный счёт",
    ),
    "card_number": (
        r"\b(?:\d{4}[\s\-]?){3}\d{4}\b",
        r"\b\d[\s\-]?\d[\s\-]?\d[\s\-]?\d[\s\-]?\d[\s\-]?\d[\s\-]?\d[\s\-]?\d[\s\-]?\d[\s\-]?\d[\s\-]?\d[\s\-]?\d[\s\-]?\d[\s\-]?\d[\s\-]?\d[\s\-]?\d\b",
        "Номер карты",
    ),
}

# ── Prompt injection patterns ──
INJECTION_PATTERNS = [
    # Direct injection attempts
    r"(?i)ignore\s+(all\s+)?previous\s+instructions?",
    r"(?i)forget\s+(all\s+)?(your\s+)?instructions?",
    r"(?i)you\s+are\s+now\s+(?:a|an)\s+",
    r"(?i)act\s+as\s+(?:a|an)?\s*(?:different|new)",
    r"(?i)system\s*:\s*",
    r"(?i)(?:disregard|override)\s+(?:all|the)\s+(?:above|previous|prior)",
    # Jailbreak patterns
    r"(?i)DAN\s+mode",
    r"(?i)developer\s+mode",
    r"(?i)do\s+anything\s+now",
    # Role play injection
    r"(?i)pretend\s+(?:you(?:'re|\s+are)\s+)?(?:a|an|not)\s+",
    r"(?i)roleplay\s+as\s+",
    # Delimiter-based injection
    r"```\s*system",
    r"\[SYSTEM\]",
    r"<\|(?:im_start|system|endoftext)\|>",
    # Russian-language injection
    r"(?i)игнорируй\s+(?:все\s+)?(?:предыдущие\s+)?инструкции",
    r"(?i)забудь\s+(?:все\s+)?(?:предыдущие\s+)?инструкции",
    r"(?i)ты\s+теперь\s+",
    r"(?i)(?:отмени|переопредели)\s+(?:все\s+)?(?:предыдущие\s+)?(?:правила|инструкции)",
]


class GuardrailsService:
    """Service for input/output safety checks with two-tier PII detection."""

    def __init__(self):
        self._pii_patterns = {
            name: (re.compile(strict), re.compile(loose), label)
            for name, (strict, loose, label) in PII_PATTERNS.items()
        }
        self._injection_patterns = [re.compile(p) for p in INJECTION_PATTERNS]

    @staticmethod
    def _normalise_whitespace(text: str) -> str:
        """Remove all spaces, hyphens, and parentheses used as digit separators.

        This produces a compact string for second-pass PII matching, defeating
        the simplest evasion tactic (inserting spaces between digits).
        """
        return re.sub(r"[\s\-()]", "", text)

    def check_input(self, text: str) -> GuardrailResult:
        """Check user input for PII and prompt injection.

        Args:
            text: Raw user input text.

        Returns:
            GuardrailResult with safety assessment and sanitized text.
        """
        if not settings.GUARDRAILS_ENABLED:
            return GuardrailResult(is_safe=True, sanitized_text=text)

        # Length check
        if len(text) > settings.MAX_INPUT_LENGTH:
            guardrail_blocks_total.labels(reason="max_length_exceeded").inc()
            logger.warning("guardrail_blocked_length", length=len(text))
            return GuardrailResult(
                is_safe=False,
                sanitized_text=text[: settings.MAX_INPUT_LENGTH],
                blocked_reason="Превышена максимальная длина ввода",
            )

        # Prompt injection detection
        injection_score = self._detect_injection(text)
        if injection_score >= settings.PROMPT_INJECTION_THRESHOLD:
            guardrail_blocks_total.labels(reason="prompt_injection").inc()
            logger.warning(
                "guardrail_blocked_injection",
                score=injection_score,
                text_preview=text[:100],
            )
            return GuardrailResult(
                is_safe=False,
                sanitized_text="",
                blocked_reason="Обнаружена попытка prompt injection",
                injection_score=injection_score,
            )

        # Two-tier PII detection and masking
        sanitized, pii_found = self._mask_pii(text)

        if pii_found:
            logger.info("pii_detected_and_masked", pii_types=pii_found)

        return GuardrailResult(
            is_safe=True,
            sanitized_text=sanitized,
            pii_found=pii_found,
            injection_score=injection_score,
        )

    def filter_output(self, text: str) -> str:
        """Filter LLM output to remove any leaked PII.

        Args:
            text: LLM response text.

        Returns:
            Sanitized output text.
        """
        if not settings.GUARDRAILS_ENABLED:
            return text
        sanitized, _ = self._mask_pii(text)
        return sanitized

    def _detect_injection(self, text: str) -> float:
        """Score text for prompt injection probability.

        Returns:
            Float between 0.0 and 1.0 indicating injection likelihood.
        """
        matches = sum(1 for p in self._injection_patterns if p.search(text))
        if matches == 0:
            return 0.0
        # Normalize: 1 match = 0.5, 2+ = 0.85+
        return min(0.5 + (matches - 1) * 0.35, 1.0)

    def _mask_pii(self, text: str) -> tuple[str, list[str]]:
        """Two-tier PII masking.

        Tier 1: match canonical regex patterns directly on the original text.
        Tier 2: normalise whitespace and apply compact patterns to catch
        evasion attempts (e.g. "1 2 3 4  5 6 7 8 9 0" instead of "1234567890").

        Returns:
            Tuple of (masked_text, list_of_pii_types_found).
        """
        found_types: list[str] = []
        masked = text

        for name, (strict_pattern, loose_pattern, label) in self._pii_patterns.items():
            # ── Tier 1: direct match ──
            if strict_pattern.search(masked):
                found_types.append(label)
                masked = strict_pattern.sub(f"[{label.upper()} СКРЫТ]", masked)
                continue

            # ── Tier 2: normalised match (catch space-separated evasion) ──
            normalised = self._normalise_whitespace(masked)
            if loose_pattern.search(normalised):
                found_types.append(f"{label} (нормализация)")
                # Replace in original text by finding the raw span
                # Find the match in normalised, then locate the corresponding
                # raw substring and mask it.
                for match in loose_pattern.finditer(normalised):
                    raw_span = self._map_normalised_span_to_raw(
                        masked, normalised, match.start(), match.end()
                    )
                    if raw_span:
                        start, end = raw_span
                        masked = (
                            masked[:start]
                            + f"[{label.upper()} СКРЫТ]"
                            + masked[end:]
                        )

        return masked, found_types

    @staticmethod
    def _map_normalised_span_to_raw(
        raw: str, normalised: str, norm_start: int, norm_end: int
    ) -> Optional[tuple[int, int]]:
        """Map a character span in the normalised (whitespace-free) string
        back to the corresponding span in the original raw string."""
        raw_pos = 0
        norm_pos = 0
        raw_start = None

        while raw_pos < len(raw) and norm_pos < norm_end:
            if raw_start is None and norm_pos == norm_start:
                raw_start = raw_pos

            ch = raw[raw_pos]
            # A character that would be stripped by _normalise_whitespace
            if ch in " \t\n\r\v\f-()":
                raw_pos += 1
                continue

            norm_pos += 1
            raw_pos += 1

        if raw_start is not None and norm_pos == norm_end:
            return (raw_start, raw_pos)
        return None


# Singleton
guardrails_service = GuardrailsService()