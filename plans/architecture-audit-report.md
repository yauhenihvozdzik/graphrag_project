# Архитектурный аудит: GraphRAG Platform

**Дата:** 2026-07-08
**Версия кода:** 1.0.0
**Тип аудита:** Сравнение документации и кода (Expectation vs Reality)

---

## A. Определение архитектурного паттерна

### Что заявлено в документации

Документация (особенно [`docs/DEFENSE_PLAN.md`](docs/DEFENSE_PLAN.md) и [`docs/architecture/workspace.dsl`](docs/architecture/workspace.dsl)) описывает архитектуру как **C4 Model** с разделением на:

- **Плоскость управления** (Control Plane): FastAPI REST API + LangGraph (конечный автомат)
- **Плоскость данных** (Data Plane): PostgreSQL, Neo4j, Qdrant, MinIO
- **Уровни C4**: System Context → Containers → Components → Deployment

Дополнительно, в [`docs/TECH_STACK.md`](docs/TECH_STACK.md) прослеживается **Layered Architecture**:
- Frontend (HTML/CSS/JS + Nginx)
- Backend API (FastAPI)
- Agent (LangGraph)
- Services (Neo4j, Qdrant, Ollama, PostgreSQL, MinIO)
- Infrastructure (Prometheus, Grafana, Jaeger)

### Что фактически реализовано в коде

Фактическая архитектура — **гибридная Layered + Pipeline + State-Machine**:

| Слой | Реализация | Паттерн |
|------|-----------|---------|
| **UI** | Vanilla JS SPA (`frontend/js/app.js`, `frontend/js/api.js`) | SPA на нативном JS |
| **API** | FastAPI роутеры (`backend/app/api/v1/`) | REST (не MVC, не DDD) |
| **Orchestration** | LangGraph StateGraph (`backend/app/core/langgraph/agent.py`) | State Machine (конечный автомат) |
| **Pipeline** | GraphRAG: ingestion → extraction → graph → vectors | Пайплайн (последовательные шаги) |
| **Services** | Database, Neo4j, Qdrant, Ollama, S3 сервисы | Сервис-прокси (Service Layer) |
| **Security** | Middleware + RBAC + Guardrails | Cross-cutting |

> **Заключение:** Фактическая архитектура **соответствует** заявленному C4-подходу, но документация местами описывает более сложные компоненты (например, отдельный API Gateway, Kong), чем реализовано. Основной паттерн — **Layered Architecture с State Machine оркестрацией**, что корректно отражено в [`backend/README.md`](backend/README.md).

---

## B. Таблица "Ожидание (док) vs Реальность (код)"

### 1. Frontend

| Компонент | Что обещает документация | Что есть в коде | Статус |
|-----------|------------------------|-----------------|--------|
| **Framework** | Vanilla JS SPA ([docs/README.md](docs/README.md:57)) | Vanilla JS SPA (`frontend/js/app.js`) | ✅ Соответствует |
| **Framework** | React ([sequence-query-flow.mmd](docs/architecture/sequence-query-flow.mmd:8)) | Vanilla JS | ⚠️ Документация противоречива (React указан только в sequence-диаграмме) |
| **Proxy** | Nginx ([docs/README.md](docs/README.md:13)) | Nginx (`frontend/nginx.conf`) | ✅ Соответствует |
| **Markdown** | Markdown рендеринг | marked.js (CDN, `index.html:559`) | ✅ Соответствует |
| **Тёмная тема** | Тёмная тема ([docs/README.md](docs/README.md:57)) | CSS custom properties + data-theme (`styles.css`) | ✅ Соответствует |
| **Admin UI** | Вкладки: Prompts, Temperatures, Guardrails и др. ([admin-architecture.md](plans/admin-architecture.md:817)) | Полностью реализовано в `app.js:1766-2000` | ✅ Соответствует |
| **SSE тесты** | Streaming результатов ([docs/DEFENSE_PLAN.md](docs/DEFENSE_PLAN.md:261)) | `app.js:1620-1745` | ✅ Соответствует |

### 2. Backend — Core

