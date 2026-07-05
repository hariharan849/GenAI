import logging
from typing import TYPE_CHECKING, List

from langchain_core.documents import Document

logger = logging.getLogger(__name__)

VALID_LABELS = frozenset({
    "NukeNode",
    "Knob",
    "InputType",
    "OutputType",
    "Category",
    "Operation",
    "Channel",
    "SupportedValue",
})
VALID_PREDICATES = frozenset({
    "HAS_KNOB",
    "KNOB_CONTROLS",
    "ACCEPTS_INPUT",
    "OUTPUTS",
    "BELONGS_TO",
    "AFFECTS_CHANNEL",
    "SUPPORTS_VALUE",
    "SIMILAR_TO",
})

if TYPE_CHECKING:
    pass


def _fact_cypher(subject_type: str, predicate: str, object_type: str) -> str | None:
    if (
        subject_type not in VALID_LABELS
        or predicate not in VALID_PREDICATES
        or object_type not in VALID_LABELS
    ):
        return None

    return (
        f"MERGE (a:{subject_type} {{name: $subject_name}}) "
        "SET a.entity_type = $subject_type "
        f"MERGE (b:{object_type} {{name: $object_name}}) "
        "SET b.entity_type = $object_type "
        f"MERGE (a)-[:{predicate}]->(b)"
    )


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
        """Merge typed graph facts into Neo4j. Returns facts written."""
        if not triples:
            return 0
        written = 0
        try:
            async with self._driver.session() as session:
                for triple in triples:
                    subject_type = getattr(triple, "subject_type", None)
                    predicate = getattr(triple, "predicate", None)
                    object_type = getattr(triple, "object_type", None)
                    cypher = _fact_cypher(subject_type, predicate, object_type)
                    if cypher is None:
                        logger.warning(
                            "Unknown graph fact shape '%s -[%s]-> %s' - skipping",
                            subject_type,
                            predicate,
                            object_type,
                        )
                        continue
                    await session.run(
                        cypher,
                        subject_name=triple.subject_name,
                        subject_type=triple.subject_type,
                        object_name=triple.object_name,
                        object_type=triple.object_type,
                    )
                    written += 1
        except Exception as e:
            logger.warning("Neo4j write_triples failed: %s", e)
        return written

    async def close(self) -> None:
        await self._driver.close()
