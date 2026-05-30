"""LangGraph tools for GraphRAG retrieval, reranking, and graph queries.

These tools can be bound to the LangGraph agent for tool-calling workflows.
"""

from langchain_core.tools import tool


@tool
async def vector_search(query: str, top_k: int = 5) -> str:
    """Search the vector knowledge base for relevant document chunks.

    Use this tool when you need to find specific information from legal documents,
    laws, or regulations in the knowledge base.

    Args:
        query: The search query in Russian.
        top_k: Number of results to return (default: 5).

    Returns:
        Relevant text chunks from the knowledge base.
    """
    from app.services.ollama_service import ollama_service
    from app.services.qdrant_service import qdrant_service
    from app.core.graphrag.vector_indexer import vector_indexer_service

    try:
        results = await vector_indexer_service.search_similar(
            query=query,
            ollama_service=ollama_service,
            qdrant_service=qdrant_service,
            top_k=top_k,
        )

        if not results:
            return "По запросу ничего не найдено в базе знаний."

        output_parts = []
        for i, r in enumerate(results, 1):
            payload = r.get("payload", {})
            text = payload.get("text", "")
            title = payload.get("title", "N/A")
            score = r.get("score", 0)
            output_parts.append(f"[{i}] (score: {score:.2f}) {title}\n{text}")

        return "\n\n---\n".join(output_parts)
    except Exception as e:
        return f"Ошибка поиска: {str(e)}"


@tool
async def graph_query(entity_name: str, depth: int = 2) -> str:
    """Query the knowledge graph for entity relationships and connections.

    Use this tool when you need to explore relationships between legal entities,
    laws, organizations, or concepts in the knowledge graph.

    Args:
        entity_name: Name of the entity to explore (in Russian).
        depth: Traversal depth (1-3, default: 2).

    Returns:
        Graph neighborhood data with entities and their relationships.
    """
    from app.services.neo4j_service import neo4j_service

    try:
        data = await neo4j_service.get_entity_neighborhood(
            entity_name=entity_name,
            depth=min(depth, 3),
            limit=30,
        )

        if not data.get("nodes"):
            return f"Сущность «{entity_name}» не найдена в графе знаний."

        parts = [f"Результаты для «{entity_name}»:"]

        for node in data["nodes"][:15]:
            name = node.get("name", "")
            ntype = node.get("entity_type", node.get("type", ""))
            parts.append(f"  • [{ntype}] {name}")

        parts.append("\nСвязи:")
        for edge in data["edges"][:15]:
            parts.append(
                f"  → {edge.get('source', '')} --[{edge.get('type', '')}]--> {edge.get('target', '')}"
            )

        return "\n".join(parts)
    except Exception as e:
        return f"Ошибка запроса графа: {str(e)}"


@tool
async def entity_search(query: str, entity_type: str = "") -> str:
    """Search for specific entities in the knowledge graph by name.

    Use this tool to find specific laws, articles, organizations, courts,
    or other legal entities by name.

    Args:
        query: Search query (entity name or part of it, in Russian).
        entity_type: Optional filter by entity type (ЗАКОН, СТАТЬЯ, ОРГАНИЗАЦИЯ, СУД, ПОНЯТИЕ).

    Returns:
        List of matching entities with their types.
    """
    from app.services.neo4j_service import neo4j_service

    try:
        results = await neo4j_service.search_entities(
            query=query,
            entity_type=entity_type or None,
            limit=20,
        )

        if not results:
            return f"Сущности по запросу «{query}» не найдены."

        parts = [f"Найдено {len(results)} сущностей:"]
        for ent in results:
            name = ent.get("name", "")
            etype = ent.get("entity_type", "")
            desc = ent.get("description", "")
            line = f"  • [{etype}] {name}"
            if desc:
                line += f" — {desc}"
            parts.append(line)

        return "\n".join(parts)
    except Exception as e:
        return f"Ошибка поиска сущностей: {str(e)}"


@tool
async def hybrid_search(query: str) -> str:
    """Perform a hybrid search combining vector similarity and graph traversal.

    Use this tool for complex queries that may benefit from both semantic
    search and structured knowledge graph exploration.

    Args:
        query: The search query in Russian.

    Returns:
        Combined results from vector search and graph traversal.
    """
    # Run vector search
    vector_result = await vector_search.ainvoke({"query": query, "top_k": 3})

    # Extract potential entity names from query for graph search
    import re

    quoted = re.findall(r'[«"]([^»"]+)[»"]', query)
    graph_results = []
    for entity in quoted[:3]:
        result = await graph_query.ainvoke({"entity_name": entity, "depth": 2})
        graph_results.append(result)

    combined = f"=== Результаты поиска по базе знаний ===\n{vector_result}"
    if graph_results:
        combined += f"\n\n=== Результаты из графа знаний ===\n" + "\n---\n".join(graph_results)

    return combined


# List of all tools for LangGraph binding
graphrag_tools = [vector_search, graph_query, entity_search, hybrid_search]