| Компонент | Что обещает документация | Что есть в коде | Статус |
|-----------|------------------------|-----------------|--------|
| **Framework** | FastAPI ([docs/README.md](docs/README.md:18)) | FastAPI (`backend/app/main.py:142`) | ✅ Соответствует |
| **API Gateway** | Kong/Nginx ([sequence-query-flow.mmd](docs/architecture/sequence-query-flow.mmd:9)) | Только Nginx (без Kong) | ⚠️ Частично |
| **Rate Limiting** | Лимиты по ролям ([security-architecture.mmd](docs/architecture/security-architecture.mmd:39)) | Конфиг в [`config.py`](backend/app/core/config.py:63-65), но **нет middleware/запуска** | ❌ Отсутствует |
| **TLS** | TLS 1.3 ([security-architecture.mmd](docs/architecture/security-architecture.mmd:38)) | Не реализовано (dev-режим) | ⚠️ Частично |
| **CORS** | CORS | `main.py:151-157` | ✅ Соответствует |
| **Middleware** | Logging, Metrics, Security Headers | `main.py:158-160` | ✅ Соответствует |

### 3. LangGraph Agent

| Компонент | Что обещает документация | Что есть в коде | Статус |
|-----------|------------------------|-----------------|--------|
| **State Machine** | classify → retrieve → generate → guardrails ([agent.py](backend/app/core/langgraph/agent.py:4-6)) | Полный граф: classify → off_topic → spelling → retrieve → generate → guardrails | ✅ Соответствует (с доп. узлами) |
| **Checkpointing** | PostgreSQL-based ([ADR-006](docs/adr/006-orchestration-framework.md:138)) | `AsyncPostgresSaver` с fallback ([agent.py:92-108](backend/app/core/langgraph/agent.py:92-108)) | ✅ Соответствует |
| **Human-in-the-loop** | `interrupt_before` ([ADR-006](docs/adr/006-orchestration-framework.md:38)) | **Не реализован** | ❌ Отсутствует |
| **Dynamic top_k** | Не описан в ADR | Реализован в `agent.py:228-242` | ❓ Не документировано |
| **Spelling correction** | Упомянуто в DEFENSE_PLAN | Реализовано (`agent.py:153-179`, `agent_utils.py:185-236`) | ✅ Соответствует |
| **Off-topic filter** | Не описан в документации | Реализован (`agent.py:128-149`, `agent_utils.py:141-153`) | ❓ Не документировано |
| **OpenTelemetry** | LangGraph → Jaeger ([ADR-006](docs/adr/006-orchestration-framework.md:188-194)) | `observability.py` + instrument FastAPI, но **нет прямых вызовов из agent** | ⚠️ Частично |

### 4. Security / RBAC

| Компонент | Что обещает документация | Что есть в коде | Статус |
|-----------|------------------------|-----------------|--------|
| **JWT Algorithm** | RS256 ([security-architecture.mmd](docs/architecture/security-architecture.mmd:25)) | **HS256** (`config.py:46`) | ⚠️ Частично (HS256 вместо RS256) |
| **JWT Expiry** | 1h access / 7d refresh ([security-architecture.mmd:25](docs/architecture/security-architecture.mmd:25)) | **30 дней** (`config.py:47`) | ⚠️ Частично (расхождение в цифрах) |
| **Roles** | admin, analyst, viewer ([docs/README.md](docs/README.md:168-169)) | admin, analyst, viewer, **auditor** (в коде [`rbac.py:21`](backend/app/core/security/rbac.py:21)) | ⚠️ Частично (роль auditor есть в коде, но не в доке) |
| **RBAC Cypher filter** | WHERE-условия ([DEFENSE_PLAN.md](docs/DEFENSE_PLAN.md:123-131)) | `rbac_service.build_cypher_filter()` (`rbac.py:146-164`) | ✅ Соответствует |
| **RBAC Qdrant filter** | Payload фильтрация ([DEFENSE_PLAN.md:137-148](docs/DEFENSE_PLAN.md:137-148)) | Параметры clearance_level/department передаются в search | ✅ Соответствует |
| **Rate limiting** | По ролям ([security-architecture.mmd:39](docs/architecture/security-architecture.mmd:39)) | **Не реализован** в рантайме | ❌ Отсутствует |
| **Guardrails (PII)** | Двухуровневая фильтрация ([DEFENSE_PLAN.md](docs/DEFENSE_PLAN.md:182-184)) | `guardrails.py` — реализовано | ✅ Соответствует |
| **Guardrails (Injection)** | 16 паттернов ([DEFENSE_PLAN.md:187](docs/DEFENSE_PLAN.md:187)) | `guardrails.py:81-104` — 13 паттернов | ⚠️ Частично (13 вместо 16) |
| **IP Allowlist** | IP Filter ([security-architecture.mmd:41](docs/architecture/security-architecture.mmd:41)) | **Не реализован** | ❌ Отсутствует |
| **Vault** | JWT signing keys, DB credentials ([security-architecture.mmd:25-26](docs/architecture/security-architecture.mmd:25-26)) | **Не реализован** | ❌ Отсутствует |

