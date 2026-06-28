import logging
from typing import List
from typing import Literal

import instructor
from openai import AsyncOpenAI
from pydantic import BaseModel

from api.config import get_settings

logger = logging.getLogger(__name__)

EXTRACTION_PROMPT = (
    "You are an information extractor for Nuke VFX documentation.\n"
    "Given the following text about Nuke nodes, extract relationships between Nuke nodes.\n"
    "Output a JSON object with a 'triples' array. Each triple must have:\n"
    "  entity_a: the source Nuke node name\n"
    "  relationship: one of ACCEPTS_INPUT, OUTPUTS_TO, or SIMILAR_TO\n"
    "  entity_b: the target Nuke node name\n"
    "Only extract relationships explicitly stated in the text. Use an empty array if none.\n\n"
    "Text:\n{text}"
)


class Triple(BaseModel):
    entity_a: str
    relationship: Literal["ACCEPTS_INPUT", "OUTPUTS_TO", "SIMILAR_TO"]
    entity_b: str


class TripleList(BaseModel):
    triples: List[Triple]


async def extract_triples(text: str) -> List[Triple]:
    """Extract (entity, relationship, entity) triples from text using instructor + Ollama.

    Returns an empty list on failure (retries exhausted, network error, or empty input).
    """
    if not text or not text.strip():
        return []

    settings = get_settings()
    try:
        client = instructor.from_openai(
            AsyncOpenAI(base_url=f"{settings.ollama_host}/v1", api_key="ollama"),
            mode=instructor.Mode.JSON,
        )
        result = await client.chat.completions.create(
            model=settings.ollama_model,
            response_model=TripleList,
            messages=[{"role": "user", "content": EXTRACTION_PROMPT.format(text=text[:3000])}],
            max_retries=3,
        )
        return result.triples
    except Exception as e:
        logger.warning("KG extraction failed: %s", e)
        return []
