# ADR-003: Выбор LLM Serving Engine

## Статус
Принято

## Контекст

Необходим движок для инференции LLM модели (T-lite-it-1.0 / Qwen 2.5-7B в GGUF Q4_K_M) с требованиями:
- **Нативная работа на Windows 11 Pro** (без Docker/WSL как hard requirement)
- **RTX 4060 8 GB VRAM** — полный GPU offload для 7B Q4_K_M модели
- **GGUF формат** — стандарт для квантованных моделей
- **OpenAI-compatible API** — для интеграции с LangGraph/LangChain
- **KV-cache optimization** — эффективное использование VRAM для длинных контекстов
- **Простота развёртывания** — on-premise без DevOps-экспертизы
- **Мониторинг** — интеграция с Prometheus/OpenTelemetry (желательно)

## Рассмотренные варианты

### 1. Ollama

| Критерий | Оценка |
|---|---|
| Windows support | ✅ **Нативный** — установщик .exe, работает как сервис |
| GGUF support | ✅ Полная поддержка, автоматическое скачивание моделей |
| OpenAI API | ✅ Совместимый endpoint (`/v1/chat/completions`) |
| VRAM overhead | ⚠️ ~0.5 GB overhead |
| KV-cache | ✅ Автоматическое управление, настраиваемый `num_ctx` |
| Quantization | ✅ Q2–Q8, K-quants, IQ-quants |
| Производительность | ✅ ~40–50 tok/s для 7B Q4_K_M на RTX 4060 |
| Concurrent requests | ⚠️ Ограниченный batching (sequential по умолчанию) |
| Мониторинг | ⚠️ Базовые метрики через API, нет нативного Prometheus |
| Простота | ✅ **Лучшая** — `ollama run model` и готово |

### 2. vLLM

| Критерий | Оценка |
|---|---|
| Windows support | ❌ **Нет нативной поддержки** — требует Linux/Docker/WSL2 |
| GGUF support | ⚠️ Ограниченная (экспериментальная поддержка) |
| OpenAI API | ✅ Полная совместимость |
| VRAM overhead | ❌ **~1.5 GB** — PagedAttention pre-allocation |
| KV-cache | ✅ PagedAttention — лучшая оптимизация |
| Quantization | ✅ AWQ, GPTQ, FP8, bitsandbytes |
| Производительность | ✅ Лучшая для multi-user, continuous batching |
| Concurrent requests | ✅ **Лучший** — continuous batching, tensor parallelism |
| Мониторинг | ✅ Prometheus + OpenTelemetry из коробки |
| Простота | ❌ Сложная настройка, требует Linux-экспертизы |

**Критический блокер**: VRAM overhead 1.5 GB на 8 GB карте — после загрузки модели (~4.5 GB) и overhead остаётся ~2.0 GB на KV-cache, что ограничивает контекст до ~2048 токенов. Для RAG-промптов с длинным контекстом — **неприемлемо**.

### 3. SGLang

| Критерий | Оценка |
|---|---|
| Windows support | ❌ **Нет нативной поддержки** — только Docker на Windows |
| GGUF support | ⚠️ Поддержка добавлена, но не primary формат |
| OpenAI API | ✅ Совместимый endpoint |
| VRAM overhead | ⚠️ ~1.0–1.5 GB (аналогично vLLM) |
| KV-cache | ✅ RadixAttention — эффективное переиспользование prefix cache |
| Quantization | ✅ AWQ, GPTQ, GGUF, FP8 |
| Производительность | ✅ Сопоставима с vLLM, лучше для structured generation |
| Concurrent requests | ✅ Continuous batching |
| Мониторинг | ⚠️ Базовый |
| Простота | ❌ Требует Docker + конфигурация |

**Интересная особенность**: RadixAttention эффективно кэширует общие prefix-ы промптов — полезно для RAG, где system prompt повторяется. Однако VRAM overhead и отсутствие Windows — блокеры.

### 4. TGI (Text Generation Inference)

| Критерий | Оценка |
|---|---|
| Windows support | ❌ **Нет** — Docker only |
| GGUF support | ❌ **Нет нативной поддержки** |
| OpenAI API | ✅ Совместимый endpoint |
| VRAM overhead | ⚠️ ~1.0 GB |
| Quantization | ✅ AWQ, GPTQ, bitsandbytes, EETQ |
| Мониторинг | ✅ **Лучший** — Prometheus + OpenTelemetry нативно |
| Простота | ⚠️ Docker required |

**Критический блокер**: TGI вошёл в **maintenance mode** (декабрь 2025), репозиторий **архивирован** (март 2026). HuggingFace официально рекомендует переход на vLLM/SGLang. Выбор TGI для нового проекта — стратегический риск.

