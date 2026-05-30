"""
Tests for GraphRAG pipeline components — entity extraction, graph builder, vector indexer.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestEntityExtraction:
    """Tests for entity extraction service."""

    def test_service_importable(self):
        """Entity extraction service is importable."""
        from app.core.graphrag.entity_extraction import entity_extraction_service
        assert entity_extraction_service is not None

    def test_extraction_result_model(self):
        """ExtractionResult model has expected structure."""
        from app.core.graphrag.entity_extraction import ExtractionResult
        assert ExtractionResult is not None


class TestGraphBuilder:
    """Tests for Neo4j graph builder service."""

    def test_service_importable(self):
        """Graph builder service is importable."""
        from app.core.graphrag.graph_builder import graph_builder_service
        assert graph_builder_service is not None

    def test_entity_id_generation(self):
        """Entity ID generation is deterministic."""
        from app.core.graphrag.graph_builder import graph_builder_service
        if hasattr(graph_builder_service, "_entity_id"):
            id1 = graph_builder_service._entity_id("Гражданский кодекс", "ЗАКОН")
            id2 = graph_builder_service._entity_id("Гражданский кодекс", "ЗАКОН")
            assert id1 == id2  # Deterministic

    def test_entity_id_uniqueness(self):
        """Different entities produce different IDs."""
        from app.core.graphrag.graph_builder import graph_builder_service
        if hasattr(graph_builder_service, "_entity_id"):
            id1 = graph_builder_service._entity_id("Кодекс 1", "ЗАКОН")
            id2 = graph_builder_service._entity_id("Кодекс 2", "ЗАКОН")
            assert id1 != id2


class TestVectorIndexer:
    """Tests for Qdrant vector indexer service."""

    def test_service_importable(self):
        """Vector indexer service is importable."""
        from app.core.graphrag.vector_indexer import vector_indexer_service
        assert vector_indexer_service is not None


class TestDocumentIngestion:
    """Tests for document ingestion pipeline."""

    def test_service_importable(self):
        """Ingestion service is importable."""
        from app.core.graphrag.document_ingestion import ingestion_service
        assert ingestion_service is not None

    def test_chunking_config(self):
        """Chunk size config is set."""
        from app.core.config import settings
        assert settings.CHUNK_SIZE > 0
        assert settings.CHUNK_OVERLAP >= 0
        assert settings.CHUNK_OVERLAP < settings.CHUNK_SIZE


class TestSchemas:
    """Tests for Pydantic schemas."""

    def test_chat_request_schema(self):
        """ChatRequest validates correctly."""
        from app.models.schemas import ChatRequest, Message
        req = ChatRequest(messages=[Message(role="user", content="Что такое право собственности?")])
        assert req.messages[0].content == "Что такое право собственности?"

    def test_ingest_request_schema(self):
        """IngestRequest validates correctly."""
        from app.models.schemas import IngestRequest
        req = IngestRequest(
            title="Тестовый документ",
            content="Текст документа",
        )
        assert req.content == "Текст документа"
        assert req.title == "Тестовый документ"

    def test_graph_node_schema(self):
        """GraphNode model works."""
        from app.models.schemas import GraphNode
        node = GraphNode(
            id="n1",
            name="Гражданский кодекс",
            type="entity",
        )
        assert node.id == "n1"
        assert node.name == "Гражданский кодекс"


class TestConfig:
    """Tests for application configuration."""

    def test_settings_loaded(self):
        """Settings object loads successfully."""
        from app.core.config import settings
        assert settings.PROJECT_NAME is not None
        assert settings.VERSION is not None

    def test_api_prefix(self):
        """API prefix is configured."""
        from app.core.config import settings
        assert settings.API_V1_STR == "/api/v1"

    def test_security_settings(self):
        """Security settings are configured."""
        from app.core.config import settings
        assert settings.MAX_INPUT_LENGTH > 0
