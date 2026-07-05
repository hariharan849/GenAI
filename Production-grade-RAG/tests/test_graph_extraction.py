"""Unit tests for api.services.graph.extraction."""
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from langextract import prompt_validation as pv

from api.services.graph.extraction import EXTRACTION_EXAMPLES, extract_triples


def _fact(
    subject_name,
    subject_type,
    predicate,
    object_name,
    object_type,
    *,
    grounded=True,
):
    return SimpleNamespace(
        extraction_class="graph_fact",
        char_interval=SimpleNamespace(start_pos=0, end_pos=10) if grounded else None,
        attributes={
            "subject_name": subject_name,
            "subject_type": subject_type,
            "predicate": predicate,
            "object_name": object_name,
            "object_type": object_type,
        },
    )


def _result(extractions):
    return SimpleNamespace(extractions=extractions)


def test_extraction_examples_are_alignable():
    assert EXTRACTION_EXAMPLES
    for example in EXTRACTION_EXAMPLES:
        assert example.text.strip()
        assert example.extractions
        for extraction in example.extractions:
            assert extraction.extraction_text.strip()
    report = pv.validate_prompt_alignment(EXTRACTION_EXAMPLES)
    assert report.issues == []


@pytest.mark.asyncio
async def test_extract_triples_parses_nuke_controls_without_langextract():
    text = (
        "Inputs and Controls Connection Type Connection Name Function "
        "Input unnamed The image sequence to blur. "
        "mask An optional image to use as a mask. "
        "Control (UI) Knob (Scripting) Default Value Function "
        "Blur Tab channels channels all The blur effect is only applied to these channels. "
        "size size 0 Sets the radius within which pixels are compared to calculate the blur. "
        "filter filter gaussian Selects the filter algorithm to use."
    )

    with patch("api.services.graph.extraction.lx.extract") as extract:
        triples = await extract_triples(text, node_name="Blur", section="filter_nodes")

    extract.assert_not_called()
    facts = {(triple.subject_name, triple.predicate, triple.object_name) for triple in triples}
    assert ("Blur", "BELONGS_TO", "filter_nodes") in facts
    assert ("Blur", "ACCEPTS_INPUT", "image input") in facts
    assert ("Blur", "ACCEPTS_INPUT", "mask input") in facts
    assert ("Blur", "HAS_KNOB", "channels") in facts
    assert ("channels", "AFFECTS_CHANNEL", "image channels") in facts
    assert ("Blur", "HAS_KNOB", "size") in facts
    assert ("size", "KNOB_CONTROLS", "Sets the radius within which pixels are compared to") in facts


@pytest.mark.asyncio
async def test_extract_triples_happy_path_typed_facts():
    mock_result = _result([
        _fact("Blur", "NukeNode", "HAS_KNOB", "Size", "Knob"),
        _fact("Size", "Knob", "KNOB_CONTROLS", "blur radius", "Operation"),
        _fact("Channels", "Knob", "AFFECTS_CHANNEL", "image channels", "Channel"),
    ])

    with patch("api.services.graph.extraction.lx.extract", return_value=mock_result):
        triples = await extract_triples(
            "Size controls the blur radius. Channels selects which image channels are affected.",
            node_name="Blur",
            section="filter_nodes",
        )

    assert len(triples) == 3
    assert triples[0].subject_name == "Blur"
    assert triples[0].subject_type == "NukeNode"
    assert triples[0].predicate == "HAS_KNOB"
    assert triples[0].object_name == "Size"
    assert triples[0].object_type == "Knob"
    assert triples[0].entity_a == "Blur"
    assert triples[0].relationship == "HAS_KNOB"
    assert triples[0].entity_b == "Size"


