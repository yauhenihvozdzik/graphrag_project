"""
LangGraph агент для GraphRAG: оркестрация retrieval-augmented generation.

Реализует конечный автомат:
  classify_query → retrieve_context → generate_response → apply_guardrails

Использует LangGraph для оркестрации с чекпоинтами в PostgreSQL.
"""

from typing import Any, AsyncGenerator, Optional
from urllib.parse import quote_plus

from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.core.config import settings
from app.core.logging import logger
from app.core.prompts import STOP_TOKENS
from app.core.security.guardrails import guardrails_service
from app.core.security.rbac import AccessContext, ClearanceLevel, Role
from app.core.langgraph.agent_utils import (
    build_system_prompt,
    clean_non_russian,
    classify_query,
    format_graph_context,
)

# Опциональная зависимость для сохранения состояния диалогов
try:
    from psycopg_pool import AsyncConnectionPool
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
    POSTGRES_CHECKPOINT_AVAILABLE = True
except ImportError:
    POSTGRES_CHECKPOINT_AVAILABLE = False


class GraphRAGAgent:
    """
    Агент GraphRAG с сохранением состояния через LangGraph.

    Узлы графа:
    1. classify_query — определяет тип запроса (факт / граф / диалог)
    2. retrieve_context — векторный поиск (Qdrant) + графовый обход (Neo4j)
    3. generate_response — генерация ответа через Ollama LLM
    4. apply_guardrails — фильтрация вывода (ПДн, инъекции)
    """

    def __init__(self):
        self._graph: Optional[CompiledStateGraph] = None
        self._connection_pool = None

    # ── Компиляция графа ──────────────────────────────────────

    async def create_graph(self) -> CompiledStateGraph:
        """Создаёт и компилирует LangGraph-граф (синглтон)."""
        if self._graph is not None:
            return self._graph

        workflow = StateGraph(dict)

        # Регистрируем узлы графа
        workflow.add_node("classify_query", self._classify_query)
        workflow.add_node("retrieve_context", self._retrieve_context)
        workflow.add_node("generate_response", self._generate_response)
        workflow.add_node("apply_guardrails", self._apply_guardrails)

        # Определяем поток выполнения
        workflow.set_entry_point("classify_query")
        workflow.add_edge("classify_query", "retrieve_context")
        workflow.add_edge("retrieve_context", "generate_response")
        workflow.add_edge("generate_response", "apply_guardrails")
        workflow.add_edge("apply_guardrails", END)

        # Настраиваем чекпоинтер для сохранения состояния диалогов
        checkpointer = None
        if POSTGRES_CHECKPOINT_AVAILABLE:
            try:
                conn_string = (
                    f"postgresql://{settings.POSTGRES_USER}:{quote_plus(settings.POSTGRES_PASSWORD)}"
                    f"@{settings.POSTGRES_HOST}:{settings.POSTGRES_PORT}/{settings.POSTGRES_DB}"
                )
                self._connection_pool = AsyncConnectionPool(
                    conninfo=conn_string, max_size=10,
                    kwargs={"autocommit": True, "row_factory": None},
                )
                checkpointer = AsyncPostgresSaver(self._connection_pool)
                await checkpointer.setup()
                logger.info("langgraph_postgres_checkpointer_ready")
            except Exception as e:
                logger.warning("langgraph_checkpointer_setup_failed", error=str(e))

        self._graph = workflow.compile(checkpointer=checkpointer)
        logger.info("langgraph_graph_compiled")
        return self._graph

    # ── Узел 1: Классификация запроса ─────────────────────────

    async def _classify_query(self, state: dict) -> dict:
        """
        Определяет, нужен ли графовый поиск, и извлекает сущности из запроса.
        Использует утилиту classify_query из agent_utils.
        """
        messages = state.get("messages", [])
        requires_graph, entities = classify_query(messages)
        state["requires_graph"] = requires_graph
        state["entities"] = entities
        logger.debug("query_classified", requires_graph=requires_graph, entities=entities)
        return state

    # ── Узел 2: Поиск контекста ───────────────────────────────

    async def _retrieve_context(self, state: dict) -> dict:
        """
        Гибридный поиск: векторный (Qdrant) + графовый (Neo4j).
        Результаты объединяются в единый контекст для LLM.
        """
        from app.services.ollama_service import ollama_service
        from app.services.qdrant_service import qdrant_service
        from app.services.neo4j_service import neo4j_service
        from app.core.graphrag.vector_indexer import vector_indexer_service

        messages = state.get("messages", [])
        if not messages:
            return state

        # Извлекаем последнее сообщение пользователя
        last_message = (
            messages[-1] if isinstance(messages[-1], str)
            else messages[-1].get("content", "")
        )

        # Контекст доступа для RBAC-фильтрации
        access_ctx = state.get("access_context", {})
        clearance = access_ctx.get("clearance_level", 0)
        department = access_ctx.get("department", "all")

        context_parts = []  # Фрагменты текста для LLM
        sources = []        # Метаданные источников

        # ── 2a. Векторный поиск в Qdrant ──
        try:
            vector_results = await vector_indexer_service.search_similar(
                query=last_message,
                ollama_service=ollama_service,
                qdrant_service=qdrant_service,
                top_k=settings.RERANKER_TOP_K,
                clearance_level=clearance,
                department=department,
            )
            for r in vector_results:
                payload = r.get("payload", {})
                context_parts.append(payload.get("text", ""))
                sources.append({
                    "type": "vector",
                    "chunk_id": payload.get("chunk_id", ""),
                    "document_id": payload.get("document_id", ""),
                    "score": r.get("score", 0),
                    "title": payload.get("title", ""),
                })
        except Exception as e:
            logger.warning("vector_search_failed", error=str(e))

        # ── 2b. Графовый поиск в Neo4j (если требуется) ──
        if state.get("requires_graph", False):
            try:
                from app.core.security.rbac import rbac_service
                rbac_filter = rbac_service.build_cypher_filter(
                    AccessContext(
                        user_id=access_ctx.get("user_id", "anonymous"),
                        role=Role(access_ctx.get("role", "viewer")),
                        clearance=ClearanceLevel(clearance),
                        department=department,
                    )
                )
                for entity_name in state.get("entities", []):
                    graph_data = await neo4j_service.get_entity_neighborhood(
                        entity_name=entity_name, depth=2, limit=20, rbac_filter=rbac_filter,
                    )
                    if graph_data.get("nodes"):
                        context_parts.append(format_graph_context(graph_data))
                        sources.append({
                            "type": "graph",
                            "entity": entity_name,
                            "nodes_count": len(graph_data["nodes"]),
                            "edges_count": len(graph_data["edges"]),
                        })
            except Exception as e:
                logger.warning("graph_search_failed", error=str(e))

        # Собираем итоговый контекст
        state["context"] = "\n\n---\n\n".join(context_parts) if context_parts else ""
        state["sources"] = sources

        logger.info(
            "context_retrieved",
            vector_results=len([s for s in sources if s.get("type") == "vector"]),
            graph_results=len([s for s in sources if s.get("type") == "graph"]),
        )
        return state

    # ── Узел 3: Генерация ответа ──────────────────────────────

    async def _generate_response(self, state: dict) -> dict:
        """
        Генерирует ответ через Ollama LLM с учётом контекста.
        Добавляет структурированные источники в конец ответа.
        """
        from app.services.ollama_service import ollama_service

        messages = state.get("messages", [])
        if not messages:
            return state

        context = state.get("context", "")

        # Строим системный промпт с контекстом
        system_prompt = build_system_prompt(context)

        # Формируем сообщения для чата (системный промпт + история)
        chat_messages = [{"role": "system", "content": system_prompt}]
        for msg in messages[-10:]:
            if isinstance(msg, dict):
                chat_messages.append(msg)
            else:
                chat_messages.append({"role": "user", "content": str(msg)})

        # Генерируем ответ через Ollama с блокировкой китайского
        response = await ollama_service.chat(
            messages=chat_messages,
            temperature=0.1,
            options={
                "num_predict": settings.MAX_TOKENS,
                "stop": STOP_TOKENS,
            },
        )

        # Пост-обработка: удаляем нежелательный текст
        response = clean_non_russian(response)

        # ── Дедупликация и структурирование источников ──
        sources = state.get("sources", [])
        structured = []  # Итоговый список с document_id

        if sources:
            # Объединяем дубликаты векторных результатов по document_id
            merged = {}
            for src in sources:
                if src.get("type") == "vector":
                    doc_id = src.get("document_id", "")
                    if not doc_id:
                        continue
                    if doc_id not in merged:
                        merged[doc_id] = {
                            "title": src.get("title", doc_id),
                            "score_sum": src.get("score", 0),
                            "count": 1,
                        }
                    else:
                        merged[doc_id]["score_sum"] += src.get("score", 0)
                        merged[doc_id]["count"] += 1
                elif src.get("type") == "graph":
                    structured.append(src)

            # Формируем финальный список
            for doc_id, m in merged.items():
                structured.append({
                    "document_id": doc_id,
                    "title": m["title"],
                    "score": m["score_sum"] / m["count"],
                    "type": "vector",
                })

            # Добавляем секцию источников в ответ
            response += "\n\n---\n**Источники:**\n"
            for i, s in enumerate(structured, 1):
                if s.get("type") == "vector":
                    response += f"- [{i}] Документ: {s['title']} (релевантность: {s['score']:.2f})\n"
                else:
                    response += f"- [{i}] Граф: сущность «{s.get('entity', '')}»\n"

        state["sources"] = structured
        state["response"] = response
        return state

    # ── Узел 4: Защитные фильтры ──────────────────────────────

    async def _apply_guardrails(self, state: dict) -> dict:
        """Применяет выходные guardrails: фильтрация ПДн, инъекций."""
        response = state.get("response", "")
        state["response"] = guardrails_service.filter_output(response)
        return state

    # ── Публичный интерфейс ───────────────────────────────────

    async def get_response(
        self,
        messages: list[dict],
        session_id: str,
        access_context: Optional[dict] = None,
    ) -> dict:
        """
        Обрабатывает запрос через весь GraphRAG-пайплайн.

        Args:
            messages: Сообщения чата.
            session_id: ID сессии для чекпоинтов.
            access_context: RBAC-контекст пользователя.

        Returns:
            Словарь с ключами 'response' (текст) и 'sources' (источники).
        """
        graph = await self.create_graph()
        input_state = {
            "messages": messages,
            "context": "",
            "entities": [],
            "sources": [],
            "requires_graph": False,
            "access_context": access_context or {},
        }
        config = {"configurable": {"thread_id": session_id}}
        result = await graph.ainvoke(input_state, config=config)
        return {
            "response": result.get("response", ""),
            "sources": result.get("sources", []),
        }

    async def get_streaming_response(
        self,
        messages: list[dict],
        session_id: str,
        access_context: Optional[dict] = None,
    ) -> AsyncGenerator[str, None]:
        """
        Потоковая версия get_response: сначала поиск, потом стриминг генерации.

        Yields:
            Текстовые чанки ответа (включая источники в конце).
        """
        from app.services.ollama_service import ollama_service

        # Запускаем классификацию и поиск
        state = {
            "messages": messages,
            "context": "",
            "entities": [],
            "sources": [],
            "requires_graph": False,
            "access_context": access_context or {},
        }
        state = await self._classify_query(state)
        state = await self._retrieve_context(state)

        # Формируем промпт и сообщения
        context = state.get("context", "")
        system_prompt = build_system_prompt(context)
        chat_messages = [{"role": "system", "content": system_prompt}]
        for msg in messages[-10:]:
            if isinstance(msg, dict):
                chat_messages.append(msg)
            else:
                chat_messages.append({"role": "user", "content": str(msg)})

        # Стримим генерацию
        async for chunk in ollama_service.chat_stream(messages=chat_messages, temperature=0.1):
            yield clean_non_russian(chunk)

        # В конце добавляем источники
        sources = state.get("sources", [])
        if sources:
            yield "\n\n---\n**Источники:**\n"
            for i, src in enumerate(sources, 1):
                if src.get("type") == "vector":
                    yield f"- [{i}] Документ: {src.get('title', 'N/A')}\n"
                elif src.get("type") == "graph":
                    yield f"- [{i}] Граф: сущность «{src.get('entity', '')}»\n"


# Синглтон-экземпляр агента
graphrag_agent = GraphRAGAgent()