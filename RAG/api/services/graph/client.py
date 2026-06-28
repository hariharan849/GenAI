import logging
from typing import TYPE_CHECKING, List

from langchain_core.documents import Document

logger = logging.getLogger(__name__)

VALID_PREDICATES = frozenset({"ACCEPTS_INPUT", "OUTPUTS_TO", "SIMILAR_TO"})

_PREDICATE_CYPHER = {
    "ACCEPTS_INPUT": (
        "MERGE (a:NukeNode {name: $ea}) "
        "MERGE (b:NukeNode {name: $eb}) "
        "MERGE (a)-[:ACCEPTS_INPUT]->(b)"
    ),
    "OUTPUTS_TO": (
        "MERGE (a:NukeNode {name: $ea}) "
        "MERGE (b:NukeNode {name: $eb}) "
        "MERGE (a)-[:OUTPUTS_TO]->(b)"
    ),
    "SIMILAR_TO": (
        "MERGE (a:NukeNode {name: $ea}) "
        "MERGE (b:NukeNode {name: $eb}) "
        "MERGE (a)-[:SIMILAR_TO]->(b)"
    ),
}

if TYPE_CHECKING:
    pass


class Neo4jClient:
    """Async Neo4j client for knowledge graph retrieval."""

    def __init__(self, bolt_url: str, user: str, password: str):
        try:
            from neo4j import AsyncGraphDatabase
        except ImportError as e:
            raise ImportError("neo4j package is required: uv add neo4j") from e
        self._driver = AsyncGraphDatabase.driver(bolt_url, auth=(user, password))

    async def verify_connectivity(self) -> bool:
        try:
            await self._driver.verify_connectivity()
            return True
        except Exception as e:
            logger.warning(f"Neo4j connectivity check failed: {e}")
            return False

    async def node_count(self) -> int:
        async with self._driver.session() as session:
            result = await session.run("MATCH (n:NukeNode) RETURN count(n) AS c")
            record = await result.single()
            return record["c"] if record else 0

    async def kg_search(self, entity: str) -> list[Document]:
        """Return 1-hop neighbours of a NukeNode as Documents."""
        async with self._driver.session() as session:
            result = await session.run(
                "MATCH (n:NukeNode {name: $entity})-[r]-(m) "
                "RETURN m.name AS neighbor, type(r) AS rel_type LIMIT 10",
                entity=entity,
            )
            docs: list[Document] = []
            async for record in result:
                neighbor = record["neighbor"]
                rel = record["rel_type"].replace("_", " ").lower()
                content = f"{entity} {rel} {neighbor}."
                docs.append(
                    Document(
                        page_content=content,
                        metadata={
                            "source": "kg",
                            "url": "",
                            "entity": entity,
                            "neighbor": neighbor,
                            "rel_type": record["rel_type"],
                        },
                    )
                )
            return docs

    async def write_triples(self, triples: "List") -> int:
        """Merge (entity, relationship, entity) triples into Neo4j. Returns triples written.

        Uses three-step MERGE to avoid creating duplicate nodes when the relationship
        is new but both nodes already exist. Skips triples with unknown predicates.
        """
        if not triples:
            return 0
        written = 0
        try:
            async with self._driver.session() as session:
                for triple in triples:
                    cypher = _PREDICATE_CYPHER.get(triple.relationship)
                    if cypher is None:
                        logger.warning("Unknown predicate '%s' — skipping", triple.relationship)
                        continue
                    await session.run(cypher, ea=triple.entity_a, eb=triple.entity_b)
                    written += 1
        except Exception as e:
            logger.warning("Neo4j write_triples failed: %s", e)
        return written

    async def close(self) -> None:
        await self._driver.close()
