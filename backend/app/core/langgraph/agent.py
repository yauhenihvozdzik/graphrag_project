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
from app.core.constants import LLM_TEMPERATURE_CHAT, STOP_TOKENS
from app.core.logging import logger
from app.core.security.guardrails import guardrails_service
from app.core.security.rbac import AccessContext, ClearanceLevel, Role
from app.core.langgraph.agent_utils import (
    build_system_prompt,
    clean_non_russian,
    classify_query,
    correct_spelling,
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
    2. correct_spelling — исправляет опечатки в запросе для лучшего поиска
    3. retrieve_context — векторный поиск (Qdrant) + графовый обход (Neo4j)
    4. generate_response — генерация ответа через Ollama LLM
    5. apply_guardrails — фильтрация вывода (ПДн, инъекции)
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
        workflow.add_node("correct_spelling", self._correct_spelling)
        workflow.add_node("retrieve_context", self._retrieve_context)
        workflow.add_node("generate_response", self._generate_response)
        workflow.add_node("apply_guardrails", self._apply_guardrails)

        # Определяем поток выполнения: classify → spelling → retrieve → generate → guardrails
        workflow.set_entry_point("classify_query")
        workflow.add_edge("classify_query", "correct_spelling")
        workflow.add_edge("correct_spelling", "retrieve_context")
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

    # ── Узел 2: Коррекция опечаток ────────────────────────────

    async def _correct_spelling(self, state: dict) -> dict:
        """
        Исправляет опечатки и орфографические ошибки в последнем сообщении пользователя.
        Сохраняет исправленный текст в state['last_message_corrected'].
        """
        from app.services.ollama_service import ollama_service

        messages = state.get("messages", [])
        if not messages:
            return state

        last_message = (
            messages[-1] if isinstance(messages[-1], str)
            else messages[-1].get("content", "")
        )

        if last_message:
            corrected = await correct_spelling(last_message, ollama_service)
            state["last_message_corrected"] = corrected
            if corrected != last_message:
                logger.info("spelling_corrected", original_preview=last_message[:50], corrected_preview=corrected[:50])
            else:
                state["last_message_corrected"] = last_message
        else:
            state["last_message_corrected"] = last_message

        return state

    # ── Узел 3: Поиск контекста ───────────────────────────────

    async def _retrieve_context(self, state: dict) -> dict:
        """
        Гибридный поиск: векторный (Qdrant) + графовый (Neo4j).
        Результаты объединяются в единый контекст для LLM.
        
        Ключевое улучшение: динамический top_k на основе плотности графа знаний.
        Чем больше связей у релевантных сущностей — тем больше документов извлекается.
        """
        from app.services.ollama_service import ollama_service
        from app.services.qdrant_service import qdrant_service
        from app.services.neo4j_service import neo4j_service
        from app.core.graphrag.vector_indexer import vector_indexer_service

        messages = state.get("messages", [])
        if not messages:
            return state

        # Используем исправленное сообщение, если доступно
        last_message = state.get("last_message_corrected", "")
        if not last_message:
            last_message = (
                messages[-1] if isinstance(messages[-1], str)
                else messages[-1].get("content", "")
            )

        # Контекст доступа для RBAC-фильтрации
        access_ctx = state.get("access_context", {})
        clearance = access_ctx.get("clearance_level", 0)
        department = access_ctx.get("department", "all")

        context_parts = []  # Фрагменты текста для LLM
        sources = []        # Метаданные источники
        
        # ── Динамический расчёт top_k на основе графа знаний ──
        # Получаем общую статистику графа для определения глубины поиска
        graph_stats = {"node_count": 0, "edge_count": 0}
        try:
            graph_stats = await neo4j_service.get_graph_stats() or graph_stats
        except Exception:
            pass
        
        total_connections = graph_stats.get("edge_count", 0)
        total_nodes = graph_stats.get("node_count", 0)
        
        # Базовая формула: минимум 10 документов, масштабируется от размера графа
        if total_connections > 0 and total_nodes > 0:
            # Плотность графа: связей на узел
            graph_density = total_connections / max(total_nodes, 1)
            # Динамический top_k: от 10 до 50 документов в зависимости от плотности
            dynamic_top_k = min(
                max(settings.RERANKER_MIN_RESULTS, int(graph_density * settings.RERANKER_SCALE_FACTOR)),
                settings.RERANKER_MAX_RESULTS
            )
        else:
            dynamic_top_k = settings.RERANKER_TOP_K  # fallback
        
        logger.debug("dynamic_top_k_calculated", 
                     total_nodes=total_nodes, 
                     total_edges=total_connections,
                     dynamic_top_k=dynamic_top_k)

        # ── 2a. Векторный поиск в Qdrant с динамическим top_k ──
        try:
            vector_results = await vector_indexer_service.search_similar(
                query=last_message,
                ollama_service=ollama_service,
                qdrant_service=qdrant_service,
                top_k=dynamic_top_k,
                clearance_level=clearance,
                department=department,
            )
            for r in vector_results:
                payload = r.get("payload", {})
                text = payload.get("text", "")
                # Пропускаем пустые чанки — не добавляем в контекст
                if not text or not text.strip():
                    continue
                context_parts.append(text)
                sources.append({
                    "type": "vector",
                    "chunk_id": payload.get("chunk_id", ""),
                    "document_id": payload.get("document_id", ""),
                    "score": r.get("score", 0),
                    "title": payload.get("title", ""),
                })
        except Exception as e:
            logger.warning("vector_search_failed", error=str(e))

        # ── 2b. Графовый поиск в Neo4j (всегда, а не только при явном запросе) ──
        # Извлекаем сущности из запроса, даже если не сработали ключевые слова
        entities = state.get("entities", [])
        if not entities:
            # Пытаемся извлечь сущности из последнего сообщения через NLP-эвристики
            import re
            # Ищем слова с заглавной буквы (потенциальные именованные сущности)
            potential_entities = re.findall(r'\b[А-ЯA-Z][а-яa-z]+\b', last_message)
            # Ищем сущности в кавычках
            quoted = re.findall(r'[«"]([^»"]+)[»"]', last_message)
            entities = list(set(potential_entities[:5] + quoted[:5]))
            state["entities"] = entities
        
        # Всегда выполняем графовый поиск — он даёт богатый контекст
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
            
            # Глубина обхода графа динамическая: чем больше граф, тем глубже идём
            graph_depth = min(3, max(1, int(graph_density / 2))) if total_connections > 0 else 2
            graph_limit = min(50, max(20, dynamic_top_k * 2))
            
            for entity_name in entities[:10]:  # обрабатываем до 10 сущностей
                try:
                    graph_data = await neo4j_service.get_entity_neighborhood(
                        entity_name=entity_name, 
                        depth=graph_depth, 
                        limit=graph_limit, 
                        rbac_filter=rbac_filter,
                    )
                    if graph_data.get("nodes"):
                        context_parts.append(format_graph_context(graph_data))
                        sources.append({
                            "type": "graph",
                            "entity": entity_name,
                            "nodes_count": len(graph_data["nodes"]),
                            "edges_count": len(graph_data["edges"]),
                        })
                except Exception as inner_e:
                    logger.debug("graph_entity_search_failed", entity=entity_name, error=str(inner_e))
                    
            # Дополнительно: если граф богатый, делаем community-level поиск
            if total_connections > 10 and entities:
                try:
                    for entity_name in entities[:3]:
                        related = await neo4j_service.get_related_documents(
                            entity_name=entity_name, 
                            limit=dynamic_top_k,
                            rbac_filter=rbac_filter,
                        )
                        if related:
                            for doc in related[:10]:
                                context_parts.append(
                                    f"Связанный документ [{doc.get('title', '')}]: {doc.get('text', '')[:1000]}"
                                )
                except Exception as inner_e:
                    logger.debug("related_docs_search_failed", error=str(inner_e))
                    
        except Exception as e:
            logger.warning("graph_search_failed", error=str(e))

        # Собираем итоговый контекст
        state["context"] = "\n\n---\n\n".join(context_parts) if context_parts else ""
        state["sources"] = sources
        
        # Сохраняем статистику для ответа
        state["graph_stats"] = graph_stats

        logger.info(
            "context_retrieved",
            vector_results=len([s for s in sources if s.get("type") == "vector"]),
            graph_results=len([s for s in sources if s.get("type") == "graph"]),
            dynamic_top_k=dynamic_top_k,
        )
        return state

    # ── Узел 4: Генерация ответа ──────────────────────────────

    async def _generate_response(self, state: dict) -> dict:
        """
        Генерирует ответ через Ollama LLM с учётом контекста.
        Добавляет структурированные источники в конец ответа.
        
        Улучшения:
        - Повышенная температура для более развёрнутых ответов (0.3 вместо 0.1)
        - Увеличенный лимит токенов для полных ответов
        - Обогащённый промпт с требованием детального ответа
        """
        from app.services.ollama_service import ollama_service

        messages = state.get("messages", [])
        if not messages:
            return state

        context = state.get("context", "")
        graph_stats = state.get("graph_stats", {})

        # Строим системный промпт с контекстом и статистикой графа
        system_prompt = build_system_prompt(
            context, 
            graph_context_stats={
                "total_nodes": graph_stats.get("node_count", 0),
                "total_edges": graph_stats.get("edge_count", 0),
            }
        )

        # Инструкция для более развёрнутого ответа
        detail_instruction = (
            "\n\nВАЖНО: Предоставь МАКСИМАЛЬНО ПОДРОБНЫЙ ответ. "
            "Не опускай детали, даты, связи. Используй ВСЮ информацию из контекста. "
            "Структурируй ответ с заголовками и списками. "
            f"В контексте доступно {len(state.get('sources', []))} источников — используй их все."
        )

        # Формируем сообщения для чата (системный промпт + история + инструкция)
        chat_messages = [{"role": "system", "content": system_prompt + detail_instruction}]
        for msg in messages[-10:]:
            if isinstance(msg, dict):
                chat_messages.append(msg)
            else:
                chat_messages.append({"role": "user", "content": str(msg)})

        # Генерируем ответ с повышенной температурой для богатства языка
        response = await ollama_service.chat(
            messages=chat_messages,
            temperature=LLM_TEMPERATURE_CHAT,
            options={
                "num_predict": max(settings.MAX_TOKENS, 4096),  # больше токенов для развёрнутых ответов
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

            # Формируем финальный список, сортируем по релевантности
            vector_sorted = sorted(merged.items(), key=lambda x: x[1]["score_sum"] / x[1]["count"], reverse=True)
            for doc_id, m in vector_sorted:
                structured.append({
                    "document_id": doc_id,
                    "title": m["title"],
                    "score": m["score_sum"] / m["count"],
                    "type": "vector",
                })

            # Добавляем секцию источников в ответ (более информативную)
            response += "\n\n---\n**📚 Источники (найдено {} релевантных документов/сущностей):**\n".format(len(structured))
            for i, s in enumerate(structured, 1):
                if s.get("type") == "vector":
                    response += f"- [{i}] 📄 {s['title']} (релевантность: {s['score']:.3f})\n"
                else:
                    response += f"- [{i}] 🔗 Граф: сущность «{s.get('entity', '')}» (узлов: {s.get('nodes_count', 0)}, связей: {s.get('edges_count', 0)})\n"

        state["sources"] = structured
        state["response"] = response
        return state

    # ── Узел 5: Защитные фильтры ──────────────────────────────

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
            "last_message_corrected": "",
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

        # Запускаем классификацию, коррекцию и поиск
        state = {
            "messages": messages,
            "context": "",
            "entities": [],
            "sources": [],
            "requires_graph": False,
            "last_message_corrected": "",
            "access_context": access_context or {},
        }
        state = await self._classify_query(state)
        state = await self._correct_spelling(state)
        state = await self._retrieve_context(state)

        # Формируем промпт и сообщения (с обогащённым контекстом)
        context = state.get("context", "")
        graph_stats = state.get("graph_stats", {})
        system_prompt = build_system_prompt(
            context, 
            graph_context_stats={
                "total_nodes": graph_stats.get("node_count", 0),
                "total_edges": graph_stats.get("edge_count", 0),
            }
        )
        
        # Инструкция для развёрнутого ответа при стриминге
        detail_instruction = (
            "\n\nВАЖНО: Дай МАКСИМАЛЬНО ПОДРОБНЫЙ и СТРУКТУРИРОВАННЫЙ ответ. "
            "Используй ВСЕ данные из контекста, описывай связи, приводи детали. "
            f"Доступно {len(state.get('sources', []))} источников информации."
        )
        
        chat_messages = [{"role": "system", "content": system_prompt + detail_instruction}]
        for msg in messages[-10:]:
            if isinstance(msg, dict):
                chat_messages.append(msg)
            else:
                chat_messages.append({"role": "user", "content": str(msg)})

        # Стримим генерацию с повышенной температурой для богатства языка
        async for chunk in ollama_service.chat_stream(
            messages=chat_messages, 
            temperature=LLM_TEMPERATURE_CHAT,
            options={
                "num_predict": max(settings.MAX_TOKENS, 4096),
                "stop": STOP_TOKENS,
            },
        ):
            yield clean_non_russian(chunk)

        # В конце добавляем структурированные источники
        sources = state.get("sources", [])
        if sources:
            yield f"\n\n---\n**📚 Источники (найдено {len(sources)} релевантных документов/сущностей):**\n"
            for i, src in enumerate(sources, 1):
                if src.get("type") == "vector":
                    yield f"- [{i}] 📄 {src.get('title', 'N/A')} (релевантность: {src.get('score', 0):.3f})\n"
                elif src.get("type") == "graph":
                    yield f"- [{i}] 🔗 Граф: сущность «{src.get('entity', '')}» (узлов: {src.get('nodes_count', 0)}, связей: {src.get('edges_count', 0)})\n"


# Синглтон-экземпляр агента
graphrag_agent = GraphRAGAgent()