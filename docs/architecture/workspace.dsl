workspace "GraphRAG Platform" "Защищённая платформа GraphRAG для корпоративных знаний (On-Premise / Air-Gapped)" {

    !identifiers hierarchical

    model {
        # ─── Внешние пользователи и системы ───────────────────────────────
        analyst = person "Аналитик" "Формирует аналитические запросы к базе знаний" "Analyst"
        manager = person "Руководитель" "Принимает решения на основе данных платформы" "Manager"
        guest   = person "Гость" "Ограниченный доступ только для чтения" "Guest"

        erp = softwareSystem "ERP System" "Корпоративная ERP (1С, SAP и др.)" "External"
        crm = softwareSystem "CRM System" "CRM для управления клиентами" "External"
        edms = softwareSystem "EDMS / СЭД" "Система электронного документооборота" "External"

        # ─── GraphRAG Platform ────────────────────────────────────────────
        graphrag = softwareSystem "GraphRAG Platform" "Защищённая платформа интеллектуального поиска и генерации ответов по корпоративным документам (RusLawOD, RFSD)" {

            # --- Level 2: Containers ---

            frontend = container "Web Frontend" "SPA-приложение для взаимодействия с платформой: чат, история, администрирование" "React + TypeScript" "WebBrowser"

            apiGateway = container "API Gateway" "Маршрутизация, rate limiting, TLS termination, аутентификация JWT" "Kong / Nginx" "Gateway"

            backend = container "Backend Service" "Основной сервис бизнес-логики, оркестрации агента и GraphRAG pipeline" "FastAPI + LangGraph (Python 3.11)" "Service" {

                # --- Level 3: Components ---

                sessionManager = component "Session Manager" "Управление пользовательскими сессиями, хранение контекста диалога, TTL" "FastAPI Dependency"
                rbacFilter     = component "RBAC Filter" "Проверка ролей и прав доступа (Руководитель / Аналитик / Гость), фильтрация узлов графа по security_level и department" "Python Middleware"
                inputGuardrails  = component "Input Guardrails" "Обнаружение PII, prompt injection, валидация входных данных" "NeMo Guardrails / Custom"
                outputGuardrails = component "Output Guardrails" "Фильтрация конфиденциальных данных из ответов, проверка галлюцинаций" "NeMo Guardrails / Custom"

                planner = component "Planner (Agent)" "LangGraph state machine: анализ запроса, планирование шагов, управление циклом agent loop" "LangGraph StateGraph"

                memoryModule = component "Memory Module" "Единый интерфейс к графовому и векторному хранилищу: загрузка, поиск, обновление" "Python Module"
                toolsInterface = component "Tools Interface" "Набор инструментов агента: GraphRAG retrieval, entity extraction, reranking, summarization" "LangGraph Tools"

                ingestionPipeline = component "Ingestion Pipeline" "Пайплайн загрузки документов: парсинг → чанкинг → экстракция сущностей → построение графа → векторизация" "Python Pipeline"
            }

            ollama = container "LLM Serving" "Обслуживание LLM (Qwen 2.5 7B) и embedding-модели (bge-m3) на GPU" "Ollama" "LLM"

            qdrant = container "Vector Database" "Хранение векторных представлений документов с RBAC-метаданными" "Qdrant" "Database"

            neo4j = container "Graph Database" "Хранение графа знаний: сущности, связи, документы с атрибутами безопасности" "Neo4j Community" "Database"

            postgres = container "Relational Database" "Хранение пользователей, сессий, аудит-логов, конфигурации RBAC" "PostgreSQL 16" "Database"

            vault = container "Secrets Manager" "Управление секретами: API-ключи, credentials для БД, JWT-секреты" "HashiCorp Vault" "Security"

            prometheus = container "Metrics Collector" "Сбор метрик со всех сервисов (latency, throughput, GPU utilization)" "Prometheus" "Observability"
            grafana    = container "Monitoring Dashboard" "Визуализация метрик, алерты, дашборды" "Grafana" "Observability"
            jaeger     = container "Distributed Tracing" "Трассировка запросов через все сервисы, анализ latency" "Jaeger" "Observability"
        }

        # ─── Level 1: Context relationships ───────────────────────────────
        analyst -> graphrag "Задаёт вопросы, анализирует документы" "HTTPS"
        manager -> graphrag "Просматривает аналитику и отчёты" "HTTPS"
        guest   -> graphrag "Ограниченный поиск по документам" "HTTPS"

        graphrag -> erp  "Импорт справочников, организационной структуры" "REST API / File Import"
        graphrag -> crm  "Получение данных о клиентах и контрактах" "REST API"
        graphrag -> edms "Загрузка документов для индексации" "REST API / File Sync"

        # ─── Level 2: Container relationships ─────────────────────────────
        analyst -> graphrag.frontend "Работает через браузер" "HTTPS"
        manager -> graphrag.frontend "Работает через браузер" "HTTPS"
        guest   -> graphrag.frontend "Работает через браузер" "HTTPS"

        graphrag.frontend -> graphrag.apiGateway "API-запросы" "HTTPS / JSON"

        graphrag.apiGateway -> graphrag.backend "Проксирование запросов" "HTTP / JSON"
        graphrag.apiGateway -> graphrag.vault "Валидация JWT-секретов" "HTTPS"

        graphrag.backend -> graphrag.ollama "LLM inference, embeddings" "HTTP (порт 11434)"
        graphrag.backend -> graphrag.qdrant "Векторный поиск, upsert" "gRPC / HTTP (порт 6333)"
        graphrag.backend -> graphrag.neo4j "Cypher-запросы, обход графа" "Bolt (порт 7687)"
        graphrag.backend -> graphrag.postgres "CRUD: users, sessions, audit" "PostgreSQL Wire Protocol (порт 5432)"
        graphrag.backend -> graphrag.vault "Получение секретов при старте" "HTTPS"
        graphrag.backend -> graphrag.jaeger "Отправка trace spans" "OTLP / HTTP"

        graphrag.prometheus -> graphrag.backend "Scrape метрик" "HTTP /metrics"
        graphrag.prometheus -> graphrag.ollama "Scrape метрик GPU" "HTTP /metrics"
        graphrag.prometheus -> graphrag.qdrant "Scrape метрик" "HTTP /metrics"
        graphrag.prometheus -> graphrag.neo4j "Scrape метрик" "HTTP /metrics"
        graphrag.prometheus -> graphrag.apiGateway "Scrape метрик" "HTTP /metrics"

        graphrag.grafana -> graphrag.prometheus "Запрос метрик" "PromQL"
        graphrag.grafana -> graphrag.jaeger "Запрос трейсов" "Jaeger Query API"

        # ─── Level 3: Component relationships ─────────────────────────────
        graphrag.apiGateway -> graphrag.backend.sessionManager "Запрос с JWT" "HTTP"

        graphrag.backend.sessionManager -> graphrag.backend.inputGuardrails "Передача валидированного запроса" ""
        graphrag.backend.inputGuardrails -> graphrag.backend.rbacFilter "Проверенный запрос" ""
        graphrag.backend.rbacFilter -> graphrag.backend.planner "Запрос с контекстом прав" ""

        graphrag.backend.planner -> graphrag.backend.toolsInterface "Вызов инструментов агента" ""
        graphrag.backend.planner -> graphrag.backend.memoryModule "Чтение/запись контекста" ""
        graphrag.backend.planner -> graphrag.backend.outputGuardrails "Сгенерированный ответ" ""

        graphrag.backend.toolsInterface -> graphrag.ollama "LLM generation / reranking" "HTTP"
        graphrag.backend.toolsInterface -> graphrag.qdrant "Векторный поиск" "gRPC"
        graphrag.backend.toolsInterface -> graphrag.neo4j "Graph traversal" "Bolt"

        graphrag.backend.memoryModule -> graphrag.neo4j "Граф знаний" "Bolt"
        graphrag.backend.memoryModule -> graphrag.qdrant "Векторные embeddings" "gRPC"
        graphrag.backend.memoryModule -> graphrag.postgres "Сессии, история" "SQL"

        graphrag.backend.ingestionPipeline -> graphrag.ollama "Генерация embeddings (bge-m3)" "HTTP"
        graphrag.backend.ingestionPipeline -> graphrag.neo4j "Построение графа знаний" "Bolt"
        graphrag.backend.ingestionPipeline -> graphrag.qdrant "Индексация векторов" "gRPC"

        graphrag.backend.outputGuardrails -> graphrag.backend.sessionManager "Финальный ответ" ""
    }

    views {

        # ═══════════════════════════════════════════════════════════════════
        #  LEVEL 1 — System Context
        # ═══════════════════════════════════════════════════════════════════
        systemContext graphrag "Level1_Context" {
            include *
            autoLayout lr
            title "Level 1 — System Context: GraphRAG Platform"
            description "Обзор интеграции GraphRAG платформы с пользователями и внешними корпоративными системами"
        }

        # ═══════════════════════════════════════════════════════════════════
        #  LEVEL 2 — Container
        # ═══════════════════════════════════════════════════════════════════
        container graphrag "Level2_Containers" {
            include *
            autoLayout tb
            title "Level 2 — Containers: Микросервисная архитектура GraphRAG"
            description "Детализация контейнеров: API Gateway, Backend, LLM Serving, базы данных, observability стек"
        }

        # ═══════════════════════════════════════════════════════════════════
        #  LEVEL 3 — Component (Backend Service)
        # ═══════════════════════════════════════════════════════════════════
        component graphrag.backend "Level3_BackendComponents" {
            include *
            autoLayout tb
            title "Level 3 — Components: Backend Service (FastAPI + LangGraph)"
            description "Внутреннее устройство Backend Service: Session Manager, RBAC, Guardrails, Planner, Memory, Tools, Ingestion"
        }

        # ═══════════════════════════════════════════════════════════════════
        #  DEPLOYMENT — Windows 11 PC (Docker Compose)
        # ═══════════════════════════════════════════════════════════════════
        deployment graphrag "Production" "Deployment_DockerCompose" {
            include *
            autoLayout tb
            title "Deployment: On-Premise Windows 11 PC (Docker Compose)"
            description "Физическое размещение на Ryzen 3900X / RTX 4060 / 64 GB RAM с сетевой сегментацией DMZ / Internal"
        }

        # ═══════════════════════════════════════════════════════════════════
        #  Styles
        # ═══════════════════════════════════════════════════════════════════
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
            element "WebBrowser" {
                shape WebBrowser
                background #438dd5
                color #ffffff
            }
            element "Gateway" {
                shape Hexagon
                background #2694ab
                color #ffffff
            }
            element "LLM" {
                shape RoundedBox
                background #e05038
                color #ffffff
            }
            element "Security" {
                shape Diamond
                background #d4a017
                color #000000
            }
            element "Observability" {
                shape Ellipse
                background #6b9e78
                color #ffffff
            }
            element "Analyst" {
                background #08427b
            }
            element "Manager" {
                background #2e6b34
            }
            element "Guest" {
                background #7b6e08
            }
        }
    }

    # ═══════════════════════════════════════════════════════════════════════
    #  Deployment Model
    # ═══════════════════════════════════════════════════════════════════════
    model {
        prodDeployment = deploymentEnvironment "Production" {

            deploymentNode "Windows 11 PC" "Ryzen 9 3900X • RTX 4060 8GB • 64 GB RAM • 2 TB NVMe" "Windows 11 + WSL2 + Docker Desktop" {

                # ── DMZ Network (172.20.0.0/24) ──
                deploymentNode "DMZ Network (docker: graphrag_dmz)" "Сегмент, доступный из локальной сети" "Docker Bridge Network" {

                    deploymentNode "frontend-container" "React SPA, порт 3000" "Docker (node:20-alpine)" {
                        frontendInstance = containerInstance graphrag.frontend
                    }

                    deploymentNode "gateway-container" "Kong / Nginx, порт 443/80" "Docker (kong:3.6)" {
                        gatewayInstance = containerInstance graphrag.apiGateway
                    }
                }

                # ── Internal Network (172.21.0.0/24) ──
                deploymentNode "Internal Network (docker: graphrag_internal)" "Изолированный внутренний сегмент" "Docker Bridge Network" {

                    deploymentNode "backend-container" "FastAPI + LangGraph, порт 8000" "Docker (python:3.11-slim)" "CPU: 4 cores, RAM: 8 GB" {
                        backendInstance = containerInstance graphrag.backend
                    }

                    deploymentNode "ollama-container" "LLM Serving, порт 11434" "Docker (ollama/ollama:latest)" "GPU: RTX 4060 (8 GB VRAM), RAM: 16 GB" {
                        ollamaInstance = containerInstance graphrag.ollama
                    }

                    deploymentNode "qdrant-container" "Vector DB, порт 6333/6334" "Docker (qdrant/qdrant:v1.9)" "CPU: 2 cores, RAM: 8 GB, Storage: 100 GB NVMe" {
                        qdrantInstance = containerInstance graphrag.qdrant
                    }

                    deploymentNode "neo4j-container" "Graph DB, порт 7474/7687" "Docker (neo4j:5.19-community)" "CPU: 4 cores, RAM: 12 GB, Storage: 200 GB NVMe" {
                        neo4jInstance = containerInstance graphrag.neo4j
                    }

                    deploymentNode "postgres-container" "RDBMS, порт 5432" "Docker (postgres:16-alpine)" "CPU: 1 core, RAM: 2 GB, Storage: 20 GB" {
                        postgresInstance = containerInstance graphrag.postgres
                    }

                    deploymentNode "vault-container" "Secrets, порт 8200" "Docker (hashicorp/vault:1.16)" "CPU: 1 core, RAM: 512 MB" {
                        vaultInstance = containerInstance graphrag.vault
                    }

                    # ── Observability sub-segment ──
                    deploymentNode "observability-stack" "Мониторинг и трассировка" "Docker Compose group" {

                        deploymentNode "prometheus-container" "порт 9090" "Docker (prom/prometheus:v2.51)" "CPU: 1 core, RAM: 2 GB" {
                            prometheusInstance = containerInstance graphrag.prometheus
                        }

                        deploymentNode "grafana-container" "порт 3001" "Docker (grafana/grafana:10.4)" "CPU: 1 core, RAM: 1 GB" {
                            grafanaInstance = containerInstance graphrag.grafana
                        }

                        deploymentNode "jaeger-container" "порт 16686/4317" "Docker (jaegertracing/all-in-one:1.56)" "CPU: 1 core, RAM: 1 GB" {
                            jaegerInstance = containerInstance graphrag.jaeger
                        }
                    }
                }
            }
        }
    }
}
