"""Azure DevOps Wiki repository document import service.

Uses Azure DevOps REST API (with PAT token) to list and download .md files
from a Wiki git repository, then imports each document via GraphRAG pipeline.
"""

import asyncio
import base64
import re
import uuid

import httpx

from app.core.logging import logger


def _decode_wiki_title(filename_stem: str) -> str:
    """Decode Azure DevOps Wiki filename to human-readable title.

    Wiki encodes special characters: - → space, %20 → space, etc.
    """
    try:
        from urllib.parse import unquote
        title = unquote(filename_stem)
    except Exception:
        title = filename_stem

    title = title.replace("-", " ")
    title = re.sub(r"\s+", " ", title).strip()
    return title


def _parse_azure_devops_url(repo_url: str) -> dict:
    """Parse Azure DevOps Wiki URL into components.

    Example: https://azure.shate-m.by/IT/Sandbox%20-%20General/_git/Sandbox---General.wiki

    Returns: {base_url, collection, project, repo_name}
    """
    # Remove trailing slash
    url = repo_url.rstrip("/")

    # Split: https://host/collection/project/_git/repo.wiki
    parts = url.split("/")
    if len(parts) < 6:
        raise ValueError(f"Invalid Azure DevOps URL: {repo_url}")

    base_url = "/".join(parts[:3])  # https://host
    collection = parts[3]  # IT
    project = parts[4]  # Sandbox%20-%20General
    # Skip _git
    repo_name = parts[6] if len(parts) > 6 else ""  # Sandbox---General.wiki

    return {
        "base_url": base_url,
        "collection": collection,
        "project": project,
        "repo_name": repo_name,
    }