### 5. Модели / Базы данных

| Компонент | Что обещает документация | Что есть в коде | Статус |
|-----------|------------------------|-----------------|--------|
| **PostgreSQL models** | users, sessions, messages, departments, file_metadata | Все реализованы | ✅ Соответствует |
| **Chat messages** | JSONB в sessions ([er-diagram.mmd](docs/architecture/er-diagram.mmd:26)) | **Отдельная таблица** `ChatMessage` (`models/message.py`) | ⚠️ Частично |
| **Audit logs** | Таблица `audit_logs` ([er-diagram.mmd](docs/architecture/er-diagram.mmd:34-44)) | **Не существует** в моделях | ❌ Отсутствует |
| **RBAC policies** | Таблица `rbac_policies` ([er-diagram.mmd:46-56](docs/architecture/er-diagram.mmd:46-56)) | **Не существует** (RBAC реализован в коде) | ❌ Отсутствует |
| **Neo4j: Concept** | Узлы `neo4j_Concept` ([er-diagram.mmd:88-93](docs/architecture/er-diagram.mmd:88-93)) | **Не используется** как label в графе | ❌ Отсутствует |
| **Qdrant collections** | `documents` + `chunks` ([ADR-004](docs/adr/004-vector-database.md:95)) | Единая коллекция `graphrag_documents` (`config.py:54`) | ⚠️ Частично |
| **Admin Settings** | 3 таблицы: settings, audit, version ([admin-architecture.md](plans/admin-architecture.md:106-188)) | Все реализованы (`models/admin.py`) | ✅ Соответствует |
| **Alembic migrations** | 001 + 002 | Обе ревизии существуют | ✅ Соответствует |

### 6. API Endpoints

| Компонент | Что обещает документация | Что есть в коде | Статус |
|-----------|------------------------|-----------------|--------|
| **Auth** | register, login, me, sessions | Все в `auth.py` | ✅ Соответствует |
| **Auth (admin)** | users CRUD, impersonate | Реализованы в `auth.py` (объединены с auth) | ✅ Соответствует |
| **Chat** | POST /chat, /chat/stream | Реализованы в `chat.py` | ✅ Соответствует |
| **Chat** | GET /chat/history, DELETE /chat/history | Реализованы в `chat.py` | ✅ Соответствует |
| **Ingest** | text, file, url, status | Все в `ingest.py` | ✅ Соответствует |
| **Graph** | visualize, search, entity, stats, documents, документ CRUD | Все в `graph.py` | ✅ Соответствует |
| **Departments** | CRUD | Все в `departments.py` | ✅ Соответствует |
| **Tests** | POST /tests/run | `tests.py` | ✅ Соответствует |
| **Health** | GET /health | `api.py:30` | ✅ Соответствует |
| **Metrics** | GET /metrics | `main.py:162` (setup_metrics) | ✅ Соответствует |
| **Admin Settings** | 6+ эндпоинтов | Все в `admin.py` | ✅ Соответствует |
| **Config/Services** | GET /config/services | `api.py:73` | ✅ Соответствует |

### 7. Инфраструктура / Мониторинг

