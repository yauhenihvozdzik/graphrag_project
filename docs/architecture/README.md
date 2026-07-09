# Архитектура GraphRAG Platform

Полная архитектурная документация платформы GraphRAG для корпоративного анализа знаний.

> **Архитектурный стиль: гибридная Layered + Pipeline + State Machine**
> - **Layered**: Frontend (Vanilla JS) → API (FastAPI) → Agent (LangGraph) → Services (Neo4j, Qdrant, Ollama, PostgreSQL, MinIO) → Infrastructure (Prometheus, Grafana, Jaeger)
> - **Pipeline (GraphRAG)**: ingestion → extraction → graph → vectors
> - **State Machine (LangGraph)**: classify → off_topic → spelling → retrieve → generate → guardrails

## Содержание

| Файл | Описание |
|------|----------|
| `workspace.dsl` | C4-диаграмма (Structurizr DSL): System Context, Containers, Components, Deployment |
| `data-flow-pipeline.mmd` | Диаграмма потока данных при загрузке документа (Mermaid) |
| `er-diagram.mmd` | ER-диаграмма базы данных PostgreSQL (Mermaid) |
| `sequence-query-flow.mmd` | Sequence-диаграмма обработки запроса (Mermaid) |
| `security-architecture.mmd` | Архитектура безопасности (Mermaid) |

## C4 диаграмма (`workspace.dsl`)

- **Level 1 (System Context):** Границы системы, внешние акторы (admin/analyst/viewer/auditor), интеграция с ERP/CRM/СЭД
- **Level 2 (Containers):** 13 Docker Compose контейнеров — Frontend (Vanilla JS SPA на nginx), Backend (FastAPI + LangGraph), Ollama, Qdrant, Neo4j, PostgreSQL, MinIO, Observability (Prometheus/Grafana/Jaeger), pgAdmin, Open WebUI, Ollama-init, Mailpit
- **Level 3 (Components):** Внутренности Backend — RBAC Filter, Input/Output Guardrails, GraphRAG Agent, Ingestion Pipeline
- **Deployment:** On-Premise развёртывание на Windows 11 PC с Docker Compose, сетевая сегментация DMZ/Internal

## Поток данных (`data-flow-pipeline.mmd`)

Описывает процесс загрузки документа:
1. Загрузка файла через веб-интерфейс
2. Сохранение в MinIO S3
3. Извлечение текста, чанкинг
4. Извлечение универсальных сущностей (regex)
5. Построение графа знаний (Neo4j)
6. Генерация векторных представлений (bge-m3 через Ollama)
7. Индексация в Qdrant с RBAC-метаданными

## ER-диаграмма (`er-diagram.mmd`)

Таблицы PostgreSQL:
- `user` — пользователи (email, роль, отдел, clearance_level, is_active)
- `chat_session` — сессии чата
- `chat_message` — история сообщений
- `department` — справочник отделов
- `file_metadata` — метаданные загруженных файлов (дедупликация по SHA-256)
- `admin_setting` — настройки платформы (SettingsRegistry)
- `rbac_policy` — RBAC-политики доступа
- `audit_log` — журнал аудита действий пользователей

## Sequence-диаграмма (`sequence-query-flow.mmd`)

Обработка запроса в чате:
1. Пользователь отправляет сообщение
2. Rate limiting (token-bucket, aiolimiter)
3. Проверка входных guardrails (PII-детекция, prompt injection, лимит длины)
4. Аутентификация JWT (RS256) + RBAC-фильтрация
5. LangGraph Agent (State Machine):
   - `classify_query` — классификация запроса
   - `check_off_topic` — проверка релевантности
   - `correct_spelling` — исправление опечаток
   - `retrieve_context` — гибридный поиск (векторный Qdrant + графовый Neo4j)
   - `generate_response` — генерация ответа (LLM через Ollama)
   - `apply_guardrails` — фильтрация вывода (PII-masking)
6. Ответ пользователю со списком источников

## Архитектура безопасности (`security-architecture.mmd`)

### Аутентификация
- **JWT**: RS256 (RSA-ключи), access-токены с настраиваемым сроком действия (по умолчанию 30 дней)
- **Пароли**: bcrypt-хеширование
- **Деактивация**: администратор может заблокировать аккаунт (is_active=false)

### Авторизация (RBAC)
- **Роли**: admin (100), auditor (50), analyst (30), viewer (10) — иерархические
- **Clearance Level**: 0 (PUBLIC), 1 (INTERNAL), 2 (CONFIDENTIAL), 3 (SECRET)
- **Отделы**: all, legal, research, management, compliance, hr, finance, it
- **Фильтрация**: на уровне Cypher-запросов (Neo4j) и payload-фильтров (Qdrant)
- **Имперсонация**: администратор может войти под любым пользователем (с записью в audit_log)
- **RBAC-политики**: хранятся в PostgreSQL, позволяют гибко настраивать права доступа к узлам графа

### Входные Guardrails
- **PII-детекция**: двухуровневая (канонические паттерны + нормализация whitespace для защиты от evasion)
- **Типы PII**: ИНН (физ./юр. лица), СНИЛС, паспорт РФ, телефон, email, банковский счёт, номер карты
- **Prompt Injection Detection**: 21 паттерн (английский + русский), включая SSTI, LDAP, NoSQL инъекции
- **Лимит длины**: настраиваемый (по умолчанию 10 000 символов)
- **Динамическая конфигурация**: все параметры guardrails загружаются из SettingsRegistry и могут меняться без перезапуска

### Выходные Guardrails
- **PII-masking**: фильтрация утечек ПДн в ответах LLM
- **Санитизация**: XSS/SQL-injection фильтрация

### Сетевая безопасность
- **DMZ/Internal сегментация**: frontend, backend и Grafana в DMZ (172.24.0.0/24); БД, Ollama, observability в Internal (172.25.0.0/24)
- **CORS**: ограниченный список разрешённых источников (ALLOWED_ORIGINS в `.env`)
- **Security Headers**: X-Content-Type-Options, X-Frame-Options, X-XSS-Protection, HSTS, Cache-Control, Referrer-Policy

### Аудит
- **Audit Log**: запись всех критических действий в PostgreSQL (`audit_logs`)
- **События**: вход в систему, имперсонация, изменение пользователей, удаление документов
- **Атрибуты**: user_id, action, entity_type, entity_id, details (JSON), ip_address, created_at

### Хранение секретов
- **Пароли**: вынесены в переменные окружения (`backend/.env`), не хранятся в коде
- **Шаблон**: `backend/.env.example` содержит структуру без реальных секретов
- **JWT-ключи**: RSA-ключи генерируются отдельно, не включены в репозиторий
- **API `/config/services`**: возвращает только несекретную конфигурацию (без паролей)
