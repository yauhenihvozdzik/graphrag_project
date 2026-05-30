# ADR-006: Выбор фреймворка оркестрации

## Статус
Принято

## Контекст

GraphRAG платформа требует фреймворк оркестрации для управления сложным RAG-пайплайном:

**Пайплайн обработки запроса:**
1. Классификация запроса (intent recognition)
2. Параллельный поиск: Vector search (Qdrant) + Graph traversal (Neo4j)
3. Ранжирование и фильтрация результатов
4. Формирование промпта с контекстом
5. Генерация ответа (LLM через Ollama)
6. Post-processing (извлечение цитат, проверка фактов)
7. Обратная связь и обновление графа

**Требования:**
- Управление сложными, нелинейными workflows с условными переходами
- Поддержка state management (сохранение контекста между шагами)
- Human-in-the-loop (юрист может одобрить/скорректировать ответ)
- Streaming output (для интерактивного UI)
- Observability (tracing каждого шага пайплайна)
- Python-native (основной язык проекта)

**Ограничение проекта**: LangGraph **обязателен** по требованиям заказчика.

## Рассмотренные варианты

### 1. LangGraph (LangChain)

| Характеристика | Детали |
|---|---|
| Парадигма | Граф состояний (state graph) с циклами |
| State management | ✅ TypedDict / Pydantic state, checkpointing |
| Conditional routing | ✅ Conditional edges, branching |
| Human-in-the-loop | ✅ `interrupt_before` / `interrupt_after` |
| Streaming | ✅ Token-level streaming, event streaming |
| Persistence | ✅ SQLite, PostgreSQL checkpointer |
| Observability | ✅ LangSmith (cloud) + **OpenTelemetry** callbacks |
| Parallel execution | ✅ Через `Send` API и parallel branches |
| Sub-graphs | ✅ Модульная композиция графов |
| Лицензия | MIT |
| Зрелость | ~2 года, активная разработка, быстро растущее сообщество |

### 2. LlamaIndex Workflows

| Характеристика | Детали |
|---|---|
| Парадигма | Event-driven workflows |
| State management | ⚠️ Через Context object (менее формализованный) |
| Conditional routing | ✅ Event-based routing |
| Human-in-the-loop | ⚠️ Требует кастомной реализации |
| Streaming | ✅ Через event handlers |
| Persistence | ⚠️ Ограниченная (нет нативного checkpointing) |
| Observability | ✅ LlamaTrace + callbacks |
| Зрелость | ~1.5 года для workflows, LlamaIndex — зрелый проект |

### 3. Haystack (deepset)

| Характеристика | Детали |
|---|---|
| Парадигма | Pipeline (DAG) |
| State management | ⚠️ Через pipeline inputs/outputs |
| Conditional routing | ✅ Routers |
| Human-in-the-loop | ❌ Нет нативной поддержки |
| Streaming | ⚠️ Ограниченная |
| Persistence | ❌ Нет checkpointing |
| Observability | ✅ OpenTelemetry |
| Зрелость | ~4 года (Haystack 2.x — полный рефакторинг) |

### 4. Custom orchestration (чистый Python)

| Характеристика | Детали |
|---|---|
| Парадигма | Произвольная |
| Гибкость | ✅ Полная |
| State management | Кастомная реализация |
| Observability | Кастомная реализация |
| Время разработки | ❌ Значительное |

## Решение

**Выбран: LangGraph**

### Архитектура графа:

```
                    ┌─────────────┐
                    │   START     │
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │  Classify   │
                    │   Intent    │
                    └──────┬──────┘
                           │
              ┌────────────┼────────────┐
              │            │            │
       ┌──────▼─────┐ ┌───▼───┐ ┌─────▼──────┐
       │  Vector    │ │ Graph │ │  Keyword   │
       │  Search    │ │ Query │ │  Search    │
       └──────┬─────┘ └───┬───┘ └─────┬──────┘
              │            │            │
              └────────────┼────────────┘
                           │
                    ┌──────▼──────┐
                    │   Fuse &    │
                    │   Rerank    │
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │  Build      │
                    │  Prompt     │
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │  Generate   │
                    │  (LLM)      │
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │  Validate   │◄─── (loop if needed)
                    │  & Cite     │
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │    END      │
                    └─────────────┘
```

