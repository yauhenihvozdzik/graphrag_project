"""Graph builder service for constructing Neo4j knowledge graph."""

import hashlib
from typing import Optional

from app.core.graphrag.entity_extraction import ExtractionResult, ExtractedEntity
from app.core.logging import logger


class GraphBuilderService:
    async def build_from_extraction(
        self,
        document_id: str, title: str, source: str,
        extraction_results: list[ExtractionResult],
        chunks: list,  # Список TextChunk-объектов для сохранения текста чанков
        neo4j_service,
        clearance_level: int = 0, department: str = "all",
        metadata: Optional[dict] = None,
        s3_key: str = "",
    ) -> dict:
        """Строит граф знаний с сохранением текста чанков в Neo4j."""
        stats = {"entities_created": 0, "relations_created": 0, "chunks_linked": 0}

        # Индекс чанков по chunk_id для быстрого доступа к тексту
        chunk_map = {c.chunk_id: c for c in chunks} if chunks else {}

        # 1. Создаём узел документа с S3-ключом и полным текстом
        # Read s3_original_key and original_filename from chunk metadata
        first_chunk = chunks[0] if chunks else None
        chunk_meta = first_chunk.metadata if first_chunk else {}
        original_key = (metadata or {}).get("s3_original_key", "") or chunk_meta.get("s3_original_key", "")
        original_filename = (metadata or {}).get("original_filename", "") or chunk_meta.get("original_filename", "") or title
        
        # Assemble full text from ALL chunks for reliable downloads
        full_text = "\n\n".join(c.text for c in chunks if c and c.text) if chunks else ""
        
        await neo4j_service.create_document_node(
            doc_id=document_id, title=title, source=source,
            metadata=metadata or {}, clearance_level=clearance_level, department=department,
            s3_key=s3_key, s3_original_key=original_key, original_filename=original_filename,
            full_text=full_text,
        )
        logger.info("graph_document_node_created", document_id=document_id)

        entity_map: dict[str, ExtractedEntity] = {}
        chunk_entity_links: list[tuple[str, str]] = []

        # 2. Создаём чанки с реальным текстом
        for result in extraction_results:
            chunk_obj = chunk_map.get(result.chunk_id)
            chunk_text = chunk_obj.text if chunk_obj else ""
            await neo4j_service.create_chunk_node(
                chunk_id=result.chunk_id, document_id=document_id,
                text=chunk_text, position=0,
            )
            for entity in result.entities:
                entity_id = self._entity_id(entity.name, entity.entity_type)
                if entity_id not in entity_map:
                    entity_map[entity_id] = entity
                chunk_entity_links.append((entity_id, result.chunk_id))

        # 3. Узлы сущностей
        for entity_id, entity in entity_map.items():
            await neo4j_service.create_entity(
                entity_id=entity_id, name=entity.name, entity_type=entity.entity_type,
                properties={"description": entity.description, "confidence": entity.confidence,
                            "source_document": document_id},
                clearance_level=clearance_level, department=department,
            )
            stats["entities_created"] += 1

        # 4. Связи
        for result in extraction_results:
            for relation in result.relations:
                se = self._find_entity_id(relation.source, entity_map)
                te = self._find_entity_id(relation.target, entity_map)
                if se and te:
                    await neo4j_service.create_relationship(
                        source_id=se, target_id=te, rel_type=relation.relation_type,
                        properties={"description": relation.description,
                                    "confidence": relation.confidence,
                                    "source_document": document_id},
                    )
                    stats["relations_created"] += 1

        # 5. Связи сущность→чанк
        for entity_id, chunk_id in chunk_entity_links:
            if entity_id in entity_map:
                await neo4j_service.link_entity_to_chunk(entity_id, chunk_id)
                stats["chunks_linked"] += 1

        logger.info("graph_build_completed", document_id=document_id, **stats)
        return stats

    def _entity_id(self, name: str, entity_type: str) -> str:
        return f"ent_{hashlib.sha256(f'{name.lower().strip()}:{entity_type.lower().strip()}'.encode()).hexdigest()[:12]}"

    def _find_entity_id(self, name: str, entity_map: dict) -> Optional[str]:
        nl = name.lower().strip()
        for eid, e in entity_map.items():
            if e.name.lower().strip() == nl: return eid
        for eid, e in entity_map.items():
            if nl in e.name.lower() or e.name.lower() in nl: return eid
        return None


graph_builder_service = GraphBuilderService()