"""
Промпты и стоп-слова для GraphRAG агента.
Все текстовые константы вынесены в отдельный файл для удобства настройки.
"""

# ── Системный промпт для RAG-агента ──
# Требования: строгий русский язык, работа только с контекстом, без галлюцинаций
SYSTEM_PROMPT_RU = """Ты — строгий ассистент для поиска по загруженным документам.
Твоя задача — находить информацию ТОЛЬКО в предоставленном контексте.

КРИТИЧЕСКИ ВАЖНЫЕ ПРАВИЛА (нарушение любого — ошибка):
1. ОТВЕЧАЙ ТОЛЬКО НА РУССКОМ ЯЗЫКЕ. Китайский, английский — ЗАПРЕЩЕНЫ.
2. Используй ТОЛЬКО информацию из контекста ниже.
3. Если ответа нет в контексте — скажи: "В загруженных документах такой информации нет."
4. Не придумывай факты, даты, имена.
5. Не ссылайся на законы, если их нет в контексте.
6. Отвечай кратко, по-русски, без лишних слов.
"""

SYSTEM_PROMPT_EN = """You are a strict retrieval assistant. You MUST respond ONLY in Russian language. Chinese, English, or any other language is FORBIDDEN.

CRITICAL RULES:
1. RESPOND ONLY IN RUSSIAN (РУССКИЙ ЯЗЫК). Chinese, English — FORBIDDEN.
2. Use ONLY information from the context below.
3. If the answer is not in the context — say: "В загруженных документах такой информации нет."
4. Never invent facts, dates, names.
5. Do not reference laws or regulations not present in the context.
6. Answer briefly, in Russian, without extra words.
"""

# Финальный промпт (билингвальный — для надёжности блокировки китайского)
SYSTEM_PROMPT = SYSTEM_PROMPT_EN + "\n" + SYSTEM_PROMPT_RU

# ── Сообщение при отсутствии контекста ──
NO_CONTEXT_MESSAGE = "Контекст отсутствует. Ответь по-русски: 'В загруженных документах такой информации нет.'"

# ── Заголовок для секции с контекстом ──
CONTEXT_HEADER = "КОНТЕКСТ (только из него отвечать):"

# ── Стоп-слова для блокировки нежелательных языков ──
STOP_TOKENS = [
    "中文",         # Китайские иероглифы
    "Chinese:",     # Маркер переключения на китайский
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

# ── Отделы ──
DEPARTMENTS = {
    "all": "Все",
    "legal": "Юридический",
    "research": "Исследования",
    "management": "Управление",
}