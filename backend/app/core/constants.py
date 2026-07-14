"""
Константы GraphRAG: стоп-слова, ключевые слова, форматы файлов, роли, уровни доступа.
"""

# ── Стоп-слова для блокировки нежелательных языков ──
STOP_TOKENS = [
    "中文",         # Китайские иероглифы
    "Chinese:",     # Маркер переключения на китайский
    "English:",     # Маркер переключения на английский
]

# ── Ключевые слова для классификации запросов как графовых ──
GRAPH_QUERY_KEYWORDS = [
    "связан", "отношени", "граф", "между", "ссылается",
    "связь", "регулирует", "относится", "зависимост",
    "сеть", "цепочка", "иерархи", "структур",
]

# ── Допустимые форматы файлов для загрузки ──
ALLOWED_FILE_EXTENSIONS = {".pdf", ".docx", ".doc", ".txt", ".md", ".xml", ".zip"}

# ── Роли пользователей ──
ROLE_VIEWER = "viewer"
ROLE_ANALYST = "analyst"
ROLE_ADMIN = "admin"

ROLE_PERMISSIONS = {
    ROLE_VIEWER: 0,
    ROLE_ANALYST: 1,
    ROLE_ADMIN: 2,
}

# ── Уровни доступа (clearance levels) ──
CLEARANCE_LEVELS = {
    0: "Открытый",
    1: "Конфиденциальный",
    2: "Секретный",
    3: "Сов. секретно",
}

# ── LLM inference parameters ──
LLM_TEMPERATURE_CHAT = 0.1        # генерация ответов в чате
LLM_TEMPERATURE_SPELLING = 0.0    # исправление опечаток (без креативности)
LLM_TEMPERATURE_NER = 0.0         # извлечение сущностей (строгий JSON)
LLM_MAX_TOKENS_NER = 2000         # лимит токенов для NER
LLM_SPELLING_MAX_TOKENS_BASE = 512  # базовый лимит для проверки орфографии
LLM_SPELLING_LENGTH_MULTIPLIER = 2  # множитель длины текста → max_tokens
LLM_SPELLING_MIN_LENGTH_RATIO = 0.3  # минимальное соотношение длин (защита)
LLM_SPELLING_MAX_LENGTH_RATIO = 2.5  # максимальное соотношение длин (защита)

# ── Embedding batch size ──
OLLAMA_EMBED_BATCH_SIZE = 64

# ── NER extraction defaults ──
NER_LLM_CONFIDENCE = 0.8    # confidence for LLM-extracted entities
NER_REGEX_CONFIDENCE = 0.6  # confidence for regex-extracted entities
NER_RELATION_CONFIDENCE = 0.7  # confidence for relations
