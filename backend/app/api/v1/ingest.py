"""API эндпоинты загрузки документов.

Fix #5: synchronous file I/O (open/write/fsync) now delegates to
asyncio.to_thread, preventing event-loop blocking on large file uploads.
"""

import asyncio
import os
import uuid
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Request, UploadFile

from app.api.v1.auth import get_access_context, get_current_user
from app.core.config import settings
from app.core.constants import ALLOWED_FILE_EXTENSIONS
from app.core.graphrag.document_ingestion import ingestion_service
from app.core.graphrag.entity_extraction import entity_extraction_service
from app.core.graphrag.graph_builder import graph_builder_service
from app.core.graphrag.vector_indexer import vector_indexer_service
from app.core.logging import logger
from app.core.metrics import documents_ingested_total
from app.core.security.rbac import AccessContext, Role
from app.models.schemas import IngestRequest, IngestUrlRequest, IngestStatusResponse
from app.services.database import database_service
from app.services.neo4j_service import neo4j_service
from app.services.ollama_service import ollama_service
from app.services.qdrant_service import qdrant_service

router = APIRouter()
_ingestion_status: dict[str, dict] = {}


def _create_status(doc_id: str, title: str, total_steps: int) -> dict:
    return {"document_id": doc_id, "title": title, "status": "processing", "step": 0,
            "step_name": "starting", "total_steps": total_steps, "chunks_count": 0,
            "entities_count": 0, "vectors_count": 0, "message": "Начало обработки...", "error": None}


async def _cleanup_failed_document(doc_id: str) -> None:
    """Remove a partially ingested document from Neo4j, Qdrant, and S3 on pipeline failure."""
    try:
        async with neo4j_service.session() as s:
            await s.run(
                "MATCH (d:Document {id: $doc_id}) "
                "OPTIONAL MATCH (d)<-[:PART_OF]-(c:Chunk) "
                "OPTIONAL MATCH (c)<-[:MENTIONED_IN]-(e:Entity) "
                "DETACH DELETE e, c, d",
                doc_id=doc_id
            )
    except Exception as e:
        logger.warning("cleanup_neo4j_failed", doc_id=doc_id, error=str(e))
    try:
        await qdrant_service.delete_by_document(doc_id)
    except Exception as e:
        logger.warning("cleanup_qdrant_failed", doc_id=doc_id, error=str(e))
    try:
        from app.services.s3_service import s3_service
        s3_service.delete_document(doc_id)
    except Exception as e:
        logger.warning("cleanup_s3_failed", doc_id=doc_id, error=str(e))
    logger.info("failed_document_cleaned_up", doc_id=doc_id)


async def _run_ingestion_pipeline(doc_id: str, text: str, title: str, source: str,
                                   metadata: dict, clearance_level: int, department: str, file_meta_id: int = 0):
    status = _ingestion_status.get(doc_id)
    if not status: return
    try:
        status["step"] = 1; status["step_name"] = "uploading"
        _, chunks, s3_key = await ingestion_service.ingest_text(
            text=text, title=title, doc_id=doc_id, source=source, metadata=metadata,
            clearance_level=clearance_level, department=department)
        status["chunks_count"] = len(chunks)

        status["step"] = 2; status["step_name"] = "extraction"
        extraction_results = await entity_extraction_service.extract_from_chunks(
            chunks=chunks, ollama_service=None, use_llm=False)
        status["entities_count"] = sum(len(r.entities) for r in extraction_results)

        status["step"] = 3; status["step_name"] = "graph"
        await graph_builder_service.build_from_extraction(
            document_id=doc_id, title=title, source=source,
            extraction_results=extraction_results, chunks=chunks, neo4j_service=neo4j_service,
            clearance_level=clearance_level, department=department, metadata=metadata, s3_key=s3_key)

        status["step"] = 4; status["step_name"] = "vectors"
        vectors_indexed = await vector_indexer_service.index_chunks(
            chunks=chunks, ollama_service=ollama_service, qdrant_service=qdrant_service,
            clearance_level=clearance_level, department=department)
        status["vectors_count"] = vectors_indexed

        # Link file metadata to document_id after success
        if file_meta_id:
            database_service.update_file_metadata(meta_id=file_meta_id, document_id=doc_id, status="completed")

        status["status"] = "completed"; status["message"] = f"Загружено: {len(chunks)} фрагментов"
        logger.info("bg_ingestion_completed", document_id=doc_id)
    except Exception as e:
        if file_meta_id:
            database_service.update_file_metadata(meta_id=file_meta_id, document_id=doc_id, status="failed")
        # Rollback: remove partially created document from Neo4j
        try:
            await _cleanup_failed_document(doc_id)
        except Exception as ce:
            logger.warning("cleanup_failed_document_failed", doc_id=doc_id, error=str(ce))
        status["status"] = "failed"; status["error"] = str(e); status["message"] = f"Ошибка: {str(e)}"
        documents_ingested_total.labels(status="failed").inc()
        logger.exception("bg_ingestion_failed", document_id=doc_id, error=str(e))


