"""K16 — every tool must advertise ONE calling convention, and accept the legacy one.

The bug, measured live on the federated hot-set 2026-07-23: 250 tools advertised flat args,
49 advertised `{"args": {"$ref": …}}` — all 49 `composition_*`, and the split cut through
sibling pairs (`*_create` wrapped, `*_delete` flat) so no per-provider rule could rescue a
model. Cause: `async def t(ctx, args: Model)` vs `async def t(ctx, a: str, b: str)`.

These tests cover the pure schema transform, the call-side tolerance, and — most importantly
— a REAL FastMCP server end to end, because a transform that is correct in isolation but not
actually wired is the silent-no-op shape this repo keeps rediscovering.
"""
from __future__ import annotations

import pytest
from pydantic import BaseModel, Field

from loreweave_mcp.flat_args import (
    flatten_wrapper_schema,
    patch_flat_args,
    rewrap_flat_arguments,
)

WRAPPED = {
    "type": "object",
    "properties": {"args": {"$ref": "#/$defs/_LinkArgs"}},
    "required": ["args"],
    "$defs": {
        "_LinkArgs": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "from_id": {"type": "string"},
                "to_id": {"type": "string"},
                "kind": {"enum": ["a", "b"], "type": "string"},
                "ord": {"anyOf": [{"type": "integer"}, {"type": "null"}], "default": None},
            },
            "required": ["from_id", "to_id", "kind"],
        }
    },
}


class TestFlattenWrapperSchema:
    def test_hoists_properties_and_required(self):
        out = flatten_wrapper_schema(WRAPPED)
        assert set(out["properties"]) == {"from_id", "to_id", "kind", "ord"}
        assert out["required"] == ["from_id", "to_id", "kind"]
        assert "args" not in out["properties"], "the wrapper must be gone, not merely joined"

    def test_preserves_additional_properties_and_enums(self):
        out = flatten_wrapper_schema(WRAPPED)
        assert out["additionalProperties"] is False
        assert out["properties"]["kind"]["enum"] == ["a", "b"], (
            "a closed-set arg must keep its enum — dropping it would re-open the "
            "free-string hole the Frontend-Tool Contract exists to close"
        )

    def test_keeps_defs_so_nested_refs_still_resolve(self):
        nested = {
            "type": "object",
            "properties": {"args": {"$ref": "#/$defs/Outer"}},
            "required": ["args"],
            "$defs": {
                "Outer": {
                    "type": "object",
                    "properties": {"inner": {"$ref": "#/$defs/Inner"}},
                    "required": ["inner"],
                },
                "Inner": {"type": "object", "properties": {"x": {"type": "string"}}},
            },
        }
        out = flatten_wrapper_schema(nested)
        assert out["properties"]["inner"] == {"$ref": "#/$defs/Inner"}
        assert "Inner" in out["$defs"], (
            "dropping $defs would leave a dangling $ref — a schema that no longer "
            "validates is worse than the wrapper it replaced"
        )

    def test_a_flat_schema_is_returned_untouched(self):
        flat = {"type": "object", "properties": {"book_id": {"type": "string"}},
                "required": ["book_id"]}
        assert flatten_wrapper_schema(flat) is flat

    def test_a_genuine_single_field_named_args_is_not_hoisted(self):
        # The wrapper is detected by NAME, so a real tool whose one parameter happens to be
        # called `args` must survive. It is not a $ref to an object model, so it is skipped.
        real = {"type": "object", "properties": {"args": {"type": "string"}},
                "required": ["args"]}
        assert flatten_wrapper_schema(real) is real

    def test_non_dict_input_is_survived(self):
        assert flatten_wrapper_schema(None) is None


class _LinkArgs(BaseModel):
    from_id: str
    to_id: str
    kind: str = Field(default="a")


class _Tool:
    """Minimal stand-in exposing only what rewrap reads (fn_metadata.arg_model)."""

    def __init__(self, model):
        self.fn_metadata = type("M", (), {"arg_model": model})()


class _Wrapper(BaseModel):
    args: _LinkArgs


class _Flat(BaseModel):
    book_id: str


