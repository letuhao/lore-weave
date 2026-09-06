"""L2 — every query that ORDERS BY `event_order` must carry a tie-break.

🔴 **WHY, measured on `lw-iso` 2026-08-30.** `event_order` is NOT unique: 51 colliding
`(project_id, event_order)` pairs stand in `g_shared`, 102 events across 6 projects, written
before `pass2_writer` stopped restarting its within-chapter index at 0 (`b6c8fde13`). Spec
§25 accepts them rather than renumbering, because there is no narrative source to renumber
FROM — so every reader has to cope with duplicates, permanently.

A bare `ORDER BY e.event_order` in front of a `LIMIT` is where that stops being harmless.
`fact_for_check._EVENTS_AT_OR_BEFORE_CYPHER` had exactly that: which of two colliding events
survived the cut was whatever the store returned, so the same canon check could see a
different evidence set on two runs and neither run was wrong to look at.

This test reads the SQL constants directly rather than executing them, on purpose: the defect
is a property of the query text, and a fixture with unique orders — the natural thing to
write — cannot reproduce it. That is the shape this repo keeps finding, so the assertion is
made where the bug lives.
"""

from __future__ import annotations

import re

import pytest

from app.db.graph_repos import events as events_repo
from app.db.graph_repos import fact_for_check

#: `ORDER BY … event_order …` up to the end of the clause. Captured so the assertion can look
#: at what FOLLOWS event_order rather than merely that the words appear.
_ORDER_BY = re.compile(
    r"ORDER\s+BY\s+(?P<clause>[^\n]*event_order[^\n]*)", re.IGNORECASE)


def _order_clauses(module) -> list[tuple[str, str]]:
    """`(constant name, ORDER BY clause)` for every module-level Cypher string."""
    found = []
    for name in dir(module):
        value = getattr(module, name)
        if not isinstance(value, str) or "ORDER BY" not in value.upper():
            continue
        for m in _ORDER_BY.finditer(value):
            found.append((name, m.group("clause").strip()))
    return found


def _has_tiebreak(clause: str) -> bool:
    """True when something ORDERS AFTER event_order.

    A tie-break is any further term in the clause. `coalesce(e.event_order, …)` is still the
    event_order term, so the comma that matters is the one after the closing paren — which is
    why this splits on commas at depth 0 rather than counting commas.
    """
    depth, parts, cur = 0, [], ""
    for ch in clause:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append(cur)
            cur = ""
            continue
        cur += ch
    parts.append(cur)
    return len(parts) > 1 and bool(parts[-1].strip())


@pytest.mark.parametrize("module", [fact_for_check, events_repo],
                         ids=["fact_for_check", "events"])
def test_every_event_order_sort_has_a_tiebreak(module):
    clauses = _order_clauses(module)
    assert clauses, f"no ORDER BY over event_order found in {module.__name__} — the regex " \
                    f"stopped matching, which would make this test vacuous"
    missing = [(n, c) for n, c in clauses if not _has_tiebreak(c)]
    assert not missing, (
        "these order by event_order with NOTHING after it, so a collision decides the row "
        f"order and a LIMIT decides it silently: {missing}"
    )


def test_the_detector_itself_can_fail():
    """Rule 3 — a criterion that cannot fail is not a criterion.

    Driven on cases this was NOT derived from, including the `coalesce(...)` form that a
    naive comma count gets wrong in the FORGIVING direction (reading the comma INSIDE the
    parens as a tie-break, and passing a query that has none).
    """
    assert not _has_tiebreak("e.event_order DESC")
    assert not _has_tiebreak("coalesce(e.event_order, 9223372036854775807)")
    assert _has_tiebreak("coalesce(e.event_order, 9223372036854775807), e.title ASC")
    assert _has_tiebreak("e.event_order DESC, e.id DESC")
    # A trailing comma is not a tie-break; it is a typo.
    assert not _has_tiebreak("e.event_order DESC,")
