# ADR-004: Выбор векторной базы данных

## Статус
Принято

## Контекст

Платформе GraphRAG необходима векторная база данных для хранения и поиска embedding-векторов юридических документов:
- **Размерность векторов**: 1024 (BAAI/bge-m3 dense) + sparse vectors
- **Ожидаемый объём**: ~100K–1M документов (RusLawOD + RFSD + расширение)
- **Гибридный поиск**: dense (семантический) + sparse (лексический)
- **Self-hosted**: полностью on-premise, air-gapped среда
- **ОС**: Windows 11 Pro (или Docker на Windows)
- **Ресурсы**: 64 GB RAM, SSD-хранилище

**Требования:**
- Низкое потребление RAM (другие компоненты: LLM ~6.5 GB VRAM, Neo4j, приложение)
- Быстрый поиск (P95 latency < 100ms для 100K векторов)
- Поддержка фильтрации по метаданным (тип документа, дата, юрисдикция)
- Scalar/binary quantization для экономии памяти
- REST/gRPC API для интеграции с LangChain

## Рассмотренные варианты

### 1. Qdrant

| Характеристика | Детали |
|---|---|
| Язык | Rust |
| Лицензия | Apache 2.0 |
| Развёртывание | Бинарник / Docker / Embedded (Python) |
| Windows | ✅ Docker, нативный бинарник доступен |
| API | REST + gRPC |
| Hybrid search | ✅ Dense + Sparse vectors в одной коллекции |
| Metadata filtering | ✅ ACORN алгоритм — быстрая фильтрация |
| Quantization | Scalar, Binary, Product quantization |
| RAM (1M, 1024-dim) | ~3 GB (с scalar quantization) |
| P95 latency | 30–40ms (1M vectors) |
| QPS | 8,000–15,000 |
| SDK | Python, JS, Rust, Go, Java, .NET |
| GitHub Stars | ~29K |

### 2. Milvus

| Характеристика | Детали |
|---|---|
| Язык | Go + C++ |
| Лицензия | Apache 2.0 |
| Развёртывание | Docker Compose / Kubernetes / Milvus Lite |
| Windows | ⚠️ Docker only (полная версия требует etcd, MinIO, Pulsar) |
| API | REST + gRPC |
| Hybrid search | ✅ Dense + full-text search |
| Metadata filtering | ✅ Хорошее, но не такое быстрое как ACORN |
| Quantization | IVF-based, scalar, PQ |
| RAM (1M, 1024-dim) | ~4 GB |
| P95 latency | 50–80ms (1M vectors) |
| QPS | 10,000–20,000 (при оптимальной конфигурации) |
| SDK | Python, Java, Go, Node.js |
| GitHub Stars | ~35K+ |

**Примечание**: Milvus Lite (embedded) подходит для прототипирования, но имеет ограничения для production.

### 3. Weaviate

| Характеристика | Детали |
|---|---|
| Язык | Go |
| Лицензия | BSD 3-Clause |
| Развёртывание | Docker / Kubernetes |
| Windows | ⚠️ Docker only |
| API | REST + gRPC + **GraphQL** |
| Hybrid search | ✅ Dense + BM25 keyword search |
| Metadata filtering | ✅ Через GraphQL |
| Quantization | Rotational quantization |
| RAM (1M, 1024-dim) | ~3.5 GB |
| P95 latency | 50–70ms (1M vectors) |
| QPS | 3,000–8,000 |
| SDK | Python, JS, Go, Java, C# |
| GitHub Stars | ~14K |

**Особенности**: встроенные vectorizers (OpenAI, Cohere, HF) — бесполезны в air-gapped среде. Knowledge graph capabilities — потенциально полезны, но дублируют Neo4j.

## Решение

**Выбран: Qdrant**

### Конфигурация развёртывания:

| Параметр | Значение |
|---|---|
| Версия | Qdrant latest (Docker или бинарник) |
| Storage | SSD, path: `./qdrant_storage` |
| RAM limit | ~4 GB (с запасом для 500K vectors) |
| API | REST (port 6333) + gRPC (port 6334) |
| Collections | `documents` (dense 1024-dim + sparse), `chunks` (если нужен chunking) |
| Quantization | Scalar quantization (INT8) |
| HNSW | `m=16, ef_construct=128, ef=64` |

### Схема коллекции:

```json
{
  "vectors": {
    "dense": { "size": 1024, "distance": "Cosine" },
    "sparse": { "index": { "on_disk": false } }
  },
  "payload_schema": {
    "doc_type": "keyword",
    "source_dataset": "keyword",
    "date": "datetime",
    "jurisdiction": "keyword",
    "title": "text"
  },
  "quantization_config": {
    "scalar": { "type": "int8", "always_ram": true }
  }
}
```

## Обоснование

### 1. Эффективность ресурсов — решающий фактор

При 64 GB RAM, из которых:
- ~6.5 GB — LLM (через GPU VRAM, но Ollama требует и RAM)
- ~3–5 GB — Neo4j
- ~1.1 GB — embedding model
- ~4–8 GB — ОС и приложения
- Остаток: ~40–50 GB для vector DB

Все три варианта укладываются, но Qdrant наиболее экономен:

| DB | RAM для 500K vectors (1024-dim, quantized) |
|---|---|
| Qdrant | ~1.5 GB (scalar quantization) |
| Milvus | ~2.0 GB |
| Weaviate | ~1.75 GB |

### 2. Hybrid Search (Dense + Sparse)

bge-m3 генерирует и dense, и sparse embeddings. Qdrant — **единственная** из рассмотренных БД, которая нативно поддерживает хранение обоих типов векторов **в одной коллекции** с единым API запросом:

```python
# Qdrant: один запрос — hybrid search
results = client.query_points(
    collection_name="documents",
    prefetch=[
        Prefetch(query=sparse_vector, using="sparse", limit=20),
        Prefetch(query=dense_vector, using="dense", limit=20),
    ],
    query=FusionQuery(fusion=Fusion.RRF),  # Reciprocal Rank Fusion
    limit=10
)
```

Milvus требует отдельную full-text коллекцию, Weaviate использует BM25 (не sparse embeddings bge-m3).

### 3. ACORN — быстрая фильтрация по метаданным

Для юридического поиска критична фильтрация:
- «Найди релевантные статьи УК РФ» → `doc_type = "criminal_code"`
- «Судебная практика за 2023 год» → `date >= 2023-01-01`

Qdrant's ACORN алгоритм оптимизирован для **одновременного** vector search + metadata filtering без деградации производительности. Milvus и Weaviate делают post-filtering, что может пропускать релевантные результаты при строгих фильтрах.

### 4. Простота развёртывания на Windows

| DB | Способ запуска на Windows |
|---|---|
| Qdrant | `qdrant.exe` (бинарник) **ИЛИ** Docker |
| Milvus | Docker Compose (etcd + MinIO + Pulsar + Milvus) — **4 контейнера** |
| Weaviate | Docker (1 контейнер, но только Docker) |

Milvus в production-режиме требует **4 отдельных сервиса** — overhead для on-premise установки с одним сервером. Milvus Lite (embedded) — опция для прототипа, но не для production.

### 5. Интеграция с LangChain

Все три БД поддерживаются LangChain, но Qdrant имеет наиболее зрелую интеграцию:
- `langchain-qdrant` — официальный пакет
- Поддержка hybrid search через LangChain retrievers
- Поддержка metadata filtering через LangChain filters

## Последствия

### Положительные:
- ✅ Минимальное потребление RAM (~1.5 GB для 500K vectors)
- ✅ Нативный hybrid search (dense + sparse) — идеально для bge-m3
- ✅ ACORN — быстрая filtered search для юридических запросов
- ✅ Бинарник для Windows — не требует Docker
- ✅ REST + gRPC API — гибкость интеграции
- ✅ Scalar quantization — экономия памяти без значимой потери recall

### Отрицательные:
- ⚠️ Меньшее сообщество по сравнению с Milvus (~29K vs ~35K stars)
- ⚠️ Нет встроенного horizontal sharding для billion-scale (не актуально для 100K–1M)
- ⚠️ Нет встроенного BM25 — зависимость от sparse embeddings bge-m3
- ⚠️ Web UI dashboard менее развит по сравнению с Milvus Attu

### Митигация:
- Для мониторинга — Qdrant предоставляет Prometheus-метрики через `/metrics` endpoint
- При росте до >10M vectors — оценка Milvus с Kubernetes
- Dashboard — использовать Qdrant Web UI (`http://localhost:6333/dashboard`) + Grafana для метрик
