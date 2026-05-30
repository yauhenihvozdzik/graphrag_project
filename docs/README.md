# GraphRAG Platform

**Корпоративная платформа анализа знаний на основе Graph RAG**

Платформа объединяет графовую базу данных (Neo4j), векторный поиск (Qdrant), LLM (Ollama), S3-хранилище (MinIO) и PostgreSQL для интеллектуального анализа корпоративных документов с многоуровневым контролем доступа (RBAC).

---

## Архитектура

```
┌──────────────────────────────────────────────────────┐
│                    Frontend (Nginx)                    │
│              HTML/CSS/JS — порт 3000                  │
└───────────────────────┬──────────────────────────────┘
                        │ /api/*
┌───────────────────────▼──────────────────────────────┐
│              Backend (FastAPI) — порт 8000             │
│  ┌──────┐ ┌──────────┐ ┌──────────┐ ┌────────────┐  │
│  │ Auth │ │   Chat   │ │  Ingest  │ │   Graph    │  │
│  └──┬───┘ └────┬─────┘ └────┬─────┘ └─────┬──────┘  │
│     │    ┌─────▼──────────────▼─────────────▼───┐    │
│     │    │       LangGraph Agent                 │    │
│     │    │  classify → retrieve → generate →     │    │
│     │    │                      guardrails       │    │
│     │    └───┬──────────┬───────────┬───────────┘    │
│     │        │          │           │                 │
│  ┌──▼───┐ ┌──▼───┐ ┌───▼────┐ ┌───▼──────┐ ┌─▼────┐ │
│  │  JWT │ │Qdrant│ │ Neo4j  │ │ Ollama   │ │Mail  │ │
│  │  +   │ │Vector│ │ Graph  │ │ LLM +    │ │pit   │ │
│  │Postgr│ │Search│ │Traversal│ │Embedding │ │SMTP  │ │
│  └──────┘ └──────┘ └────────┘ └──────────┘ └──────┘ │
│                                            ┌──▼────┐ │
│                                            │ MinIO │ │
│                                            │  S3   │ │
│                                            └───────┘ │
└──────────────────────────────────────────────────────┘

┌────────── Observability ──────────┐  ┌─── Infra & Tools ───┐
│ Prometheus │ Grafana │ Jaeger     │  │ Mailpit  :8025      │
│   :9090    │  :3001  │  :16686    │  │ OpenWebUI :3100     │
│                                    │  │ MinIO Console :9001 │
│                                    │  │ pgAdmin :5050       │
└────────────────────────────────────┘  └─────────────────────┘
```

## Технологический стек

| Компонент | Технология | Назначение |
|-----------|-----------|------------|
| LLM | Ollama + T-lite-it-1.0 (7B) / Qwen 2.5 (7B) | Генерация ответов на русском языке |
| Embeddings | bge-m3 (1024-dim) | Векторные представления документов |
| Vector DB | Qdrant | Семантический поиск с фильтрацией по RBAC |
| Graph DB | Neo4j 5.26 Community | Граф знаний, связи сущностей |
| Backend | FastAPI + LangGraph | API, оркестрация RAG pipeline |
| Auth | JWT + PostgreSQL 16 | Аутентификация, сессии, пользователи |
| Frontend | HTML/CSS/JS + Nginx:alpine | Веб-интерфейс (SPA, тёмная тема) |
| Storage | MinIO (S3-совместимое) | Хранение документов и файлов |
| Email | Mailpit (dev) / SMTP (prod) | Уведомления о регистрации и активации |
| Tracing | OpenTelemetry + Jaeger | Распределённая трассировка |
| Metrics | Prometheus + Grafana | Метрики и мониторинг |
| LLM UI | Open WebUI | Веб-интерфейс Ollama (порт 3100) |
| DB Admin | pgAdmin | Управление PostgreSQL (порт 5050) |

## Быстрый старт

### Требования
- Docker Desktop 4.x+
- Docker Compose v2
- 16 GB RAM (рекомендуется)
- GPU (опционально, для ускорения Ollama)

### Запуск

```bash
# 1. Клонировать репозиторий
git clone <repo-url>
cd graphrag_project

# 2. Запустить полный стек
docker compose up -d

# 3. Инициализировать приложение
chmod +x scripts/init.sh
./scripts/init.sh
```

