"""Graph visualization and query API endpoints."""

from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response

from app.api.v1.auth import get_access_context, get_current_user
from app.core.logging import logger
from app.core.security.rbac import AccessContext, rbac_service
from app.models.schemas import (
    GraphSearchRequest, GraphVisualizationResponse, GraphNode, GraphEdge,
)
from app.services.neo4j_service import neo4j_service
from qdrant_client import models
from app.services.s3_service import s3_service

router = APIRouter()


def _make_download_response(content: str, title: str, source: str) -> Response:
    """Создаёт ответ для скачивания файла с правильным Content-Disposition."""
    # Don't append .txt if title already has an extension
    has_ext = "." in title.rsplit("/", 1)[-1] if "/" in title else ("." in title)
    safe_filename = (title if has_ext else f"{title}.txt").replace('"', '_').replace('\\', '_')
    encoded_filename = quote(safe_filename)
    return Response(
        content=content.encode("utf-8"),
        media_type="text/plain; charset=utf-8",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}",
            "X-Download-Source": source,
        })


@router.get("/visualize", response_model=GraphVisualizationResponse)
async def get_graph_visualization(
    request: Request, limit: int = Query(default=200, ge=1, le=1000),
    current_user: dict = Depends(get_current_user),
    access_context: AccessContext = Depends(get_access_context),
):
    try:
        rbac_filter = rbac_service.build_cypher_filter(access_context)
        data = await neo4j_service.get_visualization_data(limit=limit, rbac_filter=rbac_filter)
        nodes = [GraphNode(id=n.get("id",""), name=n.get("name",""), type=n.get("type","entity"),
                   properties={k:v for k,v in n.items() if k not in ("id","name","type")}) for n in data.get("nodes",[]) if n.get("id")]
        edges = [GraphEdge(source=e.get("source",""), target=e.get("target",""), type=e.get("type",""),
                   properties={k:v for k,v in e.items() if k not in ("source","target","type")}) for e in data.get("edges",[]) if e.get("source") and e.get("target")]
        return GraphVisualizationResponse(nodes=nodes, edges=edges, stats=await neo4j_service.get_graph_stats())
    except Exception as e: logger.exception("graph_viz_failed", error=str(e)); raise HTTPException(500, str(e))


@router.post("/search")
async def search_graph(request: Request, search_request: GraphSearchRequest,
    current_user=Depends(get_current_user), access_context=Depends(get_access_context)):
    try:
        entities = await neo4j_service.search_entities(query=search_request.query, entity_type=search_request.entity_type,
            limit=search_request.limit, rbac_filter=rbac_service.build_cypher_filter(access_context))
        return {"success": True, "query": search_request.query, "count": len(entities), "entities": entities}
    except Exception as e: logger.exception("graph_search_failed", error=str(e)); raise HTTPException(500, str(e))


@router.get("/entity/{entity_name}")
async def get_entity_neighborhood(request: Request, entity_name: str, depth: int=Query(default=2,ge=1,le=5),
    limit: int=Query(default=50,ge=1,le=200), current_user=Depends(get_current_user), access_context=Depends(get_access_context)):
    try:
        data = await neo4j_service.get_entity_neighborhood(entity_name=entity_name, depth=depth, limit=limit,
            rbac_filter=rbac_service.build_cypher_filter(access_context))
        return {"success": True, "entity": entity_name, "nodes": data.get("nodes",[]), "edges": data.get("edges",[])}
    except Exception as e: logger.exception("entity_failed", error=str(e)); raise HTTPException(500, str(e))


@router.get("/stats")
async def get_graph_stats(current_user=Depends(get_current_user)):
    try:
        stats = await neo4j_service.get_graph_stats()
        qdrant_info = {}
        try:
            from app.services.qdrant_service import qdrant_service
            qdrant_info = await qdrant_service.get_collection_info()
        except Exception: pass
        return {"success": True, "graph": stats, "vectors": qdrant_info}
    except Exception as e: logger.exception("stats_failed", error=str(e)); raise HTTPException(500, str(e))


