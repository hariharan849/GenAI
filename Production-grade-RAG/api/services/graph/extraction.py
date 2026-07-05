import logging
import re
from typing import List
from typing import Literal

import langextract as lx
from pydantic import BaseModel

from api.config import get_settings

logger = logging.getLogger(__name__)


class KGExtractionError(RuntimeError):
    """Raised when the provider path fails and the caller wants retry semantics."""

EXTRACTION_PROMPT = (
    "Extract explicitly stated Nuke documentation facts for a knowledge graph. "
    "Use extraction_class='graph_fact' and attributes subject_name, subject_type, "
    "predicate, object_name, object_type. Valid entity types are NukeNode, Knob, "
    "InputType, OutputType, Category, Operation, Channel, and SupportedValue. "
    "Valid predicates are HAS_KNOB, KNOB_CONTROLS, ACCEPTS_INPUT, OUTPUTS, "
    "BELONGS_TO, AFFECTS_CHANNEL, SUPPORTS_VALUE, and SIMILAR_TO. "
    "Use the page node as subject when the text says 'this node' or describes a "
    "knob/input for the current node. Do not infer facts that are not directly stated. "
    "If no relationship is present, return no extractions. "
    "Never emit an extraction with empty extraction_text."
)

EXTRACTION_EXAMPLES = [
    lx.data.ExampleData(
        text="Page node: Blur\nSection: filter_nodes\n\nThe Blur node accepts any 2D image as input.",
        extractions=[
            lx.data.Extraction(
                extraction_class="graph_fact",
                extraction_text="Blur node accepts any 2D image as input",
                attributes={
                    "subject_name": "Blur",
                    "subject_type": "NukeNode",
                    "predicate": "ACCEPTS_INPUT",
                    "object_name": "2D image",
                    "object_type": "InputType",
                },
            )
        ],
    ),
    lx.data.ExampleData(
        text="Page node: Blur\nSection: filter_nodes\n\nThe node has a Size knob. Size controls blur radius.",
        extractions=[
            lx.data.Extraction(
                extraction_class="graph_fact",
                extraction_text="The node has a Size knob.",
                attributes={
                    "subject_name": "Blur",
                    "subject_type": "NukeNode",
                    "predicate": "HAS_KNOB",
                    "object_name": "Size",
                    "object_type": "Knob",
                },
            ),
            lx.data.Extraction(
                extraction_class="graph_fact",
                extraction_text="Size controls blur radius.",
                attributes={
                    "subject_name": "Size",
                    "subject_type": "Knob",
                    "predicate": "KNOB_CONTROLS",
                    "object_name": "blur radius",
                    "object_type": "Operation",
                },
            )
        ],
    ),
    lx.data.ExampleData(
        text="Page node: Blur\nSection: filter_nodes\n\nThe node has a Channels knob. Channels affects image channels.",
        extractions=[
            lx.data.Extraction(
                extraction_class="graph_fact",
                extraction_text="The node has a Channels knob.",
                attributes={
                    "subject_name": "Blur",
                    "subject_type": "NukeNode",
                    "predicate": "HAS_KNOB",
                    "object_name": "Channels",
                    "object_type": "Knob",
                },
            ),
            lx.data.Extraction(
                extraction_class="graph_fact",
                extraction_text="Channels affects image channels.",
                attributes={
                    "subject_name": "Channels",
                    "subject_type": "Knob",
                    "predicate": "AFFECTS_CHANNEL",
                    "object_name": "image channels",
                    "object_type": "Channel",
                },
            )
        ],
    ),
]

VALID_ENTITY_TYPES = frozenset({
    "NukeNode",
    "Knob",
    "InputType",
    "OutputType",
    "Category",
    "Operation",
    "Channel",
    "SupportedValue",
})
VALID_RELATIONSHIPS = frozenset({
    "HAS_KNOB",
    "KNOB_CONTROLS",
    "ACCEPTS_INPUT",
    "OUTPUTS",
    "BELONGS_TO",
    "AFFECTS_CHANNEL",
    "SUPPORTS_VALUE",
    "SIMILAR_TO",
})
RELATIONSHIP_CUES = (
    "accept",
    "input",
    "output",
    "knob",
    "controls",
    "selects",
    "channels",
    "supports",
    "similar",
    "operation",
    "category",
)

