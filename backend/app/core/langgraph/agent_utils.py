"""
Утилиты для GraphRAG-агента:
- Очистка ответа от нежелательного текста
- Построение системного промпта
- Форматирование контекста графа
"""

import re

from app.core.constants import (
    GRAPH_QUERY_KEYWORDS,
    LLM_SPELLING_LENGTH_MULTIPLIER,
    LLM_SPELLING_MAX_LENGTH_RATIO,
    LLM_SPELLING_MAX_TOKENS_BASE,
    LLM_SPELLING_MIN_LENGTH_RATIO,
    LLM_TEMPERATURE_SPELLING,
)
from app.core.prompts import (
    SYSTEM_PROMPT, NO_CONTEXT_MESSAGE, CONTEXT_HEADER,
    SPELLING_CORRECTION_PROMPT,
)


def build_system_prompt(context: str, graph_context_stats: dict = None) -> str:
    """
    Строит системный промпт для LLM с учётом контекста документов и статистики графа знаний.

    Args:
        context: Текст контекста из найденных документов (может быть пустым).
        graph_context_stats: Опциональная статистика графа {total_nodes, total_edges}.
    Returns:
        Строка с полным системным промптом.
    """
    messages = [SYSTEM_PROMPT]
    
    # Добавляем информацию о графе знаний для контекста
    if graph_context_stats:
        nodes = graph_context_stats.get("total_nodes", 0)
        edges = graph_context_stats.get("total_edges", 0)
        if nodes > 0 or edges > 0:
            messages.append(f"\nДОСТУПНАЯ ИНФРАСТРУКТУРА ЗНАНИЙ:\n"
                          f"- Граф знаний содержит {nodes} узлов и {edges} связей между сущностями.\n"
                          f"- При ответе используй не только текст документов, но и связи из графа знаний.\n"
                          f"- Описывай все обнаруженные взаимосвязи между сущностями.")
    
    if context:
        messages.append(f"\n{CONTEXT_HEADER}\n{context}")
    else:
        messages.append(f"\n{NO_CONTEXT_MESSAGE}")
    return "\n".join(messages)


def clean_non_russian(text: str) -> str:
    """
    Удаляет строки с китайскими иероглифами из ответа модели.
    Если весь ответ на китайском — возвращает извинение на русском.

    Args:
        text: Текст ответа от LLM.
    Returns:
        Очищенный текст на русском языке.
    """
    if not text:
        return text

    # Проверяем наличие китайских иероглифов (Unicode диапазон CJK)
    if re.search(r'[\u4e00-\u9fff]', text):
        lines = text.split('\n')
        # Оставляем только строки без китайских символов
        ru_lines = [
            line for line in lines
            if not re.search(r'[\u4e00-\u9fff]', line) and line.strip()
        ]
        if ru_lines:
            return '\n'.join(ru_lines)
        return "Извините, произошла ошибка генерации. Пожалуйста, повторите запрос."
    return text


def format_graph_context(graph_data: dict) -> str:
    """
    Форматирует данные графа знаний в текстовый контекст для LLM.

    Args:
        graph_data: Словарь с ключами 'nodes' и 'edges' из Neo4j.
    Returns:
        Текстовое представление графа.
    """
    parts = ["Данные из графа знаний:"]

    # Узлы графа
    for node in graph_data.get("nodes", [])[:20]:
        name = node.get("name", "")
        ntype = node.get("entity_type", node.get("type", ""))
        desc = node.get("description", "")
        line = f"- [{ntype}] {name}"
        if desc:
            line += f": {desc}"
        parts.append(line)

    # Рёбра графа
    for edge in graph_data.get("edges", [])[:20]:
        parts.append(
            f"  → {edge.get('source', '')} --[{edge.get('type', '')}]--> {edge.get('target', '')}"
        )

    return "\n".join(parts)


