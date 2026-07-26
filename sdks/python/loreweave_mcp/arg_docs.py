"""K19 — recover the arg documentation the Python services already wrote.

THE BUG, measured live 2026-07-23 over all 1132 advertised args:

    composition  368/368 args with NO description   (100%)
    kg           128/128                            (100%)
    translation   46/46, plan 43/43, memory 17/17, jobs 14/14, lore 12/12, story 7/7
    ---- vs ----
    book          13/121  (11%)   glossary 29/239 (12%)   world 0/45   catalog 0/8

685 of 1132 args — 61% of the whole federated surface — reach the model with no description
at all, and the split is not by team or by age. It is by LANGUAGE. Go services document args
with `jsonschema:"…"` struct tags, which the Go SDK writes into the schema. Python services
document them as ``Annotated[str, "mine | system | all"]`` — and Pydantic only honours
`Field(...)`/`Doc(...)` inside Annotated. A bare string is kept as opaque metadata and
NEVER becomes a schema description.

So the documentation exists. It is in the source, it is accurate, and it is invisible to the
only reader that matters. Same family as the enum-in-prose bug and K16's wrapper: the author
wrote it down somewhere the model cannot read.

It matters most exactly where it is worst. `composition_arc_template_list.scope` is
`Annotated[str, "mine | system | all"]` with a runtime check that rejects anything else — so
a model that cannot see the values gets a hard error it has no way to avoid. 100% of
composition's and kg's args are in that state.

THE FIX. Pydantic keeps the unrecognised metadata on `FieldInfo.metadata`, so nothing was
lost — only mis-plumbed. At registration, for every arg with no description, promote the
first bare-string metadata entry into the schema. One seam, no call-site churn, and the docs
are the ones the authors already wrote (never invented here).

Deliberately additive: an arg that already HAS a description is untouched, so migrating a
service to `Field(description=…)` later silently supersedes this with no conflict.

Applied once per process from `make_stateless_fastmcp`, in the same defensive style as the
other kit patches: idempotent, and a no-op with a warning if the SDK's shape changes.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_PATCHED = "_lw_arg_docs_patched"

# A doc string, not a validator. Pydantic's own constraint objects (Gt, MaxLen, …) also live
# in `metadata`; only bare `str` entries are prose the author meant for a reader.
def _doc_from_metadata(meta_list) -> str | None:
    for m in meta_list or []:
        if isinstance(m, str) and m.strip():
            return m.strip()
    return None


def effective_model(model):
    """Resolve the model whose fields match the ADVERTISED properties.

    A handler written `(ctx, args: SomeModel)` has an arg_model with one field, `args`; K16's
    flat_args patch then hoists SomeModel's own properties to the top level. So the docs for
    what the model actually sees live on the INNER model, and looking only at the outer one
    would quietly fill nothing for exactly the 49 tools that needed it most.
    """
    fields = getattr(model, "model_fields", None)
    if not fields or len(fields) != 1:
        return model
    only = next(iter(fields.values()))
    inner = getattr(only, "annotation", None)
    if isinstance(inner, type) and hasattr(inner, "model_fields"):
        return inner
    return model


def apply_arg_docs(schema: dict, model) -> int:
    """Fill in missing `description`s on `schema.properties` from the arg model's metadata.

    Returns how many were filled. Pure apart from mutating the schema dict it is given, so
    it is unit-tested directly.
    """
    if not isinstance(schema, dict):
        return 0
    props = schema.get("properties")
    if not isinstance(props, dict):
        return 0
    model = effective_model(model)
    fields = getattr(model, "model_fields", None)
    if not fields:
        return 0
    filled = 0
    for name, field in fields.items():
        prop = props.get(name)
        if not isinstance(prop, dict) or prop.get("description"):
            continue
        doc = getattr(field, "description", None) or _doc_from_metadata(
            getattr(field, "metadata", None)
        )
        if doc:
            prop["description"] = doc
            filled += 1
    return filled


def patch_arg_docs() -> bool:
    """Promote Annotated-metadata docs into the advertised schema at registration."""
    try:
        from mcp.server.fastmcp.tools.tool_manager import ToolManager
    except Exception:
        logger.warning(
            "loreweave_mcp.arg_docs: could not import FastMCP's ToolManager — skipping; "
            "args documented via Annotated keep reaching the model undocumented.",
            exc_info=True,
        )
        return False

    if getattr(ToolManager, _PATCHED, False):
        return True
    if not hasattr(ToolManager, "add_tool"):
        logger.warning(
            "loreweave_mcp.arg_docs: ToolManager.add_tool not found — the mcp package "
            "shape has changed since this patch was written; skipping.",
        )
        return False

    _orig_add = ToolManager.add_tool

    def add_tool(self, fn, *a, **kw):
        tool = _orig_add(self, fn, *a, **kw)
        try:
            model = getattr(getattr(tool, "fn_metadata", None), "arg_model", None)
            if model is not None:
                apply_arg_docs(tool.parameters, model)
        except Exception:  # noqa: BLE001 — documentation is never worth a boot failure
            logger.warning(
                "loreweave_mcp.arg_docs: could not promote arg docs for %s",
                getattr(tool, "name", "?"), exc_info=True,
            )
        return tool

    ToolManager.add_tool = add_tool
    setattr(ToolManager, _PATCHED, True)
    return True
