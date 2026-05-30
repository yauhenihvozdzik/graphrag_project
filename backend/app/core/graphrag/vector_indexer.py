"""Vector indexer service for storing chunk embeddings in Qdrant.

Generates embeddings via Ollama (bge-m3) and stores them with
metadata payloads including RBAC attributes.
"""

import uuid
from typing import Optional

from app.core.config import settings
from app.core.logging import logger


class VectorIndexerService:
    """Service for generating and storing vector embeddings."""

    async def index_chunks(
        self,
        chunks: list,  # list[TextChunk]
        ollama_service,
        qdrant_service,
        clearance_level: int = 0,
        department: str = "all",
    ) -> int:
        """Generate embeddings for text chunks and store in Qdrant.

        Args:
            chunks: List of TextChunk objects.
            ollama_service: OllamaService for embedding generation.
            qdrant_service: QdrantService for vector storage.
            clearance_level: RBAC clearance level for filtering.
            department: RBAC department for filtering.

        Returns:
            Number of vectors indexed.
        """
        if not chunks:
            return 0

        # Batch embed
        texts = [chunk.text for chunk in chunks]
        batch_size = 32  # Embed in batches to avoid memory issues

        all_vectors = []
        for i in range(0, len(texts), batch_size):
            batch_texts = texts[i : i + batch_size]
            vectors = await ollama_service.embed(batch_texts)
            all_vectors.extend(vectors)

        # Prepare payloads with RBAC metadata
        # Use UUID-based point IDs (Qdrant requires UUID or unsigned integer)
        payloads = []
        ids = []
        for chunk in chunks:
            payload = {
                "chunk_id": chunk.chunk_id,
                "document_id": chunk.document_id,
                "text": chunk.text,
                "position": chunk.position,
                "clearance_level": clearance_level,
                "department": department,
            }
            # Merge chunk metadata
            if chunk.metadata:
                payload.update(
                    {
                        k: v
                        for k, v in chunk.metadata.items()
                        if k not in ("clearance_level", "department")
                    }
                )
            payloads.append(payload)
            # Generate a valid UUID from the chunk_id (Qdrant point ID requirement)
            point_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, chunk.chunk_id))
            ids.append(point_id)

        # Upsert to Qdrant
        count = await qdrant_service.upsert_vectors(
            vectors=all_vectors,
            payloads=payloads,
            ids=ids,
        )

        logger.info(
            "vector_indexing_completed",
            chunks_indexed=count,
            vector_dim=len(all_vectors[0]) if all_vectors else 0,
        )
        return count

    async def search_similar(
        self,
        query: str,
        ollama_service,
        qdrant_service,
        top_k: int = 10,
        clearance_level: int = 0,
        department: str = "all",
    ) -> list[dict]:
        """Search for similar chunks using vector similarity.

        Args:
            query: Search query text.
            ollama_service: For query embedding.
            qdrant_service: For vector search.
            top_k: Number of results.
            clearance_level: User clearance for RBAC filtering.
            department: User department for RBAC filtering.

        Returns:
            List of search results with text and metadata.
        """
        # Generate query embedding
        query_vector = await ollama_service.embed_single(query)

        # Search with RBAC filtering
        results = await qdrant_service.search_with_rbac(
            query_vector=query_vector,
            clearance_level=clearance_level,
            department=department,
            top_k=top_k,
        )

        return results


# Singleton
vector_indexer_service = VectorIndexerService()
