# ADR-005: Выбор графовой базы данных

## Статус
Принято

## Контекст

GraphRAG платформа требует графовую базу данных для хранения и навигации по связям между юридическими сущностями:
- **Сущности**: законы, статьи, судебные решения, организации, персоны, даты
- **Связи**: «ссылается_на», «отменяет», «дополняет», «применяется_в», «принят_кем»
- **Запросы**: обход графа (traversal), поиск путей, подграфы связанных документов
- **Масштаб**: ~100K–1M узлов, ~500K–5M рёбер (для юридического корпуса)

**Интеграция в RAG-пайплайн:**
1. Пользователь задаёт вопрос
2. Vector search (Qdrant) → находит релевантные документы
3. **Graph traversal (Graph DB)** → расширяет контекст связанными документами
4. LLM генерирует ответ с учётом расширенного контекста

**Требования:**
- Self-hosted, on-premise
- Зрелый язык запросов для сложных traversal-операций
- Визуализация графа (для аналитиков)
- Интеграция с Python / LangGraph
- Работа на Windows 11 Pro

## Рассмотренные варианты

### 1. Neo4j Community Edition

| Характеристика | Детали |
|---|---|
| Язык запросов | **Cypher** — декларативный, SQL-подобный для графов |
| Лицензия | GPLv3 (Community) / Commercial (Enterprise) |
| Развёртывание | JAR (Java), Docker, Desktop App |
| Windows | ✅ Нативный (Neo4j Desktop) + Docker |
| RAM | ~2–4 GB для 1M узлов |
| Визуализация | ✅ **Neo4j Browser** — встроенный web UI |
| Python SDK | `neo4j` (официальный), `py2neo` |
| LangChain | ✅ `langchain-neo4j` — зрелая интеграция |
| Full-text search | ✅ Встроенный (Lucene-based) |
| APOC | ✅ Богатая библиотека процедур |
| GDS (Graph Data Science) | ⚠️ Community: PageRank, Louvain и др. (ограниченный набор) |
| Зрелость | **25+ лет**, стандарт de facto для графовых БД |

### 2. Apache AGE (PostgreSQL extension)

| Характеристика | Детали |
|---|---|
| Язык запросов | **openCypher** (подмножество Cypher) + SQL |
| Лицензия | Apache 2.0 |
| Развёртывание | PostgreSQL extension |
| Windows | ✅ Через PostgreSQL для Windows |
| RAM | Зависит от PostgreSQL (~1–2 GB base) |
| Визуализация | ⚠️ Нет встроенной (AGE Viewer — отдельный проект) |
| Python SDK | `psycopg2` + AGE-specific queries |
| LangChain | ⚠️ Экспериментальная поддержка |
| Зрелость | Молодой проект (~3 года), incubating в Apache |

**Преимущества**: единая БД для реляционных + графовых данных, Apache 2.0 лицензия.
**Недостатки**: ограниченный openCypher (не полный Cypher), слабая экосистема, нет GDS.

### 3. Memgraph

| Характеристика | Детали |
|---|---|
| Язык запросов | **openCypher** (расширенный) |
| Лицензия | BSL 1.1 (Community) / Enterprise |
| Развёртывание | Docker, бинарники |
| Windows | ⚠️ Docker only (нет нативного) |
| RAM | In-memory — ~3–6 GB для 1M узлов |
| Визуализация | ✅ Memgraph Lab — web UI |
| Python SDK | `gqlalchemy`, `neo4j` (compatible) |
| LangChain | ⚠️ Базовая поддержка |
| Зрелость | ~7 лет, фокус на real-time / streaming |

**Преимущества**: высокая производительность (in-memory), совместимость с Cypher.
**Недостатки**: BSL лицензия (ограничения для production), in-memory = высокое потребление RAM.

### 4. FalkorDB (бывший RedisGraph)

| Характеристика | Детали |
|---|---|
| Язык запросов | **openCypher** |
| Лицензия | MIT (часть Redis Stack) |
| Развёртывание | Redis module |
| Windows | ⚠️ Docker (Redis на Windows — ограниченная поддержка) |
| RAM | In-memory (как Redis) |
| Визуализация | ⚠️ Через RedisInsight (базовая) |
| Python SDK | `falkordb`, `redis` |
| LangChain | ⚠️ Ограниченная |
| Зрелость | ~5 лет, сменил название/владельца |

**Недостатки**: нестабильная судьба проекта (Redis → FalkorDB), ограниченные graph algorithms.

## Решение

**Выбран: Neo4j Community Edition**

### Конфигурация развёртывания:

