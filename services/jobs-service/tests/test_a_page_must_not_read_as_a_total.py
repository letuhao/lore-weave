"""D-PAGE-READ-AS-A-TOTAL — a listing that is one page must say so where a caller cannot skim past.

MEASURED LIVE 2026-08-14, batch 7, K=3. Asked "What background jobs do I have running right now?",
the model called jobs_list, received 10 items plus a `next_cursor`, and answered:

    "You currently have 10 background jobs running."

jobs_summary on the same account, the same day, reports **31 active**. The boundary settles it:
jobs_list returns 10 ITEMS, a next_cursor, and NO total — so 10 is the page size, and the model
reported a page as the count. That answer sent a `jobs_list` conclusion into the ledger as PROVEN;
it has been withdrawn.

world_list is the control, and it was already built the right way: it returns
`page: {total, returned, has_more, next_offset}` plus a one-line guidance, and its live answer the
same day was correct — "You have 28 worlds in total". Two tools, same model, same day, opposite
outcomes, and the difference is in the payload.

THE INVARIANT: a response that omits must SAY it omits. Same class as `always_available` on
tool_list, `withheld_pending_setup_intent` on the gated set, and `degraded` on story_search.

A `total` is deliberately NOT computed here: it would be a second query on every list, and
jobs_summary exists to answer "how many". So the guidance NAMES that tool instead of guessing.
"""
from __future__ import annotations

import pathlib

SRC = (pathlib.Path(__file__).resolve().parents[1]
       / "app" / "mcp" / "server.py").read_text(encoding="utf-8")


def _handler() -> str:
    i = SRC.index('name="jobs_list"')
    return SRC[i:SRC.index('name="jobs_summary"', i)]


def test_the_page_is_named_when_there_is_more():
    """THE FALSIFIER. Without this the payload carries next_cursor and nothing that contradicts
    reading len(items) as the answer."""
    h = _handler()
    assert 'out["page"] = {"returned": len(projected), "has_more": True}' in h
    assert "NOT the total" in h


def test_it_forbids_the_exact_sentence_that_was_measured():
    """The reply was 'You currently have 10 background jobs running'. The guidance has to speak to
    that move directly, not merely hint that pagination exists."""
    h = _handler()
    assert "Do not report this number as how many jobs there are" in h


def test_it_names_the_tool_that_actually_has_the_count():
    """C-12: a notice that names no next step leaves the caller where it found them. jobs_summary
    is the tool with the totals, so the guidance names it rather than guessing a number here."""
    h = _handler()
    assert "jobs_summary" in h


def test_the_page_block_only_appears_when_there_IS_more():
    """A last page is complete, and telling a caller it is partial would be the same defect
    inverted — under-reporting a true total as 'there may be more'."""
    h = _handler()
    assert "if next_cursor:" in h


def test_returned_is_always_present():
    """`returned` is stated on every response, page or not, so the item count is never something
    the caller has to infer by measuring the array."""
    h = _handler()
    assert '"returned": len(projected)' in h


def test_no_total_is_computed_here():
    """Guard against a well-meaning later edit adding a COUNT(*) to every list call. The cost is
    the reason jobs_summary exists; the guidance points there deliberately."""
    h = _handler()
    assert "count(*)" not in h.lower()
    assert '"total"' not in h