| Компонент | Что обещает документация | Что есть в коде | Статус |
|-----------|------------------------|-----------------|--------|
| **Prometheus** | Сбор метрик ([docs/README.md](docs/README.md:61)) | `prometheus.yml`, метрики в `metrics.py` | ✅ Соответствует |
| **Grafana** | Дашборды | Дашборд `graphrag-backend.json` | ✅ Соответствует |
| **Jaeger** | Распределённая трассировка | `observability.py` + конфиг | ⚠️ Частично (не все spans инструментированы) |
| **OpenTelemetry** | Инструментирование FastAPI/httpx | `instrument_fastapi(app)` в `main.py:163` | ✅ Соответствует |
| **GPU мониторинг** | nvidia-ml-py | Зависимость в `pyproject.toml:53` | ⚠️ Частично (зависимость есть, использование неочевидно) |
| **pgAdmin** | Управление PostgreSQL | `servers.json` | ✅ Соответствует |
| **Mailpit** | Email dev | В `docker-compose.yml` | ✅ Соответствует |
| **Open WebUI** | LLM Web UI | В `docker-compose.yml` | ✅ Соответствует |
| **Neo4j Browser** | Визуализация | Через `config/services` | ✅ Соответствует |
| **Сетевая сегментация** | DMZ/Internal ([security-architecture.mmd](docs/architecture/security-architecture.mmd:103-108)) | Указана в `workspace.dsl`, но **не в docker-compose.yml** | ⚠️ Частично |

### 8. Зависимости (pyproject.toml vs docs)

| Зависимость | Заявлено в TECH_STACK.md | В pyproject.toml | Статус |
|------------|-------------------------|------------------|--------|
| **langgraph** | ≥0.2.x | ≥0.2.0 | ✅ |
| **langchain-core** | ≥0.3.0 | ≥0.3.0 | ✅ |
| **langchain-community** | ≥0.3.0 | ≥0.3.0 | ✅ |
| **sqlmodel** | ≥0.0.21 | ≥0.0.21 | ✅ |
| **neo4j** | ≥5.20.0 | ≥5.20.0 | ✅ |
| **qdrant-client** | ≥1.11.0 | ≥1.11.0 | ✅ |
| **boto3 (S3)** | Не указан отдельно | ≥1.35.0 | ❓ Не документировано |
| **pymupdf** | Не указан | ≥1.24.0 | ❓ Не документировано |
| **python-docx** | Не указан | ≥1.1.0 | ❓ Не документировано |
| **opentelemetry** | ≥1.20.0 | ≥1.25.0 (otel extras) | ✅ |
| **langgraph-checkpoint-postgres** | Не указан | ≥2.0.0 | ❓ Не документировано |
| **pytest** | 8.0 (in README) | ≥8.0.0 | ✅ |

---

## C. Структурный анализ

### Соответствие структуры папок заявленным слоям

```
backend/
├── app/
│   ├── api/v1/           # REST API endpoints — ✅ описано в docs/README.md
│   ├── core/             # Core logic — ✅ описано
│   │   ├── graphrag/     # GraphRAG pipeline — ✅ описано
│   │   ├── langgraph/    # LangGraph agent — ✅ описано
│   │   └── security/     # RBAC + Guardrails — ✅ описано
│   ├── models/           # SQLModel + Pydantic — ✅ описано
│   ├── services/         # Внешние сервисы — ✅ описано
│   └── utils/            # JWT + sanitization — ✅ описано
```

**Вывод:** Физическая структура проекта **полностью соответствует** описанию в [`backend/README.md`](backend/README.md:7-46).

### Отсутствующие модули

| Модуль | Где обещан | Статус |
|--------|-----------|--------|
| **API Gateway (Kong)** | sequence-query-flow.mmd | ❌ — используется только Nginx |
| **Vault (управление секретами)** | security-architecture.mmd | ❌ — секреты в .env |
| **Rate Limiter middleware** | security-architecture.mmd | ❌ — конфиг есть, код отсутствует |
| **Session Manager** (отдельный компонент) | sequence-query-flow.mmd:11 | ❌ — встроен в auth |
| **Planner** (отдельный компонент) | sequence-query-flow.mmd:13 | ❌ — встроен в LangGraph agent |
| **Tools Interface** (отдельный компонент) | sequence-query-flow.mmd:14 | ❌ — встроен в agent.retrieve |
| **Memory Module** (отдельный) | sequence-query-flow.mmd:15 | ⚠️ — существует GraphRAGMemory (memory.py) |
| **ERP/CRM/EDMS интеграция** | workspace.dsl:11-13 | ❌ — не реализовано |
| **Full-text search indexes (Neo4j)** | ADR-005 | ❌ — не созданы в коде |

