"""Entity extraction service for Russian legal documents.

Extracts named entities (NER) from text chunks using LLM-based extraction
optimized for the Russian legal domain (laws, regulations, court decisions).

Entity types:
- ЗАКОН (law/statute)
- СТАТЬЯ (article/section)
- ОРГАНИЗАЦИЯ (organization)
- ПЕРСОНА (person)
- ДАТА (date)
- СУД (court)
- ДОКУМЕНТ (document reference)
- ПОНЯТИЕ (legal concept/term)
- ТЕРРИТОРИЯ (territory/jurisdiction)
- НАКАЗАНИЕ (penalty/sanction)
"""

import json
import re
from dataclasses import dataclass, field
from typing import Optional

from app.core.config import settings
from app.core.constants import (
    LLM_TEMPERATURE_NER,
    LLM_MAX_TOKENS_NER,
    NER_LLM_CONFIDENCE,
    NER_REGEX_CONFIDENCE,
    NER_RELATION_CONFIDENCE,
)
from app.core.logging import logger
from app.core.metrics import entities_extracted_total
from app.core.prompts import ENTITY_EXTRACTION_PROMPT, NER_SYSTEM_PROMPT


@dataclass
class ExtractedEntity:
    """An entity extracted from text."""

    name: str
    entity_type: str
    description: str = ""
    source_chunk_id: str = ""
    confidence: float = 0.0
    properties: dict = field(default_factory=dict)


@dataclass
class ExtractedRelation:
    """A relation between two extracted entities."""

    source: str
    target: str
    relation_type: str
    description: str = ""
    confidence: float = 0.0


@dataclass
class ExtractionResult:
    """Result of entity extraction from a chunk."""

    chunk_id: str
    entities: list[ExtractedEntity]
    relations: list[ExtractedRelation]


