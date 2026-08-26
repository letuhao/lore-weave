"""D-A-READ-INTENT-TURN-WRITES-TO-EXTRACTION-PENDING.

A turn whose only tool call was `settings_list_models` — Tier R, user scope, and in another
service entirely — left a row in `loreweave_knowledge.extraction_pending` on 1 of 5 runs, and
the harness reported "a READ-INTENT TURN WROTE TO THE STORE — a defect whatever it said".

TRACED, which the row had not done. knowledge-service's `handle_chat_turn` queues into
`extraction_pending` on the `chat.turn_completed` event, for EVERY turn whose project has
extraction enabled, whatever tool ran. It is asynchronous, which is why it appeared on 1 of 5
runs and not all five: the enqueue sometimes lands before the "after" snapshot.

MEASURED across every evidence file on disk, because a trace alone is a theory:
    349 runs in 90 batches touch it, spanning composition_arc_apply, catalog_get_book,
    jobs_cancel, kg_triage_schema_write and book_sync — no TOOL spans 90 batches
    295 of those runs have NO other store change (a pure false signal)
     54 have one beside it (which must still be flagged, and is)

The read-intent assertion is called "the strongest assertion in the loop", so this file exists
to keep the exclusion honest: it must stay narrow, it must not hide the row, and a real write
must still fail.
"""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "toolloop"))

import fe_runner  # noqa: E402


def _violates(diffs: list[dict]) -> bool:
    """Calls the SHIPPED predicate. An earlier draft re-implemented it here and passed an
    over-broad injection — proof that a guard copying the logic it guards is not a guard."""
    wrote = [{"store_diff": d} for d in diffs if d]
    return bool(fe_runner.read_intent_violations(wrote))


def test_the_exclusion_is_narrow():
    """One table, named. A set that grows quietly is how the strongest assertion in the loop
    gets switched off a table at a time."""
    assert fe_runner.TURN_BOOKKEEPING_TABLES == frozenset(
        {"loreweave_knowledge.extraction_pending"}
    )


def test_bookkeeping_alone_is_not_a_violation():
    """295 runs on disk look exactly like this."""
    assert not _violates([{"loreweave_knowledge.extraction_pending": {"rows": 1}}])


def test_a_REAL_write_still_fails():
    """The 54. The bar is unchanged for anything the tool could actually have touched."""
    assert _violates([{"loreweave_composition.outline_node": {"rows": 3}}])


def test_a_real_write_ALONGSIDE_bookkeeping_still_fails():
    """The case an over-broad fix would have hidden: dropping any run that mentions the
    bookkeeping table would have dropped these too."""
    assert _violates([{
        "loreweave_knowledge.extraction_pending": {"rows": 1},
        "loreweave_composition.outline_node": {"rows": 3},
    }])


def test_an_unchanged_store_is_still_unchanged():
    assert not _violates([{}])
    assert not _violates([])


def test_the_store_line_still_REPORTS_the_table():
    """This must not hide the row — only stop mis-attributing it. The summary line is built
    from the unfiltered diff, so a reader still sees extraction_pending in the WROTE list."""
    src = pathlib.Path(fe_runner.__file__).read_text(encoding="utf-8")
    i = src.index('store = (f"WROTE')
    assert "TURN_BOOKKEEPING" not in src[i - 400:i + 200], (
        "the displayed store line filters the bookkeeping table — it should report everything "
        "and only the VIOLATION should exclude it"
    )


def test_the_cause_is_recorded_next_to_the_exclusion():
    """An exclusion without its evidence is indistinguishable from a convenience. The constant
    has to carry the writer that justifies it, so the next person can check it."""
    src = pathlib.Path(fe_runner.__file__).read_text(encoding="utf-8")
    at = src.index("TURN_BOOKKEEPING_TABLES = ")
    doc = src[max(0, at - 1200):at]
    assert "handle_chat_turn" in doc, "the per-turn writer is not named"
    assert "chat.turn_completed" in doc, "the event that fires it is not named"
    assert "90 batches" in doc, "the evidence that it spans unrelated tools is not recorded"