### Нарушение границ слоёв

1. **Бизнес-логика в эндпоинтах:** [`auth.py:60-75`](backend/app/api/v1/auth.py:60-75) — `get_current_user()` вызывает `verify_token()` и БД напрямую, смешивая аутентификацию с бизнес-логикой.

2. **Прямые вызовы services из api:** [`ingest.py:18-20`](backend/app/api/v1/ingest.py:18-20) — эндпоинты импортируют сервисы graphrag напрямую, минуя слой оркестрации:
   ```python
   from app.core.graphrag.document_ingestion import ingestion_service
   from app.core.graphrag.entity_extraction import entity_extraction_service
   ```

3. **Импорт Qdrant client в graph.py:** [`graph.py:15`](backend/app/api/v1/graph.py:15) — прямой импорт `qdrant_client` моделей в API-слое, что является нарушением Layer Separation.

4. **DatabaseService — God Object:** [`database.py`](backend/app/services/database.py) — отвечает за users, departments, sessions, messages, admin_settings, file_metadata — явное нарушение Single Responsibility Principle.

---

## D. Анализ маршрутизации API

### Полный реестр эндпоинтов (фактический)

| # | Метод | Путь | Файл | Статус в доке |
|---|-------|------|------|--------------|
| 1 | POST | `/api/v1/auth/register` | `auth.py:82` | ✅ |
| 2 | POST | `/api/v1/auth/login` | `auth.py:102` | ✅ |
| 3 | GET | `/api/v1/auth/me` | `auth.py:121` | ✅ |
| 4 | POST | `/api/v1/auth/sessions` | `auth.py:128` | ✅ |
| 5 | GET | `/api/v1/auth/sessions` | `auth.py:134` | ✅ |
| 6 | GET | `/api/v1/auth/users` | `auth.py:140` | ✅ |
| 7 | PUT | `/api/v1/auth/users/{user_id}` | `auth.py:153` | ✅ |
| 8 | DELETE | `/api/v1/auth/users/{user_id}` | `auth.py:170` | ✅ |
| 9 | POST | `/api/v1/auth/users/{user_id}/impersonate` | `auth.py:179` | ✅ |
| 10 | POST | `/api/v1/chat` | `chat.py:20` | ✅ |
| 11 | POST | `/api/v1/chat/stream` | `chat.py:65` | ✅ |
| 12 | GET | `/api/v1/chat/history` | `chat.py:102` | ✅ |
| 13 | DELETE | `/api/v1/chat/history` | `chat.py:116` | ✅ |
| 14 | GET | `/api/v1/ingest/status/{doc_id}` | `ingest.py:112` | ✅ |
| 15 | POST | `/api/v1/ingest` | `ingest.py:123` | ✅ |
| 16 | POST | `/api/v1/ingest/file` | `ingest.py:159` | ✅ |
| 17 | POST | `/api/v1/ingest/url` | `ingest.py:243` | ✅ |
| 18 | GET | `/api/v1/graph/visualize` | `graph.py:36` | ✅ |
| 19 | POST | `/api/v1/graph/search` | `graph.py:53` | ✅ |
| 20 | GET | `/api/v1/graph/entity/{entity_name}` | `graph.py:63` | ✅ |
| 21 | GET | `/api/v1/graph/stats` | `graph.py:73` | ✅ |
| 22 | DELETE | `/api/v1/graph/clear` | `graph.py:86` | ✅ |
| 23 | GET | `/api/v1/graph/documents` | `graph.py:116` | ✅ |
| 24 | GET | `/api/v1/graph/document/{doc_id}/content` | `graph.py:135` | ✅ |
| 25 | PUT | `/api/v1/graph/document/{doc_id}` | `graph.py:221` | ✅ |
| 26 | DELETE | `/api/v1/graph/document/{doc_id}` | `graph.py:254` | ✅ |
| 27 | GET | `/api/v1/departments/` | `departments.py:12` | ✅ |
| 28 | POST | `/api/v1/departments/` | `departments.py:18` | ✅ |
| 29 | PUT | `/api/v1/departments/{dep_id}` | `departments.py:32` | ✅ |
| 30 | DELETE | `/api/v1/departments/{dep_id}` | `departments.py:48` | ✅ |
| 31 | POST | `/api/v1/tests/run` | `tests.py:35` | ✅ |
| 32 | GET | `/api/v1/health` | `api.py:30` | ✅ |
| 33 | GET | `/api/v1/config/services` | `api.py:73` | ✅ |
| 34 | GET | `/metrics` | `main.py:162` | ✅ |
| 35 | GET | `/api/v1/admin/settings` | `admin.py:53` | ❓ Не в docs/README.md |
| 36 | PUT | `/api/v1/admin/settings/{setting_id}` | `admin.py:82` | ❓ |
| 37 | PUT | `/api/v1/admin/settings/category/{category}` | `admin.py:125` | ❓ |
| 38 | GET | `/api/v1/admin/settings/{category}` | `admin.py:267` | ❓ |
| 39 | POST | `/api/v1/admin/settings/reload` | `admin.py:200` | ❓ |
| 40 | GET | `/api/v1/admin/settings/history` | `admin.py:218` | ❓ |
| 41 | GET | `/api/v1/admin/_debug/registry` | `admin.py:180` | ❓ |
| 42 | GET | `/` | `main.py:246` | ❓ |

