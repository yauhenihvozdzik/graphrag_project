"""Main application entry point for GraphRAG platform backend."""

import asyncio
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
    LoggingContextMiddleware, MetricsMiddleware, RateLimitMiddleware, SecurityHeadersMiddleware,
)
from app.core.observability import instrument_fastapi, setup_opentelemetry

load_dotenv()


async def _backfill_document_full_text():
    """One-time backfill: assemble full_text for existing documents from their chunks."""
    try:
        from app.services.neo4j_service import neo4j_service
    except Exception:
        return
    try:
        async with neo4j_service.session() as s:
            # Найти документы без full_text
            result = await s.run(
                "MATCH (d:Document) WHERE d.full_text IS NULL OR d.full_text = '' "
                "RETURN d.id AS doc_id, d.title AS title"
            )
            records = await result.data()
            if not records:
                return
            updated = 0
            for rec in records:
                doc_id = rec["doc_id"]
                # Собрать текст из чанков
                cr = await s.run(
                    "MATCH (d:Document {id: $doc_id})<-[:PART_OF]-(c:Chunk) "
                    "RETURN c.text AS text ORDER BY c.position",
                    doc_id=doc_id,
                )
                chunks = await cr.data()
                if chunks:
                    full_text = "\n\n".join(
                        c["text"] for c in chunks if c.get("text") and c["text"].strip()
                    )
                    if full_text:
                        await s.run(
                            "MATCH (d:Document {id: $doc_id}) SET d.full_text = $full_text",
                            doc_id=doc_id, full_text=full_text,
                        )
                        updated += 1
            logger.info("backfill_full_text_completed", missing=len(records), updated=updated)
    except Exception as e:
        logger.exception("backfill_full_text_failed", error=str(e))


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("application_startup", project_name=settings.PROJECT_NAME, version=settings.VERSION, environment=settings.ENVIRONMENT.value)
    settings.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    settings.PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    setup_opentelemetry()
    try:
        from app.services.neo4j_service import neo4j_service
        await neo4j_service.initialize()
    except Exception as e: logger.exception("neo4j_initialization_failed", error=str(e))
    try:
        from app.services.qdrant_service import qdrant_service
        await qdrant_service.initialize()
    except Exception as e: logger.exception("qdrant_initialization_failed", error=str(e))
    try:
        from app.services.ollama_service import ollama_service
        await ollama_service.initialize()
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
        await asyncio.to_thread(database_service.run_migrations)
    except Exception as e: logger.exception("db_migrations_failed", error=str(e))
    # Auto-seed departments on startup
    try:
        await asyncio.to_thread(_seed_departments)
    except Exception as e: logger.exception("department_seed_failed", error=str(e))
    # Auto-seed demo users on startup
    try:
        await asyncio.to_thread(_seed_demo_users)
    except Exception as e: logger.exception("demo_users_seed_failed", error=str(e))
    # Auto-ingest demo datasets on startup (disabled for startup speed; run scripts/load_datasets.py manually)
    # try:
    #     await _seed_datasets()
    # except Exception as e: logger.exception("datasets_seed_failed", error=str(e))
    # ── Seed default admin settings if empty ──
    try:
        from app.seed_admin_settings import seed_admin_settings
        await asyncio.to_thread(seed_admin_settings, database_service)
    except Exception as e:
        logger.exception("admin_settings_seed_failed", error=str(e))
    # ── Initialise dynamic settings registry ──
    try:
        from app.core.settings_registry import SettingsRegistry
        settings_registry = SettingsRegistry()
        await settings_registry.initialize()
        logger.info("settings_registry_initialised")
    except Exception as e: logger.exception("settings_registry_init_failed", error=str(e))
    # ── Reload guardrails config from registry ──
    try:
        from app.core.security.guardrails import guardrails_service
        guardrails_service.reload_config()
        logger.info("guardrails_config_initialised")
    except Exception as e: logger.exception("guardrails_config_init_failed", error=str(e))
    # Backfill full_text for existing documents from chunks
    try:
        await _backfill_document_full_text()
    except Exception as e: logger.exception("backfill_full_text_failed", error=str(e))
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
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept", "X-Request-ID"],
    expose_headers=["X-Download-Source", "Content-Disposition"],
)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(MetricsMiddleware)
app.add_middleware(LoggingContextMiddleware)
app.add_middleware(RateLimitMiddleware)

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