async def clone_and_import_wiki(
    repo_url: str,
    pat_token: str = "",
    clearance_level: int = 0,
    department: str = "all",
) -> dict:
    """Download all .md files from Azure DevOps Wiki via REST API and import them.

    Args:
        repo_url: URL of Azure DevOps Wiki git repository
        pat_token: Personal Access Token for authentication
        clearance_level: Default clearance level for imported docs
        department: Default department for imported docs

    Returns:
        Dict with import results: {total_documents, documents, errors, message}
    """
    import_result = {
        "total_documents": 0,
        "documents": [],
        "errors": [],
        "message": "",
    }

    try:
        # Parse URL
        parsed = _parse_azure_devops_url(repo_url)
        base_url = parsed["base_url"]
        collection = parsed["collection"]
        project = parsed["project"]
        repo_name = parsed["repo_name"]

        # Build auth headers
        auth_headers = {}
        if pat_token:
            auth_bytes = f":{pat_token}".encode("utf-8")
            auth_b64 = base64.b64encode(auth_bytes).decode("utf-8")
            auth_headers["Authorization"] = f"Basic {auth_b64}"

        logger.info("azure_wiki_fetching_file_list", repo_url=repo_url)

        # Step 1: Get list of all files in the repository via REST API
        # Azure DevOps REST API: GET {base}/{collection}/{project}/_apis/git/repositories/{repo}/items?recursionLevel=full&api-version=7.1
        items_url = (
                    f"{base_url}/{collection}/{project}/_apis/git/repositories"
                    f"/{repo_name}/items"
                    f"?recursionLevel=full&api-version=6.0"
                )

        async with httpx.AsyncClient(timeout=120, verify=False) as client:
            resp = await client.get(items_url, headers=auth_headers)
            resp.raise_for_status()
            items_data = resp.json()

        files = [item for item in items_data.get("value", [])
                 if item.get("path", "").endswith(".md") and not item.get("isFolder")]

        if not files:
            import_result["message"] = "В репозитории не найдено .md файлов"
            return import_result

        logger.info("azure_wiki_documents_found", count=len(files))

        # Step 2: Download each .md file content and import
        from app.core.graphrag.document_ingestion import ingestion_service
        from app.core.graphrag.entity_extraction import entity_extraction_service
        from app.core.graphrag.graph_builder import graph_builder_service
        from app.core.graphrag.vector_indexer import vector_indexer_service
        from app.services.neo4j_service import neo4j_service
        from app.services.ollama_service import ollama_service
        from app.services.qdrant_service import qdrant_service

        imported_count = 0
        for file_item in files:
            try:
                file_path = file_item["path"]
                # Skip empty files
                # Get file content via REST API
                content_url = (
                                    f"{base_url}/{collection}/{project}/_apis/git/repositories"
                                    f"/{repo_name}/items"
                                    f"?path={file_path}&includeContent=true&api-version=6.0"
                                )

                async with httpx.AsyncClient(timeout=120, verify=False) as client:
                    resp = await client.get(content_url, headers=auth_headers)
                    resp.raise_for_status()
                    content = resp.text

                if not content or not content.strip():
                    logger.info("azure_wiki_skip_empty", path=file_path)
                    continue

                # Build title from filename
                filename_stem = file_path.rsplit("/", 1)[-1].replace(".md", "")
                title = _decode_wiki_title(filename_stem)

                doc_id = f"wiki_{uuid.uuid4().hex[:12]}"

                logger.info(
                    "azure_wiki_importing_doc",
                    title=title,
                    path=file_path,
                    content_length=len(content),
                )

                # Step 1: Ingest text + upload to S3
                _, chunks, s3_key = await ingestion_service.ingest_text(
                    text=content,
                    title=title,
                    doc_id=doc_id,
                    source=f"azure-wiki:{file_path}",
                    metadata={
                        "wiki_path": file_path,
                        "original_repo": repo_url,
                        "import_type": "azure-wiki",
                    },
                    clearance_level=clearance_level,
                    department=department,
                )

                # Step 2: Entity extraction
                extraction_results = await entity_extraction_service.extract_from_chunks(
                    chunks=chunks,
                    ollama_service=None,
                    use_llm=False,
                )
                entities_count = sum(len(r.entities) for r in extraction_results)

                # Step 3: Build graph
                await graph_builder_service.build_from_extraction(
                    document_id=doc_id,
                    title=title,
                    source=f"azure-wiki:{file_path}",
                    extraction_results=extraction_results,
                    chunks=chunks,
                    neo4j_service=neo4j_service,
                    clearance_level=clearance_level,
                    department=department,
                    metadata={"wiki_path": file_path},
                    s3_key=s3_key,
                )

                # Step 4: Index vectors
                vectors_indexed = await vector_indexer_service.index_chunks(
                    chunks=chunks,
                    ollama_service=ollama_service,
                    qdrant_service=qdrant_service,
                    clearance_level=clearance_level,
                    department=department,
                )

                imported_count += 1
                import_result["documents"].append({
                    "document_id": doc_id,
                    "title": title,
                    "wiki_path": file_path,
                    "chunks": len(chunks),
                    "entities": entities_count,
                    "vectors": vectors_indexed,
                    "status": "imported",
                })

                logger.info(
                    "azure_wiki_doc_imported",
                    title=title,
                    doc_id=doc_id,
                    chunks=len(chunks),
                    entities=entities_count,
                )

            except Exception as e:
                error_detail = f"{file_item.get('path', 'unknown')}: {str(e)}"
                logger.exception("azure_wiki_doc_import_failed", error=error_detail)
                import_result["errors"].append(error_detail)

        import_result["total_documents"] = imported_count
        import_result["success"] = True
        import_result["message"] = (
            f"Импортировано {imported_count} из {len(files)} документов"
        )

        if import_result["errors"]:
            import_result["message"] += f" ({len(import_result['errors'])} ошибок)"

        logger.info(
            "azure_wiki_import_completed",
            total=imported_count,
            found=len(files),
            errors=len(import_result["errors"]),
        )

    except Exception as e:
        logger.exception("azure_wiki_import_failed", error=str(e))
        import_result["errors"].append(f"Critical error: {str(e)}")
        import_result["message"] = f"Критическая ошибка: {str(e)}"

    return import_result
