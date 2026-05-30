"""Document ingestion pipeline for GraphRAG.

Supports PDF, DOCX, TXT, MD, XML, ZIP archives, and plain text input.
Original documents are stored in MinIO/S3 — Neo4j holds only the s3_key.
"""

import hashlib
import re
import tempfile
import zipfile
import io
import subprocess
import shutil
import os
from pathlib import Path
from typing import Optional

from app.core.config import settings
from app.core.logging import logger
from app.core.metrics import documents_ingested_total
from app.services.s3_service import s3_service


class TextChunk:
    def __init__(self, chunk_id: str, document_id: str, text: str, position: int, metadata: Optional[dict] = None):
        self.chunk_id = chunk_id; self.document_id = document_id; self.text = text; self.position = position; self.metadata = metadata or {}


SUPPORTED_SUFFIXES = {'.txt', '.md', '.pdf', '.docx', '.doc', '.xml', '.json', '.csv', '.html', '.py', '.js', '.ts', '.yaml', '.yml'}


class DocumentIngestionService:
    def __init__(self):
        self.chunk_size = settings.CHUNK_SIZE; self.chunk_overlap = settings.CHUNK_OVERLAP

    async def ingest_text(
        self, text: str, title: str, doc_id: str = "",
        source: str = "upload", metadata: Optional[dict] = None,
        clearance_level: int = 0, department: str = "all",
    ) -> tuple[str, list[TextChunk], str]:
        doc_id = doc_id or self._generate_doc_id(text, title)
        logger.info("ingestion_started", document_id=doc_id, title=title, text_length=len(text))
        s3_key = s3_service.upload_document(doc_id, text)
        clean_text = self._preprocess_text(text)
        chunks = self._chunk_text(clean_text, doc_id=doc_id, metadata={
            **(metadata or {}), "title": title, "source": source,
            "clearance_level": clearance_level, "department": department,
        })
        documents_ingested_total.labels(status="success").inc()
        logger.info("ingestion_completed", document_id=doc_id, chunks_count=len(chunks))
        return doc_id, chunks, s3_key

    async def ingest_file(
        self, file_path: Path, doc_id: str = "", title: Optional[str] = None,
        metadata: Optional[dict] = None, clearance_level: int = 0, department: str = "all",
    ) -> tuple[str, list[TextChunk], str]:
        if not file_path.exists(): raise FileNotFoundError(f"Файл не найден: {file_path}")
        title = title or file_path.stem; suffix = file_path.suffix.lower()
        # ZIP archive — extract and combine
        if suffix == ".zip":
            return await self._ingest_zip_file(file_path, title, doc_id, clearance_level, department, metadata)
        original_bytes = file_path.read_bytes()
        text = await self._extract_text(file_path, suffix)
        doc_id = doc_id or self._generate_doc_id(text, title)
        # Save original binary + extracted text
        metadata = metadata or {}
        original_fname = metadata.get("original_filename", file_path.name)
        original_key = s3_service.upload_original(doc_id, original_fname, original_bytes)
        s3_key = s3_service.upload_document(doc_id, text)
        metadata["s3_original_key"] = original_key
        metadata["original_filename"] = original_fname
        clean_text = self._preprocess_text(text)
        chunks = self._chunk_text(clean_text, doc_id=doc_id, metadata={
            **(metadata or {}), "title": title, "source": str(file_path), "file_type": suffix,
            "clearance_level": clearance_level, "department": department,
        })
        documents_ingested_total.labels(status="success").inc()
        logger.info("ingestion_completed", document_id=doc_id, chunks_count=len(chunks))
        return doc_id, chunks, s3_key

    async def ingest_url(
        self, url: str, title: str, doc_id: str = "",
        clearance_level: int = 0, department: str = "all",
    ) -> tuple[str, list[TextChunk], str]:
        import httpx
        async with httpx.AsyncClient(timeout=600, follow_redirects=True) as client:
            resp = await client.get(url); resp.raise_for_status()
            content_type = resp.headers.get("content-type", "")

        # ZIP archive handling — only use system unzip
        if url.lower().endswith(".zip") or "application/zip" in content_type or "application/x-zip" in content_type:
            return await self._ingest_zip(url, title, doc_id, clearance_level, department, resp)

        raw = resp.text
        if "xml" in content_type or url.endswith(".xml") or "<" in raw[:200]:
            raw = re.sub(r"<[^>]+>", " ", raw); raw = re.sub(r"&[a-z]+;", " ", raw); raw = re.sub(r"\s+", " ", raw)
        text = raw.strip()
        doc_id = doc_id or self._generate_doc_id(text, title)
        s3_key = s3_service.upload_document(doc_id, text)
        clean_text = self._preprocess_text(text)
        chunks = self._chunk_text(clean_text, doc_id=doc_id, metadata={
            "title": title, "source": url, "url": url, "content_type": content_type,
            "clearance_level": clearance_level, "department": department,
        })
        documents_ingested_total.labels(status="success").inc()
        logger.info("ingestion_completed", document_id=doc_id, chunks_count=len(chunks))
        return doc_id, chunks, s3_key

    async def _ingest_zip_file(
        self, file_path: Path, title: str, doc_id: str,
        clearance_level: int, department: str, metadata: Optional[dict] = None,
    ) -> tuple[str, list[TextChunk], str]:
        """Extract uploaded ZIP file and process supported files inside."""
        import subprocess, os, tempfile
        logger.info("zip_file_ingestion_started", path=str(file_path), title=title)
        all_texts = []
        file_count = 0

        with tempfile.TemporaryDirectory() as tmpdir:
            extract_dir = os.path.join(tmpdir, 'extracted')
            os.makedirs(extract_dir, exist_ok=True)

            result = subprocess.run(
                ['unzip', '-o', '-q', str(file_path), '-d', extract_dir],
                capture_output=True, timeout=600
            )
            if result.returncode != 0:
                stderr = result.stderr.decode('utf-8', errors='replace')[:500]
                try:
                    result2 = subprocess.run(
                        ['7z', 'x', f'-o{extract_dir}', '-y', str(file_path)],
                        capture_output=True, timeout=600
                    )
                    if result2.returncode != 0:
                        err2 = result2.stderr.decode('utf-8', errors='replace')[:500]
                        raise RuntimeError(f"unzip failed: {stderr}. 7z failed: {err2}")
                except FileNotFoundError:
                    raise RuntimeError(f"unzip failed: {stderr}. Install 7z or unzip.")

            for root, dirs, files in os.walk(extract_dir):
                for fname in files:
                    fpath = Path(root) / fname
                    suffix = fpath.suffix.lower()
                    if suffix not in SUPPORTED_SUFFIXES:
                        continue
                    file_count += 1
                    try:
                        text = await self._extract_text(fpath, suffix)
                        rel_name = str(fpath.relative_to(extract_dir))
                        all_texts.append(f"=== {rel_name} ===\n{text}")
                    except Exception as e:
                        logger.warning("zip_file_extract_failed", file=fname, error=str(e))

        if not all_texts:
            raise ValueError("В архиве не найдено подходящих файлов (txt, md, pdf, docx, xml, json, csv, html, py, yml)")

        combined = "\n\n".join(all_texts)
        doc_id = doc_id or self._generate_doc_id(combined, title)
        s3_key = s3_service.upload_document(doc_id, combined)
        clean_text = self._preprocess_text(combined)
        chunks = self._chunk_text(clean_text, doc_id=doc_id, metadata={
            **(metadata or {}), "title": title, "source": str(file_path), "content_type": "application/zip",
            "clearance_level": clearance_level, "department": department,
            "zip_files_count": file_count,
        })
        documents_ingested_total.labels(status="success").inc()
        logger.info("zip_file_ingestion_completed", document_id=doc_id, chunks_count=len(chunks), files=file_count)
        return doc_id, chunks, s3_key

    async def _ingest_zip(
        self, url: str, title: str, doc_id: str,
        clearance_level: int, department: str, resp
    ) -> tuple[str, list[TextChunk], str]:
        """Download ZIP, extract with system unzip, combine text from all supported files."""
        logger.info("zip_ingestion_started", url=url, title=title)

        # Get raw bytes
        if hasattr(resp, 'content'):
            zip_bytes = resp.content
        else:
            zip_bytes = await resp.aread()

        all_texts = []
        file_count = 0

        with tempfile.TemporaryDirectory() as tmpdir:
            zip_tmp = os.path.join(tmpdir, 'archive.zip')
            with open(zip_tmp, 'wb') as f:
                f.write(zip_bytes)

            extract_dir = os.path.join(tmpdir, 'extracted')
            os.makedirs(extract_dir, exist_ok=True)

            # Use system unzip only — handles multi-disk/spanned/Zip64
            result = subprocess.run(
                ['unzip', '-o', '-q', zip_tmp, '-d', extract_dir],
                capture_output=True, timeout=600
            )

            if result.returncode != 0:
                stderr = result.stderr.decode('utf-8', errors='replace')[:500]
                # Try 7z as fallback
                try:
                    result2 = subprocess.run(
                        ['7z', 'x', f'-o{extract_dir}', '-y', zip_tmp],
                        capture_output=True, timeout=600
                    )
                    if result2.returncode != 0:
                        err2 = result2.stderr.decode('utf-8', errors='replace')[:500]
                        raise RuntimeError(f"unzip failed: {stderr}. 7z failed: {err2}")
                except FileNotFoundError:
                    raise RuntimeError(f"unzip failed: {stderr}. Install 7z or unzip.")

            # Walk and extract text
            for root, dirs, files in os.walk(extract_dir):
                for fname in files:
                    fpath = Path(root) / fname
                    suffix = fpath.suffix.lower()
                    if suffix not in SUPPORTED_SUFFIXES:
                        continue
                    file_count += 1
                    try:
                        text = await self._extract_text(fpath, suffix)
                        rel_name = str(fpath.relative_to(extract_dir))
                        all_texts.append(f"=== {rel_name} ===\n{text}")
                    except Exception as e:
                        logger.warning("zip_file_extract_failed", file=fname, error=str(e))

        if not all_texts:
            raise ValueError("В архиве не найдено подходящих файлов (txt, md, pdf, docx, xml, json, csv, html, py, yml)")

        combined = "\n\n".join(all_texts)
        doc_id = doc_id or self._generate_doc_id(combined, title)
        s3_key = s3_service.upload_document(doc_id, combined)
        clean_text = self._preprocess_text(combined)
        chunks = self._chunk_text(clean_text, doc_id=doc_id, metadata={
            "title": title, "source": url, "url": url, "content_type": "application/zip",
            "clearance_level": clearance_level, "department": department,
            "zip_files_count": file_count,
        })
        documents_ingested_total.labels(status="success").inc()
        logger.info("zip_ingestion_completed", document_id=doc_id, chunks_count=len(chunks), files=file_count)
        return doc_id, chunks, s3_key

    async def _extract_text(self, file_path: Path, suffix: str) -> str:
        if suffix in (".txt", ".md", ".json", ".csv", ".html", ".py", ".js", ".ts", ".yaml", ".yml"):
            return file_path.read_text(encoding="utf-8", errors="ignore")
        elif suffix == ".pdf":
            try:
                import pymupdf; doc = pymupdf.open(str(file_path))
                parts = [page.get_text() for page in doc]; doc.close(); return "\n\n".join(parts)
            except ImportError: return file_path.read_text(encoding="utf-8", errors="ignore")
        elif suffix in (".docx", ".doc"):
            try:
                from docx import Document; doc = Document(str(file_path))
                return "\n\n".join([p.text for p in doc.paragraphs if p.text.strip()])
            except ImportError: raise ValueError("python-docx не установлен")
        elif suffix == ".xml":
            raw = file_path.read_text(encoding="utf-8", errors="ignore")
            raw = re.sub(r"<[^>]+>", " ", raw); raw = re.sub(r"&[a-z]+;", " ", raw); raw = re.sub(r"\s+", " ", raw)
            return raw.strip()
        return file_path.read_text(encoding="utf-8", errors="ignore")

    def _preprocess_text(self, text: str) -> str:
        text = re.sub(r"\s+", " ", text); text = re.sub(r"\n\s*\d+\s*\n", "\n", text)
        text = text.replace("\u00ab", '"').replace("\u00bb", '"'); text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    def _chunk_text(self, text: str, doc_id: str, metadata: Optional[dict] = None) -> list[TextChunk]:
        sentences = re.split(r"(?<=[.!?])\s+", text)
        chunks: list[TextChunk] = []; current_chunk: list[str] = []; current_length = 0; position = 0
        for sentence in sentences:
            sentence_len = len(sentence)
            if current_length + sentence_len > self.chunk_size and current_chunk:
                chunk_text = " ".join(current_chunk)
                chunks.append(TextChunk(chunk_id=f"{doc_id}_chunk_{position}", document_id=doc_id, text=chunk_text, position=position, metadata=metadata))
                position += 1
                overlap_chars = 0; overlap_start = len(current_chunk)
                for i in range(len(current_chunk) - 1, -1, -1):
                    overlap_chars += len(current_chunk[i])
                    if overlap_chars >= self.chunk_overlap: overlap_start = i; break
                current_chunk = current_chunk[overlap_start:]; current_length = sum(len(s) for s in current_chunk)
            current_chunk.append(sentence); current_length += sentence_len
        if current_chunk:
            chunks.append(TextChunk(chunk_id=f"{doc_id}_chunk_{position}", document_id=doc_id, text=" ".join(current_chunk), position=position, metadata=metadata))
        return chunks

    def _generate_doc_id(self, text: str, title: str) -> str:
        return f"doc_{hashlib.sha256(f'{title}:{text[:1000]}'.encode()).hexdigest()[:12]}"


ingestion_service = DocumentIngestionService()