CONTROL_FUNCTION_VERBS = (
    "Adds",
    "Adjusts",
    "Affects",
    "Applies",
    "Blurs",
    "Controls",
    "Copies",
    "Creates",
    "Decreases",
    "Defines",
    "Disables",
    "Dissolves",
    "Enables",
    "Inverts",
    "Limits",
    "Moves",
    "Randomly",
    "Removes",
    "Resets",
    "Scales",
    "Selects",
    "Sets",
    "Simulates",
    "Specifies",
    "The",
    "Uses",
    "Where",
)
INVALID_KNOB_NAMES = frozenset({
    "area",
    "areas",
    "box",
    "gaussian",
    "image",
    "input",
    "inputs",
    "node",
    "output",
    "outputs",
    "quadratic",
    "triangle",
    "value",
    "values",
})
INVALID_CONTROL_LABEL_STARTS = frozenset({
    "at",
    "by",
    "disabling",
    "flares",
    "gray",
    "higher",
    "if",
    "injecting",
    "negative",
    "note",
    "positive",
    "setting",
    "the",
    "these",
    "this",
    "when",
    "where",
    "you",
})

EntityType = Literal[
    "NukeNode",
    "Knob",
    "InputType",
    "OutputType",
    "Category",
    "Operation",
    "Channel",
    "SupportedValue",
]
Predicate = Literal[
    "HAS_KNOB",
    "KNOB_CONTROLS",
    "ACCEPTS_INPUT",
    "OUTPUTS",
    "BELONGS_TO",
    "AFFECTS_CHANNEL",
    "SUPPORTS_VALUE",
    "SIMILAR_TO",
]


class Triple(BaseModel):
    subject_name: str
    subject_type: EntityType
    predicate: Predicate
    object_name: str
    object_type: EntityType

    @property
    def entity_a(self) -> str:
        return self.subject_name

    @property
    def relationship(self) -> str:
        return self.predicate

    @property
    def entity_b(self) -> str:
        return self.object_name


class TripleList(BaseModel):
    triples: List[Triple]


def _dedupe_triples(triples: list[Triple]) -> list[Triple]:
    seen: set[tuple[str, str, str, str, str]] = set()
    unique: list[Triple] = []
    for triple in triples:
        key = (
            triple.subject_name.lower(),
            triple.subject_type,
            triple.predicate,
            triple.object_name.lower(),
            triple.object_type,
        )
        if key not in seen:
            seen.add(key)
            unique.append(triple)
    return unique


def _sentence_fragment(text: str, *, max_words: int = 8) -> str:
    words = re.findall(r"[A-Za-z][A-Za-z0-9_-]*", text)
    if not words:
        return ""
    return " ".join(words[:max_words])


def _input_object_name(connection_name: str, description: str) -> str:
    name = connection_name.strip()
    if name.lower() != "unnamed":
        return f"{name} input"
    if "image" in description.lower():
        return "image input"
    fragment = _sentence_fragment(description, max_words=4)
    return f"{fragment} input" if fragment else "unnamed input"


def _operation_name(function_text: str) -> str:
    fragment = _sentence_fragment(function_text, max_words=9)
    return fragment or "documented behavior"


def _extract_section(text: str, start_pattern: str, stop_patterns: tuple[str, ...]) -> str:
    start = re.search(start_pattern, text, flags=re.IGNORECASE)
    if not start:
        return ""
    body = text[start.end() :]
    stops = [
        match.start()
        for pattern in stop_patterns
        if (match := re.search(pattern, body, flags=re.IGNORECASE))
    ]
    if stops:
        body = body[: min(stops)]
    return body.strip()