| Параметр | Значение |
|---|---|
| Версия | Neo4j 5.x Community Edition |
| Развёртывание | Neo4j Desktop (Windows) или Docker |
| RAM (heap) | 2 GB (`dbms.memory.heap.max_size=2G`) |
| RAM (pagecache) | 1 GB (`server.memory.pagecache.size=1G`) |
| RAM (total) | ~3–4 GB |
| Bolt port | 7687 |
| HTTP port | 7474 (Neo4j Browser) |
| APOC | Enabled |
| Full-text indexes | Enabled для `title`, `text` полей |

### Примерная схема графа:

```cypher
// Узлы
(:Law {id, title, date, type, jurisdiction})
(:Article {id, number, text, law_id})
(:CourtDecision {id, case_number, date, court, text})
(:Entity {id, name, type})  // организация, персона

// Связи
(:Article)-[:BELONGS_TO]->(:Law)
(:Article)-[:REFERENCES]->(:Article)
(:Law)-[:AMENDS]->(:Law)
(:Law)-[:REPEALS]->(:Law)
(:CourtDecision)-[:APPLIES]->(:Article)
(:CourtDecision)-[:INVOLVES]->(:Entity)
```

## Обоснование

### 1. Зрелость и стабильность — критичны для юридической системы

Neo4j — **25+ лет** разработки, стандарт de facto для графовых БД:
- Крупнейшее сообщество (500K+ разработчиков)
- Богатая документация на русском языке
- Проверенный production track record в юридических системах

Для юридической платформы, где ошибки в данных и потеря связей неприемлемы, зрелость решения — ключевой фактор.

### 2. Cypher — мощный язык для юридических запросов

```cypher
// Найти все статьи, на которые ссылается данная статья,
// и судебную практику по каждой
MATCH (a:Article {number: "159"})-[:BELONGS_TO]->(:Law {title: "УК РФ"})
MATCH (a)-[:REFERENCES]->(ref:Article)
OPTIONAL MATCH (cd:CourtDecision)-[:APPLIES]->(ref)
WHERE cd.date >= date("2023-01-01")
RETURN ref.number, ref.text, collect(cd.case_number) AS court_cases
ORDER BY ref.number
```

Cypher позволяет выразить сложные traversal-запросы декларативно. openCypher (AGE, Memgraph, FalkorDB) поддерживает лишь подмножество функциональности.

### 3. Neo4j Browser — визуализация для аналитиков

Neo4j Browser предоставляет **интерактивную визуализацию графа** из коробки:
- Drag-and-drop навигация по связям
- Цветовое кодирование типов узлов и связей
- Экспорт визуализаций в SVG/PNG

Для юристов-аналитиков визуализация сети связей между законами и судебными решениями — ключевая функция.

### 4. Интеграция с LangGraph / LangChain

```python
from langchain_neo4j import Neo4jGraph, GraphCypherQAChain

graph = Neo4jGraph(url="bolt://localhost:7687", username="neo4j", password="...")
# Автоматическая генерация Cypher из natural language
chain = GraphCypherQAChain.from_llm(llm, graph=graph)
```

`langchain-neo4j` — **официальный** пакет с поддержкой:
- Graph QA (natural language → Cypher → результат)
- Graph vector store (embeddings в Neo4j)
- Knowledge graph construction

### 5. APOC — расширения для ETL и аналитики

APOC (Awesome Procedures on Cypher) предоставляет 450+ процедур:
- Импорт JSON/CSV/XML — для загрузки RusLawOD/RFSD
- Text functions — для нормализации юридических текстов
- Graph algorithms — PageRank, community detection
- Export — в JSON, GraphML, Cypher scripts

## Последствия

### Положительные:
- ✅ Стандарт de facto — минимальный риск vendor lock-in (Cypher стандартизирован ISO GQL)
- ✅ Встроенная визуализация — Neo4j Browser для аналитиков
- ✅ Зрелая интеграция с LangChain/LangGraph
- ✅ APOC — мощный ETL для юридических данных
- ✅ Full-text search — дополнительный канал поиска
- ✅ Работает на Windows нативно (Neo4j Desktop)

### Отрицательные:
- ⚠️ **GPLv3 лицензия** (Community) — ограничения для проприетарного ПО (но допустимо для внутреннего on-premise использования)
- ⚠️ Java dependency — требуется JDK 17+
- ⚠️ Community Edition: нет clustering, нет role-based access control
- ⚠️ RAM ~3–4 GB — заметный footprint при общих 64 GB

### Митигация лицензионных рисков:
- GPLv3 Community Edition допустима для **внутреннего** корпоративного использования (не распространяется как продукт)
- При необходимости коммерческого распространения — оценка Neo4j Enterprise или переход на Apache AGE
- Архитектура с абстракцией через LangChain graph interface позволяет замену БД без переписывания бизнес-логики
