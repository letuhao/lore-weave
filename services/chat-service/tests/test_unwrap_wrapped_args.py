"""gemma arg-wrapping repair — a mid-tier model wraps the whole payload in {"args": {...}}.

Measured live in S06: glossary_extract_entities_from_doc was called with
{"args": {"book_id": ..., "source_markdown": ...}} against a FLAT schema, so book_id was
hidden, the tool got nothing, and the cast never landed.
"""
from app.services.stream_service import _unwrap_wrapped_args

FLAT_DEF = {"function": {"parameters": {"properties": {
    "book_id": {"type": "string"}, "source_markdown": {"type": "string"},
}}}}


def test_unwraps_a_lone_args_envelope_the_schema_does_not_declare():
    got = _unwrap_wrapped_args({"args": {"book_id": "b", "source_markdown": "x"}}, FLAT_DEF)
    assert got == {"book_id": "b", "source_markdown": "x"}


def test_unwraps_arguments_too():
    got = _unwrap_wrapped_args({"arguments": {"book_id": "b"}}, FLAT_DEF)
    assert got == {"book_id": "b"}


def test_a_well_formed_call_is_untouched():
    call = {"book_id": "b", "source_markdown": "x"}
    assert _unwrap_wrapped_args(call, FLAT_DEF) == call


def test_never_eats_a_real_args_parameter():
    # a tool that GENUINELY has an `args` property must not be unwrapped
    deep = {"function": {"parameters": {"properties": {"args": {"type": "object"}}}}}
    call = {"args": {"x": 1}}
    assert _unwrap_wrapped_args(call, deep) == call


def test_a_multikey_dict_is_untouched():
    call = {"args": {"x": 1}, "book_id": "b"}
    assert _unwrap_wrapped_args(call, FLAT_DEF) == call


def test_a_non_dict_inner_is_untouched():
    call = {"args": "not a dict"}
    assert _unwrap_wrapped_args(call, FLAT_DEF) == call


# ── consumer-local meta tools (find_tools / tool_load / workflow_load / run_subagent /
# *_list) — the single-point wrap-repair at the top of the per-call loop unwraps with
# tool_def=None, which is only safe if NONE of them declares an args/arguments param.
def test_meta_tools_have_no_args_param_so_none_def_unwrap_is_safe():
    from app.services.stream_service import _CONSUMER_LOCAL_META_TOOLS
    from app.services.tool_discovery import (
        FIND_TOOLS_NAME, TOOL_LIST_NAME, TOOL_LOAD_NAME,
    )
    from app.services.workflow_runner import WORKFLOW_LIST_NAME, WORKFLOW_LOAD_NAME
    from app.services.subagent_runtime import RUN_SUBAGENT_NAME, build_run_subagent_tool
    # the closed set the loop repairs
    assert _CONSUMER_LOCAL_META_TOOLS == frozenset({
        FIND_TOOLS_NAME, TOOL_LIST_NAME, TOOL_LOAD_NAME,
        WORKFLOW_LIST_NAME, WORKFLOW_LOAD_NAME, RUN_SUBAGENT_NAME,
    })
    # run_subagent's real schema must NOT declare args/arguments (else None-def unwrap eats it)
    props = build_run_subagent_tool(["persona"])["function"]["parameters"]["properties"]
    assert "args" not in props and "arguments" not in props


def test_meta_tool_wrapped_payload_unwraps_with_none_def():
    # gemma wraps find_tools as {"args":{"intent":"..."}} — the loop unwraps to the inner dict
    assert _unwrap_wrapped_args({"args": {"intent": "lore"}}, None) == {"intent": "lore"}
    # workflow_load slug, tool_load names — same shape
    assert _unwrap_wrapped_args({"args": {"slug": "w5"}}, None) == {"slug": "w5"}
    # a well-formed meta call is untouched
    assert _unwrap_wrapped_args({"intent": "lore"}, None) == {"intent": "lore"}


# ── scalar-id list-unwrap: gemma wraps a scalar id arg in a 1-element list ─────
from app.services.stream_service import _coerce_listed_scalar_ids  # noqa: E402


def test_coerces_a_1element_list_wrapped_scalar_id():
    # measured live: kg_project_entities_to_nodes project_id=["<uuid>"] → tool 400s
    a = {"project_id": ["019f579c-f359-76e2-b76b-9ff2e2247055"], "entity_ids": ["a", "b"]}
    _coerce_listed_scalar_ids(a)
    assert a["project_id"] == "019f579c-f359-76e2-b76b-9ff2e2247055"  # unwrapped
    assert a["entity_ids"] == ["a", "b"]  # a real array param is NEVER touched


