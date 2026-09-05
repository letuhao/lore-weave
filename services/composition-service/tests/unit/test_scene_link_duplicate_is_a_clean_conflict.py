"""TOOLV2 LOOP #218 — a repeat scene link leaked the raw Postgres error.

Creating the same (from, to, kind) edge twice answered:

    duplicate key value violates unique constraint "uq_scene_link_edge"
    DETAIL:  Key (from_node_id, to_node_id, kind)=(019ff045-…, 019ff045-…, setup_payoff)

which names an internal constraint and a column tuple, in a vocabulary the caller does not speak.

This was the one site that missed an established pattern rather than a missing pattern. Three
siblings in the same service already catch asyncpg.UniqueViolationError and answer in the tool's own
terms:

    composition_motif_link_create   -> "that edge already exists"
    composition_motif_create        -> "a motif with this code already exists in your library"
    composition_arc_template_create -> "an arc template with this code already exists in your library"

The refusal is shaped as `outcome: applied_conflict`, which the kit's error contract treats as a
recognised non-error result rather than a failure — the same shape the other conflicts use, so a
caller can branch on it uniformly.
"""

import ast
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "app" / "mcp" / "server.py"
BODY = SRC.read_text(encoding="utf-8").replace("\r\n", "\n")


def _handler() -> str:
    start = BODY.index("async def composition_scene_link_create(")
    nxt = BODY.find("\nasync def ", start + 10)
    return BODY[start: nxt if nxt != -1 else len(BODY)]


def test_a_duplicate_edge_is_caught_before_it_reaches_the_caller():
    h = _handler()
    assert "except asyncpg.UniqueViolationError:" in h, (
        "the raw Postgres unique-violation is exposed again, constraint name and all"
    )


def test_the_conflict_is_phrased_in_the_tools_own_terms():
    h = _handler()
    assert "that scene link already exists" in h
    # Naming which tuple collided is what makes it actionable — there are three components.
    assert "same from, to, and kind" in h


def test_it_uses_the_recognised_conflict_outcome_like_its_siblings():
    """`outcome: applied_conflict` is what the kit's error contract treats as a recognised
    non-error result; without it the payload becomes a generic failure and loses that meaning."""
    h = _handler()
    assert '"outcome": "applied_conflict"' in h


def test_the_reference_violation_path_is_untouched():
    """A missing scene must still be the uniform deny — the fix must not turn a not-found into a
    conflict, which would tell the caller the edge exists when the scene does not."""
    h = _handler()
    assert "except ReferenceViolationError as exc:" in h
    assert "raise uniform_not_accessible(exc) from exc" in h


def test_the_module_still_imports_asyncpg_for_that_catch():
    tree = ast.parse(SRC.read_text(encoding="utf-8"))
    imported = {
        a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names
    }
    assert "asyncpg" in imported, "the except clause references asyncpg; the import must stay"
