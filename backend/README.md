<!-- AUDIT: updated 2026-07-08 -->

# GraphRAG Platform — Backend

Защищённая платформа GraphRAG для анализа корпоративных знаний (юридический домен).

## Архитектура

```
app/
├── api/v1/              # REST API endpoints
│   ├── api.py           # Router aggregation + /health, /config/services
│   ├── auth.py          # /auth (register, login, sessions, users CRUD, impersonate)
│   ├── admin.py         # /admin/settings CRUD, history, reload, debug
│   ├── chat.py          # /chat, /chat/stream (SSE), /chat/history
│   ├── departments.py   # /departments CRUD
│   ├── ingest.py        # /ingest, /ingest/file, /ingest/url, /ingest/status
│   ├── graph.py         # /graph/visualize, /graph/search, /graph/entity, /graph/stats, /graph/documents, /graph/document CRUD, /graph/clear
│   └── tests.py         # /tests/run (SSE)
├── core/
│   ├── config.py        # Settings (env-based)
│   ├── constants.py     # Runtime constants (partially deprecated by SettingsRegistry)
│   ├── logging.py       # Structured logging (structlog)
│   ├── metrics.py       # Prometheus metrics
│   ├── middleware.py     # Request metrics, logging context, security headers
│   ├── observability.py  # OpenTelemetry tracing
│   ├── prompts.py       # System prompts (fallback values)
│   ├── settings_registry.py # SettingsRegistry singleton (in-memory cache from DB)
│   ├── graphrag/        # GraphRAG pipeline
│   │   ├── document_ingestion.py  # File parsing, chunking
│   │   ├── entity_extraction.py   # NER for Russian legal entities
│   │   ├── graph_builder.py       # Neo4j graph construction
│   │   └── vector_indexer.py      # Qdrant embedding storage
│   ├── langgraph/       # LangGraph orchestration
│   │   ├── agent.py     # State machine (classify → retrieve → generate → guardrails)
│   │   ├── agent_utils.py # Agent utilities (spelling, off-topic, build_system_prompt)
│   │   ├── tools.py     # GraphRAG tools (vector_search, graph_query, hybrid_search)
│   │   └── memory.py    # GraphRAGMemory (Neo4j + Qdrant hybrid memory)
│   └── security/        # Security layer
│       ├── guardrails.py # PII filtering, prompt injection protection
│       └── rbac.py      # Role-based access control on graph nodes
├── services/            # External service clients
│   ├── neo4j_service.py # Neo4j async driver
│   ├── qdrant_service.py # Qdrant async client
│   ├── ollama_service.py # Ollama LLM + embedding client
│   ├── database.py      # PostgreSQL (SQLModel) — God Object, требует рефакторинга
│   └── s3_service.py    # MinIO S3 client
├── models/              # Database models
│   ├── __init__.py      # Model exports
│   ├── base.py          # Base SQLModel with common fields
│   ├── user.py          # User model with RBAC fields
│   ├── session.py       # Chat session model
│   ├── message.py       # ChatMessage model
│   ├── department.py    # Department model
│   ├── file_metadata.py # File metadata model
│   ├── admin.py         # AdminSetting, AdminSettingAudit, AdminSettingVersion
│   └── schemas.py       # Pydantic request/response schemas
├── utils/               # Utilities
│   ├── auth.py          # JWT token management
│   └── sanitization.py  # Input sanitization
├── seed_admin_settings.py  # Seed default admin settings
└── main.py              # FastAPI app entry point
```

## Стек технологий

| Компонент | Решение |
|---|---|
| LLM | T-lite-it-1.0 (7B) GGUF Q4_K_M через Ollama |
| Embedding | BAAI/bge-m3 (1024-dim) |
| Vector DB | Qdrant |
| Graph DB | Neo4j Community 5.x |
| Orchestration | LangGraph (StateGraph State Machine) |
| Backend | FastAPI + Uvicorn |
| Auth | JWT + bcrypt |
| Sessions | PostgreSQL |
| Tracing | OpenTelemetry → Jaeger (частично) |
| Metrics | Prometheus |

