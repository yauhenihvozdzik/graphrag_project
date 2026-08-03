"""Azure DevOps Wiki repository cloning and document import service.

Clones a Wiki git repository, parses .md files respecting .order files,
and imports each document into the GraphRAG ingestion pipeline.
"""

import asyncio
import os
import re
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import Optional

from app.core.logging import logger


def _read_order_file(directory: Path) -> list[str]:
    """Read .order file from a Wiki directory, return ordered list of filenames.
    
    Azure DevOps Wiki uses .order files to define page ordering.
    Lines starting with # are comments.
    """
    order_file = directory / ".order"
    if not order_file.exists():
        return []
    
    lines = order_file.read_text(encoding="utf-8", errors="ignore").strip().splitlines()
    result = []
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        result.append(line)
    return result


def _parse_wiki_structure(repo_dir: Path) -> list[dict]:
    """Walk through cloned Wiki repo, build ordered list of documents.
    
    Returns list of dicts: {path, title, order_index, content}
    respecting .order files for ordering.
    """
    documents: list[dict] = []
    
    # Process root .order for top-level ordering
    root_order = _read_order_file(repo_dir)
    root_order_map = {name: idx for idx, name in enumerate(root_order)}
    
    # Collect all .md files in repository with their relative paths
    md_files: list[Path] = []
    for root, dirs, files in os.walk(repo_dir):
        # Skip .git directory
        if ".git" in root.split(os.sep):
            continue
        for fname in sorted(files):
            if fname.endswith(".md"):
                md_files.append(Path(root) / fname)
    
    # Build relative paths and determine order
    for fpath in md_files:
        rel_path = fpath.relative_to(repo_dir)
        parent_dir = rel_path.parent
        
        # Determine title from filename (remove .md, decode URL-encoded chars)
        title = _decode_wiki_title(fpath.stem)
        
        # Read file content
        try:
            content = fpath.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            content = ""
        
        if not content.strip():
            logger.info("azure_wiki_skip_empty", path=str(rel_path))
            continue
        
        # Determine order: check parent directory's .order first
        order_index = 9999
        parent_order_file = repo_dir / parent_dir / ".order"
        if parent_order_file.exists():
            parent_order = _read_order_file(repo_dir / parent_dir)
            if fpath.name in parent_order:
                order_index = parent_order.index(fpath.name)
        elif str(parent_dir) == "." and fpath.name in root_order_map:
            order_index = root_order_map[fpath.name]
        
        documents.append({
            "path": str(rel_path),
            "title": title,
            "order_index": order_index,
            "content": content,
        })
    
    # Sort by parent directory depth, then order_index
    documents.sort(key=lambda d: (
        len(Path(d["path"]).parent.parts),
        d["order_index"],
        d["title"],
    ))
    
    return documents


def _decode_wiki_title(filename_stem: str) -> str:
    """Decode Azure DevOps Wiki filename to human-readable title.
    
    Wiki encodes special characters: - → space, %20 → space, etc.
    Example: 'БЗ-РАЗРАБОТЧИКА' → 'БЗ РАЗРАБОТЧИКА'
    """
    # URL-decode
    try:
        from urllib.parse import unquote
        title = unquote(filename_stem)
    except Exception:
        title = filename_stem
    
    # Replace hyphens with spaces (Wiki convention)
    title = title.replace("-", " ")
    
    # Clean up multiple spaces
    title = re.sub(r"\s+", " ", title).strip()
    
    return title


def _build_auth_url(repo_url: str, pat_token: str = "", username: str = "", password: str = "") -> str:
    """Build authenticated git clone URL from Azure DevOps Wiki URL.
    
    Args:
        repo_url: Full Azure DevOps Wiki git URL
        pat_token: Personal Access Token (empty for anonymous)
        username: Username for Basic Auth (alternative to PAT)
        password: Password for Basic Auth (alternative to PAT)
    
    Returns:
        Authenticated URL for git clone.
    """
    from urllib.parse import quote
    
    if pat_token:
        # PAT token auth — encode token and embed in URL
        encoded_token = quote(pat_token, safe='')
        if repo_url.startswith("https://"):
            return repo_url.replace("https://", f"https://:{encoded_token}@")
    elif username and password:
        # Basic Auth — URL-encode credentials to handle special chars (!@# etc.)
        encoded_user = quote(username, safe='')
        encoded_pass = quote(password, safe='')
        if repo_url.startswith("https://"):
            return repo_url.replace(
                "https://",
                f"https://{encoded_user}:{encoded_pass}@",
            )
    
    return repo_url


