"""Qdrant vector database service for GraphRAG platform.

Manages vector storage, similarity search, and collection management
for document chunk embeddings (BAAI/bge-m3 1024-dim vectors).
"""

import time
import uuid
from typing import Any, Optional

from qdrant_client import AsyncQdrantClient, models
from qdrant_client.http.exceptions import UnexpectedResponse

from app.core.config import settings
from app.core.logging import logger
from app.core.metrics import vector_search_duration_seconds


class QdrantService:
    """Async Qdrant client wrapper with collection lifecycle management."""

    def __init__(self):
        self._client: Optional[AsyncQdrantClient] = None

    async def initialize(self) -> None:
        """Connect to Qdrant and ensure the collection exists."""
        try:
            self._client = AsyncQdrantClient(
                host=settings.QDRANT_HOST,
                port=settings.QDRANT_PORT,
                api_key=settings.QDRANT_API_KEY or None,
                timeout=30,
            )
            # Create collection if it doesn't exist
            await self._ensure_collection()
            logger.info(
                "qdrant_connected",
                host=settings.QDRANT_HOST,
                port=settings.QDRANT_PORT,
                collection=settings.QDRANT_COLLECTION,
            )
        except Exception as e:
            logger.error("qdrant_connection_failed", error=str(e))
            raise

    async def close(self) -> None:
        """Close the Qdrant client."""
        if self._client:
            await self._client.close()
            logger.info("qdrant_disconnected")

    async def _ensure_collection(self) -> None:
        """Create the vector collection if it doesn't exist."""
        if not self._client:
            raise RuntimeError("Qdrant client not initialized.")

        try:
            await self._client.get_collection(settings.QDRANT_COLLECTION)
            logger.info("qdrant_collection_exists", collection=settings.QDRANT_COLLECTION)
        except (UnexpectedResponse, Exception):
            await self._client.create_collection(
                collection_name=settings.QDRANT_COLLECTION,
                vectors_config=models.VectorParams(
                    size=settings.QDRANT_VECTOR_SIZE,
                    distance=models.Distance.COSINE,
                ),
                # Payload indexes for filtering
                optimizers_config=models.OptimizersConfigDiff(
                    indexing_threshold=20000,
                ),
            )
            # Create payload indexes for RBAC filtering
            await self._client.create_payload_index(
                collection_name=settings.QDRANT_COLLECTION,
                field_name="document_id",
                field_schema=models.PayloadSchemaType.KEYWORD,
            )
            await self._client.create_payload_index(
                collection_name=settings.QDRANT_COLLECTION,
                field_name="clearance_level",
                field_schema=models.PayloadSchemaType.INTEGER,
            )
            await self._client.create_payload_index(
                collection_name=settings.QDRANT_COLLECTION,
                field_name="department",
                field_schema=models.PayloadSchemaType.KEYWORD,
            )
            logger.info("qdrant_collection_created", collection=settings.QDRANT_COLLECTION)

    # ── Upsert Operations ──

    async def upsert_vectors(
        self,
        vectors: list[list[float]],
        payloads: list[dict[str, Any]],
        ids: Optional[list[str]] = None,
    ) -> int:
        """Upsert vectors with metadata payloads.

        Args:
            vectors: List of embedding vectors.
            payloads: List of metadata dicts (must include chunk_id, document_id, text).
            ids: Optional list of point IDs (auto-generated if not provided).

        Returns:
            Number of vectors upserted.
        """
        if not self._client:
            raise RuntimeError("Qdrant client not initialized.")

        if not ids:
            ids = [str(uuid.uuid4()) for _ in range(len(vectors))]

        points = [
            models.PointStruct(
                id=point_id,
                vector=vector,
                payload=payload,
            )
            for point_id, vector, payload in zip(ids, vectors, payloads)
        ]

        await self._client.upsert(
            collection_name=settings.QDRANT_COLLECTION,
            points=points,
            wait=True,
        )
        logger.info("qdrant_vectors_upserted", count=len(points))
        return len(points)

    # ── Search Operations ──

    async def search(
        self,
        query_vector: list[float],
        top_k: int = 10,
        score_threshold: float = 0.0,
        filter_conditions: Optional[models.Filter] = None,
    ) -> list[dict]:
        """Similarity search with optional filtering.

        Args:
            query_vector: Query embedding vector.
            top_k: Number of results to return.
            score_threshold: Minimum similarity score.
            filter_conditions: Qdrant filter for RBAC/metadata filtering.

        Returns:
            List of search results with payload and score.
        """
        if not self._client:
            raise RuntimeError("Qdrant client not initialized.")

        start = time.time()
        results = await self._client.query_points(
            collection_name=settings.QDRANT_COLLECTION,
            query=query_vector,
            limit=top_k,
            score_threshold=score_threshold,
            query_filter=filter_conditions,
            with_payload=True,
        )

        duration = time.time() - start
        vector_search_duration_seconds.observe(duration)

        hits = []
        for point in results.points:
            hits.append(
                {
                    "id": point.id,
                    "score": point.score,
                    "payload": point.payload,
                }
            )

        logger.debug(
            "qdrant_search_completed",
            top_k=top_k,
            results=len(hits),
            duration_ms=round(duration * 1000, 2),
        )
        return hits

    async def search_with_rbac(
        self,
        query_vector: list[float],
        clearance_level: int = 0,
        department: str = "all",
        top_k: int = 10,
    ) -> list[dict]:
        """Search vectors with RBAC-based filtering.

        Args:
            query_vector: Query embedding.
            clearance_level: User's max clearance level.
            department: User's department.
            top_k: Number of results.

        Returns:
            Filtered search results.
        """
        must_conditions = [
            models.FieldCondition(
                key="clearance_level",
                range=models.Range(lte=clearance_level),
            ),
        ]

        if department != "all":
            must_conditions.append(
                models.FieldCondition(
                    key="department",
                    match=models.MatchAny(any=[department, "all"]),
                )
            )

        filter_conditions = models.Filter(must=must_conditions)
        return await self.search(
            query_vector=query_vector,
            top_k=top_k,
            filter_conditions=filter_conditions,
        )

    # ── Collection Management ──

    async def delete_by_document(self, document_id: str) -> None:
        """Delete all vectors associated with a document."""
        if not self._client:
            raise RuntimeError("Qdrant client not initialized.")

        await self._client.delete(
            collection_name=settings.QDRANT_COLLECTION,
            points_selector=models.FilterSelector(
                filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="document_id",
                            match=models.MatchValue(value=document_id),
                        )
                    ]
                )
            ),
        )
        logger.info("qdrant_document_vectors_deleted", document_id=document_id)

    async def get_collection_info(self) -> dict:
        """Get collection statistics."""
        if not self._client:
            return {"status": "not_initialized"}
        try:
            info = await self._client.get_collection(settings.QDRANT_COLLECTION)
            return {
                "vectors_count": getattr(info, "vectors_count", 0),
                "points_count": getattr(info, "points_count", 0),
                "status": "healthy",
                "vector_size": settings.QDRANT_VECTOR_SIZE,
            }
        except Exception:
            return {"status": "unavailable"}


# Singleton
qdrant_service = QdrantService()
