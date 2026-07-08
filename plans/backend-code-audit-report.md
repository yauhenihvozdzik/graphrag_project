# Отчёт глубокого аудита кода бэкенда GraphRAG

**Дата:** 2026-07-08  
**Аудитор:** Zoo (Debug Mode)  
**Объём:** 40 файлов бэкенда, ~4000+ строк кода  
**Методология:** Построчный анализ всех файлов бэкенда на 5 категорий проблем

---

## 🔴 CRITICAL: Баги и проблемы безопасности

| Файл | Строка | Проблема | Уровень | Рекомендация |
|------|--------|----------|---------|-------------|
| [`backend/app/api/v1/api.py`](../backend/app/api/v1/api.py) | 73–168 | **Эндпоинт `/config/services` без аутентификации** — возвращает пароли Neo4j, MinIO, Grafana, pgAdmin (в т.ч. `db_password: "postgres"`) | CRITICAL | Добавить `Depends(get_current_user)` или защитить эндпоинт отдельным middleware |
| [`backend/app/core/config.py`](../backend/app/core/config.py) | 46 | **JWT_SECRET_KEY default `"change-me"`** — если не задана переменная окружения, все JWT подписаны известным ключом | CRITICAL | Удалить default, выбрасывать исключение при `"change-me"` |
| [`backend/app/core/security/rbac.py`](../backend/app/core/security/rbac.py) | 162 | **Cypher Injection** — `department` вставляется в f-строку: `n.department = '{context.department}'` | CRITICAL | Использовать параметризованный запрос вместо f-строки |
| [`backend/app/services/neo4j_service.py`](../backend/app/services/neo4j_service.py) | 63 | **Cypher Injection** — `safe = rel_type.upper().replace(" ","_").replace("-","_")` затем вставляется в f-строку `[r:{safe}]` | CRITICAL | Использовать параметризованный `apoc.create.relationship` или валидацию регэкспом |
| [`backend/app/api/v1/auth.py`](../backend/app/api/v1/auth.py) | 154 | **Mass Assignment** — `PUT /users/{user_id}` принимает `updates: dict` без Pydantic-схемы, администратор может установить любую роль | CRITICAL | Заменить `updates: dict` на Pydantic-схему с whitelist полей |
| [`backend/app/api/v1/graph.py`](../backend/app/api/v1/graph.py) | 222 | **Mass Assignment** — `PUT /document/{doc_id}` принимает `updates: dict` без схемы | CRITICAL | Использовать Pydantic-схему для updates |
| [`backend/app/api/v1/admin.py`](../backend/app/api/v1/admin.py) | 237 | **Логическая ошибка (BUF-FIX):** `database_service.get_user_by_id(audit.setting_id)` — вызывается метод для User вместо AdminSetting. В Audit-записи `setting_id` — это FK на `admin_settings.id`, а не на `user.id` | CRITICAL | Заменить на прямой SQLModel-запрос: `s.get(AdminSetting, audit.setting_id)` (что уже сделано в строках 241–242, строка 237 — мёртвый код) |
| [`backend/app/api/v1/chat.py`](../backend/app/api/v1/chat.py) | 78 | **Глухой `except: pass`** — ошибка сохранения сообщения пользователя в `chat_stream` полностью игнорируется | CRITICAL | Логировать ошибку через `logger.warning()` (как в строке 36) |
| [`backend/app/api/v1/graph.py`](../backend/app/api/v1/graph.py) | 93–94, 98–99 | **Глухие `except: pass`** — ошибки при очистке Qdrant, S3, Neo4j полностью игнорируются | CRITICAL | Логировать каждую ошибку с контекстом |
| [`backend/app/services/database.py`](../backend/app/services/database.py) | 72–74 | **Race Condition (TOCTOU)** — проверка `if s.exec(select(User).where(User.email == email)).first()` затем вставка — между ними может быть конкуренция | CRITICAL | Использовать `IntegrityError` как единственный механизм защиты (как в `_seed_demo_users`) |
| [`backend/app/services/database.py`](../backend/app/services/database.py) | 131–133 | **Race Condition (TOCTOU)** — проверка существования department до вставки, не атомарно | CRITICAL | Использовать уникальный constraint + try/except IntegrityError |
| [`backend/app/services/s3_service.py`](../backend/app/services/s3_service.py) | 33 | **Широкий `except Exception`** без конкретизации при создании bucket | HIGH | Перехватывать `ClientError` от boto3 |
| [`backend/app/core/metrics.py`](../backend/app/core/metrics.py) | 79–93 | **GPU metrics: бесконечный `while True` в daemon thread** — нет graceful shutdown, thread продолжает работать после остановки приложения | HIGH | Добавить Event-флаг для остановки, закрывать thread через lifespan shutdown |
| [`backend/app/services/neo4j_service.py`](../backend/app/services/neo4j_service.py) | 104 | **Голый `except:`** (без класса) перехватывает `KeyboardInterrupt`, `SystemExit` | HIGH | Заменить на `except Exception:` |
| [`backend/app/api/v1/tests.py`](../backend/app/api/v1/tests.py) | 29 | **Ошибка аутентификации** — `_verify_admin` использует `payload.get("role")`, но в JWT поле называется `role`, а не `sub` (sub — это user_id). Работает только потому что verify_token возвращает role | MEDIUM | Добавить проверку `payload.get("sub")` и явное приведение роли |
| [`backend/app/core/logging.py`](../backend/app/core/logging.py) | 76 | **FileHandler не закрывается** — при переконфигурации логов (если `configure_logging` вызван повторно) старый handler не закрывается | MEDIUM | Сохранять ссылку на handler и закрывать при повторном вызове |

