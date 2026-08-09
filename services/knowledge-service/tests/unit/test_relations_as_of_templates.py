"""The as-of clause must be in exactly the right Cypher templates (plan T18, fixed in T20).

This test exists because a blanket string replace put the clause in the WRONG places and
missed the right ones, and the unit suite could not tell:

  - it landed in `_EGO_HOP_STEP`, which never binds `$as_of_ordinal` — so every subgraph
    read failed with `ParameterMissing`. Loud, but only against a live Neo4j.
  - it MISSED `_FIND_RELATIONS_1HOP_OUTGOING_CYPHER` and `..._INCOMING_CYPHER`, which DO
    bind the parameter. Those queries accepted `as_of=N` and silently returned HEAD edges.
    That one is not loud at all: `relations_for(direction="outgoing", as_of=40)` returned a
    plausible answer that ignored the position entirely.

A source-level assertion catches both in CI without a database. The behavioural proof lives
in the live repo tests (`tests/integration/db/test_relations_repo.py`).
"""

from __future__ import annotations

import pathlib
import re

import pytest

_SRC = pathlib.Path(__file__).resolve().parents[2] / "app" / "db" / "neo4j_repos" / "relations.py"
_MARKER = "$as_of_ordinal IS NULL"


def _template(name: str) -> str:
    """The body of one `NAME = \"\"\"…\"\"\"` block, by name."""
    src = _SRC.read_text(encoding="utf-8").replace("\r\n", "\n")
    m = re.search(rf'^{re.escape(name)}\s*=\s*"""\n(.*?)\n"""', src, re.S | re.M)
    assert m, f"{name} is no longer a triple-quoted template in relations.py"
    return m.group(1)


# The three reads that TAKE an as_of position. Each must apply it, or it accepts the
# argument and ignores it.
@pytest.mark.parametrize("name", [
    "_FIND_RELATIONS_1HOP_OUTGOING_CYPHER",
    "_FIND_RELATIONS_1HOP_INCOMING_CYPHER",
    "_FIND_RELATIONS_1HOP_BOTH_CYPHER",
])
def test_every_one_hop_template_applies_the_as_of_clause(name):
    body = _template(name)
    assert _MARKER in body, (
        f"{name} binds $as_of_ordinal but never references it — an as-of read on that "
        "direction silently returns HEAD edges, which looks like a correct answer"
    )
    # Half-open, and spelled the same way in all three. A template that drifted to `<=`
    # on the end bound would include the position an edge ENDS at.
    assert "$as_of_ordinal < r.valid_to_ordinal" in body, f"{name} lost the half-open end bound"
    assert "r.valid_from_ordinal <= $as_of_ordinal" in body, f"{name} lost the inclusive start"


# The queries that do NOT bind the parameter. The clause here is not a style problem — it
# is a hard failure, because Neo4j rejects a statement referencing an unbound parameter.
@pytest.mark.parametrize("name", ["_EGO_HOP_STEP", "_EGO_CENTER_CYPHER", "_PROJECT_SUBGRAPH_CYPHER"])
def test_templates_that_do_not_bind_as_of_must_not_reference_it(name):
    assert _MARKER not in _template(name), (
        f"{name} references $as_of_ordinal but its caller never binds it — Neo4j raises "
        "ParameterMissing and every subgraph read fails"
    )


def test_the_both_template_applies_the_clause_to_each_union_branch():
    """`_FIND_RELATIONS_1HOP_BOTH_CYPHER` is a UNION of an outgoing and an incoming leg.
    A clause on only one leg filters half the edges and returns the other half unfiltered —
    the kind of half-correct answer that reads as correct."""
    assert _template("_FIND_RELATIONS_1HOP_BOTH_CYPHER").count(_MARKER) == 2
