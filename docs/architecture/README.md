# 📐 Архитектурная документация — GraphRAG Platform

> Защищённая платформа интеллектуального поиска и генерации ответов по корпоративным документам (On-Premise / Air-Gapped)

---

## 📁 Содержание пакета

| Файл | Формат | Описание |
|---|---|---|
| `workspace.dsl` | Structurizr DSL | C4 Model (Level 1–3) + Deployment Diagram |
| `sequence-query-flow.mmd` | Mermaid Sequence | Детальный флоу обработки запроса |
| `er-diagram.mmd` | Mermaid ER | Модель данных (PostgreSQL + Neo4j + Qdrant) |
| `data-flow-pipeline.mmd` | Mermaid Flowchart | Data Flow: Ingestion → Extraction → Graph Building → Retrieval |
| `security-architecture.mmd` | Mermaid Flowchart | Security: RBAC + Guardrails + Network Segmentation |

---

## 🏗️ Диаграммы C4 Model (`workspace.dsl`)

### Level 1 — System Context
**Что показывает:** Интеграция GraphRAG платформы в корпоративный ландшафт.

- **Пользователи:** Руководитель, Аналитик, Гость (с разными правами доступа)
- **Внешние системы:** ERP (1С/SAP), CRM, EDMS/СЭД
- **Каналы:** Web UI (React SPA)

### Level 2 — Container
**Что показывает:** Микросервисная архитектура платформы.

| Контейнер | Технология | Назначение |
|---|---|---|
| Frontend | React + TypeScript | SPA: чат, история, администрирование |
| API Gateway | Kong / Nginx | Маршрутизация, TLS, rate limiting, JWT |
| Backend Service | FastAPI + LangGraph | Бизнес-логика, оркестрация агента |
| LLM Serving | Ollama | T-lite-it-1.0 (7B) + bge-m3 на GPU |
| Vector Database | Qdrant | Векторный поиск с RBAC-фильтрацией |
| Graph Database | Neo4j Community | Граф знаний: сущности, связи, документы |
| PostgreSQL | PostgreSQL 16 | Users, sessions, audit, RBAC policies |
| Vault | HashiCorp Vault | Управление секретами |
| Prometheus | Prometheus | Сбор метрик |
| Grafana | Grafana | Дашборды и алерты |
| Jaeger | Jaeger | Распределённая трассировка |

### Level 3 — Component (Backend Service)
**Что показывает:** Внутреннее устройство Backend Service.

- **Session Manager** — управление сессиями и контекстом диалога
- **RBAC Filter** — проверка ролей, фильтрация по security_level и department
- **Input Guardrails** — обнаружение PII, prompt injection, валидация
- **Output Guardrails** — фильтрация утечек, проверка галлюцинаций, citations
- **Planner (Agent)** — LangGraph state machine для управления agent loop
- **Memory Module** — единый интерфейс к Neo4j + Qdrant + PostgreSQL
- **Tools Interface** — инструменты агента: retrieval, extraction, reranking
- **Ingestion Pipeline** — парсинг → чанкинг → экстракция → индексация

### Deployment Diagram
**Что показывает:** Физическое размещение на Windows 11 PC.

- **Хост:** Ryzen 9 3900X, RTX 4060 (8 GB VRAM), 64 GB RAM, 2 TB NVMe
- **Оркестратор:** Docker Compose (через WSL2 + Docker Desktop)
- **GPU:** Выделен для Ollama (LLM inference + embeddings)
- **Сетевая сегментация:**
  - **DMZ (172.20.0.0/24):** Frontend, API Gateway
  - **Internal (172.21.0.0/24):** Backend, все БД, Vault, Observability

---

## 🔄 Sequence Diagram (`sequence-query-flow.mmd`)

Детальный флоу обработки сложного запроса пользователя через все компоненты системы:

1. **Фаза 1:** Аутентификация — JWT валидация, загрузка сессии
2. **Фаза 2:** Guardrails — PII detection, prompt injection, RBAC проверка
3. **Фаза 3:** Agent Loop — Query Analysis → GraphRAG Retrieval (Vector + Graph) → Reranking → LLM Generation → Tool Execution (при необходимости)
4. **Фаза 4:** Output Guardrails — фильтрация утечек, citations, audit logging

---

## 📊 ER Diagram (`er-diagram.mmd`)

### PostgreSQL (реляционная модель)
- `users` — пользователи с ролями и уровнями доступа
- `sessions` — история диалогов (JSONB messages)
- `audit_logs` — журнал всех действий (query, login, security events)
- `rbac_policies` — конфигурация прав по ролям

### Neo4j (граф знаний)
- **Nodes:** Document, Entity, Concept, Chunk
- **Relationships:** CONTAINS, MENTIONS, RELATED_TO, BELONGS_TO, PARENT_OF
- **RBAC-атрибуты:** security_level, department, access_roles на каждом узле

### Qdrant (векторные коллекции)
- `documents` — embeddings чанков (bge-m3, 1024 dims) + RBAC payload
- `entities` — embeddings сущностей для entity-centric search

---

## 🔀 Data Flow Pipeline (`data-flow-pipeline.mmd`)

Четыре фазы GraphRAG pipeline:

| Фаза | Описание | Ключевые операции |
|---|---|---|
| **Ingestion** | Загрузка документов | Парсинг (PDF/DOCX/XML), семантический чанкинг, обогащение метаданными |
| **Extraction** | Извлечение знаний | NER, Relation Extraction, Concept Detection, Embedding Generation |
| **Graph Building** | Построение графа | Дедупликация, Neo4j MERGE, Qdrant Upsert, Leiden communities |
| **Retrieval** | Поиск и генерация | Vector Search + Graph Traversal → Fusion → Reranking → LLM Generation |

