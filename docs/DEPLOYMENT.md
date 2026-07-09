# Руководство по развёртыванию — Windows 11

Полная инструкция развёртывания GraphRAG Platform на Windows 11.

---

## Предварительные требования

### 1. Аппаратные требования

| Параметр | Минимум | Рекомендуется |
|----------|---------|---------------|
| RAM | 8 GB | 16 GB+ |
| Диск | 20 GB свободного места | 50 GB SSD |
| CPU | 4 ядра | 8 ядер |
| GPU | — | NVIDIA с 6+ GB VRAM |

### 2. Программное обеспечение

#### Docker Desktop
1. Скачайте Docker Desktop: https://www.docker.com/products/docker-desktop/
2. Запустите установщик
3. Убедитесь, что включён **WSL 2 Backend**:
   - Откройте PowerShell от администратора:
     ```powershell
     wsl --install
     wsl --set-default-version 2
     ```
4. Перезагрузите компьютер
5. Запустите Docker Desktop
6. В настройках Docker Desktop:
   - **Settings → Resources → WSL Integration** — включите для вашего дистрибутива
   - **Settings → Resources → Advanced**:
     - Memory: минимум 8 GB
     - CPUs: минимум 4
     - Disk image size: минимум 30 GB

#### Git
1. Скачайте Git: https://git-scm.com/download/win
2. Установите с настройками по умолчанию

#### Python 3.11+ (опционально, для скриптов)
1. Скачайте: https://www.python.org/downloads/
2. При установке отметьте **"Add Python to PATH"**
3. Установите зависимости:
   ```powershell
   pip install requests
   ```

---

## Шаг 1: Клонирование проекта

```powershell
# Откройте PowerShell
cd C:\Projects
git clone <repo-url> graphrag_project
cd graphrag_project
```

## Шаг 2: Настройка переменных окружения

Создайте файл `backend/.env` из шаблона:

```powershell
# Скопируйте шаблон
copy backend\.env.example backend\.env
```

Шаблон `backend/.env.example` содержит все необходимые переменные с безопасными значениями по умолчанию для разработки. Для production:

```powershell
# Отредактируйте
notepad backend\.env
```

Обязательно измените:
- `JWT_SECRET_KEY` — на случайный ключ (сгенерируйте: `openssl rand -hex 32`)
- `NEO4J_PASSWORD` — на надёжный пароль
- `POSTGRES_PASSWORD` — на надёжный пароль

## Шаг 3: Запуск всех сервисов (одной командой)

```powershell
# Запуск всех сервисов — полная автоинициализация
docker compose up -d

# Проверка статуса
docker compose ps
```

Ожидаемый вывод — все сервисы в статусе `Up` или `healthy`.

### Что происходит автоматически при `docker compose up`:

1. **Infrastructure**: Neo4j, Qdrant, PostgreSQL, Ollama, MinIO — запускаются с healthcheck-ами
2. **ollama-init**: Одноразовый сервис, дожидается готовности Ollama и загружает модели `qwen2.5:7b` (LLM) и `bge-m3` (embeddings)
3. **backend**: Дожидается готовности **всех** зависимостей (включая `ollama-init`), затем при старте (lifespan):
   - Выполняет миграции Alembic (PostgreSQL)
   - Инициализирует схемы Neo4j (constraints + indexes)
   - Инициализирует коллекции Qdrant
   - Seed 8 отделов (Юридический, Исследования, Управление, …)
   - Seed 3 демо-пользователей (admin, analyst, viewer)
   - Загружает 4 демо-документа (юридические + регламент)
   - Инициализирует LangGraph-агента и guardrails
4. **frontend**: Дожидается healthcheck backend и становится доступным на `:3000`

⏱ **Первичный запуск**: загрузка моделей Ollama может занять 10-30 минут. При последующих запусках — ~2-3 минуты.

### Проблемы с GPU (Ollama)

Если нет NVIDIA GPU, GPU-ускорение уже отключено в `docker-compose.yml` по умолчанию (секция `deploy` закомментирована). Ollama будет работать на CPU.

Для включения GPU на Linux-хосте с NVIDIA — раскомментируйте секцию `deploy` у сервиса `ollama` в `docker-compose.yml`.

> **Примечание**: Основная модель — `qwen2.5:7b` (мультиязычная, 29+ языков). При необходимости можно заменить на `t-lite:7b-q4_K_M` (T-lite-it-1.0, дообучена T-Bank для русского языка) — измените `OLLAMA_MODEL` в `backend/.env`.

## Шаг 4: Ручная инициализация (опционально)

Если требуется повторно проинициализировать данные или загрузить дополнительные датасеты:

```powershell
# Повторное создание отделов
python scripts\seed_departments.py

# Повторное создание пользователей
python scripts\seed_users.py

# Загрузка демо-данных через API
python scripts\load_datasets.py
```

