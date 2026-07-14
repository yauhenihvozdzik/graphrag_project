# Документация архитектуры GraphRAG Platform

Архитектурные артефакты проекта для защиты дипломной работы.

## Содержание

| Файл | Описание |
|------|----------|
| `workspace.dsl` | C4-диаграмма (Structurizr DSL): System Context, Containers, Components, Deployment |
| `data-flow-pipeline.mmd` | Диаграмма потока данных при загрузке документа (Mermaid) |
| `er-diagram.mmd` | ER-диаграмма базы данных PostgreSQL (Mermaid) |
| `sequence-query-flow.mmd` | Sequence-диаграмма обработки запроса (Mermaid) |
| `security-architecture.mmd` | Архитектура безопасности (Mermaid) |

## C4 диаграмма (`workspace.dsl`)

- **Level 1 (System Context):** Границы системы, внешние акторы (admin/analyst/viewer), интеграция с ERP/CRM/СЭД
- **Level 2 (Containers):** Docker Compose контейнеры — Frontend (Vanilla JS SPA на nginx), Backend (FastAPI + LangGraph), Ollama, Qdrant, Neo4j, PostgreSQL, MinIO, Observability (Prometheus/Grafana/Jaeger)
- **Level 3 (Components):** Внутренности Backend — RBAC Filter, Input/Output Guardrails, GraphRAG Agent, Ingestion Pipeline
- **Deployment:** One-Premise развёртывание на Windows 11 PC с Docker Compose, сетевая сегментация DMZ/Internal

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
- `users` — пользователи (email, роль, отдел, clearance_level)
- `chat_sessions` — сессии чата
- `chat_messages` — история сообщений
- `departments` — справочник отделов
- `file_metadata` — метаданные загруженных файлов (дедупликация)

## Sequence-диаграмма (`sequence-query-flow.mmd`)

Обработка запроса в чате:
1. Пользователь отправляет сообщение
2. Проверка guardrails (PII, injection)
3. Аутентификация JWT + RBAC-фильтрация
4. LangGraph Agent:
   - `classify_query` — классификация запроса
   - `correct_spelling` — исправление опечаток
   - `retrieve_context` — гибридный поиск (Qdrant + Neo4j)
   - `generate_response` — генерация ответа (qwen2.5:7b)
   - `apply_guardrails` — фильтрация вывода
5. Ответ пользователю со списком источников

## Архитектура безопасности (`security-architecture.mmd`)

- **Аутентификация:** JWT (access tokens, 30 дней)
- **Авторизация:** RBAC с тремя ролями (admin/analyst/viewer), clearance_level (0-3), department
- **Входные guardrails:** PII-детекция, prompt injection detection, лимит длины
- **Выходные guardrails:** PII-masking (телефоны, email, ИНН)
- **Сетевая безопасность:** DMZ/Internal сегментация, HTTPS
- **Хранение:** пароли bcrypt, документы в S3 с контролем доступа