@pytest.mark.asyncio
async def test_extract_triples_passes_page_context_to_langextract():
    mock_result = _result([
        _fact("Blur", "NukeNode", "ACCEPTS_INPUT", "2D image", "InputType"),
    ])

    with patch("api.services.graph.extraction.lx.extract", return_value=mock_result) as extract:
        triples = await extract_triples(
            "This node accepts any 2D image as input.",
            node_name="Blur",
            section="filter_nodes",
        )

    assert len(triples) == 1
    source_text = extract.call_args.kwargs["text_or_documents"]
    assert source_text.startswith("Page node: Blur\nSection: filter_nodes")
    assert "This node accepts any 2D image as input." in source_text


@pytest.mark.asyncio
async def test_extract_triples_empty_text():
    triples = await extract_triples("")
    assert triples == []

    triples = await extract_triples("   ")
    assert triples == []


@pytest.mark.asyncio
async def test_extract_triples_retry_exhausted():
    with patch("api.services.graph.extraction.lx.extract", side_effect=Exception("provider error")):
        triples = await extract_triples("The Size knob controls blur radius.")

    assert triples == []


@pytest.mark.asyncio
async def test_extract_triples_empty_token_alignment_error_is_no_result(caplog):
    with patch(
        "api.services.graph.extraction.lx.extract",
        side_effect=ValueError("Source tokens and extraction tokens cannot be empty."),
    ):
        triples = await extract_triples("Blur node accepts input from Read node.")

    assert triples == []
    assert "KG extraction failed" not in caplog.text


@pytest.mark.asyncio
async def test_extract_triples_ollama_unreachable():
    import httpx

    with patch("api.services.graph.extraction.lx.extract", side_effect=httpx.ConnectError("Connection refused")):
        triples = await extract_triples("The Size knob controls blur radius.")

    assert triples == []


@pytest.mark.asyncio
async def test_extract_triples_no_relationships():
    mock_result = _result([])

    with patch("api.services.graph.extraction.lx.extract", return_value=mock_result):
        triples = await extract_triples("No knob, input, output, or channel facts here.")

    assert triples == []


@pytest.mark.asyncio
async def test_extract_triples_skips_invalid_predicate():
    mock_result = _result([
        _fact("Blur", "NukeNode", "USES", "Read", "NukeNode"),
        _fact("Blur", "NukeNode", "SIMILAR_TO", "Defocus", "NukeNode"),
    ])

    with patch("api.services.graph.extraction.lx.extract", return_value=mock_result):
        triples = await extract_triples("The Blur node is similar to Defocus.")

    assert len(triples) == 1
    assert triples[0].predicate == "SIMILAR_TO"


@pytest.mark.asyncio
async def test_extract_triples_skips_invalid_entity_type():
    mock_result = _result([
        _fact("Blur", "Tool", "HAS_KNOB", "Size", "Knob"),
        _fact("Blur", "NukeNode", "HAS_KNOB", "Size", "Knob"),
    ])

    with patch("api.services.graph.extraction.lx.extract", return_value=mock_result):
        triples = await extract_triples("The Size knob controls blur radius.")

    assert len(triples) == 1
    assert triples[0].subject_type == "NukeNode"


@pytest.mark.asyncio
async def test_extract_triples_skips_missing_attributes():
    extraction = SimpleNamespace(
        extraction_class="graph_fact",
        char_interval=SimpleNamespace(start_pos=0, end_pos=10),
        attributes={
            "subject_name": "Blur",
            "subject_type": "NukeNode",
            "predicate": "HAS_KNOB",
            "object_name": "Size",
        },
    )
    mock_result = _result([extraction])

    with patch("api.services.graph.extraction.lx.extract", return_value=mock_result):
        triples = await extract_triples("The Size knob controls blur radius.")

    assert triples == []


@pytest.mark.asyncio
async def test_extract_triples_skips_ungrounded_extraction():
    mock_result = _result([
        _fact("Blur", "NukeNode", "ACCEPTS_INPUT", "2D image", "InputType", grounded=False),
    ])

    with patch("api.services.graph.extraction.lx.extract", return_value=mock_result):
        triples = await extract_triples("Blur accepts any 2D image as input.")

    assert triples == []