def test_coerce_is_a_noop_for_wellformed_and_multi_element():
    a = {"book_id": "b1", "project_id": ["x", "y"]}  # scalar already; 2-elem list not a scalar
    _coerce_listed_scalar_ids(a)
    assert a == {"book_id": "b1", "project_id": ["x", "y"]}


def test_coerce_only_touches_known_scalar_id_args():
    # a non-id arg that happens to be a 1-elem list is left alone (not in the closed set)
    a = {"items": [{"kind": "character"}]}
    _coerce_listed_scalar_ids(a)
    assert a == {"items": [{"kind": "character"}]}


# ── stringified-JSON struct repair: gemma sends a STRUCTURED arg as a JSON *string* ──────
# Measured live (M0a, 2026-07-13): book_chapter_save_draft body="[{...}]" → schema rejects
# (declared array, got str) → the model's repair MANGLES the JSON → blank-args breaker →
# the flagship's chapter row was created but its prose NEVER landed (empty shell read as done).
from app.services.stream_service import _coerce_json_string_structs  # noqa: E402

SAVE_DRAFT_DEF = {"function": {"parameters": {"properties": {
    "book_id": {"type": "string"},
    "chapter_id": {"type": "string"},
    "base_version": {"type": "integer"},
    "commit_message": {"type": "string"},
    "body": {"type": "array", "items": {"type": "object"}},
}}}}


def test_parses_a_stringified_json_array_for_an_array_param():
    # the EXACT live failure: correct prose, correct ids — only `body` was a string
    a = {
        "book_id": "b1", "chapter_id": "c1", "base_version": 1,
        "body": '[{"type":"paragraph","children":[{"text":"The silk felt like a shroud."}]}]',
    }
    _coerce_json_string_structs(a, SAVE_DRAFT_DEF)
    assert a["body"] == [
        {"type": "paragraph", "children": [{"text": "The silk felt like a shroud."}]}
    ]
    assert a["chapter_id"] == "c1"  # untouched


def test_leaves_a_real_array_alone():
    body = [{"type": "paragraph", "children": [{"text": "already correct"}]}]
    a = {"body": body}
    _coerce_json_string_structs(a, SAVE_DRAFT_DEF)
    assert a["body"] == body


def test_never_parses_a_string_param_even_if_it_looks_like_json():
    # a commit_message (declared string) that HAPPENS to start with '[' must survive verbatim —
    # this is the guard that stops the repair from eating real prose/text.
    a = {"commit_message": '[draft] chapter one', "book_id": "b1"}
    _coerce_json_string_structs(a, SAVE_DRAFT_DEF)
    assert a["commit_message"] == '[draft] chapter one'


def test_non_json_string_in_a_struct_param_is_left_for_the_validator():
    # garbage that does not parse must NOT be silently swallowed — the validator rejects it honestly
    a = {"body": "not json at all"}
    _coerce_json_string_structs(a, SAVE_DRAFT_DEF)
    assert a["body"] == "not json at all"


def test_wrong_parsed_type_is_left_alone():
    # parses fine, but to an OBJECT where the schema wants an ARRAY → not our repair
    a = {"body": '{"type":"paragraph"}'}
    _coerce_json_string_structs(a, SAVE_DRAFT_DEF)
    assert a["body"] == '{"type":"paragraph"}'


def test_object_param_stringified_is_parsed():
    d = {"function": {"parameters": {"properties": {"ctx": {"type": "object"}}}}}
    a = {"ctx": '{"k":1}'}
    _coerce_json_string_structs(a, d)
    assert a["ctx"] == {"k": 1}


def test_union_typed_param_still_repairs():
    # "type": ["array", "null"] — a nullable struct param must still repair
    d = {"function": {"parameters": {"properties": {"body": {"type": ["array", "null"]}}}}}
    a = {"body": '[{"x":1}]'}
    _coerce_json_string_structs(a, d)
    assert a["body"] == [{"x": 1}]


def test_a_param_that_may_be_string_or_array_is_NOT_coerced():
    # if the schema legitimately accepts a string, a string is a VALID value — hands off,
    # or we would silently change the caller's meaning.
    d = {"function": {"parameters": {"properties": {"q": {"type": ["string", "array"]}}}}}
    a = {"q": '["a","b"]'}
    _coerce_json_string_structs(a, d)
    assert a["q"] == '["a","b"]'


def test_no_tool_def_is_a_safe_noop():
    a = {"body": '[{"x":1}]'}
    _coerce_json_string_structs(a, None)
    assert a["body"] == '[{"x":1}]'  # schema-free ⇒ we cannot know it's a struct ⇒ don't guess