@router.get("/ingest/status/{doc_id}", response_model=IngestStatusResponse)
async def get_ingest_status(doc_id: str):
    if doc_id not in _ingestion_status: raise HTTPException(404, "Документ не найден")
    s = _ingestion_status[doc_id]
    return IngestStatusResponse(document_id=s["document_id"], status=s["status"],
                                step=s.get("step", 0), step_name=s.get("step_name", ""),
                                total_steps=s.get("total_steps", 4), message=s.get("message", ""),
                                chunks_count=s.get("chunks_count", 0), entities_count=s.get("entities_count", 0),
                                vectors_count=s.get("vectors_count", 0), error=s.get("error"))


@router.post("/ingest", response_model=IngestStatusResponse)
async def ingest_text(request: Request, background_tasks: BackgroundTasks, ingest_request: IngestRequest,
                      current_user=Depends(get_current_user), access_context=Depends(get_access_context)):
    if access_context.role not in (Role.ADMIN, Role.ANALYST): raise HTTPException(403, "Недостаточно прав")
    if not ingest_request.content: raise HTTPException(400, "Необходимо предоставить текст")

    # Simple duplicate check for text: hash-based doc_id
    doc_id = ingestion_service._generate_doc_id(ingest_request.content, ingest_request.title)
    existing = _ingestion_status.get(doc_id)
    if existing and existing.get("status") == "completed":
        raise HTTPException(409, f"Документ с таким содержимым уже загружен (id: {doc_id})")

    _ingestion_status[doc_id] = _create_status(doc_id, ingest_request.title, 5)
    background_tasks.add_task(_run_ingestion_pipeline, doc_id=doc_id, text=ingest_request.content,
        title=ingest_request.title, source=ingest_request.source, metadata=ingest_request.metadata,
        clearance_level=ingest_request.clearance_level, department=ingest_request.department)
    logger.info("bg_ingestion_started", user_id=current_user["user_id"], document_id=doc_id)
    documents_ingested_total.labels(status="queued").inc()
    return IngestStatusResponse(document_id=doc_id, status="processing")


async def _save_upload_file(file: UploadFile, file_path: Path) -> None:
    """Save uploaded file to disk in a thread-pool to avoid blocking the event loop."""
    def _sync_write() -> None:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(file_path, "wb") as f:
            # Read file content in the main thread, write in thread-pool
            f.write(file.file.read())
            f.flush()
            os_fsync = getattr(os, 'fsync', None)
            if os_fsync:
                os_fsync(f.fileno())

    await asyncio.to_thread(_sync_write)


