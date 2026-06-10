workspace "GraphRAG Platform" "Защищённая платформа GraphRAG для корпоративных знаний (On-Premise / Air-Gapped)" {

    !identifiers hierarchical

    model {
        # ─── Внешние пользователи и системы ───────────────────────────────
        viewer  = person "Viewer" "Просмотр документов только своего отдела" "Viewer"
        analyst = person "Аналитик" "Загрузка документов, аналитические запросы" "Analyst"
        admin   = person "Администратор" "Полный доступ: пользователи, отделы, тесты, инфраструктура" "Admin"

        erp = softwareSystem "ERP System" "Корпоративная ERP (1С, SAP и др.)" "External"
        crm = softwareSystem "CRM System" "CRM для управления клиентами" "External"
        edms = softwareSystem "EDMS / СЭД" "Система электронного документооборота" "External"

        # ─── GraphRAG Platform ────────────────────────────────────────────
        graphrag = softwareSystem "GraphRAG Platform" "Защищённая платформа интеллектуального поиска и генерации ответов по корпоративным документам" {

            # --- Level 2: Containers ---

            frontend = container "Web Frontend" "SPA-приложение для взаимодействия с платформой: чат, история, администрирование" "Vanilla JavaScript SPA" "WebBrowser"

            backend = container "Backend Service" "Основной сервис бизнес-логики, оркестрации агента и GraphRAG pipeline. Включает JWT-аутентификацию, rate limiting, CORS" "FastAPI + LangGraph (Python 3.11)" "Service" {

                # --- Level 3: Components ---

                rbacFilter     = component "RBAC Filter" "Проверка ролей и прав доступа (admin / analyst / viewer), фильтрация по clearance_level и department" "Python Middleware"
                inputGuardrails  = component "Input Guardrails" "Обнаружение PII, prompt injection, валидация входных данных" "Custom Python"
                outputGuardrails = component "Output Guardrails" "Фильтрация ПДн (PII masking) из ответов" "Custom Python"

                graphragAgent = component "GraphRAG Agent" "LangGraph state machine: classify → correct_spelling → retrieve → generate → guardrails" "LangGraph StateGraph"

                ingestionPipeline = component "Ingestion Pipeline" "Загрузка: парсинг → чанкинг → экстракция сущностей → граф знаний → векторизация" "Python Pipeline"
            }

            ollama = container "LLM Serving" "Обслуживание LLM (qwen2.5:7b) и embedding-модели (bge-m3) на GPU" "Ollama" "LLM"

            qdrant = container "Vector Database" "Хранение векторных представлений документов с RBAC-метаданными" "Qdrant" "Database"

            neo4j = container "Graph Database" "Хранение графа знаний: сущности, связи, документы с атрибутами безопасности" "Neo4j Community" "Database"

            postgres = container "Relational Database" "Хранение пользователей, сессий, аудит-логов, конфигурации RBAC" "PostgreSQL 16" "Database"

            minio = container "Object Storage" "S3-совместимое хранилище документов и извлечённого текста" "MinIO" "Storage"

            prometheus = container "Metrics Collector" "Сбор метрик со всех сервисов (latency, throughput, GPU utilization)" "Prometheus" "Observability"
            grafana    = container "Monitoring Dashboard" "Визуализация метрик, алерты, дашборды" "Grafana" "Observability"
            jaeger     = container "Distributed Tracing" "Трассировка запросов через все сервисы, анализ latency" "Jaeger" "Observability"
        }

        # ─── Level 1: Context relationships ───────────────────────────────
        admin   -> graphrag "Полное управление платформой" "HTTPS"
        analyst -> graphrag "Загрузка документов, аналитические запросы" "HTTPS"
        viewer  -> graphrag "Просмотр документов своего отдела" "HTTPS"

        graphrag -> erp  "Импорт справочников, организационной структуры" "REST API / File Import"
        graphrag -> crm  "Получение данных о клиентах и контрактах" "REST API"
        graphrag -> edms "Загрузка документов для индексации" "REST API / File Sync"

        # ─── Level 2: Container relationships ─────────────────────────────
        admin   -> graphrag.frontend "Работает через браузер" "HTTPS"
        analyst -> graphrag.frontend "Работает через браузер" "HTTPS"
        viewer  -> graphrag.frontend "Работает через браузер" "HTTPS"

        graphrag.frontend -> graphrag.backend "API-запросы (nginx proxy_pass)" "HTTP / JSON"

        graphrag.backend -> graphrag.ollama "LLM inference, embeddings" "HTTP (порт 11434)"
        graphrag.backend -> graphrag.qdrant "Векторный поиск, upsert" "HTTP (порт 6333)"
        graphrag.backend -> graphrag.neo4j "Cypher-запросы, обход графа" "Bolt (порт 7687)"
        graphrag.backend -> graphrag.postgres "CRUD: users, sessions, audit" "PostgreSQL Wire Protocol (порт 5432)"
        graphrag.backend -> graphrag.minio "Сохранение/загрузка документов" "S3 API (порт 9000)"
        graphrag.backend -> graphrag.jaeger "Отправка trace spans" "OTLP / HTTP"

        graphrag.prometheus -> graphrag.backend "Scrape метрик" "HTTP /metrics"
        graphrag.prometheus -> graphrag.ollama "Scrape метрик GPU" "HTTP /metrics"
        graphrag.prometheus -> graphrag.qdrant "Scrape метрик" "HTTP /metrics"
        graphrag.prometheus -> graphrag.neo4j "Scrape метрик" "HTTP /metrics"

        graphrag.grafana -> graphrag.prometheus "Запрос метрик" "PromQL"
        graphrag.grafana -> graphrag.jaeger "Запрос трейсов" "Jaeger Query API"

        # ─── Level 3: Component relationships ─────────────────────────────
        graphrag.backend.rbacFilter -> graphrag.backend.graphragAgent "Запрос с контекстом прав" ""
        graphrag.backend.graphragAgent -> graphrag.backend.outputGuardrails "Сгенерированный ответ" ""

        graphrag.backend.graphragAgent -> graphrag.ollama "LLM generation / embeddings" "HTTP"
        graphrag.backend.graphragAgent -> graphrag.qdrant "Векторный поиск" "HTTP"
        graphrag.backend.graphragAgent -> graphrag.neo4j "Graph traversal" "Bolt"

        graphrag.backend.ingestionPipeline -> graphrag.ollama "Генерация embeddings (bge-m3)" "HTTP"
        graphrag.backend.ingestionPipeline -> graphrag.neo4j "Построение графа знаний" "Bolt"
        graphrag.backend.ingestionPipeline -> graphrag.qdrant "Индексация векторов" "HTTP"
        graphrag.backend.ingestionPipeline -> graphrag.minio "Сохранение документов" "S3 API"

        graphrag.backend.outputGuardrails -> graphrag.frontend "Финальный ответ через API" "HTTP"

        # ─── Deployment Model ─────────────────────────────────────────────
        prodDeployment = deploymentEnvironment "Production" {

            deploymentNode "Windows 11 PC" "Ryzen 9 3900X • RTX 4060 8GB • 64 GB RAM • 2 TB NVMe" "Windows 11 + WSL2 + Docker Desktop" {

                deploymentNode "DMZ Network" "Сегмент, доступный из локальной сети" "Docker Bridge Network 172.20.0.0/24" {

                    deploymentNode "frontend-container" "Vanilla JS SPA, порт 80" "Docker (nginx:alpine)" {
                        frontendInstance = containerInstance graphrag.frontend
                    }
                }

                deploymentNode "Internal Network" "Изолированный внутренний сегмент" "Docker Bridge Network 172.21.0.0/24" {

                    deploymentNode "backend-container" "FastAPI + LangGraph, порт 8000" "Docker (python:3.11-slim)" "CPU: 4 cores, RAM: 8 GB" {
                        backendInstance = containerInstance graphrag.backend
                    }

                    deploymentNode "ollama-container" "LLM Serving, порт 11434" "Docker (ollama/ollama:latest)" "GPU: RTX 4060 (8 GB VRAM), RAM: 16 GB" {
                        ollamaInstance = containerInstance graphrag.ollama
                    }

                    deploymentNode "qdrant-container" "Vector DB, порт 6333/6334" "Docker (qdrant/qdrant:latest)" "CPU: 2 cores, RAM: 8 GB" {
                        qdrantInstance = containerInstance graphrag.qdrant
                    }

                    deploymentNode "neo4j-container" "Graph DB, порт 7474/7687" "Docker (neo4j:5-community)" "CPU: 4 cores, RAM: 12 GB" {
                        neo4jInstance = containerInstance graphrag.neo4j
                    }

                    deploymentNode "postgres-container" "RDBMS, порт 5432" "Docker (postgres:16-alpine)" "CPU: 1 core, RAM: 2 GB" {
                        postgresInstance = containerInstance graphrag.postgres
                    }

                    deploymentNode "minio-container" "Object Storage, порт 9000/9001" "Docker (minio/minio:latest)" "CPU: 1 core, RAM: 1 GB" {
                        minioInstance = containerInstance graphrag.minio
                    }

                    deploymentNode "observability-stack" "Мониторинг и трассировка" "Docker Compose group" {

                        deploymentNode "prometheus-container" "порт 9090" "Docker (prom/prometheus:latest)" "CPU: 1 core, RAM: 2 GB" {
                            prometheusInstance = containerInstance graphrag.prometheus
                        }

                        deploymentNode "grafana-container" "порт 3001" "Docker (grafana/grafana:latest)" "CPU: 1 core, RAM: 1 GB" {
                            grafanaInstance = containerInstance graphrag.grafana
                        }

                        deploymentNode "jaeger-container" "порт 16686/4317" "Docker (jaegertracing/all-in-one:latest)" "CPU: 1 core, RAM: 1 GB" {
                            jaegerInstance = containerInstance graphrag.jaeger
                        }
                    }
                }
            }
        }
    }

    views {

        systemContext graphrag "Level1_Context" {
            include *
            autoLayout lr
            title "Level 1 — System Context: GraphRAG Platform"
            description "Обзор интеграции GraphRAG платформы с пользователями и внешними корпоративными системами"
        }

        container graphrag "Level2_Containers" {
            include *
            autoLayout tb
            title "Level 2 — Containers: Микросервисная архитектура GraphRAG"
            description "Детализация контейнеров: Backend, LLM Serving, базы данных, observability стек"
        }

        component graphrag.backend "Level3_BackendComponents" {
            include *
            autoLayout tb
            title "Level 3 — Components: Backend Service (FastAPI + LangGraph)"
            description "Внутреннее устройство Backend Service: RBAC, Guardrails, GraphRAG Agent, Ingestion Pipeline"
        }

        deployment graphrag "Production" "Deployment_DockerCompose" {
            include *
            autoLayout tb
            title "Deployment: On-Premise Windows 11 PC (Docker Compose)"
            description "Физическое размещение на Ryzen 3900X / RTX 4060 / 64 GB RAM с сетевой сегментацией DMZ / Internal"
        }

        styles {
            element "Person" {
                shape Person
                background #08427b
                color #ffffff
            }
            element "Software System" {
                background #1168bd
                color #ffffff
            }
            element "External" {
                background #999999
                color #ffffff
            }
            element "Container" {
                background #438dd5
                color #ffffff
            }
            element "Component" {
                background #85bbf0
                color #000000
            }
            element "Database" {
                shape Cylinder
                background #438dd5
                color #ffffff
            }
            element "Storage" {
                shape Cylinder
                background #6b9e78
                color #ffffff
            }
            element "WebBrowser" {
                shape WebBrowser
                background #438dd5
                color #ffffff
            }
            element "LLM" {
                shape RoundedBox
                background #e05038
                color #ffffff
            }
            element "Observability" {
                shape Ellipse
                background #6b9e78
                color #ffffff
            }
            element "Analyst" {
                background #08427b
            }
            element "Viewer" {
                background #7b6e08
            }
            element "Admin" {
                background #2e6b34
            }
        }
    }
}