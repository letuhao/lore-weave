"""K21.1 — unit tests for the memory tool definitions.

Covers: OpenAI-schema well-formedness, schema↔arg-model drift lock,
the design-D3 envelope/tool-arg separation, and arg-model validation
(enums, bounds, `extra="forbid"`, the timeline date pattern).
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.db.neo4j_repos.facts import FACT_TYPES
from app.tools.definitions import (
    ARG_MODELS,
    TOOL_DEFINITIONS,
    TOOL_NAMES,
    MemoryForgetArgs,
    MemoryRecallEntityArgs,
    MemoryRememberArgs,
    MemorySearchArgs,
    MemoryTimelineArgs,
)

# Identity/session keys that must NEVER appear in an LLM-facing tool schema —
# they come from the trusted envelope (design D3). INV-K2 amendment (H-I):
# `project_id` is NO LONGER here — it is a deliberately-allowed, ownership-checked
# SCOPE selector (the public edge mints no X-Project-Id, so a public agent supplies
# it as an arg; the owner gate confines it to the caller's own projects). user_id /
# session_id stay envelope-only forever — they are identity, never an LLM arg.
_ENVELOPE_KEYS = {"user_id", "session_id"}


def _defn(name: str) -> dict:
    """The TOOL_DEFINITIONS entry for `name`."""
    return next(d for d in TOOL_DEFINITIONS if d["function"]["name"] == name)


# ── registry consistency ──────────────────────────────────────────────


def test_memory_tools_still_defined():
    """The 5 memory tools remain registered (lane LF appended KG tools but
    must not drop any). The exact total is asserted in test_graph_schema_tools."""
    names = {d["function"]["name"] for d in TOOL_DEFINITIONS}
    assert {
        "memory_search",
        "memory_recall_entity",
        "memory_timeline",
        "memory_remember",
        "memory_forget",
    }.issubset(names)
    assert len(TOOL_DEFINITIONS) == len(TOOL_NAMES)


def test_tool_names_match_arg_models_and_definitions():
    """TOOL_NAMES, ARG_MODELS keys, and the schema function names are
    the same set — a tool added to one place must land in all three."""
    schema_names = {d["function"]["name"] for d in TOOL_DEFINITIONS}
    assert set(TOOL_NAMES) == set(ARG_MODELS) == schema_names


def test_no_duplicate_tool_names():
    names = [d["function"]["name"] for d in TOOL_DEFINITIONS]
    assert len(names) == len(set(names))


# ── OpenAI schema well-formedness ─────────────────────────────────────


@pytest.mark.parametrize("name", ["memory_search", "memory_recall_entity",
                                  "memory_timeline", "memory_remember",
                                  "memory_forget"])
def test_tool_is_valid_openai_function_schema(name: str):
    defn = _defn(name)
    assert defn["type"] == "function"
    fn = defn["function"]
    assert isinstance(fn["name"], str) and fn["name"]
    assert isinstance(fn["description"], str) and len(fn["description"]) > 20
    params = fn["parameters"]
    assert params["type"] == "object"
    assert isinstance(params["properties"], dict)
    assert isinstance(params["required"], list)
    # OpenAI strict tool-calling expects additionalProperties:false.
    assert params["additionalProperties"] is False
    # Every required key is an actual property.
    assert set(params["required"]).issubset(params["properties"])
    # Every property carries a type + a model-facing description.
    for prop_name, prop in params["properties"].items():
        assert "type" in prop, prop_name
        assert prop.get("description"), prop_name


# ── schema ↔ arg-model drift lock ─────────────────────────────────────


@pytest.mark.parametrize("name", list(ARG_MODELS))
def test_schema_properties_match_arg_model_fields(name: str):
    """The JSON-schema properties and the Pydantic arg-model fields are
    the same set, and `required` agrees on both sides. This is the
    drift lock — hand-written schema + validated model can't diverge."""
    params = _defn(name)["function"]["parameters"]
    model = ARG_MODELS[name]

    schema_props = set(params["properties"])
    model_fields = set(model.model_fields)
    assert schema_props == model_fields

    schema_required = set(params["required"])
    model_required = {
        f for f, info in model.model_fields.items() if info.is_required()
    }
    assert schema_required == model_required