---

## 🔒 Security Architecture (`security-architecture.mmd`)

Многоуровневая модель безопасности:

1. **Authentication** — JWT (RS256), Vault для signing keys
2. **API Gateway** — TLS 1.3, rate limiting по ролям, IP allowlist
3. **Input Guardrails** — PII detection (ИНН, СНИЛС, паспорт), prompt injection defense
4. **RBAC** — фильтры на уровне Qdrant metadata и Neo4j Cypher
5. **Output Guardrails** — data leak prevention, hallucination check, citation injection
6. **Network** — DMZ / Internal сегментация через Docker networks
7. **Audit** — полное логирование всех действий с trace_id (Jaeger)

### Ролевая модель

| Роль | Security Level | Departments | Действия | Rate Limit |
|---|---|---|---|---|
| Руководитель | 3 (все) | Все | query, export, admin | 100 rpm |
| Аналитик | 2 | Свой + shared | query, export | 60 rpm |
| Гость | 0 (public) | Public only | query (limited) | 10 rpm |

---

## 🛠️ Инструкции по просмотру

### Structurizr DSL (`workspace.dsl`)

**Вариант 1 — Structurizr Lite (рекомендуется):**
```bash
# Запуск Structurizr Lite в Docker
docker run -it --rm \
  -p 8080:8080 \
  -v $(pwd)/docs/architecture:/usr/local/structurizr \
  structurizr/lite

# Открыть в браузере: http://localhost:8080
```

**Вариант 2 — Structurizr CLI (экспорт в PNG/SVG):**
```bash
# Установка
docker pull structurizr/cli

# Экспорт в PlantUML
docker run --rm \
  -v $(pwd)/docs/architecture:/usr/local/structurizr \
  structurizr/cli export \
  -workspace /usr/local/structurizr/workspace.dsl \
  -format plantuml

# Экспорт в Mermaid
docker run --rm \
  -v $(pwd)/docs/architecture:/usr/local/structurizr \
  structurizr/cli export \
  -workspace /usr/local/structurizr/workspace.dsl \
  -format mermaid
```

**Вариант 3 — Онлайн (если нет air-gap):**
1. Перейти на [Structurizr DSL Editor](https://structurizr.com/dsl)
2. Вставить содержимое `workspace.dsl`
3. Переключаться между видами в левой панели

### Mermaid диаграммы (`.mmd` файлы)

**Вариант 1 — Mermaid Live Editor (онлайн):**
1. Перейти на [Mermaid Live Editor](https://mermaid.live)
2. Вставить содержимое `.mmd` файла
3. Экспорт в PNG/SVG через кнопку в интерфейсе

**Вариант 2 — Mermaid CLI (локально):**
```bash
# Установка
npm install -g @mermaid-js/mermaid-cli

# Генерация PNG
mmdc -i docs/architecture/sequence-query-flow.mmd -o sequence.png -t dark -w 2400
mmdc -i docs/architecture/er-diagram.mmd -o er.png -t dark -w 2000
mmdc -i docs/architecture/data-flow-pipeline.mmd -o dataflow.png -t dark -w 2000
mmdc -i docs/architecture/security-architecture.mmd -o security.png -t dark -w 2000

# Генерация SVG
mmdc -i docs/architecture/sequence-query-flow.mmd -o sequence.svg
```

**Вариант 3 — VS Code:**
1. Установить расширение **Mermaid Preview** или **Markdown Preview Mermaid Support**
2. Открыть `.mmd` файл → `Ctrl+Shift+P` → "Mermaid: Preview"

**Вариант 4 — Интеграция в Markdown:**
```markdown
```mermaid
%% Вставить содержимое .mmd файла
​```
```
GitHub, GitLab, Notion и другие платформы автоматически отрендерят Mermaid-диаграммы.

---

## 📋 Матрица соответствия требованиям

| Требование | Покрытие | Файл(ы) |
|---|---|---|
| C4 Level 1 (Context) | ✅ | `workspace.dsl` → view `Level1_Context` |
| C4 Level 2 (Container) | ✅ | `workspace.dsl` → view `Level2_Containers` |
| C4 Level 3 (Component) | ✅ | `workspace.dsl` → view `Level3_BackendComponents` |
| Deployment Diagram | ✅ | `workspace.dsl` → view `Deployment_DockerCompose` |
| Sequence Diagram | ✅ | `sequence-query-flow.mmd` |
| ER Diagram (PostgreSQL) | ✅ | `er-diagram.mmd` |
| ER Diagram (Neo4j schema) | ✅ | `er-diagram.mmd` |
| ER Diagram (Qdrant collections) | ✅ | `er-diagram.mmd` |
| Data Flow Diagram | ✅ | `data-flow-pipeline.mmd` |
| Security Architecture | ✅ | `security-architecture.mmd` |
| RBAC Model | ✅ | `security-architecture.mmd` + `er-diagram.mmd` |
| Guardrails (Input + Output) | ✅ | `security-architecture.mmd` + `sequence-query-flow.mmd` |
| Network Segmentation | ✅ | `workspace.dsl` (deployment) + `security-architecture.mmd` |
| Vault / Secrets | ✅ | `workspace.dsl` + `security-architecture.mmd` |
