"""D-A-TURN-PROMISES-WORK-THAT-CONTINUES-AFTER-IT-ENDS — the count the row asked for.

    THE INVARIANT. A synchronous turn cannot send a later message, so a reply that promises one
    is false the moment the turn ends — and it is false in the way the author is least able to
    detect, because waiting looks exactly like working.

The row closes: "Recorded so the population is countable." Nobody had counted it.

🔴 MEASURED 2026-08-27 over 158 batches / 1,551 runs:

    26   promise a later message or ask the author to wait
    20     …but the store DID move — the work happened, only the promise is unkeepable
     1     …but a card is pending, which IS a real wait the author can act on
     5   >>> NOTHING QUEUED AND NOTHING WRITTEN

THE SIGNAL IS NOT FUTURE TENSE. "I'll cancel them now" is an intention inside the turn and is
fine. It is a promise of a LATER MESSAGE, or a request to WAIT.

🔴 AND ONE CLAUSE WAS MEASURED AND REJECTED. `in a moment` produced 4 of the first 9 hits and
every one was the assistant telling the USER to retry — "perhaps try asking again in a
moment?", "you can try again in a moment" — the opposite of a promise it owes. The
DETERMINER is the whole discrimination: `one/just a/give me a moment` is the assistant
asking to be waited for.

AND IT IS NOT ANCHORED TO A SENTENCE BOUNDARY, though it was for one round. The anchor
looked free and cost a true positive — see the test below. A falsifier that removed it
stayed GREEN, which is what sent me to look at what it was excluding.
"""
from __future__ import annotations

import glob
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "toolloop"))

import fe_runner as fr  # noqa: E402

CARD = {"run_id": "r", "tool_call_id": "t", "kind": "tool_approval"}


def _run(text, *, tables=(), card=None):
    return {"text": text, "pending_approval": card,
            "store_diff": {t: {"before": {"rows": 1}, "after": {"rows": 2}} for t in tables}}


def _corpus():
    out = []
    for fp in sorted(glob.glob(str(ROOT / "docs" / "eval" / "toolloop" / "**" / "*-raw.json"),
                               recursive=True)):
        try:
            runs = json.loads(pathlib.Path(fp).read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        if isinstance(runs, list):
            out += [r for r in runs if isinstance(r, dict)]
    return out


def test_the_MEASURED_instances_are_caught():
    """🔴 THE FALSIFIER, on the corpus itself rather than on invented strings."""
    flagged = fr.promised_work_that_cannot_continue(_corpus())
    assert len(flagged) >= 5, len(flagged)
    joined = " ".join((r.get("text") or "") for r in flagged)
    assert "let you know as soon as" in joined
    assert "One moment" in joined
    for r in flagged:
        assert not r.get("pending_approval")


def test_the_rows_own_quoted_replies_are_caught():
    """The four the row records verbatim, which is what it filed on."""
    for text in (
        "I am working on resolving this now. I'll let you know as soon as the structure is live.",
        "I'm going to attempt to re-establish the connection. One moment while I fix this.",
        "I am going to take a moment to pull the detailed outline. I'll update you as soon as "
        "the chapters are ready.",
        "I'm going to attempt to re-propose the plan. One moment.",
    ):
        assert fr.promised_work_that_cannot_continue([_run(text)]), text


def test_an_intention_INSIDE_the_turn_is_not_this():
    """🔴 THE PRECISION ARM. Future tense is not the signal; an unkeepable promise is."""
    for text in (
        "I'll go ahead and cancel all of them.",
        "I'll rename the chapter now.",
        "I need to find the unique IDs before I can link them. I'll search for them.",
        "I'll try that a different way if you'd like.",
    ):
        assert not fr.promised_work_that_cannot_continue([_run(text)]), text


def test_the_REJECTED_clause_stays_rejected():
    """🔴 `in a moment` IS THE ASSISTANT TALKING ABOUT THE USER'S NEXT ACTION. It cost four
    false positives before it was dropped; if it ever fires again the trade must be re-measured
    rather than quietly re-accepted."""
    for text in (
        "I'm having trouble retrieving the map ID. Perhaps try asking again in a moment?",
        "I was unable to unfavourite the model. You can try again in a moment.",
    ):
        assert not fr.promised_work_that_cannot_continue([_run(text)]), text
    # …and the form that IS a promise still fires, so the narrowing did not gut the clause.
    assert fr.promised_work_that_cannot_continue(
        [_run("I'll find the ID for you now. One moment.")])


def test_a_turn_whose_WORK_HAPPENED_is_not_this():
    """The promise is still unkeepable, but the work is real and the author will see it — a
    different problem with a different remedy, so it is counted apart and not flagged.

    🔴 THIS TEST USED TO NAME A JOB TABLE AND ASSERT A SEPARATE `_JOBISH_TABLE` ARM. A falsifier
    that DELETED that arm stayed green, because anything asynchronous also moves the store: the
    arm could never change an outcome. It is gone from the code, and this asserts the property
    that actually holds."""
    started = _run("I'll let you know as soon as it's done.",
                   tables=("loreweave_jobs.generation_job",))
    assert not fr.promised_work_that_cannot_continue([started])
    other = _run("I'll let you know as soon as it's done.",
                 tables=("loreweave_book.chapters",))
    assert not fr.promised_work_that_cannot_continue([other])
    quiet = _run("I'll let you know as soon as it's done.")
    assert fr.promised_work_that_cannot_continue([quiet])


def test_one_moment_is_caught_MID_SENTENCE_too():
    """🔴 THE TRUE POSITIVE A SENTENCE-BOUNDARY ANCHOR COST. The corpus's only mid-sentence
    occurrence follows a list item with no full stop, and it is a genuine promise. The anchor
    looked free; a falsifier that removed it stayed green, which is what sent me to look at what
    it was excluding."""
    real = ("Here is the outline: 1. The Ember Codex 2. The Waterline 3. The Black Stair Again "
            "4. The Last Tide One moment while I refresh that for you.")
    assert fr.promised_work_that_cannot_continue([_run(real)])


def test_a_card_is_a_real_wait():
    """An author holding a confirm card has something to act on; telling them to wait is true."""
    assert not fr.promised_work_that_cannot_continue(
        [_run("I'll let you know as soon as it's applied.", card=dict(CARD))])


def test_an_audit_row_does_not_count_as_the_work_happening():
    """Shares the exemption sets with the other bars for the same reason: a row the turn writes
    about ITSELF is not the author's data changing."""
    for table in ("loreweave_knowledge.entity_access_log",
                  "loreweave_knowledge.extraction_pending", "neo4j.Fact.total"):
        assert fr.promised_work_that_cannot_continue(
            [_run("I'll update you as soon as it's ready.", tables=(table,))]), table