async def _seed_datasets():
    """Auto-load sample datasets on first startup via internal ingestion pipeline.

    Waits for Ollama models to be available, then ingests a set of demo
    legal/company documents so the GraphRAG knowledge graph is non-empty
    right after ``docker compose up``.
    """
    import asyncio

    import httpx

    from app.core.config import settings
    from app.core.graphrag.document_ingestion import ingestion_service
    from app.core.graphrag.entity_extraction import entity_extraction_service
    from app.core.graphrag.graph_builder import graph_builder_service
    from app.core.graphrag.vector_indexer import vector_indexer_service
    from app.services.neo4j_service import neo4j_service
    from app.services.ollama_service import ollama_service
    from app.services.qdrant_service import qdrant_service

    SAMPLE_DOCUMENTS = [
        {
            "title": "Гражданский кодекс РФ — Статья 1",
            "text": (
                "Гражданское законодательство основывается на признании равенства участников "
                "регулируемых им отношений, неприкосновенности собственности, свободы договора, "
                "недопустимости произвольного вмешательства кого-либо в частные дела, "
                "необходимости беспрепятственного осуществления гражданских прав, обеспечения "
                "восстановления нарушенных прав, их судебной защиты."
            ),
            "clearance_level": 0,
            "department": "legal",
        },
        {
            "title": "Трудовой кодекс РФ — Статья 2",
            "text": (
                "Исходя из общепризнанных принципов и норм международного права и в соответствии "
                "с Конституцией Российской Федерации основными принципами правового регулирования "
                "трудовых отношений и иных непосредственно связанных с ними отношений признаются: "
                "свобода труда, включая право на труд, который каждый свободно выбирает или на "
                "который свободно соглашается, право распоряжаться своими способностями к труду, "
                "выбирать профессию и род деятельности."
            ),
            "clearance_level": 0,
            "department": "legal",
        },
        {
            "title": "Федеральный закон о персональных данных",
            "text": (
                "Настоящим Федеральным законом регулируются отношения, связанные с обработкой "
                "персональных данных, осуществляемой федеральными органами государственной власти, "
                "органами государственной власти субъектов Российской Федерации, иными "
                "государственными органами, органами местного самоуправления, юридическими лицами, "
                "физическими лицами с использованием средств автоматизации."
            ),
            "clearance_level": 2,
            "department": "legal",
        },
        {
            "title": "Внутренний регламент — Политика безопасности",
            "text": (
                "Доступ к конфиденциальным документам предоставляется только сотрудникам "
                "с соответствующим уровнем допуска. Все операции с секретными материалами "
                "должны быть зарегистрированы в журнале аудита. Передача документов за пределы "
                "организации требует письменного разрешения руководителя отдела безопасности."
            ),
            "clearance_level": 3,
            "department": "management",
        },
    ]

    # ── Wait for Ollama models to be available ──
    logger.info("seed_datasets_waiting_ollama")
    for attempt in range(1, 31):
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as client:
                resp = await client.get(f"{settings.OLLAMA_BASE_URL}/api/tags")
                if resp.status_code == 200:
                    models = [m["name"] for m in resp.json().get("models", [])]
                    has_llm = any(settings.OLLAMA_MODEL in m for m in models)
                    has_emb = any(settings.OLLAMA_EMBEDDING_MODEL in m for m in models)
                    if has_llm and has_emb:
                        logger.info("seed_datasets_ollama_ready", models=models)
                        break
        except Exception:
            pass
        logger.info("seed_datasets_ollama_waiting", attempt=attempt)
        await asyncio.sleep(4)
    else:
        logger.warning("seed_datasets_ollama_not_ready_timeout", skipping=True)
        return

    # ── Ingest each document via internal pipeline ──
    ingested = 0
    for doc in SAMPLE_DOCUMENTS:
        try:
            doc_id, chunks, s3_key = await ingestion_service.ingest_text(
                text=doc["text"],
                title=doc["title"],
                clearance_level=doc["clearance_level"],
                department=doc["department"],
            )
            logger.info("seed_dataset_ingested", doc_id=doc_id, title=doc["title"], chunks=len(chunks))

            extraction_results = await entity_extraction_service.extract_from_chunks(
                chunks=chunks, ollama_service=None, use_llm=False,
            )
            logger.info("seed_dataset_entities_extracted", doc_id=doc_id, entities=sum(len(r.entities) for r in extraction_results))

            await graph_builder_service.build_from_extraction(
                document_id=doc_id,
                title=doc["title"],
                source="seed_datasets",
                extraction_results=extraction_results,
                chunks=chunks,
                neo4j_service=neo4j_service,
                clearance_level=doc["clearance_level"],
                department=doc["department"],
                metadata={},
                s3_key=s3_key,
            )

            vectors_indexed = await vector_indexer_service.index_chunks(
                chunks=chunks,
                ollama_service=ollama_service,
                qdrant_service=qdrant_service,
                clearance_level=doc["clearance_level"],
                department=doc["department"],
            )
            logger.info("seed_dataset_vectors_indexed", doc_id=doc_id, vectors=vectors_indexed)
            ingested += 1
        except Exception as e:
            logger.exception("seed_dataset_failed", title=doc["title"], error=str(e))

    if ingested:
        logger.info("seed_datasets_completed", ingested=ingested, total=len(SAMPLE_DOCUMENTS))


@app.get("/")
async def root():
    return {"name": settings.PROJECT_NAME, "version": settings.VERSION, "description": settings.DESCRIPTION,
            "docs": f"{settings.API_V1_STR}/docs" if settings.DEBUG else "disabled",
            "health": f"{settings.API_V1_STR}/health"}