## Запуск

### Docker Compose (рекомендуется)

```bash
docker compose up -d
```

### Локальная разработка

```bash
# 1. Установка зависимостей
pip install -e ".[dev,otel]"

# 2. Запуск внешних сервисов
docker compose up -d neo4j qdrant postgres jaeger

# 3. Запуск Ollama с моделями
ollama pull qwen2.5:7b
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

### Admin (users)
- `GET /api/v1/auth/users` — Список пользователей
- `PUT /api/v1/auth/users/{user_id}` — Изменение пользователя
- `DELETE /api/v1/auth/users/{user_id}` — Удаление пользователя
- `POST /api/v1/auth/users/{user_id}/impersonate` — Имперсонация

### Chat
- `POST /api/v1/chat` — Запрос к GraphRAG (JSON)
- `POST /api/v1/chat/stream` — Streaming ответ (SSE)
- `GET /api/v1/chat/history` — История сообщений
- `DELETE /api/v1/chat/history` — Очистка истории

### Ingestion
- `POST /api/v1/ingest` — Загрузка текста (с дедупликацией по хешу)
- `POST /api/v1/ingest/file` — Загрузка файла (PDF/DOCX/TXT/MD/ZIP)
- `POST /api/v1/ingest/url` — Загрузка по URL
- `GET /api/v1/ingest/status/{doc_id}` — Статус обработки

### Graph
- `GET /api/v1/graph/visualize` — Данные для визуализации графа (с RBAC-фильтрацией)
- `POST /api/v1/graph/search` — Поиск сущностей
- `GET /api/v1/graph/entity/{entity_name}` — Окрестность сущности
- `GET /api/v1/graph/stats` — Статистика графа + Qdrant
- `GET /api/v1/graph/documents` — Список документов (пагинация, сортировка, фильтры)
- `GET /api/v1/graph/document/{doc_id}/content` — Скачивание документа
- `PUT /api/v1/graph/document/{doc_id}` — Обновление clearance_level/department
- `DELETE /api/v1/graph/document/{doc_id}` — Удаление документа
- `DELETE /api/v1/graph/clear` — Полная очистка графа, векторов и S3

### Departments
- `GET /api/v1/departments/` — Список отделов
- `POST /api/v1/departments/` — Создание отдела (admin)
- `PUT /api/v1/departments/{dep_id}` — Изменение отдела (admin)
- `DELETE /api/v1/departments/{dep_id}` — Удаление отдела (admin)

### Admin Settings
- `GET /api/v1/admin/settings` — Все настройки по категориям
- `PUT /api/v1/admin/settings/{setting_id}` — Обновление настройки
- `PUT /api/v1/admin/settings/category/{category}` — Обновление категории
- `GET /api/v1/admin/settings/{category}` — Настройки категории
- `POST /api/v1/admin/settings/reload` — Перезагрузка кэша SettingsRegistry
- `GET /api/v1/admin/settings/history` — История изменений

### Tests
- `POST /api/v1/tests/run` — Запуск тестов (SSE, admin only)

### System
- `GET /api/v1/health` — Health check
- `GET /api/v1/config/services` — Конфигурация сервисов для frontend
- `GET /metrics` — Prometheus метрики

## Безопасность

### Guardrails
- **PII фильтрация**: ИНН, СНИЛС, паспорт, телефон, email, банковские реквизиты
- **Prompt injection защита**: обнаружение инъекций на русском и английском языках
- **XSS/Injection sanitization**: очистка входных данных

### RBAC
- **Роли**: admin, analyst, viewer, **auditor** (доступ только на чтение)
- **Отделы**: legal, compliance, hr, finance, management, it
- **Уровни доступа**: public (0), internal (1), confidential (2), secret (3)
- **Фильтрация на уровне узлов графа**: каждый узел имеет метаданные RBAC

## Датасеты

Платформа оптимизирована для работы с юридическими документами РФ:
- **RusLawOD**: открытые данные российского законодательства
- **RFSD**: Federal System of Legal Documents