@router.post("/ingest/file", response_model=IngestStatusResponse)
async def ingest_file(request: Request, file: UploadFile = File(...),
                      title: str = Form(""), clearance_level: int = Form(0), department: str = Form("all"),
                      current_user=Depends(get_current_user), access_context=Depends(get_access_context)):
    if access_context.role not in (Role.ADMIN, Role.ANALYST): raise HTTPException(403, "Недостаточно прав")
    file_ext = Path(file.filename).suffix.lower() if file.filename else ""
    title = title or file.filename or "Без названия"
    if file_ext not in ALLOWED_FILE_EXTENSIONS and file_ext != ".zip":
        raise HTTPException(400, f"Неподдерживаемый формат: {file_ext}")
    
    # Проверка на нулевой размер файла — не загружаем пустые файлы
    if file.size is not None and file.size == 0:
        raise HTTPException(400, "Файл имеет нулевой размер. Загрузка пустых файлов не поддерживается.")

    # Check for duplicate by file metadata (name + size)
    file_size = file.size or 0
    existing = database_service.file_exists(filename=file.filename, file_size=file_size)
    if existing:
        raise HTTPException(409, f"Файл уже был загружен ранее (документ: {existing.get('document_id', 'N/A')})")

    # Record file metadata BEFORE processing
    file_meta = database_service.create_file_metadata(filename=file.filename, file_size=file_size)

    upload_dir = settings.UPLOAD_DIR; upload_dir.mkdir(parents=True, exist_ok=True)
    doc_id = f"doc_{uuid.uuid4().hex[:12]}"
    file_path = upload_dir / f"{doc_id}{file_ext}"
    try:
        await _save_upload_file(file, file_path)
    except Exception as e:
        database_service.update_file_metadata(meta_id=file_meta.id, document_id="", status="failed")
        raise HTTPException(500, f"Ошибка сохранения: {str(e)}")

    _ingestion_status[doc_id] = _create_status(doc_id, title, 5)

    async def file_pipeline():
        try:
            _ingestion_status[doc_id]["step"] = 1; _ingestion_status[doc_id]["step_name"] = "uploading"
            _ingestion_status[doc_id]["message"] = "Извлечение текста + S3..."
            _, chunks, s3_key = await ingestion_service.ingest_file(
                file_path=file_path, doc_id=doc_id, title=title,
                metadata={"original_filename": file.filename, "file_size": file.size or 0}, clearance_level=clearance_level, department=department)
            _ingestion_status[doc_id]["chunks_count"] = len(chunks)
            _ingestion_status[doc_id]["step"] = 2; _ingestion_status[doc_id]["step_name"] = "extraction"
            extraction_results = await entity_extraction_service.extract_from_chunks(chunks=chunks, ollama_service=None, use_llm=False)
            _ingestion_status[doc_id]["entities_count"] = sum(len(r.entities) for r in extraction_results)
            _ingestion_status[doc_id]["step"] = 3; _ingestion_status[doc_id]["step_name"] = "graph"
            await graph_builder_service.build_from_extraction(
                document_id=doc_id, title=title, source=str(file_path),
                extraction_results=extraction_results, chunks=chunks, neo4j_service=neo4j_service,
                clearance_level=clearance_level, department=department, s3_key=s3_key)
            _ingestion_status[doc_id]["step"] = 4; _ingestion_status[doc_id]["step_name"] = "vectors"
            vectors_indexed = await vector_indexer_service.index_chunks(chunks=chunks, ollama_service=ollama_service,
                qdrant_service=qdrant_service, clearance_level=clearance_level, department=department)
            _ingestion_status[doc_id]["vectors_count"] = vectors_indexed

            # Link file metadata to document_id after success
            database_service.update_file_metadata(meta_id=file_meta.id, document_id=doc_id, status="completed")

            _ingestion_status[doc_id]["status"] = "completed"; _ingestion_status[doc_id]["message"] = f"Загружено: {len(chunks)} фрагментов"
            logger.info("bg_file_ingestion_completed", document_id=doc_id)
        except Exception as e:
            database_service.update_file_metadata(meta_id=file_meta.id, document_id=doc_id, status="failed")
            # Rollback: remove partially created document from Neo4j + S3
            try:
                await _cleanup_failed_document(doc_id)
            except Exception as ce:
                logger.warning("cleanup_failed_document_failed", doc_id=doc_id, error=str(ce))
            _ingestion_status[doc_id]["status"] = "failed"; _ingestion_status[doc_id]["error"] = str(e); _ingestion_status[doc_id]["message"] = f"Ошибка: {str(e)}"
            documents_ingested_total.labels(status="failed").inc(); logger.exception("bg_file_ingestion_failed", document_id=doc_id, error=str(e))
        finally:
            if file_path.exists(): file_path.unlink()

    # Verify file exists before starting pipeline
    if not file_path.exists():
        logger.error("file_not_found_after_save", path=str(file_path))
        database_service.update_file_metadata(meta_id=file_meta.id, document_id="", status="failed")
        raise HTTPException(500, "Файл не был сохранён")
    logger.info("file_saved_successfully", path=str(file_path), size=file_path.stat().st_size)
    asyncio.create_task(file_pipeline())
    logger.info("bg_file_ingestion_started", user_id=current_user["user_id"], document_id=doc_id)
    documents_ingested_total.labels(status="queued").inc()
    return IngestStatusResponse(document_id=doc_id, status="processing")


