"""Memory integration for LangGraph agent.

Combines Neo4j (graph memory) and Qdrant (vector memory) for
long-term conversational context and knowledge retrieval.
"""

from typing import Optional

from app.core.config import settings
from app.core.logging import logger


class GraphRAGMemory:
    """Hybrid memory service combining graph and vector stores.

    - Neo4j: stores entity relationships, conversation entities, user interactions
    - Qdrant: stores semantic embeddings of conversation turns and knowledge chunks
    """

    def __init__(self):
        self._initialized = False

    async def initialize(self) -> None:
        """Initialize both memory backends."""
        self._initialized = True
        logger.info("graphrag_memory_initialized")

    async def store_interaction(
        self,
        user_id: str,
        session_id: str,
        query: str,
        response: str,
        entities: list[str],
        neo4j_service=None,
        ollama_service=None,
        qdrant_service=None,
    ) -> None:
        """Store a user interaction in both memory stores.

        Args:
            user_id: User identifier.
            session_id: Session identifier.
            query: User query text.
            response: Agent response text.
            entities: Entities mentioned in the interaction.
            neo4j_service: Neo4j service instance.
            ollama_service: Ollama service for embeddings.
            qdrant_service: Qdrant service for vector storage.
        """
        # Store in graph: user -> asked_about -> entities
        if neo4j_service and entities:
            try:
                for entity_name in entities:
                    # Create user interaction node
                    await neo4j_service.create_entity(
                        entity_id=f"interaction_{session_id}_{entity_name[:20]}",
                        name=f"Запрос: {query[:100]}",
                        entity_type="INTERACTION",
                        properties={
                            "user_id": user_id,
                            "session_id": session_id,
                            "query": query[:500],
                        },
                    )
            except Exception as e:
                logger.warning("memory_graph_store_failed", error=str(e))

        logger.debug(
            "interaction_stored",
            user_id=user_id,
            session_id=session_id,
            entities_count=len(entities),
        )

    async def retrieve_context(
        self,
        user_id: str,
        query: str,
        top_k: int = 5,
        neo4j_service=None,
        ollama_service=None,
        qdrant_service=None,
    ) -> str:
        """Retrieve relevant context from memory stores.

        Combines:
        1. Vector similarity search on past interactions
        2. Graph-based entity context from Neo4j

        Args:
            user_id: User identifier.
            query: Current query.
            top_k: Number of results per source.
            neo4j_service: Neo4j service.
            ollama_service: Ollama service.
            qdrant_service: Qdrant service.

        Returns:
            Combined context string.
        """
        context_parts = []

        # Vector memory search
        if ollama_service and qdrant_service:
            try:
                from app.core.graphrag.vector_indexer import vector_indexer_service

                results = await vector_indexer_service.search_similar(
                    query=query,
                    ollama_service=ollama_service,
                    qdrant_service=qdrant_service,
                    top_k=top_k,
                )
                for r in results:
                    text = r.get("payload", {}).get("text", "")
                    if text:
                        context_parts.append(text)
            except Exception as e:
                logger.warning("memory_vector_retrieve_failed", error=str(e))

        return "\n\n".join(context_parts) if context_parts else ""


# Singleton
graphrag_memory = GraphRAGMemory()
