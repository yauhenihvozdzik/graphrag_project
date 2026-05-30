"""Neo4j graph database service for GraphRAG platform."""

from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator, Optional

from neo4j import AsyncGraphDatabase, AsyncDriver, AsyncSession
from neo4j.exceptions import ServiceUnavailable, AuthError

from app.core.config import settings
from app.core.logging import logger
from app.core.metrics import graph_nodes_total, graph_edges_total, graph_query_duration_seconds
import time


class Neo4jService:
    def __init__(self): self._driver: Optional[AsyncDriver] = None

    async def initialize(self) -> None:
        try:
            self._driver = AsyncGraphDatabase.driver(
                settings.NEO4J_URI, auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD),
                max_connection_pool_size=settings.NEO4J_MAX_CONNECTION_POOL_SIZE)
            await self._driver.verify_connectivity()
            logger.info("neo4j_connected")
            await self._setup_schema()
        except (ServiceUnavailable, AuthError) as e:
            logger.error("neo4j_failed", error=str(e))
            raise

    async def close(self) -> None:
        if self._driver:
            await self._driver.close()
            logger.info("neo4j_disconnected")

    @asynccontextmanager
    async def session(self) -> AsyncGenerator[AsyncSession, None]:
        if not self._driver:
            raise RuntimeError("Neo4j not initialized")
        async with self._driver.session(database=settings.NEO4J_DATABASE) as s:
            yield s

    async def _setup_schema(self) -> None:
        for q in [
            "CREATE CONSTRAINT entity_id IF NOT EXISTS FOR (e:Entity) REQUIRE e.id IS UNIQUE",
            "CREATE CONSTRAINT document_id IF NOT EXISTS FOR (d:Document) REQUIRE d.id IS UNIQUE",
            "CREATE CONSTRAINT chunk_id IF NOT EXISTS FOR (c:Chunk) REQUIRE c.id IS UNIQUE",
        ]:
            try:
                async with self.session() as s:
                    await s.run(q)
            except Exception as e:
                logger.debug("schema_skip", error=str(e))

    async def create_entity(self, entity_id: str, name: str, entity_type: str, properties: Optional[dict] = None, clearance_level: int = 0, department: str = "all") -> dict:
        props = properties or {}
        q = "MERGE (e:Entity {id:$entity_id}) SET e.name=$name, e.entity_type=$entity_type, e.clearance_level=$clearance_level, e.department=$department, e.updated_at=datetime(), e+=$properties RETURN e{.*, labels:labels(e)} AS entity"
        async with self.session() as s:
            r = await s.run(q, entity_id=entity_id, name=name, entity_type=entity_type, clearance_level=clearance_level, department=department, properties=props)
            return (await r.single())["entity"]

    async def create_relationship(self, source_id: str, target_id: str, rel_type: str, properties: Optional[dict] = None) -> dict:
        props = properties or {}; safe = rel_type.upper().replace(" ","_").replace("-","_")
        q = f"MATCH (s:Entity {{id:$source_id}}) MATCH (t:Entity {{id:$target_id}}) MERGE (s)-[r:{safe}]->(t) SET r+=$properties, r.updated_at=datetime() RETURN type(r) AS rel_type, r{{.*}} AS properties"
        async with self.session() as s:
            r = await s.run(q, source_id=source_id, target_id=target_id, properties=props)
            rec = await r.single(); return {"rel_type":rec["rel_type"],"properties":rec["properties"]} if rec else {}

    async def link_entity_to_chunk(self, entity_id: str, chunk_id: str) -> None:
        async with self.session() as s: await s.run("MATCH (e:Entity {id:$eid}) MATCH (c:Chunk {id:$cid}) MERGE (e)-[:MENTIONED_IN]->(c)", eid=entity_id, cid=chunk_id)

    async def document_exists_by_id(self, doc_id: str) -> bool:
        async with self.session() as s:
            r = await s.run("MATCH (d:Document {id:$doc_id}) RETURN d LIMIT 1", doc_id=doc_id)
            return await r.single() is not None

    async def update_document_access(self, doc_id: str, clearance_level: int, department: str) -> Optional[dict]:
        q = "MATCH (d:Document {id:$doc_id}) SET d.clearance_level=$clearance_level, d.department=$department RETURN d{.*} AS document"
        async with self.session() as s:
            r = await s.run(q, doc_id=doc_id, clearance_level=clearance_level, department=department)
            rec = await r.single()
            return rec["document"] if rec else None

    async def create_document_node(self, doc_id: str, title: str, source: str, metadata: Optional[dict] = None, clearance_level: int = 0, department: str = "all", s3_key: str = "", s3_original_key: str = "", original_filename: str = "") -> dict:
        props = metadata or {}
        q = "MERGE (d:Document {id:$doc_id}) SET d.title=$title, d.source=$source, d.clearance_level=$clearance_level, d.department=$department, d.s3_key=$s3_key, d.s3_original_key=$s3_original_key, d.original_filename=$original_filename, d.created_at=datetime(), d+=$metadata RETURN d{.*} AS document"
        async with self.session() as s:
            r = await s.run(q, doc_id=doc_id, title=title, source=source, clearance_level=clearance_level, department=department, s3_key=s3_key, s3_original_key=s3_original_key, original_filename=original_filename, metadata=props)
            return (await r.single())["document"]

    async def create_chunk_node(self, chunk_id: str, document_id: str, text: str, position: int) -> dict:
        q = "MERGE (c:Chunk {id:$chunk_id}) SET c.document_id=$document_id, c.text=$text, c.position=$position, c.created_at=datetime() WITH c MATCH (d:Document {id:$document_id}) MERGE (c)-[:PART_OF]->(d) RETURN c{.*} AS chunk"
        async with self.session() as s:
            r = await s.run(q, chunk_id=chunk_id, document_id=document_id, text=text, position=position)
            return (await r.single())["chunk"]

    async def get_entity_neighborhood(self, entity_name: str, depth: int = 2, limit: int = 50, rbac_filter: str = "") -> dict:
        start = time.time(); w = f"WHERE {rbac_filter}" if rbac_filter else ""
        q = f"MATCH (root:Entity {{name:$entity_name}}) CALL apoc.path.subgraphAll(root, {{maxLevel:$depth, limit:$limit}}) YIELD nodes, relationships UNWIND nodes AS n {w} WITH collect(DISTINCT n{{.*, labels:labels(n), id:n.id}}) AS filtered_nodes, relationships UNWIND relationships AS r RETURN filtered_nodes AS nodes, collect(DISTINCT {{source:startNode(r).id, target:endNode(r).id, type:type(r), properties:properties(r)}}) AS edges"
        try:
            async with self.session() as s:
                r = await s.run(q, entity_name=entity_name, depth=depth, limit=limit); rec = await r.single()
                graph_query_duration_seconds.observe(time.time()-start)
                return {"nodes":rec["nodes"],"edges":rec["edges"]} if rec else {"nodes":[],"edges":[]}
        except:
            return await self._fallback(entity_name, depth, limit, rbac_filter)

    async def _fallback(self, entity_name: str, depth: int, limit: int, rbac_filter: str) -> dict:
        wc = f"AND {rbac_filter}" if rbac_filter else ""
        q = f"MATCH path=(root:Entity {{name:$entity_name}})-[*1..{depth}]-(n) WHERE n:Entity {wc} WITH DISTINCT n, relationships(path) AS rels LIMIT $limit UNWIND rels AS r RETURN collect(DISTINCT n{{.*, id:n.id, entity_type:n.entity_type}}) AS nodes, collect(DISTINCT {{source:startNode(r).id, target:endNode(r).id, type:type(r)}}) AS edges"
        async with self.session() as s:
            r = await s.run(q, entity_name=entity_name, limit=limit); rec = await r.single()
            return {"nodes":rec["nodes"],"edges":rec["edges"]} if rec else {"nodes":[],"edges":[]}

    async def search_entities(self, query: str, entity_type: Optional[str] = None, limit: int = 20, rbac_filter: str = "") -> list[dict]:
        tc = "AND e.entity_type=$entity_type" if entity_type else ""; rc = f"AND {rbac_filter}" if rbac_filter else ""
        p: dict = {"query":query,"limit":limit}
        if entity_type: p["entity_type"] = entity_type
        async with self.session() as s:
            r = await s.run(f"MATCH (e:Entity) WHERE toLower(e.name) CONTAINS toLower($query) {tc} {rc} RETURN e{{.*, id:e.id}} AS entity ORDER BY e.name LIMIT $limit", **p)
            return [rec["entity"] for rec in await r.data()]

    async def get_graph_stats(self) -> dict:
        async with self.session() as s:
            r = await s.run("OPTIONAL MATCH (d:Document) WITH count(d) AS doc_count OPTIONAL MATCH (e:Entity) WITH doc_count, count(e) AS entity_count OPTIONAL MATCH (c:Chunk) WITH doc_count, entity_count, count(c) AS chunk_count OPTIONAL MATCH ()-[r]->() WITH doc_count, entity_count, chunk_count, count(r) AS edge_count RETURN doc_count, entity_count, chunk_count, (doc_count+entity_count+chunk_count) AS node_count, edge_count")
            rec = await r.single()
            if rec: graph_nodes_total.set(rec["node_count"]); graph_edges_total.set(rec["edge_count"]); return {"node_count":rec["node_count"],"edge_count":rec["edge_count"],"documents":rec["doc_count"],"entities":rec["entity_count"]}
            return {"node_count":0,"edge_count":0,"documents":0,"entities":0}

    async def get_visualization_data(self, limit: int = 200, rbac_filter: str = "") -> dict:
        wc = f"WHERE {rbac_filter}" if rbac_filter else ""
        async with self.session() as s:
            r = await s.run(f"MATCH (n:Entity) {wc} WITH n LIMIT $limit OPTIONAL MATCH (n)-[r]-(m:Entity) RETURN collect(DISTINCT {{id:n.id,name:n.name,type:n.entity_type,clearance:n.clearance_level}}) AS nodes, collect(DISTINCT {{source:startNode(r).id,target:endNode(r).id,type:type(r)}}) AS edges", limit=limit)
            rec = await r.single(); return {"nodes":rec["nodes"],"edges":rec["edges"]} if rec else {"nodes":[],"edges":[]}


neo4j_service = Neo4jService()