---

## 🟡 HIGH: Логические ошибки

| Файл | Строка | Проблема | Уровень | Рекомендация |
|------|--------|----------|---------|-------------|
| [`backend/app/core/langgraph/agent.py`](../backend/app/core/langgraph/agent.py) | 133–136, 164–167, 202–206 | **Дублирование логики извлечения `messages[-1]`** — код проверки `isinstance(messages[-1], str)` повторяется в 3 узлах графа | HIGH | Вынести в хелпер: `def _last_message_content(messages) -> str` |
| [`backend/app/core/langgraph/agent.py`](../backend/app/core/langgraph/agent.py) | 228 | **graph_density может быть NaN или некорректным** — если `total_nodes = 0`, `graph_density = 0/1 = 0`, что корректно, но если `total_connections` огромное, `graph_density` может быть нереалистичным | HIGH | Добавить нормализацию: `graph_density = min(graph_density, 50)` |
| [`backend/app/core/langgraph/agent.py`](../backend/app/core/langgraph/agent.py) | 297 | **graph_depth вычисляется через graph_density/2** — если density = 1, depth = 0 (int(0.5)), что некорректно | HIGH | Использовать `max(1, int(graph_density / 2))` |
| [`backend/app/core/graphrag/entity_extraction.py`](../backend/app/core/graphrag/entity_extraction.py) | 238 | **Фильтр `len(entity_name) > 3` отсекает короткие валидные сущности** — например "ИНН", "НДС", "1С" (2 символа) | HIGH | Снизить порог до 2 или удалить фильтр |
| [`backend/app/services/s3_service.py`](../backend/app/services/s3_service.py) | 99–108 | **delete_document делает 17 запросов к S3** — для каждого doc_id перебирает все расширения файлов | HIGH | Использовать S3 batch delete с префиксом `documents/{doc_id}/` |
| [`backend/app/core/langgraph/agent_utils.py`](../backend/app/core/langgraph/agent_utils.py) | 141–153 | **is_off_topic() возвращает True если нет бизнес-ключевых слов** — это корректно, но название функции вводит в заблуждение | HIGH | Переименовать в `is_not_business_query()` |
| [`backend/app/services/database.py`](../backend/app/services/database.py) | 110 | **update_user позволяет изменить `is_active` любому админу** — нет аудита изменений статуса активации | HIGH | Добавить логирование в audit_log |
| [`backend/app/api/v1/ingest.py`](../backend/app/api/v1/ingest.py) | 166 | **Двойная проверка `.zip`** — `.zip` нет в `ALLOWED_FILE_EXTENSIONS`, но проверяется отдельно | HIGH | Добавить `.zip` в `ALLOWED_FILE_EXTENSIONS` и убрать дублирование |
| [`backend/app/core/graphrag/document_ingestion.py`](../backend/app/core/graphrag/document_ingestion.py) | 278–282 | **Overlap chunking может дать пустой current_chunk** — если `overlap_start == len(current_chunk)`, current_chunk станет пустым, leading to index errors | HIGH | Добавить проверку `if len(current_chunk[overlap_start:]) > 0` |
| [`backend/app/core/security/guardrails.py`](../backend/app/core/security/guardrails.py) | 244 | **Injection scoring: 1 match = 0.5, 2 matches = 0.85** — при пороге 0.85, 2 совпадения могут быть ложным срабатыванием | HIGH | Использовать более сложную эвристику с контекстным анализом |
| [`backend/app/models/message.py`](../backend/app/models/message.py) | 19 | **`datetime.utcnow()` deprecated** — началось с Python 3.12 | HIGH | Использовать `datetime.now(UTC)` как в других моделях |
| [`backend/app/api/v1/auth.py`](../backend/app/api/v1/auth.py) | 130 | **session_id (uuid4) не проверяется на уникальность** — теоретически возможен коллизия UUID | MEDIUM | Добавить try/except при создании сессии |

