# План обновления документации GraphRAG Platform

**Дата:** 2026-07-08
**Основание:** Архитектурный аудит (`plans/architecture-audit-report.md`)

---

## 1. [`docs/TECH_STACK.md`](docs/TECH_STACK.md)

### Добавить недостающие зависимости в блок Python-зависимости (строка ~143-215)
- `pymupdf>=1.24.0` — PDF parsing (есть в pyproject.toml:56, отсутствует в доке)
- `python-docx>=1.1.0` — DOCX parsing (есть в pyproject.toml:57, отсутствует в доке)
- `aiolimiter>=1.1.0` — **planned**: Rate Limiting middleware (будет реализован post-MVP)

### Уточнить версии (сверить с pyproject.toml)
| Пакет | TECH_STACK.md | pyproject.toml | Исправить на |
|-------|--------------|----------------|--------------|
| opentelemetry-api | >=1.20.0 | >=1.25.0 (otel extras) | >=1.25.0 |
| opentelemetry-sdk | >=1.20.0 | >=1.25.0 (otel extras) | >=1.25.0 |
| opentelemetry-exporter-otlp-proto-grpc | >=1.20.0 | >=1.25.0 (otel extras) | >=1.25.0 |
| pytest-asyncio | >=0.24 | >=0.23.0 | >=0.23.0 |

### React не упоминается — изменений не требуется

### Добавить секцию "Планируемые зависимости" с aiolimiter

---

## 2. [`docs/README.md`](docs/README.md)

### Добавить раздел с admin-эндпоинтами (7 шт., из audit отчёта строка 249-256)
```markdown
### Администрирование (настройки)
- `GET /api/v1/admin/settings` — Все настройки по категориям
- `PUT /api/v1/admin/settings/{setting_id}` — Обновление настройки
- `PUT /api/v1/admin/settings/category/{category}` — Обновление категории настроек
- `GET /api/v1/admin/settings/{category}` — Настройки категории
- `POST /api/v1/admin/settings/reload` — Перезагрузка настроек в кэш
- `GET /api/v1/admin/settings/history` — История изменений (пагинация)
```

### Исправить неточности
- В секции "Администрирование" (строка 153) эндпоинты users CRUD фактически находятся в auth.py, а не отдельно — можно оставить как есть, это нормально
- Уточнить описание эндпоинта `PUT /api/v1/graph/document/{doc_id}` — обновляет clearance_level/department

---

## 3. [`docs/architecture/README.md`](docs/architecture/README.md)

### Уточнить архитектурный паттерн
Добавить в начало строки о типе архитектуры:
> **Фактическая архитектура: гибридная Layered + Pipeline + State Machine**
> - Layered: Frontend → API → Agent → Services → Infrastructure
> - Pipeline: ingestion → extraction → graph → vectors
> - State Machine: LangGraph StateGraph (classify → off_topic → spelling → retrieve → generate → guardrails)

### Добавить информацию об аудите
```markdown
## Аудит архитектуры

По результатам аудита (июль 2026):
- [Архитектурный аудит](../plans/architecture-audit-report.md)
- [Патчи и исправления](../plans/patches.md)
```

### Указать DatabaseService как God Object
В секции про ER-диаграмму или в конце:
> **DatabaseService** (`backend/app/services/database.py`) отвечает за users, departments, sessions, messages, admin_settings, file_metadata — **God Object**, требует рефакторинга на предметные сервисы.

---

## 4. [`docs/architecture/er-diagram.mmd`](docs/architecture/er-diagram.mmd)

### Изменения в PostgreSQL секции:
1. **Удалить блок `audit_logs`** (строки 34-44) — таблица не существует в моделях
2. **Удалить блок `rbac_policies`** (строки 46-56) — RBAC реализован в коде, таблицы нет
3. **Удалить связи** с этими таблицами (строки 59-60)
4. **Добавить таблицу `chat_messages`** (отдельная таблица, не JSONB в sessions):
```mermaid
    chat_messages {
        uuid id PK "UUID v4"
        uuid session_id FK "Ссылка на sessions.id"
        varchar role "user | assistant | system"
        text content "Текст сообщения"
        timestamp created_at "Время создания"
    }
```
5. **Удалить блок `neo4j_Concept`** (строки 88-93) — не используется как label
6. **Удалить связи Concept** (строки 107-108)
7. **Уточнить Qdrant коллекцию** — `graphrag_documents` (единая, не две)

---

