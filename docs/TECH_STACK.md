# Технологический стек GraphRAG платформы

> **Платформа**: GraphRAG для анализа корпоративных знаний (юридический домен)
> **Целевое железо**: Ryzen 3900X (12C/24T) · RTX 4060 8 GB · 64 GB RAM · Windows 11 Pro
> **Режим**: On-premise / Air-gapped (без облачных API)

---

## Сводная таблица выбранного стека

| Компонент | Решение | Версия / Квантование | Ресурсы | ADR |
|---|---|---|---|---|
| **LLM** | T-lite-it-1.0 (7B) / Qwen 2.5 (7B) | Q4_K_M (Ollama) | ~6.5 GB VRAM (веса + KV-cache) | [ADR-001](adr/001-llm-model-selection.md) |
| **Embedding** | BAAI/bge-m3 | FP16 (1024-dim) | ~1.1 GB RAM (CPU inference) | [ADR-002](adr/002-embedding-model-selection.md) |
| **LLM Serving** | Ollama | Latest | ~0.5 GB overhead | [ADR-003](adr/003-llm-serving-engine.md) |
| **Vector DB** | Qdrant | Latest | ~1.5 GB RAM (500K vectors) | [ADR-004](adr/004-vector-database.md) |
| **Graph DB** | Neo4j Community | 5.26 | ~3–4 GB RAM | [ADR-005](adr/005-graph-database.md) |
| **Orchestration** | LangGraph | ≥ 0.2.x | Negligible | [ADR-006](adr/006-orchestration-framework.md) |
| **Relational DB** | PostgreSQL 16 | Latest | ~1 GB RAM (пользователи, сессии, checkpoints) | — |
| **Object Storage** | MinIO | Latest | ~0.5 GB RAM (S3-совместимое хранение документов) | — |
| **LLM Web UI** | Open WebUI | Latest | ~1 GB RAM (веб-интерфейс к Ollama) | — |
| **DB Admin** | pgAdmin | Latest | ~0.3 GB RAM (GUI для PostgreSQL) | — |

---

## Распределение ресурсов

### VRAM Budget (RTX 4060 — 8 GB)

```
┌──────────────────────────────────────────────────┐
│                  RTX 4060 — 8 GB VRAM            │
├──────────────────────────────────────┬───────────┤
│ T-lite 7B Q4_K_M / Qwen 2.5 7B     │  4.5 GB   │
│ Q4_K_M (веса)                        │           │
├──────────────────────────────────────┼───────────┤
│ KV-cache (авто, ctx 4096)            │  1.5 GB   │
├──────────────────────────────────────┼───────────┤
│ Ollama runtime overhead              │  0.5 GB   │
├──────────────────────────────────────┼───────────┤
│ OS / display / reserve               │  1.5 GB   │
├──────────────────────────────────────┼───────────┤
│ ИТОГО                                │  8.0 GB   │
└──────────────────────────────────────┴───────────┘
```

### RAM Budget (64 GB)

```
┌──────────────────────────────────────────────────┐
│                    64 GB RAM                     │
├──────────────────────────────────────┬───────────┤
│ Windows 11 + системные процессы      │  6–8 GB   │
├──────────────────────────────────────┼───────────┤
│ Neo4j (heap + pagecache)             │  3–4 GB   │
├──────────────────────────────────────┼───────────┤
│ Qdrant                               │  1.5–3 GB │
├──────────────────────────────────────┼───────────┤
│ bge-m3 embedding model               │  1.1 GB   │
├──────────────────────────────────────┼───────────┤
│ Ollama (system RAM component)        │  1–2 GB   │
├──────────────────────────────────────┼───────────┤
│ PostgreSQL 16                         │  1 GB     │
├──────────────────────────────────────┼───────────┤
│ MinIO                                │  0.5 GB   │
├──────────────────────────────────────┼───────────┤
│ Python app + LangGraph               │  1–2 GB   │
├──────────────────────────────────────┼───────────┤
│ Prometheus + Grafana + Jaeger        │  1–2 GB   │
├──────────────────────────────────────┼───────────┤
│ Open WebUI + pgAdmin                 │  1.3 GB   │
├──────────────────────────────────────┼───────────┤
│ Свободно (buffer / batch indexing)   │ 38–45 GB  │
├──────────────────────────────────────┼───────────┤
│ ИТОГО                                │  64 GB    │
└──────────────────────────────────────┴───────────┘
```

---

## Ключевые обоснования выбора

### LLM: T-lite-it-1.0 (7B) — основная модель
- **Русский язык**: дообучена T-Bank специально для русского языка, показывает лучшие результаты на русскоязычных бенчмарках среди 7B-моделей
- **VRAM**: Q4_K_M (~4.5 GB) оставляет ~3.5 GB для KV-cache → контекст до 8K токенов
- **Совместимость**: нативная поддержка Ollama, официальные GGUF
- **Резервная модель**: Qwen 2.5 (7B) — обучена на 29+ языках, может быть использована как замена (изменить `OLLAMA_MODEL` в `backend/.env`)

### Embedding: bge-m3 (а не e5-large / rubert)
- **Контекст 8192 токенов**: юридические документы без chunking
- **Hybrid search**: dense + sparse embeddings в одном запросе (1024-dim)
- **CPU inference**: не конкурирует с LLM за GPU VRAM

### Serving: Ollama (а не vLLM / SGLang / TGI)
- **Windows native**: единственный вариант без Docker/WSL
- **VRAM efficiency**: overhead 0.5 GB (vs 1.5 GB у vLLM)
- **Простота**: `ollama pull t-lite:7b-q4_K_M && ollama serve`

