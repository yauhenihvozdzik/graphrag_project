"""File metadata model for duplicate detection on upload."""

from datetime import UTC, datetime
from typing import Optional

from sqlmodel import Field

from app.models.base import BaseModel


class FileMetadata(BaseModel, table=True):
    """Tracks uploaded file metadata to prevent duplicate ingestion.

    Attributes:
        id: Primary key (auto-increment).
        filename: Original filename.
        file_size: File size in bytes.
        file_modified: Last modification timestamp of the source file.
        document_id: Linked Neo4j/S3 document ID after successful ingestion.
        uploaded_at: When the file was uploaded.
        status: Ingestion status (pending, completed, failed).
    """

    id: Optional[int] = Field(default=None, primary_key=True)
    filename: str
    file_size: int
    file_modified: Optional[datetime] = Field(default=None)
    document_id: Optional[str] = Field(default=None, index=True)
    uploaded_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    status: str = Field(default="pending")