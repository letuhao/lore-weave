"""composition_conformance_run declared a required-list that could not be satisfied.

FOUND 2026-09-02 by DQ-T72's owner-directed read ("retire on a CAUSE, not on a rate"): of the
twelve tools that have never returned ok and never reached a confirm card, this is the ONLY one
whose own CONTRACT is the defect. 37 calls, ZERO successes — the whole recorded population:

    arc_id is required when scope='arc'                                    8
    chapter_id is required when scope='chapter'                            3
    model_ref is required when scope='arc' (the deep overlay tags prose)   3
    pydantic validation errors (1, 2 and 3 at a time)                     11
    missing required argument(s): ['args'] / the repeat breaker            7
    not found or not accessible                                            5

THE INVARIANT: a tool's DECLARED required-list must be satisfiable — supplying exactly what the
schema says is required must not be refused FOR A MISSING ARGUMENT. Here the schema advertised
`required: [project_id, scope]` with SIX properties carrying no description at all, while the
handler refused per scope. Whichever scope a caller picked, it was refused.

The conditional rule was written down all along — in a CODE COMMENT, where the model never sees
it. The same shape as DQ-T4's `,omitempty` and DQ-T5's refusal naming a tool it could not reach.
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from app.mcp.server import _ConformanceRunArgs  # noqa: E402

SCHEMA = _ConformanceRunArgs.model_json_schema()
PROPS = SCHEMA.get("properties") or {}


def _desc(name: str) -> str:
    return (PROPS.get(name) or {}).get("description") or ""


def test_every_conditionally_required_argument_SAYS_when_it_is_required():
    """🔴 THE REGRESSION THIS EXISTS FOR. All six properties shipped with NO description, so the
    schema was silent about a rule the handler enforces. A caller cannot satisfy a requirement
    it is never told about."""
    for name, scope in (("chapter_id", "chapter"), ("arc_id", "arc"), ("model_ref", "arc")):
        d = _desc(name)
        assert d, (
            f"{name} carries no description — the handler refuses without it "
            f"(\"{name} is required when scope='{scope}'\") and the schema says nothing"
        )
        assert "REQUIRED" in d and scope in d, (
            f"{name}'s description does not say it is REQUIRED when scope='{scope}': {d!r}"
        )


def test_the_scope_argument_names_what_it_makes_required():
    """`scope` is the discriminator; reading it must tell the caller what else to send."""
    d = _desc("scope")
    assert "chapter_id" in d and "arc_id" in d and "model_ref" in d, (
        f"scope does not name the arguments it makes required: {d!r}"
    )


def test_the_declared_required_list_is_unchanged():
    """The fix is HONESTY, not a schema change. Making chapter_id/arc_id unconditionally
    required would break the other scope — each is required for exactly one of the two."""
    assert set(SCHEMA.get("required") or []) == {"project_id", "scope"}
    for optional in ("chapter_id", "arc_id", "model_ref", "model_source"):
        assert optional not in (SCHEMA.get("required") or []), (
            f"{optional} was made unconditionally required — it is required for ONE scope, so "
            "this now refuses the other scope for an argument it does not need"
        )


def test_arc_id_still_says_it_is_a_structure_node_not_a_template():
    """BA4 (23): the arc scope diffs the SPEC against the prose, so arc_id is a structure_node
    id. Template drift is a different tool, and this distinction lived only in the comment."""
    d = _desc("arc_id")
    assert "template" in d.lower(), f"arc_id no longer warns against a template id: {d!r}"