### 5. llama.cpp (server mode)

| Критерий | Оценка |
|---|---|
| Windows support | ✅ Нативные бинарники для Windows |
| GGUF support | ✅ **Создатель формата** — лучшая поддержка |
| OpenAI API | ✅ Через `llama-server` (OpenAI-compatible) |
| VRAM overhead | ✅ **Минимальный** — ~0.3 GB |
| KV-cache | ✅ Flash Attention, KV-cache quantization (Q4/Q8) |
| Quantization | ✅ Все GGUF варианты, включая IQ-quants |
| Производительность | ✅ Максимальная для single-user |
| Concurrent requests | ⚠️ Базовый HTTP server, ограниченный batching |
| Мониторинг | ❌ Минимальный, нет Prometheus/OTel |
| Простота | ⚠️ Требует ручной настройки параметров |

## Решение

**Выбран: Ollama (основной) + llama.cpp (как fallback / для тонкой настройки)**

### Конфигурация:

| Параметр | Значение |
|---|---|
| Engine | Ollama (latest) |
| Backend | llama.cpp (встроенный) |
| Модель | T-lite-it-1.0 GGUF Q4_K_M |
| GPU offload | Полный (все слои) |
| `num_ctx` | 4096 (default) / 8192 (при необходимости) |
| API endpoint | `http://localhost:11434/v1/chat/completions` |
| Параллельные запросы | `OLLAMA_NUM_PARALLEL=2` |

## Обоснование

### Матрица принятия решения

| Критерий (вес) | Ollama | vLLM | SGLang | TGI | llama.cpp |
|---|---|---|---|---|---|
| Windows native (×3) | ✅ 9 | ❌ 0 | ❌ 0 | ❌ 0 | ✅ 9 |
| VRAM efficiency (×3) | ⚠️ 7 | ❌ 4 | ❌ 4 | ⚠️ 5 | ✅ 9 |
| GGUF support (×2) | ✅ 9 | ⚠️ 4 | ⚠️ 6 | ❌ 0 | ✅ 10 |
| Простота (×2) | ✅ 10 | ❌ 3 | ❌ 4 | ⚠️ 5 | ⚠️ 6 |
| OpenAI API (×2) | ✅ 9 | ✅ 10 | ✅ 9 | ✅ 9 | ✅ 8 |
| Мониторинг (×1) | ⚠️ 5 | ✅ 10 | ⚠️ 6 | ✅ 10 | ❌ 2 |
| Долгосрочность (×1) | ✅ 9 | ✅ 9 | ✅ 8 | ❌ 2 | ✅ 9 |
| **Итого** | **113** | **59** | **57** | **45** | **110** |

### Почему Ollama, а не raw llama.cpp:

1. **Управление моделями**: автоматическое скачивание, версионирование, переключение
2. **OpenAI API**: более зрелая реализация, лучше совместимость с LangChain
3. **Автозапуск**: работает как Windows-сервис, автоматический рестарт
4. **Простота для команды**: `ollama pull model && ollama serve` vs ручная сборка llama.cpp

### Компенсация недостатков Ollama:

- **Мониторинг**: внешний Prometheus exporter для Ollama API метрик + OpenTelemetry через LangGraph
- **Batching**: `OLLAMA_NUM_PARALLEL=2` для ограниченного параллелизма
- **Performance tuning**: доступ к llama.cpp параметрам через Modelfile

## Последствия

### Положительные:
- ✅ Нативная работа на Windows 11 без Docker/WSL
- ✅ Минимальный VRAM overhead (~0.5 GB) — больше места для KV-cache
- ✅ Установка за 5 минут, нет зависимости от DevOps
- ✅ OpenAI-compatible API — бесшовная интеграция с LangGraph
- ✅ Активное сообщество, частые обновления

### Отрицательные:
- ⚠️ Ограниченный concurrent batching — не подходит для 10+ одновременных пользователей
- ⚠️ Нет нативного Prometheus/OpenTelemetry — требуется внешний мониторинг
- ⚠️ Абстракция над llama.cpp скрывает некоторые low-level настройки
- ⚠️ Зависимость от одного проекта (Ollama Inc.)

### Путь эволюции:
- **Фаза 1 (MVP)**: Ollama — быстрый старт, простое развёртывание
- **Фаза 2 (Scale)**: при росте до 5+ пользователей — оценка перехода на vLLM/SGLang через Docker
- **Фаза 3 (Production)**: при обновлении GPU (≥16 GB) — vLLM с continuous batching и Prometheus
