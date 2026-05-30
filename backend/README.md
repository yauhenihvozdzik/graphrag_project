# GraphRAG Platform — Backend

Защищённая платформа GraphRAG для анализа корпоративных знаний (юридический домен).

## Архитектура

```
app/
├── api/v1/              # REST API endpoints
│   ├── api.py           # Router aggregation + /health
│   ├── auth.py          # /auth (register, login, sessions)
│   ├── chat.py          # /chat, /chat/stream (SSE)
│   ├── ingest.py        # /ingest, /ingest/file
│   └── graph.py         # /graph/visualize, /graph/search, /graph/entity
├── core/
│   ├── config.py        # Settings (env-based)
│   ├── logging.py       # Structured logging (structlog)
│   ├── metrics.py       # Prometheus metrics
│   ├── middleware.py     # Request metrics, logging context, security headers
│   ├── observability.py  # OpenTelemetry tracing
│   ├── graphrag/        # GraphRAG pipeline
│   │   ├── document_ingestion.py  # File parsing, chunking
│   │   ├── entity_extraction.py   # NER for Russian legal entities
│   │   ├── graph_builder.py       # Neo4j graph construction
│   │   └── vector_indexer.py      # Qdrant embedding storage
│   ├── langgraph/       # LangGraph orchestration
│   │   ├── agent.py     # State machine (classify → retrieve → generate → guardrails)
│   │   ├── tools.py     # GraphRAG tools (vector_search, graph_query, hybrid_search)
│   │   └── memory.py    # Neo4j + Qdrant hybrid memory
│   └── security/        # Security layer
│       ├── guardrails.py # PII filtering, prompt injection protection
│       └── rbac.py      # Role-based access control on graph nodes
├── services/            # External service clients
│   ├── neo4j_service.py # Neo4j async driver
│   ├── qdrant_service.py # Qdrant async client
│   ├── ollama_service.py # Ollama LLM + embedding client
│   └── database.py      # PostgreSQL (SQLModel)
├── models/              # Database models
│   ├── user.py          # User model with RBAC fields
│   ├── session.py       # Chat session model
│   └── schemas.py       # Pydantic request/response schemas
├── utils/               # Utilities
│   ├── auth.py          # JWT token management
│   └── sanitization.py  # Input sanitization
└── main.py              # FastAPI app entry point
```

## Стек технологий

| Компонент | Решение |
|---|---|
| LLM | T-lite-it-1.0 (7B) GGUF Q4_K_M через Ollama |
| Embedding | BAAI/bge-m3 (1024-dim) |
| Vector DB | Qdrant |
| Graph DB | Neo4j Community 5.x |
| Orchestration | LangGraph |
| Backend | FastAPI + Uvicorn |
| Auth | JWT + bcrypt |
| Sessions | PostgreSQL |
| Tracing | OpenTelemetry → Jaeger |
| Metrics | Prometheus |

## Запуск

### Docker Compose (рекомендуется)

```bash
docker-compose up -d
```

### Локальная разработка

```bash
# 1. Установка зависимостей
pip install -e ".[dev,otel]"

# 2. Запуск внешних сервисов
docker-compose up -d neo4j qdrant postgres jaeger

# 3. Запуск Ollama с моделями
ollama pull t-lite:7b-q4_K_M
ollama pull bge-m3

# 4. Запуск backend
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## API Endpoints

### Auth
- `POST /api/v1/auth/register` — Регистрация
- `POST /api/v1/auth/login` — Авторизация (JWT)
- `GET /api/v1/auth/me` — Профиль
- `POST /api/v1/auth/sessions` — Создание сессии
- `GET /api/v1/auth/sessions` — Список сессий

### Chat
- `POST /api/v1/chat` — Запрос к GraphRAG (JSON)
- `POST /api/v1/chat/stream` — Streaming ответ (SSE)

### Ingestion
- `POST /api/v1/ingest` — Загрузка текста
- `POST /api/v1/ingest/file` — Загрузка файла (PDF/DOCX/TXT)

### Graph
- `GET /api/v1/graph/visualize` — Данные для визуализации графа
- `POST /api/v1/graph/search` — Поиск сущностей
- `GET /api/v1/graph/entity/{name}` — Окрестность сущности
- `GET /api/v1/graph/stats` — Статистика графа

### System
- `GET /api/v1/health` — Health check
- `GET /metrics` — Prometheus метрики

## Безопасность

### Guardrails
- **PII фильтрация**: ИНН, СНИЛС, паспорт, телефон, email, банковские реквизиты
- **Prompt injection защита**: обнаружение инъекций на русском и английском языках
- **XSS/Injection sanitization**: очистка входных данных

### RBAC
- **Роли**: admin, analyst, viewer, auditor
- **Отделы**: legal, compliance, hr, finance, management, it
- **Уровни доступа**: public (0), internal (1), confidential (2), secret (3)
- **Фильтрация на уровне узлов графа**: каждый узел имеет метаданные RBAC

## Датасеты

Платформа оптимизирована для работы с юридическими документами РФ:
- **RusLawOD**: открытые данные российского законодательства
- **RFSD**: Federal System of Legal Documents
