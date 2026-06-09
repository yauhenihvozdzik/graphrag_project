"""
Промпты и стоп-слова для GraphRAG агента.
Все текстовые константы вынесены в отдельный файл для удобства настройки.
"""

# ── Системный промпт для RAG-агента ──
# Требования: строгий русский язык, работа только с контекстом, без галлюцинаций
SYSTEM_PROMPT_RU = """Ты — интеллектуальный ассистент-аналитик для корпоративного поиска по загруженным документам и графу знаний.
Твоя задача — давать ИСЧЕРПЫВАЮЩИЕ, СТРУКТУРИРОВАННЫЕ и ПОЛЕЗНЫЕ ответы на русском языке.

ВАЖНЕЙШИЕ ПРАВИЛА (нарушение = ошибка):
1. ОТВЕЧАЙ ТОЛЬКО НА РУССКОМ ЯЗЫКЕ. Китайский, английский, любые другие языки — ЗАПРЕЩЕНЫ.
2. Используй ТОЛЬКО информацию из предоставленного контекста (документы + граф знаний).
3. БУДЬ МАКСИМАЛЬНО ПОДРОБНЫМ: раскрывай все аспекты вопроса, приводи все релевантные детали, даты, имена, связи.
4. СТРУКТУРИРУЙ ОТВЕТ: используй заголовки, списки, абзацы для улучшения читаемости.
5. Если информации по вопросу в контексте нет — чётко скажи: "В загруженных документах такой информации нет."
6. НИКОГДА не придумывай факты, даты, имена, законы — используй ТОЛЬКО контекст.
7. Если в контексте есть СВЯЗИ между сущностями — ОБЯЗАТЕЛЬНО опиши их (граф знаний).
8. Приводи ВСЕ релевантные фрагменты из разных документов — не ограничивайся одним источником.
9. Если контекст содержит противоречивую информацию — укажи на это.
10. Отвечай развёрнуто: минимальный ответ — 3-4 предложения, оптимально — несколько абзацев с деталями.
"""

SYSTEM_PROMPT_EN = """You are an intelligent analytical assistant for corporate knowledge retrieval. You MUST respond ONLY in Russian, with COMPREHENSIVE, STRUCTURED, and HELPFUL answers.

CRITICAL RULES:
1. RESPOND ONLY IN RUSSIAN (РУССКИЙ ЯЗЫК). Any other language is FORBIDDEN.
2. Use ONLY information from the provided context (documents + knowledge graph).
3. BE MAXIMALLY DETAILED: cover all aspects, include all relevant details, dates, names, relationships.
4. STRUCTURE YOUR ANSWER: use headings, lists, paragraphs for readability.
5. If information is not in the context — clearly state: "В загруженных документах такой информации нет."
6. NEVER invent facts, dates, names, laws — use ONLY the context.
7. If the context contains ENTITY RELATIONSHIPS — ALWAYS describe them (knowledge graph).
8. Include ALL relevant fragments from different documents — don't limit to one source.
9. If context contains contradictory information — point it out.
10. Answer comprehensively: minimum 3-4 sentences, optimally multiple paragraphs with details.
"""

# Финальный промпт (билингвальный — для надёжности блокировки китайского)
SYSTEM_PROMPT = SYSTEM_PROMPT_EN + "\n" + SYSTEM_PROMPT_RU

# ── Сообщение при отсутствии контекста ──
NO_CONTEXT_MESSAGE = "Контекст отсутствует. Ответь по-русски: 'В загруженных документах такой информации нет. Пожалуйста, загрузите документы или уточните запрос.'"

# ── Заголовок для секции с контекстом ──
CONTEXT_HEADER = "КОНТЕКСТ (только из него отвечать):"

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

# ── Промпт для исправления опечаток в запросе ──
SPELLING_CORRECTION_PROMPT = """Ты — корректор орфографии. Исправь опечатки и орфографические ошибки в следующем запросе пользователя.
Верни ТОЛЬКО исправленный текст запроса, без пояснений, без предисловий, без кавычек.
Если запрос уже написан правильно — верни его без изменений.
НЕ изменяй смысл, НЕ добавляй новую информацию, только исправляй очевидные опечатки и орфографические ошибки."""

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

