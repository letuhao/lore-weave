"""K19 — the arg documentation the Python services already wrote must reach the model.

Measured live over all 1132 federated args: 685 (61%) carried NO description, and the split
was by LANGUAGE, not by team — Go's `jsonschema:"…"` tags land in the schema, Python's
`Annotated[str, "…"]` does not (Pydantic honours only Field/Doc inside Annotated; a bare
string is kept as opaque metadata). composition and kg were at 100% undocumented.

The docs were never lost, only mis-plumbed — Pydantic keeps them on `FieldInfo.metadata`.
These tests pin the recovery, and pin that it never INVENTS or OVERWRITES documentation.
"""
from __future__ import annotations

from typing import Annotated

import pytest
from pydantic import BaseModel, Field

from loreweave_mcp.arg_docs import apply_arg_docs, effective_model, patch_arg_docs


class _Flat(BaseModel):
    scope: Annotated[str, "mine | system | all"] = "all"
    limit: Annotated[int, "1..100"] = 10
    plain: str = "x"
    already: str = Field(default="y", description="an explicit description")


class TestApplyArgDocs:
    def test_promotes_annotated_metadata(self):
        schema = {"properties": {"scope": {"type": "string"}, "limit": {"type": "integer"}}}
        assert apply_arg_docs(schema, _Flat) == 2
        assert schema["properties"]["scope"]["description"] == "mine | system | all"
        assert schema["properties"]["limit"]["description"] == "1..100"

    def test_never_overwrites_an_existing_description(self):
        # Additive by design: a service migrating to Field(description=…) must silently
        # supersede this patch, never fight it.
        schema = {"properties": {"scope": {"type": "string", "description": "mine, please"}}}
        assert apply_arg_docs(schema, _Flat) == 0
        assert schema["properties"]["scope"]["description"] == "mine, please"

    def test_an_arg_with_no_docs_anywhere_is_left_alone(self):
        schema = {"properties": {"plain": {"type": "string"}}}
        assert apply_arg_docs(schema, _Flat) == 0
        assert "description" not in schema["properties"]["plain"]

    def test_a_real_field_description_is_preferred_over_metadata(self):
        schema = {"properties": {"already": {"type": "string"}}}
        apply_arg_docs(schema, _Flat)
        assert schema["properties"]["already"]["description"] == "an explicit description"

    def test_non_string_metadata_is_not_mistaken_for_docs(self):
        # Pydantic's own constraint objects (Gt, MaxLen, …) also live in `metadata`.
        class M(BaseModel):
            n: int = Field(default=1, gt=0)

        schema = {"properties": {"n": {"type": "integer"}}}
        assert apply_arg_docs(schema, M) == 0
        assert "description" not in schema["properties"]["n"]

    def test_malformed_inputs_are_survived(self):
        assert apply_arg_docs(None, _Flat) == 0
        assert apply_arg_docs({}, _Flat) == 0
        assert apply_arg_docs({"properties": {}}, None) == 0


class _Inner(BaseModel):
    from_id: Annotated[str, "the source motif id"]
    kind: Annotated[str, "composed_of | precedes | variant_of"] = "precedes"


class _Wrapper(BaseModel):
    args: _Inner


class TestEffectiveModel:
    def test_unwraps_a_single_model_field(self):
        # Without this, the 49 tools K16 flattened — the ones that needed docs most —
        # would silently get none: their properties come from the INNER model.
        assert effective_model(_Wrapper) is _Inner

    def test_a_flat_model_is_returned_as_is(self):
        assert effective_model(_Flat) is _Flat

    def test_a_single_NON_model_field_is_not_unwrapped(self):
        class One(BaseModel):
            only: Annotated[str, "just one arg"] = "a"

        assert effective_model(One) is One
        schema = {"properties": {"only": {"type": "string"}}}
        assert apply_arg_docs(schema, One) == 1


async def _flat_tool(
    scope: Annotated[str, "mine | system | all"] = "all",
    limit: Annotated[int, "1..100"] = 10,
) -> dict:
    return {}


async def _wrapped_tool(args: _Inner) -> dict:
    return {}


class TestAgainstARealFastMCPServer:
    @pytest.fixture
    def server(self):
        from mcp.server.fastmcp import FastMCP

        from loreweave_mcp.flat_args import patch_flat_args

        # Same order as make_stateless_fastmcp: flat_args first, arg_docs LAST so it runs
        # outermost and sees the already-flattened properties.
        patch_flat_args()
        patch_arg_docs()
        mcp = FastMCP("k19-test")
        mcp.tool(name="flat_tool", description="d")(_flat_tool)
        mcp.tool(name="wrapped_tool", description="d")(_wrapped_tool)
        return mcp

    @pytest.mark.asyncio
    async def test_a_flat_tool_advertises_its_docs(self, server):
        tools = {t.name: t for t in await server.list_tools()}
        props = tools["flat_tool"].inputSchema["properties"]
        assert props["scope"]["description"] == "mine | system | all"
        assert props["limit"]["description"] == "1..100"

    @pytest.mark.asyncio
    async def test_a_WRAPPED_tool_advertises_its_docs_after_flattening(self, server):
        # The composition case: K16 hoists the inner model's properties, K19 must then find
        # the docs on that inner model. Getting the patch ORDER wrong makes this red.
        tools = {t.name: t for t in await server.list_tools()}
        props = tools["wrapped_tool"].inputSchema["properties"]
        assert "args" not in props
        assert props["from_id"]["description"] == "the source motif id"
        assert props["kind"]["description"] == "composed_of | precedes | variant_of"

    def test_the_patch_is_idempotent(self):
        assert patch_arg_docs() is True
        assert patch_arg_docs() is True