def _extract_input_triples(text: str, node_name: str) -> list[Triple]:
    section = _extract_section(
        text,
        r"Inputs and Controls\s+Connection Type\s+Connection Name\s+Function",
        (r"Control \(UI\)", r"Can't find what you're looking for\?", r"Nuke \d"),
    )
    if not section:
        return []

    row_pattern = re.compile(
        r"(?:^|(?<=\.)\s+)Input\s+"
        r"(?P<name>[A-Za-z][A-Za-z0-9_ -]{0,40}?)\s+"
        r"(?P<description>(?:The|An|A|By default|Optional|Required|This|If|When)\b.*?)(?=\s+\bInput\s+|\s+\bOutput\s+|$)",
        flags=re.IGNORECASE,
    )
    triples: list[Triple] = []
    for match in row_pattern.finditer(section):
        connection_name = " ".join(match.group("name").split())
        description = " ".join(match.group("description").split())
        object_name = _input_object_name(connection_name, description)
        triples.append(Triple(
            subject_name=node_name,
            subject_type="NukeNode",
            predicate="ACCEPTS_INPUT",
            object_name=object_name,
            object_type="InputType",
        ))

    followup_row_pattern = re.compile(
        r"(?:^|(?<=\.)\s+)"
        r"\b(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s+"
        r"(?P<description>(?:The|An|A|By default|Optional|Required|This|If|When)\b.*?)(?="
        r"\s+\b[A-Za-z][A-Za-z0-9_ -]{0,40}?\s+(?:The|An|A|By default|Optional|Required|This|If|When)\b|$)",
        flags=re.IGNORECASE,
    )
    for match in followup_row_pattern.finditer(section):
        connection_name = " ".join(match.group("name").split())
        if (
            connection_name.lower() in {"connection type", "connection name", "function", "input", "output"}
            or connection_name.lower().startswith(("input ", "output "))
        ):
            continue
        description = " ".join(match.group("description").split())
        object_name = _input_object_name(connection_name, description)
        triples.append(Triple(
            subject_name=node_name,
            subject_type="NukeNode",
            predicate="ACCEPTS_INPUT",
            object_name=object_name,
            object_type="InputType",
        ))
    return triples


def _extract_control_triples(text: str, node_name: str) -> list[Triple]:
    section = _extract_section(
        text,
        r"Control \(UI\)\s+Knob \(Scripting\)\s+Default Value\s+Function",
        (r"Can't find what you're looking for\?", r"Nuke \d"),
    )
    if not section:
        return []

    function_start = "|".join(CONTROL_FUNCTION_VERBS)
    row_pattern = re.compile(
        rf"(?P<label>[A-Za-z][A-Za-z0-9_/() -]{{0,48}}?)\s+"
        rf"(?P<knob>[A-Za-z_][A-Za-z0-9_]*|N/A)\s+"
        rf"(?P<default>disabled|enabled|none|all|N/A|[-+]?\d+(?:[.,]\d+)?(?:,\s*[-+]?\d+(?:[.,]\d+)?){{0,2}}|[A-Za-z0-9_.:-]+)\s+"
        rf"(?P<function>(?:{function_start})\b.*?)(?="
        rf"\.\s+[A-Za-z][A-Za-z0-9_/() -]{{0,48}}?\s+(?:[A-Za-z_][A-Za-z0-9_]*|N/A)\s+"
        rf"(?:disabled|enabled|none|all|N/A|[-+]?\d+(?:[.,]\d+)?|[A-Za-z0-9_.:-]+)\s+(?:{function_start})\b|$)",
        flags=re.IGNORECASE,
    )

    triples: list[Triple] = []
    for match in row_pattern.finditer(section):
        label = " ".join(match.group("label").split())
        knob = match.group("knob").strip()
        function_text = " ".join(match.group("function").split())
        label_first_word = label.split(maxsplit=1)[0].lower()
        if (
            knob.lower() == "tab"
            or knob.lower() in INVALID_KNOB_NAMES
            or label_first_word in INVALID_CONTROL_LABEL_STARTS
        ):
            continue
        knob_name = label if knob.upper() == "N/A" else knob
        if not knob_name:
            continue

        triples.append(Triple(
            subject_name=node_name,
            subject_type="NukeNode",
            predicate="HAS_KNOB",
            object_name=knob_name,
            object_type="Knob",
        ))
        triples.append(Triple(
            subject_name=knob_name,
            subject_type="Knob",
            predicate="KNOB_CONTROLS",
            object_name=_operation_name(function_text),
            object_type="Operation",
        ))
        if "channel" in function_text.lower():
            triples.append(Triple(
                subject_name=knob_name,
                subject_type="Knob",
                predicate="AFFECTS_CHANNEL",
                object_name="image channels",
                object_type="Channel",
            ))

    return triples


