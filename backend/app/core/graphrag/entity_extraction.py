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
from app.core.logging import logger
from app.core.metrics import entities_extracted_total


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


# System prompt for LLM-based entity extraction
ENTITY_EXTRACTION_PROMPT = """Ты — система извлечения сущностей из юридических документов на русском языке.

Из данного фрагмента текста извлеки все именованные сущности и отношения между ними.

Типы сущностей:
- ЗАКОН: названия законов, кодексов, постановлений (например: "Гражданский кодекс РФ", "Федеральный закон №152-ФЗ")
- СТАТЬЯ: ссылки на статьи, пункты, подпункты (например: "статья 15", "п. 3 ст. 421")
- ОРГАНИЗАЦИЯ: юридические лица, госорганы, суды (например: "Верховный Суд РФ", "ООО Ромашка")
- ПЕРСОНА: физические лица, должностные лица
- ДАТА: даты, сроки (например: "01.01.2024", "в течение 30 дней")
- СУД: суды и судебные органы (например: "Арбитражный суд г. Москвы")
- ДОКУМЕНТ: ссылки на документы, решения, постановления
- ПОНЯТИЕ: юридические термины и концепции (например: "неустойка", "залог")
- ТЕРРИТОРИЯ: географические объекты, юрисдикции
- НАКАЗАНИЕ: виды наказаний, санкции, штрафы

Типы отношений:
- РЕГУЛИРУЕТ: закон/статья регулирует область
- ССЫЛАЕТСЯ_НА: документ ссылается на другой документ
- ОТНОСИТСЯ_К: сущность относится к другой сущности
- ВЫНЕС_РЕШЕНИЕ: суд вынес решение
- УСТАНАВЛИВАЕТ: закон устанавливает правило/наказание
- УЧАСТНИК: персона/организация является участником дела

Верни результат ТОЛЬКО в формате JSON:
{
  "entities": [
    {"name": "...", "type": "...", "description": "..."}
  ],
  "relations": [
    {"source": "...", "target": "...", "type": "...", "description": "..."}
  ]
}

Текст для анализа:
"""


class EntityExtractionService:
    """Service for extracting entities and relations from text chunks."""

    # Regex-based fallback patterns for Russian legal entities
    LEGAL_PATTERNS = {
        "ЗАКОН": [
            r"(?:Федеральн(?:ый|ого)\s+закон(?:а|у|ом|е)?\s+(?:от\s+)?\d{1,2}[\.\-]\d{1,2}[\.\-]\d{2,4}\s*(?:г\.?)?\s*(?:№\s*\d+[\-]?[А-Яа-яA-Za-z]*)?)",
            r"(?:(?:Гражданск|Уголовн|Трудов|Налогов|Административн|Земельн|Жилищн|Семейн|Бюджетн|Арбитражн|Процессуальн)[а-я]*\s+кодекс[а-я]*\s+(?:РФ|Российской\s+Федерации)?)",
            r"(?:Конституци[а-я]*\s+(?:РФ|Российской\s+Федерации))",
            r"(?:Постановлени[а-я]*\s+Правительства\s+РФ\s+(?:от\s+)?\d{1,2}[\.\-]\d{1,2}[\.\-]\d{2,4})",
            r"(?:Указ[а-я]*\s+Президента\s+РФ)",
        ],
        "СТАТЬЯ": [
            r"(?:(?:ст(?:атья|\.)\s*\d+(?:\.\d+)?(?:\s*п(?:ункт|\.)\s*\d+)?))",
            r"(?:(?:п(?:ункт|\.)\s*\d+(?:\.\d+)?)\s+(?:ст(?:атья|\.)\s*\d+))",
            r"(?:(?:ч(?:асть|\.)\s*\d+)\s+(?:ст(?:атья|\.)\s*\d+))",
        ],
        "ОРГАНИЗАЦИЯ": [
            r"(?:(?:ООО|ОАО|ЗАО|ПАО|АО|ИП|ФГУП|ГУП|МУП)\s+[«\"]?[\w\s]+[»\"]?)",
            r"(?:Министерств[а-я]*\s+[\w\s]+(?:РФ|Российской\s+Федерации))",
        ],
        "СУД": [
            r"(?:(?:Верховн|Конституционн|Арбитражн)[а-я]*\s+[Сс]уд[а-я]*\s+[\w\s]*)",
            r"(?:(?:районн|городск|областн|краев|мировой|апелляционн|кассационн)[а-я]*\s+суд[а-я]*)",
        ],
        "ДАТА": [
            r"\b\d{1,2}[\.\-/]\d{1,2}[\.\-/]\d{2,4}\b",
            r"\b\d{1,2}\s+(?:январ|феврал|март|апрел|ма[яй]|июн|июл|август|сентябр|октябр|ноябр|декабр)[а-я]*\s+\d{4}\s*(?:г(?:ода?)?\.?)?\b",
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
            system="Ты — система NER для юридических текстов. Отвечай только JSON.",
            temperature=0.0,
            max_tokens=2000,
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
                        confidence=0.8,  # LLM default confidence
                    )
                )

            for rel in data.get("relations", []):
                relations.append(
                    ExtractedRelation(
                        source=rel.get("source", ""),
                        target=rel.get("target", ""),
                        relation_type=rel.get("type", "ОТНОСИТСЯ_К"),
                        description=rel.get("description", ""),
                        confidence=0.7,
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

    # Generic patterns for any text (not just legal)
    GENERIC_PATTERNS = {
        "ПОНЯТИЕ": [
            r"\b(?:граф знаний|графа знаний|графы знаний|векторная база|векторный поиск|база знаний|онтология|семантический поиск)\b",
            r"\b(?:RAG|LLM|API|REST|GraphQL|GraphRAG|embeddings?|tokenization|inference|fine-tuning|prompt engineering)\b",
            r"\b(?:Neo4j|Qdrant|Ollama|PostgreSQL|LangChain|LangGraph|FastAPI|Kubernetes|Docker)\b",
        ],
        "ТЕХНОЛОГИЯ": [
            r"\b[A-ZА-Я][a-zа-я]{3,}(?:\s+[A-ZА-Я][a-zа-я]{2,}){1,3}\b",  # Capitalized multi-word phrases
            r"\b[A-ZА-Я]{2,}(?:\.[A-ZА-Я]{2,})*\b",  # Acronyms
        ],
    }

    def _extract_with_regex(self, chunk) -> ExtractionResult:
        """Fallback: extract entities using regex patterns."""
        entities = []
        text = chunk.text

        # Try legal patterns first, then generic
        all_patterns = {**self.LEGAL_PATTERNS, **self.GENERIC_PATTERNS}
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
                                confidence=0.6,  # Regex lower confidence
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