# ── Business domain keywords for off-topic filtering ──
BUSINESS_DOMAIN_KEYWORDS = [
    "закон", "статья", "кодекс", "постановлени", "договор",
    "документ", "отчёт", "отчет", "накладн", "счёт", "счет", "акт",
    "инструкци", "регламент", "приказ", "распоряжени", "протокол",
    "заказ", "продаж", "покупк", "поставк", "поставщик", "клиент",
    "товар", "склад", "маркировк", "перемещени", "приёмк", "отгрузк",
    "водител", "кассир", "касс", "эквайринг", "чеков",
    "бухгалтер", "финанс", "налог", "ндс", "инвойс", "платёж",
    "возврат", "списани", "оприходовани", "инвентаризаци",
    "ERP", "NAV", "CRM", "WMS", "TMS", "EDI", "1С", "SAP",
    "ЭСЧФ", "УПД", "ТОРГ", "Диадок", "ЭДО",
    "маршрут", "рейс", "доставк", "логистик", "транспорт",
    "контур", "рб", "рф", "рк", "шате", "shate", "бизнес",
    "настройк", "ошибк", "пользовател", "систем", "модул",
    "бренд", "штрихкод", "цен", "скидк",
    "кросс", "сборк", "упаковк", "ячейк", "размещени",
    "зарплат", "сотрудник", "отдел", "рол",
]


def is_off_topic(query: str) -> bool:
    """
    Проверяет, относится ли запрос к бизнес-домену.
    Возвращает True если запрос НЕ относится к бизнес-темам.
    """
    if not query or not query.strip():
        return True
    query_lower = query.lower()
    for kw in BUSINESS_DOMAIN_KEYWORDS:
        if kw.lower() in query_lower:
            return False  # found business keyword — the query IS in domain
    return True  # no business keywords found — off-topic


def classify_query(messages: list) -> tuple[bool, list[str]]:
    """
    Классифицирует запрос пользователя: нужен ли графовый поиск.
    Также извлекает сущности в кавычках.

    Args:
        messages: Список сообщений чата (последнее — запрос пользователя).
    Returns:
        Кортеж (requires_graph: bool, entities: list[str]).
    """
    if not messages:
        return False, []

    last_message = (
        messages[-1] if isinstance(messages[-1], str)
        else messages[-1].get("content", "")
    )

    # Проверяем наличие ключевых слов графового запроса
    requires_graph = any(
        kw in last_message.lower() for kw in GRAPH_QUERY_KEYWORDS
    )

    # Извлекаем сущности в кавычках «» или ""
    entities = re.findall(r'[«"]([^»"]+)[»"]', last_message)

    return requires_graph, entities


async def correct_spelling(text: str, ollama_service) -> str:
    """
    Исправляет опечатки и орфографические ошибки в запросе через LLM.
    Если исправление не требуется или модель недоступна — возвращает исходный текст.

    Args:
        text: Исходный запрос пользователя (возможно, с опечатками).
        ollama_service: Сервис Ollama для вызова LLM.
    Returns:
        Исправленный текст запроса.
    """
    if not text or not text.strip():
        return text

    # Пропускаем короткие запросы (1-2 слова) — эвристика: мало смысла править
    words = text.split()
    if len(words) <= 2:
        return text

    # Проверяем, есть ли явные признаки опечаток:
    # - повторяющиеся буквы (более 2 подряд)
    # - слова с заглавной буквы посреди предложения
    # - небуквенные символы в середине слов
    has_typo_indicators = (
        re.search(r'(.)\1{2,}', text) is not None  # повтор букв: «чтооо»
        or re.search(r'\b[a-z]+[A-Z]', text) is not None  # смешанный регистр внутри слова
    )

    if not has_typo_indicators:
        return text  # не тратим LLM-вызов на чистый запрос

    try:
        messages = [
            {"role": "system", "content": SPELLING_CORRECTION_PROMPT},
            {"role": "user", "content": text},
        ]
        corrected = await ollama_service.chat(
            messages=messages,
            temperature=LLM_TEMPERATURE_SPELLING,
            options={"num_predict": min(len(text) * LLM_SPELLING_LENGTH_MULTIPLIER, LLM_SPELLING_MAX_TOKENS_BASE)},
        )
        corrected = corrected.strip().strip('"').strip("'")
        # Если модель вернула пустоту или слишком сильно изменила длину — не рискуем
        if not corrected or len(corrected) < len(text) * LLM_SPELLING_MIN_LENGTH_RATIO or len(corrected) > len(text) * LLM_SPELLING_MAX_LENGTH_RATIO:
            return text
        return corrected
    except Exception:
        return text