### Vector DB: Qdrant (а не Milvus / Weaviate)
- **Rust-based**: минимальное потребление RAM
- **Payload filtering**: нативная фильтрация по clearance_level и department для RBAC
- **Dashboard**: встроенный веб-интерфейс на порту 6333/dashboard/

### Graph DB: Neo4j (а не AGE / Memgraph / FalkorDB)
- **25+ лет зрелости**: стандарт de facto
- **Cypher**: мощный язык для юридических traversal-запросов
- **Neo4j Browser**: визуализация графа для аналитиков

### Orchestration: LangGraph (обязательное требование)
- **Циклы**: iterative refinement ответов
- **Checkpointing**: PostgreSQL-based через langgraph-checkpoint-postgres
- **Экосистема**: langchain-community, langchain-core

### Object Storage: MinIO
- **S3-совместимый**: стандартный API для хранения документов
- **Локальное развёртывание**: не требует облачных сервисов
- **Deduplication**: хранение оригиналов и извлечённого текста

---

## Стек инфраструктуры

| Компонент | Назначение | Порт |
|---|---|---|
| **PostgreSQL 16** | Пользователи, сессии, LangGraph checkpoints | 5432 |
| **MinIO** | S3-хранилище документов | 9000 (API), 9001 (Console) |
| **Mailpit** | Перехват email (dev) | 1025 (SMTP), 8025 (Web UI) |
| **pgAdmin** | GUI для PostgreSQL | 5050 |
| **Open WebUI** | Веб-интерфейс к Ollama | 3100 |
| **Nginx** | Фронтенд-прокси (SPA + /api/* → backend) | 3000 |

## Стек мониторинга

| Компонент | Назначение |
|---|---|
| **OpenTelemetry** | Distributed tracing (LangGraph → Ollama → Qdrant → Neo4j) |
| **Jaeger** | UI для просмотра traces (self-hosted, замена LangSmith) |
| **Prometheus** | Сбор метрик (Qdrant, Neo4j, NVIDIA GPU, кастомные) |
| **Grafana** | Dashboards (latency, throughput, token usage, error rates) |

---

## Python-зависимости (основные)

```toml
[project]
dependencies = [
    # ── Web Framework ──
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.30.0",
    "python-dotenv>=1.0.0",
    "python-multipart>=0.0.9",

    # ── LangGraph / LangChain ──
    "langgraph>=0.2.0",
    "langchain-core>=0.3.0",
    "langchain-community>=0.3.0",

    # ── Database ──
    "sqlmodel>=0.0.21",
    "psycopg2-binary>=2.9.0",
    "psycopg[binary]>=3.2.0",
    "psycopg-pool>=3.2.0",
    "langgraph-checkpoint-postgres>=2.0.0",

    # ── Neo4j ──
    "neo4j>=5.20.0",

    # ── Qdrant ──
    "qdrant-client>=1.11.0",

    # ── HTTP ──
    "httpx>=0.27.0",

    # ── Auth ──
    "python-jose[cryptography]>=3.3.0",
    "bcrypt>=4.0.0",
    "pydantic[email]>=2.0.0",

    # ── S3 / MinIO Storage ──
    "boto3>=1.35.0",

    # ── Logging ──
    "structlog>=24.0.0",

    # ── Metrics ──
    "prometheus-client>=0.20.0",
    "starlette-prometheus>=0.9.0",

    # ── GPU Monitoring ──
    "nvidia-ml-py>=12.0.0",

    # ── Tracing ──
    "opentelemetry-api>=1.20.0",
    "opentelemetry-sdk>=1.20.0",
    "opentelemetry-exporter-otlp-proto-grpc>=1.20.0",
    "opentelemetry-instrumentation-fastapi",
    "opentelemetry-instrumentation-httpx",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.24",
    "pytest-timeout>=2.2",
    "httpx>=0.27",
]
otel = [
    "opentelemetry-api>=1.20.0",
    "opentelemetry-sdk>=1.20.0",
    "opentelemetry-exporter-otlp-proto-grpc>=1.20.0",
    "opentelemetry-instrumentation-fastapi",
    "opentelemetry-instrumentation-httpx",
]
```

---

## Путь эволюции стека

| Фаза | Триггер | Изменения |
|---|---|---|
| **MVP** | Старт проекта | Текущий стек |
| **Scale** | 5+ пользователей | Ollama → vLLM (Docker), добавить Redis для кэширования |
| **GPU Upgrade** | ≥16 GB VRAM | T-lite 7B → Qwen 2.5-14B Q4_K_M, vLLM с continuous batching |
| **Enterprise** | Требование HA | Neo4j Enterprise (clustering), Qdrant distributed mode |
| **Multi-GPU** | 2× GPU | Tensor parallelism через vLLM, больший контекст |

---

## Список ADR документов

1. [ADR-001: Выбор LLM модели](adr/001-llm-model-selection.md) — T-lite-it-1.0 (7B) GGUF Q4_K_M (основная), Qwen 2.5 (7B) резервная
2. [ADR-002: Выбор Embedding модели](adr/002-embedding-model-selection.md) — BAAI/bge-m3 (1024-dim)
3. [ADR-003: Выбор LLM Serving Engine](adr/003-llm-serving-engine.md) — Ollama
4. [ADR-004: Выбор Vector Database](adr/004-vector-database.md) — Qdrant
5. [ADR-005: Выбор Graph Database](adr/005-graph-database.md) — Neo4j Community Edition
6. [ADR-006: Выбор Orchestration Framework](adr/006-orchestration-framework.md) — LangGraph