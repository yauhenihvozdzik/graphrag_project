"""
Утилиты для GraphRAG-агента:
- Очистка ответа от нежелательного текста
- Построение системного промпта
- Форматирование контекста графа
"""

import re

from app.core.prompts import (
    SYSTEM_PROMPT, NO_CONTEXT_MESSAGE, CONTEXT_HEADER,
    GRAPH_QUERY_KEYWORDS,
)


def build_system_prompt(context: str) -> str:
    """
    Строит системный промпт для LLM с учётом контекста документов.

    Args:
        context: Текст контекста из найденных документов (может быть пустым).
    Returns:
        Строка с полным системным промптом.
    """
    messages = [SYSTEM_PROMPT]
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