Индексы Neo4j при необходимости:
```powershell
docker exec graphrag-neo4j cypher-shell -u neo4j -p neo4j_password "CREATE CONSTRAINT entity_id IF NOT EXISTS FOR (e:Entity) REQUIRE e.id IS UNIQUE;"
docker exec graphrag-neo4j cypher-shell -u neo4j -p neo4j_password "CREATE CONSTRAINT document_id IF NOT EXISTS FOR (d:Document) REQUIRE d.id IS UNIQUE;"
docker exec graphrag-neo4j cypher-shell -u neo4j -p neo4j_password "CREATE INDEX entity_name IF NOT EXISTS FOR (e:Entity) ON (e.name);"
docker exec graphrag-neo4j cypher-shell -u neo4j -p neo4j_password "CREATE INDEX entity_type IF NOT EXISTS FOR (e:Entity) ON (e.entity_type);"
docker exec graphrag-neo4j cypher-shell -u neo4j -p neo4j_password "CREATE INDEX chunk_clearance IF NOT EXISTS FOR (c:Chunk) ON (c.clearance_level);"
```

## Шаг 8: Проверка

Откройте в браузере:
- **Frontend**: http://localhost:3000
- **API Docs**: http://localhost:8000/docs
- **Neo4j Browser**: http://localhost:7474
- **Grafana**: http://localhost:3001 (admin / graphrag_admin)
- **Jaeger**: http://localhost:16686
- **MinIO Console**: http://localhost:9001 (minioadmin / minioadmin)
- **Open WebUI**: http://localhost:3100
- **pgAdmin**: http://localhost:5050 (admin@graphrag.com / pgadmin)

---

## Автоматическая инициализация (рекомендуется)

**При `docker compose up` всё инициализируется автоматически** — ручные шаги не требуются.

Однако если вы предпочитаете запускать сервисы пошагово (например, для отладки), используйте скрипт `scripts/init.sh` (требуется Git Bash или WSL):

```bash
chmod +x scripts/init.sh
./scripts/init.sh
```

Скрипт `init.sh` выполняет полный цикл инициализации:
1. Проверяет зависимости (`docker`, `curl`, `python3`)
2. Создаёт `backend/.env` из шаблона `backend/.env.example` (если отсутствует)
3. Запускает инфраструктуру (`docker compose up -d neo4j qdrant postgres ollama jaeger prometheus grafana`)
4. Ожидает готовности сервисов (health checks)
5. Загружает модели Ollama: `qwen2.5:7b` и `bge-m3`
6. Создаёт индексы и constraints Neo4j
7. Запускает backend и frontend
8. Ожидает готовности backend (health check)
9. Seed отделов (`seed_departments.py`)
10. Seed пользователей (`seed_users.py`)
11. Загружает демо-датасеты (`load_datasets.py`)

Для переопределения учётных данных администратора задайте переменные окружения перед запуском:
```bash
ADMIN_EMAIL="custom@example.com" ADMIN_PASSWORD="CustomPass123!" ./scripts/init.sh
```

---

## Управление сервисами

```powershell
# Остановить все
docker compose down

# Остановить с удалением данных
docker compose down -v

# Пересобрать backend после изменений кода
docker compose build backend
docker compose up -d backend

# Логи конкретного сервиса
docker compose logs -f backend
docker compose logs -f neo4j

# Перезапуск конкретного сервиса
docker compose restart backend
```

---

## Решение проблем

### Docker не запускается
1. Убедитесь, что WSL 2 установлен: `wsl --status`
2. Перезапустите Docker Desktop
3. Проверьте, что виртуализация включена в BIOS

### Ollama не отвечает
```powershell
# Проверить логи
docker compose logs ollama

# Перезапустить
docker compose restart ollama

# Проверить доступность
curl http://localhost:11434/api/tags
```

### Neo4j недоступен
```powershell
# Логи
docker compose logs neo4j

# Проверить здоровье
docker exec graphrag-neo4j cypher-shell -u neo4j -p neo4j_password "RETURN 1"
```

### Backend не запускается
```powershell
# Проверить логи
docker compose logs backend

# Частая причина: зависимые сервисы не готовы
docker compose restart backend
```

### Нехватка памяти
1. Увеличьте лимиты в Docker Desktop → Settings → Resources
2. Или используйте менее ресурсоёмкую модель:
   ```powershell
   # В backend/.env замените:
   OLLAMA_MODEL=gemma:2b
   ```

### Порт занят
```powershell
# Найти процесс на порту (например, 8000)
netstat -ano | findstr :8000
# Завершить процесс
taskkill /PID <pid> /F
```

---

## Обновление

```powershell
# Получить обновления
git pull origin main

# Пересобрать и перезапустить
docker compose build
docker compose up -d
```
