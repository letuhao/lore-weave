"""Lane LD — pure unit tests for app.ontology.view_filter.

No DB, no driver. Covers:
  * the temporal as-of predicate truth table (spec §3.6),
  * view-scope build + the empty-facet-is-identity rule,
  * deprecated-edge flagging (spec §10-A4).
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.db.ontology_models import GraphView
from app.ontology.view_filter import (
    IDENTITY_SCOPE,
    build_view_scope,
    deprecated_edge_warnings,
    edge_visible_at,
)


def _view(**kw) -> GraphView:
    now = datetime.now(timezone.utc)
    base = dict(
        view_id=uuid4(),
        project_id="proj-1",
        user_id=uuid4(),
        code="lens",
        name="Lens",
        description="",
        edge_type_codes=[],
        node_kind_codes=[],
        created_at=now,
        updated_at=now,
    )
    base.update(kw)
    return GraphView(**base)


# ── temporal as-of truth table (§3.6) ─────────────────────────────────────
@pytest.mark.parametrize(
    "valid_from,valid_to,as_of,expected",
    [
        # invariant edge (no valid_from) → always visible, any as_of
        (None, None, None, True),
        (None, None, 5, True),
        (None, 10, 3, True),   # valid_from None dominates even if valid_to set
        # as_of=None → latest: only still-open instances
        (1, None, None, True),
        (1, 5, None, False),   # closed instance is not "latest"
        # open instance, lower bound
        (3, None, 3, True),    # valid_from <= N (equal) visible
        (3, None, 2, False),   # before it opened → hidden
        (3, None, 100, True),
        # closed instance, exclusive upper bound
        (1, 5, 4, True),       # 4 < 5 visible
        (1, 5, 5, False),      # valid_to is EXCLUSIVE: at 5 it's closed
        (1, 5, 6, False),
        (1, 5, 0, False),      # before open
        (1, 5, 1, True),       # at open
    ],
)
def test_edge_visible_at_truth_table(valid_from, valid_to, as_of, expected):
    assert edge_visible_at(valid_from, valid_to, as_of) is expected


# ── view scope build ──────────────────────────────────────────────────────
def test_none_view_is_identity_scope():
    scope = build_view_scope(None)
    assert scope is IDENTITY_SCOPE
    assert scope.allows_edge_type("ANYTHING")
    assert scope.allows_node_kind("anything")


def test_empty_facet_is_identity_not_empty_filter():
    """A view with edge_type_codes=[] passes ALL edge types (identity on that
    facet), and a populated node-kind facet filters only nodes."""
    scope = build_view_scope(_view(edge_type_codes=[], node_kind_codes=["character"]))
    assert scope.allows_edge_type("PURSUES")   # empty edge facet → all pass
    assert scope.allows_node_kind("character")
    assert not scope.allows_node_kind("location")


def test_populated_edge_facet_filters():
    scope = build_view_scope(_view(edge_type_codes=["PURSUES", "ALLY_OF"]))
    assert scope.allows_edge_type("PURSUES")
    assert not scope.allows_edge_type("ENEMY_OF")


def test_scope_normalises_whitespace_and_drops_empties():
    scope = build_view_scope(_view(edge_type_codes=[" PURSUES ", "", "  "]))
    assert scope.edge_type_codes == frozenset({"PURSUES"})
    assert scope.allows_edge_type("PURSUES")


def test_codes_are_case_sensitive():
    scope = build_view_scope(_view(edge_type_codes=["PURSUES"]))
    assert scope.allows_edge_type("PURSUES")
    assert not scope.allows_edge_type("pursues")


# ── deprecated-edge flagging (§10-A4) ─────────────────────────────────────
def test_deprecated_warning_flags_referenced_deprecated_codes():
    view = _view(edge_type_codes=["PURSUES", "OLD_EDGE"])
    warnings = deprecated_edge_warnings(view, ["OLD_EDGE", "UNRELATED"])
    assert warnings == ["view references deprecated edge type 'OLD_EDGE'"]


def test_deprecated_warning_only_for_referenced_codes():
    """A deprecated code the view does NOT reference produces no warning."""
    view = _view(edge_type_codes=["PURSUES"])
    assert deprecated_edge_warnings(view, ["OLD_EDGE"]) == []


def test_deprecated_warning_sorted_and_deterministic():
    view = _view(edge_type_codes=["B_EDGE", "A_EDGE", "C_EDGE"])
    warnings = deprecated_edge_warnings(view, ["C_EDGE", "A_EDGE", "B_EDGE"])
    assert warnings == [
        "view references deprecated edge type 'A_EDGE'",
        "view references deprecated edge type 'B_EDGE'",
        "view references deprecated edge type 'C_EDGE'",
    ]


def test_deprecated_warning_none_view_and_empty_facet():
    assert deprecated_edge_warnings(None, ["X"]) == []
    assert deprecated_edge_warnings(_view(edge_type_codes=[]), ["X"]) == []