@router.delete("/clear")
async def clear_graph_data(current_user=Depends(get_current_user)):
    try:
        doc_ids = []
        try:
            async with neo4j_service.session() as s:
                records = await (await s.run("MATCH (d:Document) RETURN d.id AS doc_id")).data()
                doc_ids = [r["doc_id"] for r in records]
        except Exception: pass
        async with neo4j_service.session() as s: await s.run("MATCH (n) DETACH DELETE n")
        from app.services.qdrant_service import qdrant_service as qs
        from app.core.config import settings
        try: await qs._client.delete_collection(settings.QDRANT_COLLECTION)
        except Exception: pass
        await qs.initialize()
        for doc_id in doc_ids:
            try: s3_service.delete_document(doc_id)
            except Exception: pass
        # Clear file_metadata table in PostgreSQL (dedup check source)
        try:
            from app.services.database import database_service
            cleared_meta = database_service.clear_all_file_metadata()
            logger.info("file_metadata_cleared", count=cleared_meta)
        except Exception as e:
            logger.warning("file_metadata_clear_failed", error=str(e))
        logger.info("graph_cleared", user_id=current_user["user_id"], s3_docs=len(doc_ids))
        return {"success": True, "message": f"Граф, векторы, S3 и метаданные файлов очищены ({len(doc_ids)} док.)"}
    except Exception as e: logger.exception("clear_failed", error=str(e)); raise HTTPException(500, str(e))


@router.get("/documents")
async def get_documents(current_user=Depends(get_current_user), page: int=Query(default=1,ge=1), page_size: int=Query(default=20,ge=1,le=100),
    sort: str=Query(default="created_at"), order: str=Query(default="desc"),
    department: str=Query(default=""), clearance: int=Query(default=-1)):
    try:
        filters = []; params = {}
        if department and department!="all": filters.append("d.department=$department"); params["department"]=department
        if clearance>=0: filters.append("d.clearance_level=$clearance"); params["clearance"]=clearance
        wc = "WHERE " + " AND ".join(filters) if filters else ""
        sf = "d.created_at" if sort=="created_at" else "d.title"; so = "DESC" if order=="desc" else "ASC"
        params["skip"]=(page-1)*page_size; params["limit"]=page_size
        q = f"MATCH (d:Document) {wc} OPTIONAL MATCH (d)<-[:PART_OF]-(c:Chunk) RETURN d.id AS id, d.title AS title, d.clearance_level AS clearance, d.department AS department, count(c) AS chunks, d.created_at AS created_at ORDER BY {sf} {so} SKIP $skip LIMIT $limit"
        async with neo4j_service.session() as s:
            records=await (await s.run(q,**params)).data(); total=(await (await s.run(f"MATCH (d:Document) {wc} RETURN count(d) AS total",**{k:v for k,v in params.items() if k not in ('skip','limit')})).single())["total"]
        docs=[{"id":r["id"],"title":r["title"] or r["id"],"clearance_level":r["clearance"] or 0,"department":r["department"] or "all","chunks":r["chunks"],"created_at":r["created_at"].isoformat() if r["created_at"] else None} for r in records]
        return {"success":True,"documents":docs,"total":total,"page":page,"page_size":page_size}
    except Exception as e: logger.exception("docs_failed", error=str(e)); raise HTTPException(500, str(e))


