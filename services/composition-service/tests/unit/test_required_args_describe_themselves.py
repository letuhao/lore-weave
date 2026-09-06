"""A REQUIRED argument must say what it is and where its value comes from.

🔴 **MEASURED 2026-08-25, and it is what a whole investigation turned on.**
`composition_build_cast_and_graph` requires `model_ref` for `op=start`. The argument carried **no
description at all** — schema `anyOf[string, null]`, default `null`, title "Model Ref", and
nothing else. Neither did `source_text`, which the same op also requires.

For weeks the tool was never selected, so this never surfaced. The moment a synonym de-duplication
let it be chosen — 6 of 15 live runs — **every single call failed**:

    ok=false  op=start  "model_ref is required for op=start"

The model picked the right tool, picked the right op, invented no `run_id`, and could not
complete, because the argument it was missing described neither what it is nor where to get one.
Describing all three took the same scenario to **15/15 called, 14/15 succeeding**.

IN-4: a constraint lives in the machine-readable schema, not only in the tool's prose. A required
argument whose description is empty is that rule's worst case — the tool's own text says it is
needed and the schema says nothing at all.
"""
from __future__ import annotations

import pytest

from app.mcp.server import _GlossaryBuildArgs

#: Arguments the tool's own description names as required for an op. Each must describe itself.
OP_REQUIRED = ["source_text", "model_ref"]


def _described(field) -> str:
    """The Field description, wherever pydantic put it (annotation metadata or the FieldInfo)."""
    if getattr(field, "description", None):
        return field.description
    for meta in getattr(field, "metadata", ()) or ():
        if getattr(meta, "description", None):
            return meta.description
    return ""


@pytest.mark.parametrize("name", OP_REQUIRED)
def test_an_op_required_argument_has_a_description(name):
    field = _GlossaryBuildArgs.model_fields[name]
    assert _described(field).strip(), (
        f"{name} is required by an op and describes itself as nothing. That is what made the "
        f"tool uncallable once it was finally chosen."
    )


def test_model_ref_names_where_its_value_comes_from():
    """Not merely described — a UUID argument must name its SUPPLIER.

    'the model to build with' would still leave a caller with nowhere to go. The value is
    `settings_list_models`' `user_model_id`, and saying so is the difference between an argument
    a model can fill and one it cannot.
    """
    d = _described(_GlossaryBuildArgs.model_fields["model_ref"]).lower()
    assert "settings_list_models" in d, "model_ref must name the tool that supplies it"
    assert "user_model_id" in d, "model_ref must name the FIELD that carries the value"


def test_source_text_says_the_caller_supplies_the_prose():
    """The whole distinction from kg_build: this tool reads what it is handed, not the chapters."""
    d = _described(_GlossaryBuildArgs.model_fields["source_text"]).lower()
    assert "op=start" in d or "start" in d