## 5. [`docs/architecture/security-architecture.mmd`](docs/architecture/security-architecture.mmd)

### Исправить JWT алгоритм
- Строка 25: `HS256` → `HS256 (текущий) / RS256 (planned — требуется миграция)`

### Исправить количество injection patterns
- Строка 53: уточнить что сейчас 13 паттернов

### Убрать/пометить нереализованные компоненты
- **Rate Limiting** (строка 39): добавить `⏳ Planned — not yet implemented`
- **Vault** (строка 26): добавить `⏳ Planned — secrets in .env currently`
- **IP Allowlist** (строка 41): добавить `⏳ Planned — not yet implemented`
- **Hallucination Check** (строка 90-91): добавить `⏳ Planned — not yet implemented`
- **Audit Logging** → SIEM (строка 92): добавить `⏳ Planned — not yet implemented`

### Исправить JWT Expiry
- Строка 25: `1h (access) / 7d (refresh)` → `30 days (access only, no refresh token)`

---

## 6. [`docs/architecture/sequence-query-flow.mmd`](docs/architecture/sequence-query-flow.mmd)

### Заменить "React" на "Vanilla JS"
- Строка 8: `participant FE as 🌐 Frontend<br/>(React)` → `participant FE as 🌐 Frontend<br/>(Vanilla JS)`

### Уточнить API Gateway
- Строка 9: `participant GW as 🔷 API Gateway<br/>(Kong/Nginx)` → `participant GW as 🔷 API Gateway<br/>(Nginx)`

### Пометить нереализованные отдельные компоненты
- Строка 11 Session Manager → `(встроен в auth модуль)`
- Строка 13 Planner → `(встроен в LangGraph agent)`
- audit_logs INSERT (строка 130) → убрать или пометить как planned

---

## 7. [`backend/README.md`](backend/README.md)

### Обновить структуру проекта
- Добавить `admin.py` в api/v1/ (строка 14)
- Добавить `models/admin.py` (строка ~39)
- Добавить `services/s3_service.py` (строка ~35)
- Добавить `core/settings_registry.py` (строка ~26)
- Добавить `seed_admin_settings.py`

### Обновить API Endpoints
- Добавить пропущенные эндпоинты из graph.py (document CRUD: строки 109-113 в docs/README.md уже есть, но в backend/README.md их нет)
- Добавить admin settings эндпоинты
- Добавить `/ingest/url`, `/ingest/status/{doc_id}`
- Добавить `/chat/history` GET/DELETE
- Добавить `/departments/` CRUD
- Добавить `/tests/run`
- Добавить `/config/services`

### Обновить RBAC
- Добавить роль `auditor` (строка 123)

---

## 8. [`plans/admin-architecture.md`](plans/admin-architecture.md)

### Добавить примечание о результатах аудита
В начало файла, после строки с заголовком, добавить:

```markdown
> **Результаты аудита (2026-07-08):**
> - ✅ Admin API полностью реализована — 7 эндпоинтов в `backend/app/api/v1/admin.py`
> - ✅ SettingsRegistry singleton реализован в `backend/app/core/settings_registry.py`
> - ✅ Миграция `002_admin_settings.py` применена, таблицы созданы
> - ✅ Seed-данные загружаются через `backend/app/seed_admin_settings.py`
> - ⚠️ Найден мёртвый код в `admin.py:237` (`get_user_by_id(audit.setting_id)` вместо AdminSetting) — исправлен в патчах
> - ⚠️ Frontend админка полностью реализована в `frontend/js/app.js` (строки 1766-2000)
> - ℹ️ Рекомендуется добавить тесты для admin API
```

---

## Порядок выполнения

1. [`docs/architecture/sequence-query-flow.mmd`](docs/architecture/sequence-query-flow.mmd) — самые простые изменения
2. [`docs/architecture/security-architecture.mmd`](docs/architecture/security-architecture.mmd) — средняя сложность
3. [`docs/architecture/er-diagram.mmd`](docs/architecture/er-diagram.mmd) — средняя сложность  
4. [`docs/architecture/README.md`](docs/architecture/README.md) — простые добавления
5. [`docs/TECH_STACK.md`](docs/TECH_STACK.md) — добавление зависимостей
6. [`docs/README.md`](docs/README.md) — добавление admin эндпоинтов
7. [`backend/README.md`](backend/README.md) — комплексное обновление
8. [`plans/admin-architecture.md`](plans/admin-architecture.md) — добавление примечания

**Важно:** Все изменения — только документация. Никаких изменений исходного кода.