@router.get("/document/{doc_id}/content")
async def download_document(doc_id: str, current_user=Depends(get_current_user)):
    """Скачивание: оригинальный файл из S3 → извлечённый текст из S3 → Neo4j full_text → чанки."""
    try:
        async with neo4j_service.session() as session:
            r = await session.run(
                "MATCH (d:Document {id:$id}) RETURN d.title AS title, d.s3_key AS s3_key, d.s3_original_key AS s3_original_key, d.original_filename AS original_filename, d.full_text AS full_text",
                id=doc_id)
            rec = await r.single()
            if not rec:
                raise HTTPException(404, "Документ не найден")
            title = rec["title"] or doc_id
            s3 = rec.get("s3_key")
            s3_original = rec.get("s3_original_key") or ""
            orig_fname = rec.get("original_filename") or ""
            ft = rec.get("full_text")

            # Уровень 1: оригинальный файл из S3 (если есть s3_original_key)
            if s3_original:
                try:
                    content_bytes, content_type, _ = s3_service.get_original(doc_id, s3_original_key=s3_original)
                    if content_bytes and len(content_bytes) > 0:
                        safe_filename = orig_fname if orig_fname else f"{title}.bin"
                        from urllib.parse import quote
                        encoded = quote(safe_filename)
                        logger.info("download_source", doc_id=doc_id, source="minio-original", size=len(content_bytes))
                        return Response(
                            content=content_bytes,
                            media_type=content_type,
                            headers={
                                "Content-Disposition": f"attachment; filename*=UTF-8''{encoded}",
                                "X-Download-Source": "minio-original",
                            })
                    else:
                        logger.warning("original_file_empty", doc_id=doc_id, key=s3_original)
                except Exception as e:
                    logger.warning("original_file_fallback", doc_id=doc_id, error=str(e))

            # Уровень 2: извлечённый текст из S3 (фоллбэк)
            if s3:
                try:
                    content_bytes = s3_service.get_document(doc_id)
                    if content_bytes and len(content_bytes) > 0:
                        content = content_bytes.decode("utf-8")
                        if content.strip():
                            logger.info("download_source", doc_id=doc_id, source="s3", size=len(content_bytes))
                            return _make_download_response(content, title, "minio-s3")
                        else:
                            logger.warning("s3_content_empty", doc_id=doc_id)
                    else:
                        logger.warning("s3_file_empty", doc_id=doc_id)
                except Exception as e:
                    logger.warning("s3_fallback", doc_id=doc_id, error=str(e))

            # Уровень 3: Neo4j full_text
            if ft and ft.strip():
                logger.info("download_source", doc_id=doc_id, source="neo4j_full_text", size=len(ft))
                return _make_download_response(ft, title, "neo4j-full_text")

            # Уровень 4: Сборка из чанков
            cr = await session.run(
                "MATCH (d:Document {id:$id})<-[:PART_OF]-(c:Chunk) RETURN c.text AS text ORDER BY c.position",
                id=doc_id)
            chunk_records = await cr.data()
            chunk_texts = [r["text"] for r in chunk_records if r.get("text") and r["text"].strip()]
            if chunk_texts:
                logger.info("download_source", doc_id=doc_id, source="neo4j_chunks", chunks=len(chunk_texts))
                return _make_download_response("\n\n".join(chunk_texts), title, "neo4j-chunks")

            # Документ пуст — возвращаем текстовый файл с пояснением
            logger.info("download_empty_return_placeholder", doc_id=doc_id, title=title)
            return _make_download_response(
                "Документ не содержит текстового содержимого.\n\n"
                "Этот файл был загружен как мета-запись без извлекаемого текста "
                "(например, пустой файл, бинарный файл без текстового слоя, "
                "или файл нулевого размера).",
                title,
                "empty-document"
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("download_failed", doc_id=doc_id, error=str(e))
        raise HTTPException(500, str(e))


@router.put("/document/{doc_id}")
async def update_document(doc_id: str, updates: dict, current_user=Depends(get_current_user)):
    """Обновление clearance_level и department документа в Neo4j + Qdrant."""
    try:
        clearance_level = updates.get("clearance_level", 0)
        department = updates.get("department", "all")

        # Update Neo4j Document node
        doc = await neo4j_service.update_document_access(doc_id=doc_id, clearance_level=clearance_level, department=department)
        if not doc:
            raise HTTPException(404, "Документ не найден")

        # Update Qdrant vectors
        try:
            from app.services.qdrant_service import qdrant_service as qs
            from app.core.config import settings as s
            await qs._client.set_payload(
                collection_name=s.QDRANT_COLLECTION,
                payload={"clearance_level": clearance_level, "department": department},
                points=models.FilterSelector(filter=models.Filter(must=[models.FieldCondition(key="document_id", match=models.MatchValue(value=doc_id))])),
            )
        except Exception as e:
            logger.warning("qdrant_update_failed", doc_id=doc_id, error=str(e))

        logger.info("document_updated", doc_id=doc_id, clearance=clearance_level, department=department)
        return {"success": True, "message": "Документ обновлён"}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("update_failed", error=str(e))
        raise HTTPException(500, str(e))


@router.delete("/document/{doc_id}")
async def delete_document(doc_id: str, current_user=Depends(get_current_user)):
    """Удаление документа: Neo4j + Qdrant + S3."""
    try:
        async with neo4j_service.session() as s:
            await s.run("MATCH (d:Document {id:$doc_id}) OPTIONAL MATCH (d)<-[:PART_OF]-(c:Chunk) OPTIONAL MATCH (c)<-[:MENTIONED_IN]-(e:Entity) DETACH DELETE e,c,d", doc_id=doc_id)
        from app.services.qdrant_service import qdrant_service as qs
        try: await qs.delete_by_document(doc_id)
        except Exception: pass
        try: s3_service.delete_document(doc_id)
        except Exception: pass
        from app.services.database import database_service
        try: database_service.delete_file_metadata_by_document(doc_id)
        except Exception: pass
        logger.info("document_deleted", doc_id=doc_id)
        return {"success": True, "message": "Документ удалён (Neo4j + Qdrant + S3 + file_metadata)"}
    except Exception as e: logger.exception("delete_failed", error=str(e)); raise HTTPException(500, str(e))