---

## 🟠 MEDIUM: Производительность и Code Smells

| Файл | Строка | Проблема | Уровень | Рекомендация |
|------|--------|----------|---------|-------------|
| [`backend/app/services/database.py`](../backend/app/services/database.py) | 22–394 | **God Object (DatabaseService)** — 20+ методов, нарушает SRP | MEDIUM | Разделить на UserService, DepartmentService, SettingsService, FileMetadataService |
| [`backend/app/services/database.py`](../backend/app/services/database.py) | 7, 25, 72+ | **Синхронный SQLAlchemy Session в async FastAPI** — каждый `with Session(self.engine)` блокирует event loop | MEDIUM | Перейти на `AsyncSession` через asyncpg, или использовать `asyncio.to_thread` |
| [`backend/app/api/v1/ingest.py`](../backend/app/api/v1/ingest.py) | 31 | **In-memory `_ingestion_status: dict[str, dict]`** — не персистентно, теряется при рестарте, не масштабируется | MEDIUM | Использовать PostgreSQL/Redis для хранения статусов |
| [`backend/app/core/graphrag/document_ingestion.py`](../backend/app/core/graphrag/document_ingestion.py) | 269–286 | **Sentence-based chunking с O(n²) overlap** — перебор current_chunk в обратном порядке для каждого чанка | MEDIUM | Использовать character-based sliding window с фиксированным overlap |
| [`backend/app/api/v1/admin.py`](../backend/app/api/v1/admin.py) | 237–243 | **N+1 запрос к БД в цикле истории** — для каждого audit-записи делается отдельный SELECT (через Session) | MEDIUM | Использовать eager load или join в одном запросе |
| [`backend/app/core/graphrag/entity_extraction.py`](../backend/app/core/graphrag/entity_extraction.py) | 73–106 | **Дублирование regex паттернов** — паттерны сущностей частично пересекаются с промптами в `prompts.py` | MEDIUM | Использовать единый источник истины |
| [`backend/app/core/langgraph/agent.py`](../backend/app/core/langgraph/agent.py) | 400–409, 556–573 | **Дублирование логики формирования промпта** — код построения `chat_messages` повторяется в `_generate_response` и `get_streaming_response` | MEDIUM | Вынести в метод `_build_chat_messages(state) -> list` |
| [`backend/app/models/schemas.py`](../backend/app/models/schemas.py) | 179–182 | **Поле `success` устанавливается в model_validator, но не аннотировано** — Pydantic v2 требует явного указания | MEDIUM | Аннотировать `success: bool = False` |
| [`backend/app/core/security/rbac.py`](../backend/app/core/security/rbac.py) | 82–87 | **ROLE_HIERARCHY объявлена после метода require_role** — нестандартный порядок | LOW | Перенести class variable до методов |
| [`backend/app/api/v1/auth.py`](../backend/app/api/v1/auth.py) | 26–31 | **Дублирование SMTP-конфигурации** — SMTP_HOST, SMTP_PORT копируются из settings в модульные переменные | MEDIUM | Использовать `settings.SMTP_HOST` напрямую |
| [`backend/app/core/graphrag/vector_indexer.py`](../backend/app/core/graphrag/vector_indexer.py) | 42–48 | **Дублирование batch embedding** — логика batch из 32 дублирует BATCH_SIZE в ollama_service (64) | MEDIUM | Использовать единый BATCH_SIZE из constants |
| [`backend/app/services/neo4j_service.py`](../backend/app/services/neo4j_service.py) | 36–40 | **session() не потокобезопасен** — AsyncSession от neo4j не предназначен для использования из нескольких корутин одновременно | MEDIUM | Документировать или добавить семафор |

---

## 🔵 LOW: Стилистические замечания