Примечание: `scripts/init.sh` запускает инфраструктуру, ожидает готовности сервисов, загружает модели Ollama (`t-lite:7b-q4_K_M`, `bge-m3`), создаёт индексы Neo4j, seed-пользователей и запускает backend+frontend.

### Доступ к сервисам

| Сервис | URL | Назначение |
|--------|-----|------------|
| Frontend | http://localhost:3000 | Веб-интерфейс платформы |
| Backend API | http://localhost:8000/docs | Swagger-документация |
| Neo4j Browser | http://localhost:7474 | Графовая БД (neo4j / neo4j_password) |
| Mailpit | http://localhost:8025 | Перехватчик писем (dev) |
| Grafana | http://localhost:3001 | Дашборды (admin / graphrag_admin) |
| Jaeger | http://localhost:16686 | Трассировка запросов |
| Prometheus | http://localhost:9090 | Метрики |
| MinIO Console | http://localhost:9001 | S3-хранилище (minioadmin / minioadmin) |
| Open WebUI | http://localhost:3100 | Веб-интерфейс Ollama |
| pgAdmin | http://localhost:5050 | PostgreSQL GUI (admin@graphrag.com / pgadmin) |

### Демо-пользователи

| Email | Пароль | Роль | Отдел | Доступ |
|-------|--------|------|-------|--------|
| admin@graphrag.local | Admin123! | Администратор | management | Все разделы + управление пользователями |
| analyst@graphrag.local | Analyst123! | Аналитик | legal | Чат + Загрузка + Документы |
| viewer@graphrag.local | Viewer123! | Читатель | research | Только чат |
| legal@graphrag.local | Legal123! | Аналитик | legal | Чат + Загрузка + Документы |

## API Endpoints

### Аутентификация
- `POST /api/v1/auth/register` — Регистрация
- `POST /api/v1/auth/login` — Вход
- `GET /api/v1/auth/me` — Профиль
- `POST /api/v1/auth/sessions` — Создание сессии чата
- `GET /api/v1/auth/sessions` — Список сессий пользователя

### Чат
- `POST /api/v1/chat` — Запрос к GraphRAG (JSON)
- `POST /api/v1/chat/stream` — Потоковый ответ (SSE)
- `GET /api/v1/chat/history` — История сообщений
- `DELETE /api/v1/chat/history` — Очистка истории

### Загрузка документов
- `POST /api/v1/ingest` — Загрузка текста (с дедупликацией по хешу)
- `POST /api/v1/ingest/file` — Загрузка файла (PDF, DOCX, TXT, MD, ZIP)
- `POST /api/v1/ingest/url` — Загрузка по URL
- `GET /api/v1/ingest/status/{doc_id}` — Статус обработки

### Граф знаний
- `GET /api/v1/graph/visualize` — Визуализация графа (с RBAC-фильтрацией)
- `POST /api/v1/graph/search` — Поиск сущностей
- `GET /api/v1/graph/entity/{entity_name}` — Окрестность сущности в графе
- `GET /api/v1/graph/stats` — Статистика графа + Qdrant
- `GET /api/v1/graph/documents` — Список документов (пагинация, сортировка, фильтры)
- `GET /api/v1/graph/document/{doc_id}/content` — Скачивание документа (S3 → Neo4j full_text → чанки)
- `PUT /api/v1/graph/document/{doc_id}` — Обновление clearance_level/department документа
- `DELETE /api/v1/graph/document/{doc_id}` — Удаление документа (Neo4j + Qdrant + S3 + file_metadata)
- `DELETE /api/v1/graph/clear` — Полная очистка графа, векторов и S3

### Отделы
- `GET /api/v1/departments/` — Список отделов
- `POST /api/v1/departments/` — Создание отдела (admin)
- `PUT /api/v1/departments/{dep_id}` — Изменение отдела (admin)
- `DELETE /api/v1/departments/{dep_id}` — Удаление отдела (admin)

### Администрирование
- `GET /api/v1/auth/users` — Список пользователей (пагинация, фильтры, поиск)
- `PUT /api/v1/auth/users/{id}` — Изменение пользователя (роль, отдел, активация)
- `DELETE /api/v1/auth/users/{id}` — Удаление пользователя
- `POST /api/v1/auth/users/{id}/impersonate` — Войти под пользователем

### Тестирование
- `POST /api/v1/tests/run` — Запуск pytest через SSE (admin only)

