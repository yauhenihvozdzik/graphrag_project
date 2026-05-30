"""MinIO/S3 document storage service for GraphRAG platform."""

from pathlib import Path

import boto3
from botocore.config import Config
from fastapi import HTTPException

from app.core.config import settings
from app.core.logging import logger


class S3Service:
    def __init__(self):
        self._client = None

    def _get_client(self):
        if self._client is None:
            self._client = boto3.client(
                "s3",
                endpoint_url=settings.S3_ENDPOINT,
                aws_access_key_id=settings.S3_ACCESS_KEY,
                aws_secret_access_key=settings.S3_SECRET_KEY,
                region_name=settings.S3_REGION,
                config=Config(signature_version="s3v4"),
            )
            self._ensure_bucket()
        return self._client

    def _ensure_bucket(self):
        try:
            self._client.head_bucket(Bucket=settings.S3_BUCKET)
        except Exception:
            self._client.create_bucket(Bucket=settings.S3_BUCKET)
            logger.info("s3_bucket_created", bucket=settings.S3_BUCKET)

    def upload_original(self, doc_id: str, filename: str, file_bytes: bytes, content_type: str = "application/octet-stream") -> str:
        """Upload the original binary file to S3. Returns S3 object key."""
        safe_name = Path(filename).name if filename else "original.bin"
        ext = Path(safe_name).suffix if "." in safe_name else ".bin"
        key = f"documents/{doc_id}/original{ext}"
        try:
            self._get_client().put_object(
                Bucket=settings.S3_BUCKET,
                Key=key,
                Body=file_bytes,
                ContentType=content_type,
            )
            logger.info("s3_original_uploaded", document_id=doc_id, key=key)
            return key
        except Exception as e:
            logger.exception("s3_original_upload_failed", document_id=doc_id, error=str(e))
            raise HTTPException(500, "Ошибка сохранения оригинального файла в S3")

    def get_original(self, doc_id: str, s3_original_key: str = "") -> tuple[bytes, str, str]:
        """Get original binary file from S3. Returns (bytes, content_type, filename)."""
        from pathlib import Path
        # If exact key is known, use it directly
        if s3_original_key:
            try:
                resp = self._get_client().get_object(Bucket=settings.S3_BUCKET, Key=s3_original_key)
                body = resp["Body"].read()
                ct = resp.get("ContentType", "application/octet-stream")
                fname = Path(s3_original_key).name
                logger.info("s3_original_downloaded", document_id=doc_id, key=s3_original_key)
                return body, ct, fname
            except Exception:
                pass  # fall through to generic search
        raise HTTPException(404, "Оригинальный файл не найден в хранилище")

    def upload_document(self, doc_id: str, content: str, content_type: str = "text/plain") -> str:
        """Upload document content to S3. Returns S3 object key."""
        key = f"documents/{doc_id}/original.txt"
        try:
            self._get_client().put_object(
                Bucket=settings.S3_BUCKET,
                Key=key,
                Body=content.encode("utf-8"),
                ContentType=content_type,
            )
            logger.info("s3_upload_completed", document_id=doc_id, key=key)
            return key
        except Exception as e:
            logger.exception("s3_upload_failed", document_id=doc_id, error=str(e))
            raise HTTPException(500, "Ошибка сохранения документа в S3")

    def get_document(self, doc_id: str) -> bytes:
        """Get document content from S3 by doc_id."""
        key = f"documents/{doc_id}/original.txt"
        try:
            resp = self._get_client().get_object(Bucket=settings.S3_BUCKET, Key=key)
            return resp["Body"].read()
        except Exception as e:
            logger.exception("s3_download_failed", document_id=doc_id, error=str(e))
            raise HTTPException(404, "Документ не найден в хранилище")

    def delete_document(self, doc_id: str):
        """Delete all document objects from S3 (text + original)."""
        keys = [f"documents/{doc_id}/original.txt"]
        # Also try to delete original binary file with common extensions
        for ext in [".pdf", ".docx", ".doc", ".txt", ".zip", ".png", ".jpg", ".xml", ".json", ".csv", ".html", ".md", ".bin"]:
            keys.append(f"documents/{doc_id}/original{ext}")
        for key in keys:
            try:
                self._get_client().delete_object(Bucket=settings.S3_BUCKET, Key=key)
                logger.info("s3_document_deleted", document_id=doc_id, key=key)
            except Exception as e:
                pass


s3_service = S3Service()