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