### Конфигурация:

| Параметр | Значение |
|---|---|
| Фреймворк | `langgraph` >= 0.2.x |
| State | `TypedDict` с полями: query, intent, documents, graph_context, response |
| Checkpointer | `SqliteSaver` (local, для air-gapped) |
| Streaming | `astream_events` (token-level) |
| Tracing | OpenTelemetry callback handler → Jaeger/OTLP |
| Parallel branches | `Send` API для Vector + Graph + Keyword search |

## Обоснование

### 1. Обязательное требование проекта

LangGraph указан как обязательный компонент в требованиях заказчика. Данный ADR обосновывает, почему это требование **технически оправдано**, а не просто формально выполнено.

### 2. Граф состояний идеально подходит для GraphRAG

RAG-пайплайн для юридических текстов — **нелинейный**:
- Классификация запроса определяет ветку обработки
- Валидация ответа может запустить **повторный** поиск (цикл)
- Human-in-the-loop прерывает выполнение для одобрения юристом

LangGraph — единственный из рассмотренных фреймворков, который нативно поддерживает **циклы** в графе выполнения. Haystack (DAG) и LlamaIndex Workflows требуют workarounds.

### 3. State Management с Checkpointing

```python
from langgraph.graph import StateGraph
from langgraph.checkpoint.sqlite import SqliteSaver

class GraphRAGState(TypedDict):
    query: str
    intent: str
    vector_results: list[Document]
    graph_context: list[dict]
    fused_context: list[Document]
    response: str
    citations: list[str]
    iteration: int

checkpointer = SqliteSaver.from_conn_string("graphrag_checkpoints.db")
graph = StateGraph(GraphRAGState)
app = graph.compile(checkpointer=checkpointer)
```

Checkpointing критичен для:
- **Resumability**: если LLM-генерация прервалась — продолжение с последнего шага
- **Debugging**: просмотр state на каждом шаге пайплайна
- **Audit trail**: для юридической системы важна прослеживаемость решений

### 4. OpenTelemetry интеграция

```python
from langchain_core.tracers import LangChainTracer
from opentelemetry import trace

# Каждый шаг пайплайна — span в OpenTelemetry
# Метрики: latency, token count, retrieval recall
```

Требование проекта — OpenTelemetry для tracing. LangGraph поддерживает это через callback-систему LangChain, которая транслирует events в OTel spans.

### 5. Экосистема LangChain

LangGraph работает в экосистеме LangChain, что даёт:
- `langchain-qdrant` — интеграция с vector DB
- `langchain-neo4j` — интеграция с graph DB
- `langchain-community` — Ollama LLM/embeddings
- `langchain-core` — базовые абстракции (Document, Retriever)

## Trade-offs

### Положительные:
- ✅ Нативные циклы в графе — для iterative refinement ответов
- ✅ Human-in-the-loop — `interrupt_before` для одобрения юристом
- ✅ Checkpointing — audit trail и resumability
- ✅ Streaming — token-level для интерактивного UI
- ✅ Параллельные branches — одновременный vector + graph search
- ✅ Модульность — sub-graphs для изоляции компонентов
- ✅ MIT лицензия

### Отрицательные:
- ⚠️ **Быстро меняющийся API** — breaking changes между версиями (mitigation: pin версию)
- ⚠️ **Learning curve** — концепция state graph сложнее простого pipeline
- ⚠️ **Overhead абстракций** — LangChain/LangGraph добавляет latency (~5–10ms per step)
- ⚠️ **Vendor coupling** — зависимость от экосистемы LangChain (mitigation: абстракция через interfaces)
- ⚠️ **Debugging** — стек вызовов через callbacks может быть сложным для отладки
- ⚠️ **LangSmith зависимость** — лучший debugging UI требует облачного LangSmith (не air-gapped); альтернатива — OpenTelemetry + Jaeger

### Критические митигации:

1. **Pinning версий**: `langgraph==0.2.x` в `pyproject.toml`
2. **Абстракция**: бизнес-логика в отдельных модулях, LangGraph — только оркестрация
3. **Тестирование**: unit-тесты для каждого node отдельно от графа
4. **Мониторинг**: OpenTelemetry + Jaeger вместо LangSmith для air-gapped
