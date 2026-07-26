"""D-LLM-FAILURE-RATE #1 — glossary-translate structured-output schema.

The glossary-translate worker forces its output to a JSON OBJECT of string values
keyed by the expected attribute codes (exactly what ``parse_translation_response``
consumes), killing the malformed-JSON parse failures ("Expecting ',' delimiter")
that fail an entity. The schema is the loose-but-typed contract; the per-call
LLMInvalidRequest fallback (worker) degrades a model that rejects it.
"""
from app.workers.glossary_translate_prompt import (
    attr_response_format,
    parse_translation_response,
)


def test_attr_response_format_is_string_object_over_expected_codes():
    rf = attr_response_format({"name", "description"})
    assert rf["type"] == "json_schema"
    schema = rf["json_schema"]["schema"]
    assert schema["type"] == "object"
    # additionalProperties:false matches the prompt's "do not add keys"
    assert schema["additionalProperties"] is False
    # each expected code is a string property; keys are sorted for stability
    assert schema["properties"] == {
        "description": {"type": "string"},
        "name": {"type": "string"},
    }


def test_attr_response_format_tracks_the_codes():
    rf = attr_response_format({"title"})
    assert list(rf["json_schema"]["schema"]["properties"].keys()) == ["title"]


def test_schema_shape_matches_what_the_parser_accepts():
    """A response conforming to the schema (object of code->string) parses cleanly
    into the expected dict — the schema and parser agree on the contract."""
    import json

    rf = attr_response_format({"name", "description"})
    props = rf["json_schema"]["schema"]["properties"]
    # a conforming payload: object with string values keyed by the schema's props
    payload = json.dumps({c: f"translated-{c}" for c in props})
    out = parse_translation_response(payload, {"name", "description"})
    assert out == {"name": "translated-name", "description": "translated-description"}
