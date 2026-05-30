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

Файл `backend/.env` уже содержит настройки для разработки. Для production:

```powershell
# Скопируйте и отредактируйте
copy backend\.env backend\.env.backup
notepad backend\.env
```

Обязательно измените:
- `JWT_SECRET_KEY` — на случайный ключ длиной 32+ символов
- `NEO4J_PASSWORD` — на надёжный пароль
- `POSTGRES_PASSWORD` — на надёжный пароль

## Шаг 3: Запуск инфраструктуры

```powershell
# Запуск всех сервисов
docker compose up -d

# Проверка статуса
docker compose ps
```

Ожидаемый вывод — все сервисы в статусе `Up` или `healthy`.

### Проблемы с GPU (Ollama)

Если нет NVIDIA GPU, отредактируйте `docker-compose.yml`:

```yaml
# Удалите или закомментируйте секцию deploy у ollama:
  ollama:
    image: ollama/ollama:latest
    # deploy:           # ← Закомментировать
    #   resources:
    #     reservations:
    #       devices:
    #         - driver: nvidia
    #           count: all
    #           capabilities: [gpu]
```

## Шаг 4: Загрузка моделей Ollama

```powershell
# Подождите ~30 секунд после запуска ollama
docker exec graphrag-ollama ollama pull t-lite:7b-q4_K_M
docker exec graphrag-ollama ollama pull bge-m3
```

⏱ Загрузка моделей может занять 10-30 минут в зависимости от скорости интернета.

> **Примечание**: Основная модель — `t-lite:7b-q4_K_M` (T-lite-it-1.0, дообучена T-Bank для русского языка). При необходимости можно заменить на `qwen2.5:7b` — измените `OLLAMA_MODEL` в `backend/.env`.

## Шаг 5: Инициализация базы данных

```powershell
# Создание индексов и ограничений Neo4j
docker exec graphrag-neo4j cypher-shell -u neo4j -p neo4j_password "CREATE CONSTRAINT entity_id IF NOT EXISTS FOR (e:Entity) REQUIRE e.entity_id IS UNIQUE;"
docker exec graphrag-neo4j cypher-shell -u neo4j -p neo4j_password "CREATE CONSTRAINT document_id IF NOT EXISTS FOR (d:Document) REQUIRE d.document_id IS UNIQUE;"
docker exec graphrag-neo4j cypher-shell -u neo4j -p neo4j_password "CREATE INDEX entity_name IF NOT EXISTS FOR (e:Entity) ON (e.name);"
docker exec graphrag-neo4j cypher-shell -u neo4j -p neo4j_password "CREATE INDEX entity_type IF NOT EXISTS FOR (e:Entity) ON (e.entity_type);"
docker exec graphrag-neo4j cypher-shell -u neo4j -p neo4j_password "CREATE INDEX chunk_clearance IF NOT EXISTS FOR (c:Chunk) ON (c.clearance_level);"
```

## Шаг 6: Создание пользователей и отделов

```powershell
# Убедитесь, что backend запущен и здоров
curl http://localhost:8000/api/v1/health

# Создание отделов
python scripts\seed_departments.py

# Создание демо-пользователей
python scripts\seed_users.py
```

> **Примечание**: `seed_departments.py` создаёт 8 отделов: Все, Юридический, Исследования, Управление, Комплаенс, HR, Финансы, IT.

## Шаг 7: Загрузка демо-данных (опционально)

```powershell
python scripts\load_datasets.py
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

## Альтернатива: автоматическая инициализация

Вместо шагов 4–7 можно использовать скрипт инициализации (требуется Git Bash или WSL):

```bash
chmod +x scripts/init.sh
./scripts/init.sh
```

Скрипт `init.sh` автоматически:
1. Проверяет зависимости (docker, docker-compose, curl, python3)
2. Создаёт `backend/.env` из шаблона
3. Запускает инфраструктуру (neo4j, qdrant, postgres, ollama, jaeger, prometheus, grafana)
4. Ожидает готовности сервисов
5. Загружает модели: `t-lite:7b-q4_K_M` и `bge-m3`
6. Создаёт индексы Neo4j
7. Seed-пользователей
8. Запускает backend и frontend

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