def test_no_envelope_keys_leak_into_any_schema():
    """Design D3 / INV-K2 (H-I-amended) — user_id / session_id are envelope
    identity fields, NEVER tool parameters. (project_id IS now an allowed
    ownership-checked scope arg — see test_search_args_accepts_project_id.)"""
    for defn in TOOL_DEFINITIONS:
        props = set(defn["function"]["parameters"]["properties"])
        assert _ENVELOPE_KEYS.isdisjoint(props), defn["function"]["name"]
    for model in ARG_MODELS.values():
        assert _ENVELOPE_KEYS.isdisjoint(model.model_fields)


def test_enum_values_match_their_source_of_truth():
    remember_props = _defn("memory_remember")["function"]["parameters"]["properties"]
    assert remember_props["fact_type"]["enum"] == list(FACT_TYPES)
    search_props = _defn("memory_search")["function"]["parameters"]["properties"]
    assert search_props["source_type"]["enum"] == ["chapter", "chat", "glossary"]


# ── arg-model validation ──────────────────────────────────────────────


def test_search_args_defaults_and_bounds():
    args = MemorySearchArgs(query="who is Kai")
    assert args.limit == 10
    assert args.source_type is None
    with pytest.raises(ValidationError):
        MemorySearchArgs(query="x", limit=21)  # le=20
    with pytest.raises(ValidationError):
        MemorySearchArgs(query="x", limit=0)  # ge=1
    with pytest.raises(ValidationError):
        MemorySearchArgs(query="")  # min_length=1


def test_search_args_accepts_project_id_but_rejects_identity_and_typos():
    """H-I — project_id is now a valid, optional, ownership-checked scope arg.
    extra='forbid' still rejects a hallucinated/typo param and (critically) the
    identity keys user_id / session_id, which an LLM must never set."""
    ok = MemorySearchArgs(query="x", project_id="11111111-1111-1111-1111-111111111111")
    assert ok.project_id == "11111111-1111-1111-1111-111111111111"
    assert MemorySearchArgs(query="x").project_id is None  # optional
    with pytest.raises(ValidationError):
        MemorySearchArgs(query="x", typo_param=1)
    with pytest.raises(ValidationError):
        MemorySearchArgs(query="x", user_id="smuggled")  # identity stays forbidden
    with pytest.raises(ValidationError):
        MemorySearchArgs(query="x", session_id="smuggled")


def test_search_args_source_type_enum():
    assert MemorySearchArgs(query="x", source_type="chat").source_type == "chat"
    with pytest.raises(ValidationError):
        MemorySearchArgs(query="x", source_type="wiki")


def test_remember_args_fact_type_enum():
    for ft in FACT_TYPES:
        assert MemoryRememberArgs(fact_text="x", fact_type=ft).fact_type == ft
    with pytest.raises(ValidationError):
        MemoryRememberArgs(fact_text="x", fact_type="rumour")
    with pytest.raises(ValidationError):
        MemoryRememberArgs(fact_text="x")  # fact_type required


def test_timeline_args_all_optional_with_default_limit():
    args = MemoryTimelineArgs()
    assert args.from_date is None and args.to_date is None
    assert args.entity_name is None
    assert args.limit == 20


@pytest.mark.parametrize("ok", ["1850", "1850-03", "1850-03-21", "0001-12-31"])
def test_timeline_args_accept_truncated_iso(ok: str):
    assert MemoryTimelineArgs(from_date=ok).from_date == ok


@pytest.mark.parametrize("bad", ["1850-13", "1850-00", "1850-03-32",
                                 "not-a-date", "50", "1850/03"])
def test_timeline_args_reject_malformed_date(bad: str):
    with pytest.raises(ValidationError):
        MemoryTimelineArgs(from_date=bad)


def test_timeline_args_reject_reversed_range():
    """/review-impl MED#1 — from_date after to_date is rejected at the
    model, so the executor surfaces a clear tool error instead of a
    silently-empty timeline."""
    with pytest.raises(ValidationError):
        MemoryTimelineArgs(from_date="1850-12", to_date="1850-01")
    # Forward, equal, and open-ended ranges all stay valid.
    MemoryTimelineArgs(from_date="1850-01", to_date="1850-12")
    MemoryTimelineArgs(from_date="1850", to_date="1850")
    MemoryTimelineArgs(from_date="1850-06")
    MemoryTimelineArgs(to_date="1850-06")


def test_recall_and_forget_args_require_their_field():
    assert MemoryRecallEntityArgs(entity_name="Kai").entity_name == "Kai"
    with pytest.raises(ValidationError):
        MemoryRecallEntityArgs(entity_name="")
    assert MemoryForgetArgs(fact_id="fact-abc").fact_id == "fact-abc"
    with pytest.raises(ValidationError):
        MemoryForgetArgs(fact_id="")
