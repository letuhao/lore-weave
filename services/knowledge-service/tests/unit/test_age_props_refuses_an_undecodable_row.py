"""T17 A20 — an undecodable agtype row must RAISE, not become a blank Entity.

`_props` turned a `json.JSONDecodeError` into `{}`, and `_to_entity({})` does not fail: every
field has a default, so the result is a well-formed `Entity` with `id=""`, `name=""`,
`kind=""`, `confidence=0.0` that passes `model_validate` and flows downstream looking exactly
like a real row. Rule 9: never empty, never half-written.

The second path was quieter still — a value that parsed but was not a dict (a scalar, a list)
also returned `{}`, via `isinstance(parsed, dict)`.
"""

from __future__ import annotations

import pytest

from app.adapters.age_graph_store import _props, _to_entity


def test_an_undecodable_row_raises_instead_of_becoming_an_empty_node():
    with pytest.raises(ValueError) as exc:
        _props("{not json at all::vertex")
    msg = str(exc.value)
    assert "_props" in msg, "the refusal must name where the mapping lives"
    assert "§10.1" in msg, "rule 9 — a refusal cites the section that owns the boundary"


def test_a_non_dict_agtype_raises_too():
    """A scalar parses fine and is still not a node; the old code returned {} for it."""
    with pytest.raises(ValueError, match="vertex/edge"):
        _props("42::vertex")


def test_an_INCOMPLETE_vertex_can_no_longer_become_a_blank_entity():
    """A21 changed this test's premise, and the new fact is stronger than the old one.

    A20 asserted that `_to_entity({})` produced a WELL-FORMED blank `Entity` — every field
    defaulted, `model_validate` satisfied — which is what made `_props`'s refusal the only
    thing between an undecodable row and a blank row in a result set.

    A21 replaced `_to_entity`'s 14 hand-named keys with a pass-through, so the identity
    fields are no longer defaulted and an incomplete mapping raises here too. `_props`'s
    refusal is now belt-and-braces rather than load-bearing — kept, because the two catch
    different things: this fires on a DECODABLE vertex missing fields, `_props` on a row that
    could not be decoded at all.
    """
    with pytest.raises(Exception) as exc:
        _to_entity({})
    assert "id" in str(exc.value), (
        "the mapper must object to the MISSING IDENTITY specifically — an entity with no id "
        "is the thing that used to flow downstream looking real"
    )


def test_a_MISSING_column_is_still_an_absence_not_an_error():
    """Control arm — the change must not turn absence into a failure.

    `row is None` means the column was not there, which every caller already guards with
    `… if rows else None`. A guard that refused this too would break every optional read.
    """
    assert _props(None) == {}


def test_a_REAL_vertex_still_decodes():
    """Control arm — validated on the shape the adapter exists for, not on the failure that
    motivated the change (rule 3)."""
    row = '{"id": 1, "label": "Entity", "properties": {"id": "e1", "name": "Kai"}}::vertex'
    assert _props(row) == {"id": "e1", "name": "Kai"}