### Система
- `GET /api/v1/health` — Здоровье сервисов (Ollama, Neo4j, Qdrant)
- `GET /api/v1/config/services` — Конфигурация сервисов для frontend
- `GET /metrics` — Prometheus метрики

## Безопасность

### RBAC (Контроль доступа)
- **Роли**: admin, analyst, viewer
- **Отделы**: all, legal, research, management, compliance, hr, finance, it
- **Уровни доступа**: 0 (public/открытый), 1 (internal/внутренний), 2 (confidential/конфиденциальный), 3 (secret/секретный)
- Фильтрация на уровне узлов графа (Cypher WHERE) и векторного поиска (Qdrant payload filter)
- **Активация аккаунтов**: пользователь регистрируется → получает email → админ активирует через панель пользователей → пользователь получает email об активации
- **Имперсонация**: админ может войти под любым пользователем (в frontend сохраняется admin-токен для возврата)

### Email-уведомления
- При регистрации — письмо с ожиданием активации
- При активации/деактивации — уведомление с контактом админа
- Отправитель: `graph@rag.by`
- **Разработка**: Mailpit (SMTP на порту 1025, Web UI на http://localhost:8025)
- **Продакшен**: реальный SMTP через `SMTP_USER` / `SMTP_PASSWORD` в `backend/.env`

### Guardrails
- Фильтрация ПДн (ИНН, СНИЛС, паспорт, телефон, email, банковские реквизиты)
- Детекция prompt injection (русский и английский языки)
- Санитизация XSS/SQL injection

## Тестирование

```bash
cd backend
pip install -e ".[dev]"
pytest ../tests/ -v
```

Либо через API: `POST /api/v1/tests/run` (SSE-стриминг результатов, admin only).

## Структура проекта

```
graphrag_project/
├── docker-compose.yml          # Полный стек (13 сервисов)
├── monitoring/
│   ├── prometheus.yml          # Конфигурация Prometheus
│   ├── grafana/                # Дашборды Grafana
│   └── pgadmin/                # Конфигурация pgAdmin
├── scripts/
│   ├── init.sh                 # Скрипт инициализации
│   ├── seed_users.py           # Создание демо-пользователей
│   ├── seed_departments.py     # Создание отделов
│   ├── load_datasets.py        # Загрузка демо-данных
│   └── ollama-init/            # Авто-загрузка моделей Ollama
├── frontend/
│   ├── index.html              # SPA интерфейс
│   ├── css/styles.css          # Стили (тёмная тема)
│   ├── js/api.js               # API клиент
│   ├── js/app.js               # Логика приложения (auth, чат, ingest, админка, тесты)
│   ├── Dockerfile              # nginx:alpine
│   └── nginx.conf              # Прокси /api/* → backend:8000, SSE
├── backend/
│   ├── app/
│   │   ├── api/v1/             # REST API endpoints (auth, chat, ingest, graph, departments, tests)
│   │   ├── core/
│   │   │   ├── config.py       # Settings (env-based)
│   │   │   ├── logging.py      # Структурное логирование (structlog)
│   │   │   ├── metrics.py      # Prometheus метрики
│   │   │   ├── middleware.py    # CORS, SecurityHeaders, Logging, Metrics
│   │   │   ├── observability.py # OpenTelemetry трассировка
│   │   │   ├── prompts.py      # Системные промпты и константы
│   │   │   ├── graphrag/       # GraphRAG pipeline (ingestion, extraction, graph, vectors)
│   │   │   ├── langgraph/      # LangGraph agent (agent, tools, memory)
│   │   │   └── security/       # RBAC + Guardrails
│   │   ├── models/             # Pydantic schemas + SQLModel (user, session, schemas)
│   │   ├── services/           # Neo4j, Qdrant, Ollama, DB (PostgreSQL), S3 (MinIO)
│   │   └── utils/              # Auth (JWT), sanitization
│   ├── Dockerfile
│   ├── pyproject.toml
│   └── .env
├── tests/                      # Pytest тесты
│   ├── conftest.py             # Фикстуры
│   ├── test_api.py
│   ├── test_rbac.py
│   ├── test_guardrails.py
│   ├── test_graphrag.py
│   └── test_llm_judge.py
└── docs/
    ├── README.md
    ├── DEPLOYMENT.md
    ├── TECH_STACK.md
    ├── USER_GUIDE.md
    └── VIDEO_DEMO_SCRIPT.md
```

## Лицензия

Internal / Учебный проект