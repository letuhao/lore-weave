"""K16 — advertise ONE calling convention for every tool.

THE BUG (measured live 2026-07-23 across the federated hot-set):

    250 tools advertise their arguments FLAT      {"properties": {"from_motif_id": …}}
     49 tools advertise them WRAPPED              {"properties": {"args": {"$ref": …}},
                                                   "required": ["args"]}

All 49 wrapped ones were `composition_*`, and the split is not even a per-provider rule the
model could learn — it cuts through SIBLING PAIRS of the same concept:

    composition_motif_link_create    WRAPPED   |  composition_motif_link_delete    FLAT
    composition_scene_link_create    WRAPPED   |  composition_scene_link_delete    FLAT
    composition_outline_node_create  WRAPPED   |  composition_outline_node_delete  FLAT
    composition_canon_rule_create    WRAPPED   |  composition_canon_rule_delete    FLAT

The cause is a FastMCP signature detail, not a design decision: a handler written
``async def t(ctx, args: SomeModel)`` gets a single wrapper parameter named ``args``, while
``async def t(ctx, project_id: str, link_id: str)`` gets flat properties. Two authoring
styles in one file became two calling conventions on the wire.

WHY IT MATTERS. The Frontend-Tool Contract's "one name for one concept" rule exists because
a surface joined only by an LLM cannot afford ambiguity. This is the same failure at the
ARG-SHAPE level, and it is worse than a naming slip: a model that has learned the flat shape
from 250 tools sends flat args to these 49 and gets ``Field required: args``. The `$ref`
indirection compounds it — a weak model must resolve `#/$defs/_MotifLinkCreateArgs` to see
any parameter name at all.

THE FIX — two halves, deliberately asymmetric:

  * SCHEMA (what we advertise): hoist the wrapped model's own properties/required to the top
    level, so every tool advertises flat args. `$defs` is preserved so nested `$ref`s inside
    the hoisted properties still resolve.
  * CALLS (what we accept): accept BOTH shapes forever. Flat args get re-wrapped before
    validation; a legacy ``{"args": {…}}`` payload passes through untouched. Pydantic remains
    the single source of validation truth — this patch never re-implements it.

Accepting both is not fence-sitting. A saved workflow, a pinned skill, or a cached tool
schema may still send the wrapped shape, and breaking those to fix a discoverability bug
would trade one silent failure for another.

Applied once per process from `make_stateless_fastmcp`, alongside the other kit patches, and
written in the same defensive style: idempotent, and on any SDK shape change it logs and
leaves the SDK's behaviour untouched rather than raising at import time.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_SCHEMA_PATCHED = "_lw_flat_args_schema_patched"
_CALL_PATCHED = "_lw_flat_args_call_patched"

# The wrapper parameter FastMCP generates for a single Pydantic-model parameter. It is the
# PARAMETER NAME, so it is whatever the handler called it; `args` is the only name in use
# here and pinning it keeps the patch from firing on a genuine one-field tool.
_WRAPPER_NAME = "args"


def _resolve_ref(schema: dict, defs: dict) -> dict | None:
    """Follow a single local `$ref` into `$defs`. Returns None for anything else —
    a remote/unknown ref is left alone rather than guessed at."""
    ref = schema.get("$ref")
    if not isinstance(ref, str):
        return schema if schema.get("type") == "object" else None
    prefix = "#/$defs/"
    if not ref.startswith(prefix):
        return None
    return defs.get(ref[len(prefix):])


def flatten_wrapper_schema(parameters: dict) -> dict:
    """Hoist a single `args` wrapper's fields to the top level.

    Returns the schema UNCHANGED when it is not the wrapped shape, so this is safe to run
    over every tool. Pure function — unit-tested directly.
    """
    if not isinstance(parameters, dict):
        return parameters
    props = parameters.get("properties")
    if not isinstance(props, dict) or list(props) != [_WRAPPER_NAME]:
        return parameters
    if parameters.get("required") not in ([_WRAPPER_NAME], None):
        return parameters

    defs = parameters.get("$defs") or {}
    target = _resolve_ref(props[_WRAPPER_NAME], defs)
    if not isinstance(target, dict) or not isinstance(target.get("properties"), dict):
        return parameters

    out = {"type": "object", "properties": dict(target["properties"])}
    if target.get("required"):
        out["required"] = list(target["required"])
    if "additionalProperties" in target:
        out["additionalProperties"] = target["additionalProperties"]
    # Keep the WHOLE $defs table: a hoisted property may still `$ref` a sibling model
    # (a nested value object), and dropping the table would leave a dangling ref — a
    # schema that no longer validates is worse than the wrapper it replaced.
    if defs:
        out["$defs"] = defs
    return out


def rewrap_flat_arguments(tool, arguments: dict) -> dict:
    """Re-wrap flat call arguments into `{args: {...}}` for a wrapper-shaped tool.

    Pass-through when the tool is not wrapper-shaped, or when the caller already sent the
    wrapped shape (a legacy workflow / a cached schema).
    """
    if not isinstance(arguments, dict):
        return arguments
    meta = getattr(tool, "fn_metadata", None)
    model = getattr(meta, "arg_model", None)
    fields = getattr(model, "model_fields", None)
    if not fields or list(fields) != [_WRAPPER_NAME]:
        return arguments
    # Already wrapped — the ONLY key is `args` and it carries an object. Untouched.
    if list(arguments) == [_WRAPPER_NAME] and isinstance(
        arguments.get(_WRAPPER_NAME), dict
    ):
        return arguments
    # An empty payload stays empty: wrapping it as {"args": {}} would turn a "you sent
    # nothing" error into a confusing per-field one.
    if not arguments:
        return arguments
    return {_WRAPPER_NAME: arguments}


def patch_flat_args() -> bool:
    """Apply both halves. Idempotent; returns False (with a warning) if the SDK's shape
    changed, leaving the default behaviour in place."""
    try:
        from mcp.server.fastmcp.tools.tool_manager import ToolManager
    except Exception:
        logger.warning(
            "loreweave_mcp.flat_args: could not import FastMCP's ToolManager — skipping "
            "the flat-args patch; wrapper-shaped tools keep the SDK's nested schema.",
            exc_info=True,
        )
        return False

    if not hasattr(ToolManager, "add_tool") or not hasattr(ToolManager, "call_tool"):
        logger.warning(
            "loreweave_mcp.flat_args: ToolManager.add_tool/call_tool not found — the mcp "
            "package shape has changed since this patch was written; skipping.",
        )
        return False

    if not getattr(ToolManager, _SCHEMA_PATCHED, False):
        _orig_add = ToolManager.add_tool

        def add_tool(self, fn, *a, **kw):
            tool = _orig_add(self, fn, *a, **kw)
            try:
                flat = flatten_wrapper_schema(tool.parameters)
                if flat is not tool.parameters:
                    tool.parameters = flat
            except Exception:  # noqa: BLE001 — advertising is never worth a boot failure
                logger.warning(
                    "loreweave_mcp.flat_args: could not flatten the schema for %s — it "
                    "keeps the nested `args` shape.", getattr(tool, "name", "?"),
                    exc_info=True,
                )
            return tool

        ToolManager.add_tool = add_tool
        setattr(ToolManager, _SCHEMA_PATCHED, True)

    if not getattr(ToolManager, _CALL_PATCHED, False):
        _orig_call = ToolManager.call_tool

        async def call_tool(self, name, arguments, *a, **kw):
            tool = self.get_tool(name)
            if tool is not None:
                try:
                    arguments = rewrap_flat_arguments(tool, arguments)
                except Exception:  # noqa: BLE001 — fall through to the SDK's own error
                    logger.warning(
                        "loreweave_mcp.flat_args: re-wrap failed for %s — passing the "
                        "arguments through unchanged.", name, exc_info=True,
                    )
            return await _orig_call(self, name, arguments, *a, **kw)

        ToolManager.call_tool = call_tool
        setattr(ToolManager, _CALL_PATCHED, True)

    return True