class EntityExtractionService:
    """Service for extracting entities and relations from text chunks — universal (topic-agnostic)."""

    # Universal regex-based fallback patterns (topic-agnostic)
    UNIVERSAL_PATTERNS = {
        "ОРГАНИЗАЦИЯ": [
            r"(?:(?:ООО|ОАО|ЗАО|ПАО|АО|ИП|ФГУП|ГУП|МУП)\s+[«\"]?[\w\s]+[»\"]?)",
            r"(?:Министерств[а-я]*\s+[\w\s]+)",
            r"\b(?:отдел|департамент|управление|служба|сектор|подразделение)\s+[\w\s]+",
        ],
        "ПЕРСОНА": [
            r"\b[А-Я][а-я]+\s+[А-Я]\.[А-Я]\.",  # Иванов И.И.
            r"\b(?:менеджер|администратор|бухгалтер|водитель|кладовщик|экспедитор|оператор|диспетчер|руководитель|начальник|директор|специалист|техподдержка|аналитик)\b",
        ],
        "ДОКУМЕНТ": [
            r"\b(?:акт|накладная|счёт-фактура|счёт|договор|отчёт|журнал|ведомость|заказ|спецификация|сертификат|декларация|устав|регламент|инструкция|приказ|распоряжение|протокол|заявка|чек|квитанция)\s*(?:[\w\s/\-№]*)?",
            r"\b[A-ZА-Я]{2,}[\w\-]*\.[a-z]{2,4}\b",  # filenames like ТОРГ-12.xlsx
        ],
        "ДАТА": [
            r"\b\d{1,2}[\.\-/]\d{1,2}[\.\-/]\d{2,4}\b",
            r"\b\d{1,2}\s+(?:январ|феврал|март|апрел|ма[яй]|июн|июл|август|сентябр|октябр|ноябр|декабр)[а-я]*\s+\d{4}\s*(?:г(?:ода?)?\.?)?\b",
        ],
        "ТЕХНОЛОГИЯ": [
            r"\b(?:1С|SAP|Oracle|Microsoft|NAV|ERP|CRM|WMS|TMS|EDI|XML|JSON|API|REST|S3|MinIO|Qdrant|Neo4j|Ollama|Kubernetes|Docker|PostgreSQL|nginx|GitLab|GitHub)\b",
            r"\b[A-ZА-Я][\w]*(?:\s*[\d.]+)?(?:\s+(?:система|программа|модуль|сервис|приложение|платформа))\b",
        ],
        "ПРОЦЕСС": [
            r"\b(?:приёмка|отгрузка|перемещение|инвентаризация|маркировка|согласование|утверждение|списание|оприходование|возврат|доставка|сборка|упаковка|проверка|импорт|экспорт|синхронизация|загрузка|выгрузка|обработка|формирование|печать|расчёт|сверка)\s*(?:[\w\s]*)",
        ],
        "ЛОКАЦИЯ": [
            r"\b(?:г\.|город)\s+[\w\s\-]+",
            r"\b(?:склад|магазин|точка|офис|филиал)\s*(?:№?\s*[\d\w]+)?",
            r"\b(?:РБ|РФ|РК|Минск|Москва|Астана)\b",
        ],
        "ПОКАЗАТЕЛЬ": [
            r"\b\d+(?:\.\d+)?\s*(?:%|руб|BYN|RUB|USD|EUR|шт|кг|л|км|ч|мин)\b",
        ],
    }

    async def extract_from_chunks(
        self,
        chunks: list,  # list[TextChunk]
        ollama_service=None,
        use_llm: bool = True,
    ) -> list[ExtractionResult]:
        """Extract entities and relations from text chunks.

        Args:
            chunks: List of TextChunk objects.
            ollama_service: OllamaService instance for LLM extraction.
            use_llm: Whether to use LLM (True) or regex fallback (False).

        Returns:
            List of ExtractionResult objects.
        """
        results = []
        batch_size = settings.ENTITY_EXTRACTION_BATCH_SIZE

        for i in range(0, len(chunks), batch_size):
            batch = chunks[i : i + batch_size]
            for chunk in batch:
                try:
                    if use_llm and ollama_service:
                        result = await self._extract_with_llm(chunk, ollama_service)
                    else:
                        result = self._extract_with_regex(chunk)
                    results.append(result)
                    # Track metrics
                    for entity in result.entities:
                        entities_extracted_total.labels(entity_type=entity.entity_type).inc()
                except Exception as e:
                    logger.error(
                        "entity_extraction_failed",
                        chunk_id=chunk.chunk_id,
                        error=str(e),
                    )
                    # Return empty result on failure
                    results.append(
                        ExtractionResult(
                            chunk_id=chunk.chunk_id, entities=[], relations=[]
                        )
                    )

        total_entities = sum(len(r.entities) for r in results)
        total_relations = sum(len(r.relations) for r in results)
        logger.info(
            "extraction_completed",
            chunks_processed=len(chunks),
            total_entities=total_entities,
            total_relations=total_relations,
        )
        return results

    async def _extract_with_llm(self, chunk, ollama_service) -> ExtractionResult:
        """Extract entities using LLM."""
        prompt = ENTITY_EXTRACTION_PROMPT + chunk.text

        response = await ollama_service.generate(
            prompt=prompt,
            system=NER_SYSTEM_PROMPT,
            temperature=LLM_TEMPERATURE_NER,
            max_tokens=LLM_MAX_TOKENS_NER,
        )

        # Parse JSON from LLM response
        entities, relations = self._parse_llm_response(response, chunk.chunk_id)
        return ExtractionResult(
            chunk_id=chunk.chunk_id, entities=entities, relations=relations
        )

    def _parse_llm_response(
        self, response: str, chunk_id: str
    ) -> tuple[list[ExtractedEntity], list[ExtractedRelation]]:
        """Parse LLM JSON response into entities and relations."""
        entities = []
        relations = []

        try:
            # Try to extract JSON from response
            json_match = re.search(r"\{[\s\S]*\}", response)
            if not json_match:
                logger.warning("llm_response_no_json", chunk_id=chunk_id)
                return entities, relations

            data = json.loads(json_match.group())

            for ent in data.get("entities", []):
                entities.append(
                    ExtractedEntity(
                        name=ent.get("name", ""),
                        entity_type=ent.get("type", "ПОНЯТИЕ"),
                        description=ent.get("description", ""),
                        source_chunk_id=chunk_id,
                        confidence=NER_LLM_CONFIDENCE,
                    )
                )

            for rel in data.get("relations", []):
                relations.append(
                    ExtractedRelation(
                        source=rel.get("source", ""),
                        target=rel.get("target", ""),
                        relation_type=rel.get("type", "ОТНОСИТСЯ_К"),
                        description=rel.get("description", ""),
                        confidence=NER_RELATION_CONFIDENCE,
                    )
                )
        except json.JSONDecodeError as e:
            logger.warning(
                "llm_response_json_parse_error",
                chunk_id=chunk_id,
                error=str(e),
                response_preview=response[:200],
            )

        return entities, relations


    def _extract_with_regex(self, chunk) -> ExtractionResult:
        """Fallback: extract entities using universal regex patterns."""
        entities = []
        text = chunk.text

        all_patterns = self.UNIVERSAL_PATTERNS
        for entity_type, patterns in all_patterns.items():
            for pattern in patterns:
                matches = re.finditer(pattern, text, re.IGNORECASE)
                for match in matches:
                    entity_name = match.group().strip()
                    if len(entity_name) > 3:  # filter noise
                        entities.append(
                            ExtractedEntity(
                                name=entity_name,
                                entity_type=entity_type,
                                source_chunk_id=chunk.chunk_id,
                                confidence=NER_REGEX_CONFIDENCE,
                            )
                        )

        # Deduplicate by name+type
        seen = set()
        unique_entities = []
        for ent in entities:
            key = (ent.name.lower(), ent.entity_type)
            if key not in seen:
                seen.add(key)
                unique_entities.append(ent)

        return ExtractionResult(
            chunk_id=chunk.chunk_id, entities=unique_entities, relations=[]
        )


# Singleton
entity_extraction_service = EntityExtractionService()
