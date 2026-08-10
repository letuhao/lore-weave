"""World order as a partial order over events (plan T33 / D0.1-D8).

Two things changed and they pull in opposite directions, which is the point:

1. The edge vocabulary WIDENED from one implicit kind to `causes | precedes`. `causes` claims
   why; `precedes` claims only when. Collapsing them loses the distinction a canon check needs
   — "B happened after A" is cheap and usually safe, "A caused B" is expensive and often wrong.

2. `unknown` became a FIRST-CLASS answer, so the inference produces FEWER edges than before.
   The plan's reason: *a wrong order is worse than an absent one for a canon check*, and the
   sibling relation proposer was measured at 3-of-8 defensible.

A widening that only ever adds edges would be the failure mode here, so the tests below assert
both directions: the new kinds land, and the refusals actually refuse.
"""

from __future__ import annotations

import json

from app.extraction.causal_edges import (
    REL_CAUSES,
    REL_PRECEDES,
    drop_cycles,
    parse_edges,
)

ORDER = {"e1": 0, "e2": 1, "e3": 2, "e4": 3}
WINDOW = set(ORDER)


def _parse(payload) -> list[tuple[str, str, str]]:
    return parse_edges(json.dumps(payload), order_index=ORDER, window_ids=WINDOW)


def test_both_ordered_kinds_survive():
    out = _parse([["e1", "e2", "causes"], ["e2", "e3", "precedes"]])
    assert out == [("e1", "e2", REL_CAUSES), ("e2", "e3", REL_PRECEDES)]


def test_unknown_is_dropped_not_downgraded():
    """The whole of T33's caution in one assertion.

    `unknown` must not become a `precedes` edge. Downgrading it would look conservative and be
    the opposite: the graph would fill with order claims the model explicitly declined to make,
    and nothing downstream could tell them from the ones it did.
    """
    out = _parse([["e1", "e2", "unknown"], ["e2", "e3", "causes"]])
    assert out == [("e2", "e3", REL_CAUSES)], (
        "an 'unknown' pair produced an edge — a refusal was turned into a claim"
    )


def test_unrecognised_relation_is_dropped():
    # A typo or a kind we do not model is the same situation as `unknown`: we do not know what
    # was meant, so we assert nothing. Failing open here would let a prompt change silently
    # invent a third edge kind nobody reads.
    assert _parse([["e1", "e2", "enables"], ["e1", "e3", ""]]) == []


def test_legacy_two_element_pair_reads_as_the_WEAKER_claim():
    """Back-compat that cannot over-claim.

    The pre-T33 shape was `[cause, effect]` and meant "causes". A cached or replayed response
    in that shape is nonetheless read as `precedes`, because promoting an unlabelled pair into
    a CAUSAL assertion invents a claim the model never made. Weakening is recoverable;
    over-claiming is what puts a wrong cause into canon.
    """
    assert _parse([["e1", "e2"]]) == [("e1", "e2", REL_PRECEDES)]


def test_backward_and_self_links_still_refused():
    # Unchanged by T33, and re-asserted because the parse body was rewritten around it.
    assert _parse([["e3", "e1", "causes"], ["e1", "e1", "causes"]]) == []


def test_ids_outside_the_window_still_refused():
    assert _parse([["e1", "ghost", "causes"], ["ghost", "e2", "precedes"]]) == []


# ── the cycle guard (mirrors motif_link) ──────────────────────────────────────

def test_drop_cycles_refuses_the_edge_that_closes_a_loop():
    kept, refused = drop_cycles([
        ("a", "b", REL_CAUSES),
        ("b", "c", REL_CAUSES),
        ("c", "a", REL_CAUSES),   # closes a -> b -> c -> a
    ])
    assert kept == [("a", "b", REL_CAUSES), ("b", "c", REL_CAUSES)]
    assert refused == [("c", "a", REL_CAUSES)]


def test_cycles_are_judged_PER_KIND():
    """`causes` and `precedes` are different assertions, so a loop in one is not a loop in the
    other. Judging them together would refuse an edge that contradicts nothing — and the
    refusal would be invisible, because a dropped advisory edge looks exactly like an edge the
    model never proposed."""
    kept, refused = drop_cycles([
        ("a", "b", REL_CAUSES),
        ("b", "a", REL_PRECEDES),
    ])
    assert refused == []
    assert len(kept) == 2


def test_drop_cycles_is_a_no_op_on_a_forward_only_graph():
    """Today every edge runs forward in reading order, so the guard refuses nothing — which is
    exactly why it is tested with a hand-built cycle above. D0.1 will accept edges NOT derived
    from reading order, and on that day this stops being a no-op."""
    edges = [("e1", "e2", REL_CAUSES), ("e1", "e3", REL_PRECEDES), ("e2", "e4", REL_CAUSES)]
    kept, refused = drop_cycles(edges)
    assert kept == edges and refused == []