@router.post("/ingest/url", response_model=IngestStatusResponse)
async def ingest_url_json(
    request: Request,
    background_tasks: BackgroundTasks,
    body: IngestUrlRequest,
    current_user=Depends(get_current_user),
    access_context=Depends(get_access_context),
):
    if access_context.role not in (Role.ADMIN, Role.ANALYST):
        raise HTTPException(403, "Недостаточно прав")
    url = body.url; title = body.title or url.rsplit("/", 1)[-1] or "Документ из URL"
    clearance_level = body.clearance_level; department = body.department
    doc_id = f"doc_{uuid.uuid4().hex[:12]}"
    _ingestion_status[doc_id] = _create_status(doc_id, title, 5)

    async def url_pipeline():
        try:
            _ingestion_status[doc_id]["message"] = "Загрузка по URL + S3..."
            _, chunks, s3_key = await ingestion_service.ingest_url(url=url, title=title, doc_id=doc_id,
                clearance_level=clearance_level, department=department)
            _ingestion_status[doc_id]["chunks_count"] = len(chunks)
            _ingestion_status[doc_id]["step"] = 2; _ingestion_status[doc_id]["step_name"] = "extraction"
            extraction_results = await entity_extraction_service.extract_from_chunks(chunks=chunks, ollama_service=None, use_llm=False)
            _ingestion_status[doc_id]["entities_count"] = sum(len(r.entities) for r in extraction_results)
            _ingestion_status[doc_id]["step"] = 3; _ingestion_status[doc_id]["step_name"] = "graph"
            await graph_builder_service.build_from_extraction(
                document_id=doc_id, title=title, source=url,
                extraction_results=extraction_results, chunks=chunks, neo4j_service=neo4j_service,
                clearance_level=clearance_level, department=department, s3_key=s3_key)
            _ingestion_status[doc_id]["step"] = 4; _ingestion_status[doc_id]["step_name"] = "vectors"
            vectors_indexed = await vector_indexer_service.index_chunks(chunks=chunks, ollama_service=ollama_service,
                qdrant_service=qdrant_service, clearance_level=clearance_level, department=department)
            _ingestion_status[doc_id]["vectors_count"] = vectors_indexed
            _ingestion_status[doc_id]["status"] = "completed"; _ingestion_status[doc_id]["message"] = f"Загружено: {len(chunks)} фрагментов"
            logger.info("bg_url_ingestion_completed", document_id=doc_id)
        except Exception as e:
            # Rollback: remove partially created document from Neo4j + S3
            try:
                await _cleanup_failed_document(doc_id)
            except Exception as ce:
                logger.warning("cleanup_failed_document_failed", doc_id=doc_id, error=str(ce))
            _ingestion_status[doc_id]["status"] = "failed"; _ingestion_status[doc_id]["error"] = str(e); _ingestion_status[doc_id]["message"] = f"Ошибка: {str(e)}"
            documents_ingested_total.labels(status="failed").inc(); logger.exception("bg_url_ingestion_failed", document_id=doc_id, error=str(e))

    background_tasks.add_task(url_pipeline)
    logger.info("bg_url_ingestion_started", user_id=current_user["user_id"], document_id=doc_id)
    documents_ingested_total.labels(status="queued").inc()
    return IngestStatusResponse(document_id=doc_id, status="processing")