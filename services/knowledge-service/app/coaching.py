"""WS-5.7/5.8 (P5 Gate-1) — commitment + thread coaching detectors.

A `commitment` fact (fact_type='commitment') is a promised action + a due date. The due date
rides the WS-2.6b s/p/o supersession trio (predicate='due', object=<date>), so a Friday →
Tuesday → next-week slip is an ordered chain (group_supersessions gives the HEAD = the latest
due). Gate 1 is therefore small: a `due_date` field + a deterministic OVERDUE-vs-now detector
here (no parallel identity model). A `thread` is an open work-item with open|resolved status.

Pure functions — the caller supplies the recalled commitments/threads (already
supersession-collapsed to their head), so this stays testable without the KG.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

THREAD_OPEN = "open"
THREAD_RESOLVED = "resolved"
_THREAD_STATUSES = frozenset({THREAD_OPEN, THREAD_RESOLVED})


@dataclass(frozen=True)
class OverdueCommitment:
    content: str
    due_date: str          # ISO date (the supersession chain's HEAD)
    days_overdue: int


def find_overdue_commitments(commitments: list[dict], today: date) -> list[OverdueCommitment]:
    """WS-5.7 — a commitment is OVERDUE when its (latest) due date is strictly before `today`
    AND it is not resolved. `commitments` items: {content, due_date(ISO), resolved(bool)}. A
    missing/blank due_date is skipped (a commitment with no date can't be overdue). Sorted most
    overdue first so the coach surfaces the longest slip."""
    out: list[OverdueCommitment] = []
    for c in commitments:
        if c.get("resolved"):
            continue
        raw = (c.get("due_date") or "").strip()
        if not raw:
            continue
        try:
            due = date.fromisoformat(raw[:10])
        except ValueError:
            continue
        if due < today:
            out.append(OverdueCommitment(
                content=str(c.get("content") or "").strip(),
                due_date=due.isoformat(),
                days_overdue=(today - due).days,
            ))
    return sorted(out, key=lambda o: o.days_overdue, reverse=True)


def validate_thread_status(status: str) -> None:
    """WS-5.8 — a thread status is a closed set {open, resolved}; anything else is rejected."""
    if status not in _THREAD_STATUSES:
        raise ValueError(f"thread status {status!r} must be one of {sorted(_THREAD_STATUSES)}")
