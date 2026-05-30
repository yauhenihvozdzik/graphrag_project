"""API v1 router configuration.

Aggregates all sub-routers for the GraphRAG platform endpoints.
"""

from fastapi import APIRouter

from app.api.v1.auth import router as auth_router
from app.api.v1.chat import router as chat_router
from app.api.v1.ingest import router as ingest_router
from app.api.v1.graph import router as graph_router
from app.api.v1.tests import router as tests_router
from app.api.v1.departments import router as departments_router
from app.core.logging import logger
from app.models.schemas import HealthResponse

api_router = APIRouter()

# Include sub-routers
api_router.include_router(auth_router, prefix="/auth", tags=["auth"])
api_router.include_router(chat_router, prefix="", tags=["chat"])
api_router.include_router(ingest_router, prefix="", tags=["ingest"])
api_router.include_router(graph_router, prefix="/graph", tags=["graph"])
api_router.include_router(tests_router, prefix="/tests", tags=["tests"])
api_router.include_router(departments_router, prefix="/departments", tags=["departments"])


@api_router.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint with service status."""
    from app.core.config import settings

    services = {}

    # Check Ollama
    try:
        from app.services.ollama_service import ollama_service

        health = await ollama_service.health_check()
        services["ollama"] = health.get("status", "unknown")
    except Exception:
        services["ollama"] = "unavailable"

    # Check Neo4j
    try:
        from app.services.neo4j_service import neo4j_service

        await neo4j_service.get_graph_stats()
        services["neo4j"] = "healthy"
    except Exception:
        services["neo4j"] = "unavailable"

    # Check Qdrant
    try:
        from app.services.qdrant_service import qdrant_service

        await qdrant_service.get_collection_info()
        services["qdrant"] = "healthy"
    except Exception:
        services["qdrant"] = "unavailable"

    logger.info("health_check", services=services)

    return HealthResponse(
        version=settings.VERSION,
        environment=settings.ENVIRONMENT.value,
        services=services,
    )


@api_router.get("/config/services")
async def service_config():
    """Return service connection info (URLs, credentials) for frontend integration."""
    from app.core.config import settings

    def _host_to_localhost(url: str) -> str:
        """Replace Docker hostnames with localhost for browser access."""
        import re
        return re.sub(r"://[^:/]+:", "://localhost:", url)

    def _auto_login(url: str, user: str, pw: str) -> str:
        """Embed credentials into URL for auto-login."""
        import re
        return re.sub(r"(https?://)(.+)", rf"\1{user}:{pw}@\2", url)

    neo4j_browser = _host_to_localhost(
        settings.NEO4J_URI.replace("bolt://", "http://").replace(":7687", ":7474") + "/browser/"
    )

    return {
        "success": True,
        "services": {
            "neo4j": {
                "label": "Neo4j Browser",
                "description": "Графовая СУБД",
                "browser_url": neo4j_browser,
                "auto_login_url": _auto_login(neo4j_browser, settings.NEO4J_USER, settings.NEO4J_PASSWORD),
                "user": settings.NEO4J_USER,
                "password": settings.NEO4J_PASSWORD,
            },
            "minio": {
                "label": "MinIO Console",
                "description": "S3-хранилище документов",
                "browser_url": "http://localhost:9001",
                "user": settings.S3_ACCESS_KEY,
                "password": settings.S3_SECRET_KEY,
            },
            "qdrant": {
                "label": "Qdrant Dashboard",
                "description": "Векторная СУБД",
                "browser_url": f"http://localhost:{settings.QDRANT_PORT}/dashboard/",
            },
            "ollama": {
                "label": "Ollama API",
                "description": "LLM-сервер",
                "base_url": _host_to_localhost(settings.OLLAMA_BASE_URL),
            },
            "openwebui": {
                "label": "Open WebUI",
                "description": "Веб-интерфейс Ollama",
                "browser_url": "http://localhost:3100",
            },
            "mailpit": {
                "label": "Mailpit",
                "description": "Перехватчик email",
                "browser_url": "http://localhost:8025",
            },
            "jaeger": {
                "label": "Jaeger UI",
                "description": "Трассировка запросов",
                "browser_url": "http://localhost:16686",
            },
            "grafana": {
                "label": "Grafana",
                "description": "Метрики и дашборды",
                "browser_url": "http://localhost:3001",
                "user": "admin",
                "password": "graphrag_admin",
            },
            "prometheus": {
                "label": "Prometheus",
                "description": "Сбор метрик",
                "browser_url": "http://localhost:9090",
            },
            "pgadmin": {
                "label": "pgAdmin",
                "description": "Управление PostgreSQL (БД: postgres / postgres)",
                "browser_url": "http://localhost:5050",
                "user": "admin@graphrag.com",
                "password": "pgadmin",
                "db_user": "postgres",
                "db_password": "postgres",
            },
        },
    }