def _extract_deterministic_triples(
    text: str,
    *,
    node_name: str | None = None,
    section: str | None = None,
) -> list[Triple]:
    if not node_name:
        return []

    table_triples: list[Triple] = []
    table_triples.extend(_extract_input_triples(text, node_name))
    table_triples.extend(_extract_control_triples(text, node_name))
    table_triples = _dedupe_triples(table_triples)
    if not table_triples:
        return []

    triples: list[Triple] = []
    if section:
        triples.append(Triple(
            subject_name=node_name,
            subject_type="NukeNode",
            predicate="BELONGS_TO",
            object_name=section,
            object_type="Category",
        ))
    triples.extend(table_triples)
    return _dedupe_triples(triples)


def _extraction_to_triple(extraction) -> Triple | None:
    if extraction.extraction_class != "graph_fact":
        return None
    if not getattr(extraction, "char_interval", None):
        return None

    attributes = getattr(extraction, "attributes", None) or {}
    subject_name = attributes.get("subject_name")
    subject_type = attributes.get("subject_type")
    predicate = attributes.get("predicate")
    object_name = attributes.get("object_name")
    object_type = attributes.get("object_type")
    if (
        not subject_name
        or subject_type not in VALID_ENTITY_TYPES
        or predicate not in VALID_RELATIONSHIPS
        or not object_name
        or object_type not in VALID_ENTITY_TYPES
    ):
        return None

    return Triple(
        subject_name=subject_name.strip(),
        subject_type=subject_type,
        predicate=predicate,
        object_name=object_name.strip(),
        object_type=object_type,
    )


async def extract_triples(
    text: str,
    *,
    node_name: str | None = None,
    section: str | None = None,
    raise_on_provider_error: bool = False,
) -> List[Triple]:
    """Extract graph triples from Nuke docs.

    Deterministic parsing handles the Nuke docs table structure first. LangExtract
    is only a fallback for prose-only pages where no table facts are available.
    """
    if not text or not text.strip():
        return []

    deterministic_triples = _extract_deterministic_triples(text, node_name=node_name, section=section)
    if deterministic_triples:
        return deterministic_triples

    source_text = text[:3000]
    normalized_text = " ".join(source_text.lower().split())
    if not any(cue in normalized_text for cue in RELATIONSHIP_CUES):
        return []

    context_header = ""
    if node_name:
        context_header += f"Page node: {node_name}\n"
    if section:
        context_header += f"Section: {section}\n"
    if context_header:
        source_text = f"{context_header}\n{source_text}"

    settings = get_settings()
    try:
        result = lx.extract(
            text_or_documents=source_text,
            prompt_description=EXTRACTION_PROMPT,
            examples=EXTRACTION_EXAMPLES,
            model_id=settings.ollama_model,
            model_url=settings.ollama_host,
        )
        triples = [
            triple
            for extraction in getattr(result, "extractions", [])
            if (triple := _extraction_to_triple(extraction)) is not None
        ]
        return triples
    except Exception as e:
        message = str(e)
        if "Source tokens and extraction tokens cannot be empty" in message:
            logger.debug("KG extraction returned no alignable relationship text: %s", e)
            return []
        if raise_on_provider_error:
            raise KGExtractionError(message) from e
        logger.warning("KG extraction failed: %s", e)
        return []