**Итого:** **42 эндпоинта** (из них 7 admin-эндпоинтов не описаны в main README, но описаны в [`plans/admin-architecture.md`](plans/admin-architecture.md)).

### Расхождения:

1. **Admin settings эндпоинты** (7 шт.) — не включены в основную документацию [`docs/README.md`](docs/README.md:116-164)
2. **`GET /api/v1/admin/_debug/registry`** — debug-эндпоинт, не предназначен для продакшена
3. **`GET /`** — корневой эндпоинт не описан в документации
4. **Эндпоинты сгруппированы** в README по группам, а в коде админские эндпоинты users (CRUD) находятся рядом с auth, а не отдельно

---

## E. Анализ зависимостей

### Сравнение заявленных и фактических зависимостей

| Категория | Заявлено в TECH_STACK.md | В pyproject.toml | Статус |
|-----------|-------------------------|------------------|--------|
| **Python** | ≥3.11 | ≥3.11 | ✅ |
| **FastAPI** | ≥0.115.0 | ≥0.115.0 | ✅ |
| **Uvicorn** | ≥0.30.0 | ≥0.30.0 | ✅ |
| **LangGraph** | ≥0.2.x | ≥0.2.0 | ✅ |
| **LangChain** | core≥0.3.0, community≥0.3.0 | core≥0.3.0, community≥0.3.0 | ✅ |
| **SQLModel** | ≥0.0.21 | ≥0.0.21 | ✅ |
| **Neo4j** | ≥5.20.0 | ≥5.20.0 | ✅ |
| **Qdrant** | ≥1.11.0 | ≥1.11.0 | ✅ |
| **Python-jose** | ≥3.3.0 | ≥3.3.0 | ✅ |
| **bcrypt** | ≥4.0.0 | ≥4.0.0 | ✅ |
| **boto3** | Не указан | ≥1.35.0 | ❓ Не документировано |
| **pymupdf** | Не указан | ≥1.24.0 | ❓ Не документировано |
| **python-docx** | Не указан | ≥1.1.0 | ❓ Не документировано |
| **nvidia-ml-py** | ≥12.0.0 | ≥12.0.0 | ✅ |
| **LangGraph Checkpoint PG** | Не указан | ≥2.0.0 | ❓ Не документировано |
| **Opentelemetry** | ≥1.20.0 | ≥1.25.0 (extras) | ✅ |
| **pytest** | ≥8.0 (in README) | ≥8.0.0 | ✅ |
| **ruff** | Не указан | ≥0.4.0 (dev) | ❓ Не документировано |

### Критические замечания