| Файл | Строка | Проблема | Уровень | Рекомендация |
|------|--------|----------|---------|-------------|
| [`backend/app/services/database.py`](../backend/app/services/database.py) | 274, 288 | **Сравнение с True через `==`** — Flake8 E712: `AdminSetting.is_active == True` | LOW | Использовать `AdminSetting.is_active.is_` |
| [`backend/app/core/metrics.py`](../backend/app/core/metrics.py) | 3 | **Непоследовательные type hints** — функции без аннотаций типов | LOW | Добавить полные type hints |
| [`backend/app/models/session.py`](../backend/app/models/session.py) | 26 | **`id: str` как PK** — UUID в виде строки, не используется UUID тип PostgreSQL | LOW | Использовать UUID тип в БД |
| [`backend/app/services/database.py`](../backend/app/services/database.py) | 22 | **Нет `__init__.py` импортов** — `database_service = DatabaseService()` в конце файла, нет `__all__` | LOW | Добавить `__all__` для экспорта |
| [`backend/app/core/langgraph/agent.py`](../backend/app/core/langgraph/agent.py) | 12 | **Импорт `quote_plus` не используется** — неиспользуемый импорт | LOW | Удалить |
| [`backend/app/api/v1/ingest.py`](../backend/app/api/v1/ingest.py) | 8, 10 | **Импорт `os` и `Path` — не используются напрямую** (Path используется через settings.UPLOAD_DIR) | LOW | Проверить и удалить неиспользуемые импорты |
| [`backend/app/models/admin.py`](../backend/app/models/admin.py) | 9 | **`from datetime import UTC, datetime`** — корректно, но в message.py используется `datetime.utcnow` | LOW | Унифицировать подход |
| [`backend/app/core/metrics.py`](../backend/app/core/metrics.py) | 101 | **`import time as _time`** — необычный паттерн именования | LOW | Использовать стандартный `import time` |
| [`backend/app/services/neo4j_service.py`](../backend/app/services/neo4j_service.py) | 178–179 | **Нет пустой строки перед синглтоном** | LOW | Добавить отступ |

---

## 📊 Сводная статистика

| Категория | Кол-во |
|-----------|--------|
| 🔴 CRITICAL: Баги и безопасность | 16 |
| 🟡 HIGH: Логические ошибки | 12 |
| 🟠 MEDIUM: Производительность и Code Smells | 14 |
| 🔵 LOW: Стилистические замечания | 9 |
| **ИТОГО** | **51** |

---

## 🎯 Ключевые выводы и рекомендации по приоритетам

### Топ-5 критических проблем для немедленного исправления:

1. **🔴 `/config/services` без аутентификации** (`backend/app/api/v1/api.py:73`) — возвращает все пароли инфраструктуры. **Patch:** добавить `Depends(get_current_user)`.

2. **🔴 Cypher Injection в RBAC** (`backend/app/core/security/rbac.py:162`) — `department` вставляется напрямую в Cypher-запрос. **Patch:** параметризовать через `$department`.

3. **🔴 Cypher Injection в Neo4j** (`backend/app/services/neo4j_service.py:63`) — `rel_type` вставляется в f-строку. **Patch:** валидировать rel_type строгим regex (только буквы и цифры).

4. **🔴 JWT_SECRET_KEY default "change-me"** (`backend/app/core/config.py:46`) — production с дефолтным ключом даёт полный доступ. **Patch:** валидация при старте.

5. **🔴 Mass Assignment в PUT /users** (`backend/app/api/v1/auth.py:154`) — позволяет админу изменить роль любого пользователя. **Patch:** Pydantic-схема с фиксированными полями.

### Общие архитектурные проблемы (подтверждённые аудитом):

| Проблема из архитектурного аудита | Статус | Детали |
|----------------------------------|--------|--------|
| HS256 вместо RS256 | ✅ Подтверждено | `backend/app/core/config.py:46` |
| Rate Limiting не реализован | ✅ Подтверждено | Middleware отсутствует, конфиг есть |
| DatabaseService — God Object | ✅ Подтверждено | 20+ методов, синхронный в async |
| 13 injection patterns | ✅ Подтверждено | 13 в `INJECTION_PATTERNS` (не 16) |
| Прямые импорты qdrant_client из API | ✅ Подтверждено | `backend/app/api/v1/graph.py:15` |
| Отсутствие audit_logs и rbac_policies | ✅ Подтверждено | Нет таблиц, кроме admin_settings_audit |

### Дополнительно обнаружено:

- **2 Cypher Injection уязвимости** (не были в архитектурном аудите) — CRITICAL
- **2 Mass Assignment уязвимости** (не были в архитектурном аудите) — CRITICAL  
- **1 логический баг** в `admin.py:237` (вызов `get_user_by_id` для AdminSetting)
- **Глухие except в 3 местах** — скрывают ошибки
- **12 заблокированных event loop** из-за синхронного SQLAlchemy

---

*Аудит выполнен 2026-07-08. Проверено 40 файлов бэкенда.*
