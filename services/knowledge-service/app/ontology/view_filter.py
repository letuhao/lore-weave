"""Lane LD — pure view-scope + temporal-as-of read helpers.

READ-only. These helpers are used **only** at query time to filter the
graph slice a caller sees through a `GraphView` lens and/or an
`as_of_chapter` ordinal. They are NEVER used to scope extraction —
extraction always runs the whole resolved schema (spec §10-C3); a view
is a read lens, full stop.

Two concerns, kept pure (no I/O, no driver) so they are exhaustively
unit-testable offline:

1. **View scope** (`build_view_scope`) — given a `GraphView`'s
   `edge_type_codes` / `node_kind_codes`, produce the predicate/kind
   allow-sets the graph-read query filters by. An *empty* list on a
   facet means "no filter on that facet" (the whole resolved schema for
   that facet) — a view with no edge types is the identity lens, not a
   lens that hides every edge.

2. **Temporal as-of** (`edge_visible_at`) — the spec §3.6 predicate:
   an edge is visible at chapter `N` when
   `valid_from <= N AND (valid_to IS NULL OR valid_to > N)`. Invariant
   edges (`temporal=false`, encoded here as a missing `valid_from`)
   always show. `as_of=None` means "latest" → every currently-open
   instance (no upper bound applied).

Deprecated-edge flagging (`deprecated_edge_warnings`, spec §10-A4): a
view that references an edge-type the resolved schema has deprecated is
surfaced as a `warnings[]` entry — the lens still works (the edge may
still carry data) but the user is told the type is on its way out.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

from app.db.ontology_models import GraphView


@dataclass(frozen=True)
class ViewScope:
    """The resolved read-scope of a view (or the identity lens).

    `edge_type_codes` / `node_kind_codes` are the allow-sets the
    graph-read query filters by. An EMPTY frozenset on a facet means
    "do not filter that facet" — the whole resolved schema passes. This
    asymmetry (empty == no-filter, not filter-to-nothing) matches the
    contract: omitting `?view=` OR a view with `edge_type_codes: []`
    both yield the full edge set.
    """

    edge_type_codes: frozenset[str] = field(default_factory=frozenset)
    node_kind_codes: frozenset[str] = field(default_factory=frozenset)

    def allows_edge_type(self, code: str) -> bool:
        """True if `code` passes the edge-type facet (empty facet ⇒ all)."""
        return not self.edge_type_codes or code in self.edge_type_codes

    def allows_node_kind(self, code: str) -> bool:
        """True if `code` passes the node-kind facet (empty facet ⇒ all)."""
        return not self.node_kind_codes or code in self.node_kind_codes


# The identity lens — no `?view=` supplied: everything passes both facets.
IDENTITY_SCOPE = ViewScope()


def _norm(codes: Iterable[str]) -> frozenset[str]:
    """Normalise a code list: strip, drop empties, dedupe (case-sensitive —
    schema codes are case-sensitive slugs, mirroring `SchemaCode`)."""
    return frozenset(c.strip() for c in codes if c and c.strip())


def build_view_scope(view: GraphView | None) -> ViewScope:
    """Build the read-scope for a view, or the identity lens when `view`
    is None (no `?view=` supplied → whole resolved schema).

    A view facet left empty (`edge_type_codes: []`) is the identity on
    that facet — NOT a filter that hides everything. See `ViewScope`.
    """
    if view is None:
        return IDENTITY_SCOPE
    return ViewScope(
        edge_type_codes=_norm(view.edge_type_codes),
        node_kind_codes=_norm(view.node_kind_codes),
    )


def edge_visible_at(
    valid_from: int | None,
    valid_to: int | None,
    as_of: int | None,
) -> bool:
    """Spec §3.6 temporal as-of predicate.

    An edge is visible at chapter ordinal `as_of` when
    `valid_from <= as_of AND (valid_to IS NULL OR valid_to > as_of)`.

    Edge cases, all load-bearing:
      - `valid_from is None` → **invariant** edge (`temporal=false`):
        it has no opening ordinal and ALWAYS shows, at every `as_of`
        (including `as_of=None`). This is how the model encodes a
        non-temporal edge in the read path.
      - `as_of is None` → "latest": show every currently-OPEN instance,
        i.e. drop the `valid_from <= N` lower bound (we are at the
        present, every opened edge has opened) and keep only the
        "still open" test `valid_to IS NULL`. A closed temporal
        instance (`valid_to` set) is NOT latest and is hidden.
      - `valid_to` is an EXCLUSIVE upper bound: an edge closed at
        chapter `K` is visible at `K-1` but not at `K` (`valid_to > N`).
    """
    # Invariant edge — no opening ordinal → always visible.
    if valid_from is None:
        return True
    if as_of is None:
        # "latest": only still-open instances (no closing ordinal).
        return valid_to is None
    if valid_from > as_of:
        return False
    return valid_to is None or valid_to > as_of


def deprecated_edge_warnings(
    view: GraphView | None,
    deprecated_edge_codes: Iterable[str],
) -> list[str]:
    """Spec §10-A4 — flag every edge-type the view references that the
    project's schema has marked deprecated.

    `deprecated_edge_codes` is the set of edge-type codes the resolved
    schema carries with `deprecated_at IS NOT NULL` (the router reads
    these explicitly via an `include_deprecated` schema fetch, because
    the default resolve drops deprecated edge-types entirely).

    Only edge-types the view EXPLICITLY names are checked (the identity
    lens names nothing, so it never warns). A view code that the schema
    does not know at all is NOT a deprecation warning (it is simply
    absent from the graph slice); we only surface codes that exist AND
    are deprecated, so the message is actionable ("this lens points at a
    dying edge type").

    Deterministic (sorted) so the warnings list is stable across calls.
    """
    if view is None or not view.edge_type_codes:
        return []
    deprecated = _norm(deprecated_edge_codes)
    referenced = _norm(view.edge_type_codes)
    flagged = sorted(referenced & deprecated)
    return [
        f"view references deprecated edge type '{code}'" for code in flagged
    ]