1. **boto3** (S3/MinIO) — ключевая зависимость, не указана в TECH_STACK.md
2. **pymupdf** (PDF парсинг) — не указан
3. **python-docx** (DOCX парсинг) — не указан
4. **langgraph-checkpoint-postgres** — не указан, но критичен для checkpointing
5. **structlog** — указана в TECH_STACK.md, но версия ≥24.0.0 не указана

---

## F. Общие замечания и риски

### 🔴 Критические расхождения

1. **HS256 вместо RS256** — JWT подписывается симметричным ключом, что снижает безопасность по сравнению с асимметричной подписью, указанной в security-architecture.mmd.
2. **Rate limiting не реализован** — настройки в [`config.py:63-65`](backend/app/core/config.py:63-65) есть, но middleware или зависимости отсутствуют.
3. **Отсутствие audit_logs таблицы** — ER-диаграмма показывает таблицу аудита, которая не реализована в моделях.

### 🟡 Средние расхождения

4. **ChatMessage — отдельная таблица** вместо JSONB в sessions, как показано в ER-диаграмме.
5. **30-day JWT expiry** вместо 1h/7d, указанных в security-architecture.mmd.
6. **Роль "auditor"** в коде [`rbac.py:21`](backend/app/core/security/rbac.py:21) не упомянута ни в одной документации.
7. **React в sequence diagram** — фронтенд реализован на Vanilla JS, а не React.
8. **ERP/CRM/EDMS интеграции** — показаны в C4 модели, но не реализованы.

### 🟢 Малые расхождения

9. **13 injection patterns** в коде против 16 заявленных в DEFENSE_PLAN.md.
10. **Коллекция Qdrant `graphrag_documents`** вместо двух (`documents` + `chunks`).
11. **Clearance levels** — в constants.py названия (Открытый/Конфиденциальный/Секретный/Сов. секретно) не совпадают с английскими названиями в документации (public/internal/confidential/secret).
12. **Guardrails config key** — в registry используется ключ `guardrails_enabled` (через подчёркивание), в то время как категория называется `guardrails`.

---

## G. Позитивные аспекты

1. **Документация в целом актуальна** — большая часть описанных компонентов действительно реализована.
2. **C4-моделирование** — workspace.dsl корректно отражает архитектуру на всех 4 уровнях.
3. **ADR** — 6 документов с детальным обоснованием технологических решений.
4. **Alembic миграции** — внедрены корректно, с seed-данными для admin_settings.
5. **SettingsRegistry** — реализован как описано в плане admin-architecture.md, с graceful fallback.
6. **Dynamic top_k** — в LangGraph агенте реализована адаптивная глубина поиска.
7. **Полное покрытие API** — все 35+ эндпоинтов реализованы и документированы.

---

## H. Рекомендации

| # | Описание | Приоритет | Тип |
|---|----------|-----------|-----|
| 1 | Реализовать Rate Limiter middleware (конфиг уже есть) | 🔴 High | Code |
| 2 | Обновить security-architecture.mmd: HS256, 30-day expiry, auditor role | 🔴 High | Docs |
| 3 | Удалить React из sequence-query-flow.mmd | 🟡 Medium | Docs |
| 4 | Удалить ERP/CRM/EDMS из C4 модели или пометить как "planned" | 🟡 Medium | Docs |
| 5 | Исправить ER-диаграмму: убрать audit_logs, rbac_policies, Concept | 🟡 Medium | Docs |
| 6 | Обновить TECH_STACK.md: добавить boto3, pymupdf, python-docx | 🟡 Medium | Docs |
| 7 | Добавить auditor роль в документацию RBAC | 🟢 Low | Docs |
| 8 | Обновить docs/README.md: добавить admin settings эндпоинты | 🟢 Low | Docs |
| 9 | Вынести `get_current_user` из auth.py в отдельный middleware | 🟡 Medium | Code |
| 10 | Рефакторинг DatabaseService — разделить на предметные сервисы | 🟡 Medium | Code |
| 11 | Убрать прямые импорты qdrant_client из graph.py | 🟢 Low | Code |
| 12 | Добавить тесты для admin API | 🟡 Medium | Test |