async def clone_and_import_wiki(
    repo_url: str,
    pat_token: str = "",
    username: str = "",
    password: str = "",
    clearance_level: int = 0,
    department: str = "all",
) -> dict:
    """Clone Azure DevOps Wiki repo and import all .md documents.
    
    Args:
        repo_url: URL of Azure DevOps Wiki git repository
        pat_token: Optional PAT for authentication
        username: Username for Basic Auth (alternative to PAT)
        password: Password for Basic Auth (alternative to PAT)
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
    
    # Create temp directory for cloning
    tmpdir = tempfile.mkdtemp(prefix="azure_wiki_")
    
    try:
        # Build authenticated URL
        auth_url = _build_auth_url(repo_url, pat_token, username, password)
        
        logger.info("azure_wiki_cloning_started", url=repo_url)
        
        # Clone repository (shallow, no blobs for speed)
        clone_cmd = [
            "git", "clone", "--depth", "1", "--filter=blob:none",
            auth_url, tmpdir,
        ]
        
        env = os.environ.copy()
        env["GIT_TERMINAL_PROMPT"] = "0"
        env["GCM_INTERACTIVE"] = "Never"
        
        result = subprocess.run(
            clone_cmd,
            capture_output=True,
            text=True,
            timeout=300,
            env=env,
        )
        
        if result.returncode != 0:
            stderr = result.stderr[:1000] if result.stderr else "Unknown error"
            error_msg = f"Git clone failed: {stderr}"
            logger.error("azure_wiki_clone_failed", error=stderr)
            import_result["errors"].append(error_msg)
            import_result["message"] = error_msg
            return import_result
        
        logger.info("azure_wiki_cloned_successfully", tmpdir=tmpdir)
        
        # Parse wiki structure
        wiki_dir = Path(tmpdir)
        documents = _parse_wiki_structure(wiki_dir)
        
        logger.info("azure_wiki_documents_found", count=len(documents))
        
        # Import documents one by one
        from app.core.graphrag.document_ingestion import ingestion_service
        from app.core.graphrag.entity_extraction import entity_extraction_service
        from app.core.graphrag.graph_builder import graph_builder_service
        from app.core.graphrag.vector_indexer import vector_indexer_service
        from app.services.neo4j_service import neo4j_service
        from app.services.ollama_service import ollama_service
        from app.services.qdrant_service import qdrant_service
        
        imported_count = 0
        for doc in documents:
            try:
                doc_id = f"wiki_{uuid.uuid4().hex[:12]}"
                title = doc["title"]
                content = doc["content"]
                wiki_path = doc["path"]
                
                logger.info(
                    "azure_wiki_importing_doc",
                    title=title,
                    path=wiki_path,
                    content_length=len(content),
                )
                
                # Step 1: Ingest text + upload to S3
                _, chunks, s3_key = await ingestion_service.ingest_text(
                    text=content,
                    title=title,
                    doc_id=doc_id,
                    source=f"azure-wiki:{wiki_path}",
                    metadata={
                        "wiki_path": wiki_path,
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
                    source=f"azure-wiki:{wiki_path}",
                    extraction_results=extraction_results,
                    chunks=chunks,
                    neo4j_service=neo4j_service,
                    clearance_level=clearance_level,
                    department=department,
                    metadata={"wiki_path": wiki_path},
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
                    "wiki_path": wiki_path,
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
                error_detail = f"{doc['title']} ({doc['path']}): {str(e)}"
                logger.exception("azure_wiki_doc_import_failed", error=error_detail)
                import_result["errors"].append(error_detail)
                import_result["documents"].append({
                    "title": doc["title"],
                    "wiki_path": doc["path"],
                    "status": "failed",
                    "error": str(e),
                })
        
        import_result["total_documents"] = imported_count
        import_result["success"] = True
        import_result["message"] = (
            f"Импортировано {imported_count} из {len(documents)} документов"
        )
        
        if import_result["errors"]:
            import_result["message"] += f" ({len(import_result['errors'])} ошибок)"
        
        logger.info(
            "azure_wiki_import_completed",
            total=imported_count,
            found=len(documents),
            errors=len(import_result["errors"]),
        )
        
    except Exception as e:
        logger.exception("azure_wiki_import_failed", error=str(e))
        import_result["errors"].append(f"Critical error: {str(e)}")
        import_result["message"] = f"Критическая ошибка: {str(e)}"
    
    finally:
        # Cleanup temp directory
        try:
            shutil.rmtree(tmpdir, ignore_errors=True)
        except Exception:
            pass
    
    return import_result
