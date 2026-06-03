"""Main application entry point for GraphRAG platform backend."""

from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError

from app.api.v1.api import api_router
from app.core.config import settings
from app.core.logging import logger
from app.core.metrics import setup_metrics
from app.core.middleware import (
    LoggingContextMiddleware, MetricsMiddleware, SecurityHeadersMiddleware,
)
from app.core.observability import instrument_fastapi, setup_opentelemetry

load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("application_startup", project_name=settings.PROJECT_NAME, version=settings.VERSION, environment=settings.ENVIRONMENT.value)
    settings.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    settings.PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    setup_opentelemetry()
    try:
        from app.services.neo4j_service import neo4j_service; await neo4j_service.initialize()
    except Exception as e: logger.exception("neo4j_initialization_failed", error=str(e))
    try:
        from app.services.qdrant_service import qdrant_service; await qdrant_service.initialize()
    except Exception as e: logger.exception("qdrant_initialization_failed", error=str(e))
    try:
        from app.services.ollama_service import ollama_service; await ollama_service.initialize()
    except Exception as e: logger.exception("ollama_initialization_failed", error=str(e))
    try:
        from app.core.langgraph.agent import graphrag_agent; await graphrag_agent.create_graph()
        logger.info("langgraph_agent_pre_warmed")
    except Exception as e: logger.exception("langgraph_agent_pre_warm_failed", error=str(e))
    try:
        from app.core.langgraph.memory import graphrag_memory; await graphrag_memory.initialize()
    except Exception as e: logger.exception("graphrag_memory_init_failed", error=str(e))
    # ── Run Alembic migrations (replaces raw SQLModel.create_all for safer concurrent deploys) ──
    try:
        from app.services.database import database_service
        database_service.run_migrations()
    except Exception as e: logger.exception("db_migrations_failed", error=str(e))
    # Auto-seed departments on startup
    try:
        _seed_departments()
    except Exception as e: logger.exception("department_seed_failed", error=str(e))
    # Auto-seed demo users on startup
    try:
        _seed_demo_users()
    except Exception as e: logger.exception("demo_users_seed_failed", error=str(e))
    yield
    logger.info("application_shutdown_started")
    try:
        from app.services.neo4j_service import neo4j_service; await neo4j_service.close()
    except Exception as e: logger.warning("neo4j_shutdown_error", error=str(e))
    try:
        from app.services.qdrant_service import qdrant_service; await qdrant_service.close()
    except Exception as e: logger.warning("qdrant_shutdown_error", error=str(e))
    try:
        from app.services.ollama_service import ollama_service; await ollama_service.close()
    except Exception as e: logger.warning("ollama_shutdown_error", error=str(e))
    try:
        from app.core.langgraph.agent import graphrag_agent
        if graphrag_agent._connection_pool: await graphrag_agent._connection_pool.close()
    except Exception as e: logger.warning("langgraph_pool_shutdown_error", error=str(e))
    logger.info("application_shutdown_complete")


app = FastAPI(
    title=settings.PROJECT_NAME, description=settings.DESCRIPTION, version=settings.VERSION,
    lifespan=lifespan, docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
    openapi_url="/openapi.json" if settings.DEBUG else None,
)

# ── CORS с expose_headers для X-Download-Source ──
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Download-Source", "Content-Disposition"],
)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(MetricsMiddleware)
app.add_middleware(LoggingContextMiddleware)

setup_metrics(app)
instrument_fastapi(app)
app.include_router(api_router, prefix=settings.API_V1_STR)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    logger.warning("validation_error", path=request.url.path, errors=str(exc.errors()))
    serializable_errors = []
    for err in exc.errors():
        err_copy = dict(err)
        if "ctx" in err_copy and "error" in err_copy["ctx"]:
            err_copy["ctx"] = {**err_copy["ctx"], "error": str(err_copy["ctx"]["error"])}
        serializable_errors.append(err_copy)
    return JSONResponse(status_code=422, content={"success": False, "detail": "Ошибка валидации данных", "errors": serializable_errors})


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    logger.exception("unhandled_exception", path=request.url.path, error=str(exc))
    return JSONResponse(status_code=500, content={"success": False, "detail": "Внутренняя ошибка сервера"})


def _seed_departments():
    """Seed initial departments if not present."""
    from app.services.database import database_service
    defaults = [
        ("Все", "all", "Все отделы (доступ без ограничений)"),
        ("Юридический", "legal", "Юридический отдел"),
        ("Исследования", "research", "Отдел исследований и аналитики"),
        ("Управление", "management", "Руководство и управление"),
        ("Комплаенс", "compliance", "Отдел комплаенс и внутреннего контроля"),
        ("HR", "hr", "Отдел кадров"),
        ("Финансы", "finance", "Финансовый отдел"),
        ("IT", "it", "Информационные технологии"),
    ]
    existing = {d["code"] for d in database_service.get_departments()}
    created = 0
    for name, code, desc in defaults:
        if code not in existing:
            database_service.create_department(name=name, code=code, description=desc)
            created += 1
    if created:
        logger.info("departments_seeded", count=created)


def _seed_demo_users():
    """Seed demo users (admin, analyst, viewer) if not present.

    Uses specific exception handling for uniqueness violations instead of bare except.
    """
    from app.services.database import database_service
    demo_users = [
        ("admin@graphrag.local", "Admin123!", "admin", "admin", "all", 3),
        ("analyst@graphrag.local", "Analyst123!", "analyst", "analyst", "legal", 2),
        ("viewer@graphrag.local", "Viewer123!", "viewer", "viewer", "all", 0),
    ]
    created = 0
    for email, password, username, role, department, clearance_level in demo_users:
        existing = database_service.get_user_by_email(email)
        if existing:
            continue
        try:
            u = database_service.create_user(email=email, password=password, username=username)
        except HTTPException as e:
            if e.status_code == 409:
                logger.info("demo_user_already_exists", email=email)
                continue
            raise
        except IntegrityError:
            # Race condition — duplicate key between check and insert
            logger.info("demo_user_integrity_race", email=email)
            continue
        database_service.update_user(user_id=u.id, updates={
            "role": role,
            "department": department,
            "clearance_level": clearance_level,
            "is_active": True,
        })
        created += 1
    if created:
        logger.info("demo_users_seeded", count=created)


@app.get("/")
async def root():
    return {"name": settings.PROJECT_NAME, "version": settings.VERSION, "description": settings.DESCRIPTION,
            "docs": f"{settings.API_V1_STR}/docs" if settings.DEBUG else "disabled",
            "health": f"{settings.API_V1_STR}/health"}