class TestRewrapFlatArguments:
    def test_flat_args_are_wrapped(self):
        t = _Tool(_Wrapper)
        got = rewrap_flat_arguments(t, {"from_id": "1", "to_id": "2", "kind": "a"})
        assert got == {"args": {"from_id": "1", "to_id": "2", "kind": "a"}}

    def test_already_wrapped_passes_through(self):
        # The legacy shape must keep working: a saved workflow or a cached tool schema may
        # still send it, and breaking those to fix a discoverability bug would trade one
        # silent failure for another.
        t = _Tool(_Wrapper)
        payload = {"args": {"from_id": "1", "to_id": "2"}}
        assert rewrap_flat_arguments(t, payload) is payload

    def test_a_flat_tool_is_never_touched(self):
        t = _Tool(_Flat)
        payload = {"book_id": "b"}
        assert rewrap_flat_arguments(t, payload) is payload

    def test_empty_payload_stays_empty(self):
        # Wrapping {} into {"args": {}} would turn "you sent nothing" into a confusing
        # per-field validation error.
        t = _Tool(_Wrapper)
        assert rewrap_flat_arguments(t, {}) == {}


class _LiveLinkArgs(BaseModel):
    from_id: str
    to_id: str
    kind: str = "a"


async def _wrapped_tool(args: _LiveLinkArgs) -> dict:
    return {"from_id": args.from_id, "to_id": args.to_id, "kind": args.kind}


async def _flat_tool(book_id: str) -> dict:
    return {"book_id": book_id}


class TestAgainstARealFastMCPServer:
    """The half that matters: proven through a real server, not the helpers in isolation."""

    @pytest.fixture
    def server(self):
        from mcp.server.fastmcp import FastMCP

        patch_flat_args()
        mcp = FastMCP("k16-test")
        # NB: the arg model must be MODULE-level (see _LiveLinkArgs). FastMCP resolves
        # annotations with `inspect.signature(eval_str=True)`, which cannot see a class
        # defined inside this fixture — the first draft did that and every live test
        # errored with InvalidSignature before reaching a single assertion.
        mcp.tool(name="wrapped_tool", description="wrapper-shaped")(_wrapped_tool)
        mcp.tool(name="flat_tool", description="flat")(_flat_tool)
        return mcp

    @pytest.mark.asyncio
    async def test_the_advertised_schema_is_flat(self, server):
        tools = {t.name: t for t in await server.list_tools()}
        props = tools["wrapped_tool"].inputSchema["properties"]
        assert set(props) >= {"from_id", "to_id", "kind"}
        assert "args" not in props, (
            "the wrapper still reaches the model — this is the exact schema a weak model "
            "cannot call without resolving a $ref first"
        )

    @pytest.mark.asyncio
    async def test_a_flat_call_now_works(self, server):
        # Before the patch this raised `Field required: args`.
        out = await server.call_tool("wrapped_tool", {"from_id": "1", "to_id": "2"})
        assert '"from_id": "1"' in str(out) or "1" in str(out)

    @pytest.mark.asyncio
    async def test_the_legacy_wrapped_call_still_works(self, server):
        out = await server.call_tool("wrapped_tool", {"args": {"from_id": "9", "to_id": "8"}})
        assert "9" in str(out)

    @pytest.mark.asyncio
    async def test_validation_is_still_pydantic_not_reimplemented(self, server):
        # A missing REQUIRED field must still fail. If the re-wrap swallowed validation we
        # would have traded a wire-shape bug for a data-integrity one.
        with pytest.raises(Exception):
            await server.call_tool("wrapped_tool", {"from_id": "only-one"})

    @pytest.mark.asyncio
    async def test_a_flat_tool_is_unaffected(self, server):
        tools = {t.name: t for t in await server.list_tools()}
        assert set(tools["flat_tool"].inputSchema["properties"]) == {"book_id"}
        out = await server.call_tool("flat_tool", {"book_id": "b1"})
        assert "b1" in str(out)

    def test_the_patch_is_idempotent(self):
        assert patch_flat_args() is True
        assert patch_flat_args() is True
