"""Tests for the federation-safety check (see schema_federation.py)."""

from __future__ import annotations

import pytest

from loreweave_mcp.schema_federation import (
    assert_no_boolean_subschemas,
    check_tools,
    find_boolean_subschemas,
)


def test_flags_a_boolean_where_a_schema_belongs():
    # The shape that took the whole glossary provider down: a union payload whose
    # schema is the bare boolean `true`.
    schema = {"type": "object", "properties": {"items": True}}
    assert find_boolean_subschemas(schema, "t") == ["t/properties/items"]


def test_exempts_non_subschema_keywords():
    # `default: true` on a bool flag is normal — measured live, ALL 12 apparent hits
    # across the five Python providers were `.../<flag>/default`. Flagging those would
    # make the check fire on every healthy service.
    schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "include_archived": {"type": "boolean", "default": False},
            "use_web": {"type": "boolean", "default": True, "examples": [True, False]},
            "tags": {"type": "array", "uniqueItems": True},
            "mode": {"const": True},
            "flag": {"enum": [True, False]},
        },
    }
    assert find_boolean_subschemas(schema, "t") == []


def test_check_tools_reads_both_dict_and_object_tools():
    class ToolObj:
        name = "obj_tool"
        input_schema = {"type": "object", "properties": {"x": True}}
        output_schema = None

    dict_tool = {"name": "dict_tool", "outputSchema": {"type": "object", "properties": {"y": True}}}
    # Findings come back in tool order (each tool's own paths sorted within it).
    bad = check_tools([ToolObj(), dict_tool])
    assert bad == ["obj_tool.inputSchema/properties/x", "dict_tool.outputSchema/properties/y"]


def test_assert_names_every_offending_path():
    with pytest.raises(AssertionError) as exc:
        assert_no_boolean_subschemas([{"name": "t", "inputSchema": {"properties": {"a": True}}}])
    # The message must name the path AND the consequence, or the next person hits the
    # same cross-service, cross-language dead end.
    assert "t.inputSchema/properties/a" in str(exc.value)
    assert "EVERY tool of this provider" in str(exc.value)


def test_clean_tools_pass():
    assert_no_boolean_subschemas([
        {"name": "ok", "inputSchema": {"type": "object", "properties": {"n": {"type": "integer"}}}},
    ])
