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
