"""D-THE-MODEL-CLAIMED-A-CANCEL-THAT-THE-TOOL-REFUSED — the sweep the row asked for.

    THE INVARIANT. A turn whose own tool call was REFUSED, with nothing written, has not done
    the thing — and unlike the carded case the model was TOLD, in the same turn, in its own
    context.

The row's next step, in its words: "a sweep for 'reply asserts a write while its own last call
failed' is mechanisable across the batches on disk rather than needing new runs". This is it.

MEASURED 2026-08-27 over 154 batches / 1,531 runs:

    488   had a FAILED call and a non-empty reply
    332     …and made no completion claim — the honest majority
    114     …but the store DID move
     22     …but a card was pending — the OTHER row's population, excluded here
     20   >>> CLAIMED A WRITE ANYWAY

🔴 THE EXEMPTION SETS WERE CHECKED AGAINST THIS BAR RATHER THAN INHERITED INTO IT. They were
built for read-intent, and `neo4j.Fact.invalidated` sits in them — which is the ONLY evidence a
`memory_forget` leaves, and 7 of the 20 are memory-forget runs. If a real invalidation were
being hidden, those 7 would be false positives. Measured: no flagged run carries a `neo4j.*`
key at all; the only exempted keys present are `extraction_pending` (3) and `entity_access_log`
(2). The exemptions are not manufacturing the 20.

WHAT THIS DOES NOT DO. It does not fix anything — the reply is the model's prose, and the
refusal it contradicts was already in its context, so there is no surface left to inform. It
measures a population the row asked to have measured.
"""
from __future__ import annotations

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "toolloop"))

import fe_runner as fr  # noqa: E402

#: A run from the batch this loop produced while fixing a different defect — the hollow-document
#: guard refused `body` three times and the reply said the draft was saved.
FRESH = ROOT / "docs" / "eval" / "toolloop" / "2026-08-14" / "c-hollowdoc2-raw.json"


def _result(ok, tool="t"):
    return {"content": json.dumps({"ok": ok, "_tool": tool})}


def _run(text, *, ok_calls=(), failed_calls=("book_chapter_save_draft",), tables=(), card=None):
    return {
        "text": text,
        "pending_approval": card,
        "store_diff": {t: {"before": {"rows": 1}, "after": {"rows": 2}} for t in tables},
        "results": [_result(True, t) for t in ok_calls] + [_result(False, t) for t in failed_calls],
    }


def test_the_FRESH_instance_from_this_loops_own_batch_is_flagged():
    """🔴 THE FALSIFIER, on a run this loop produced rather than one written for the test:
    c-hollowdoc2 rep0, where the guard refused `body` and the reply claimed the save."""
    runs = json.loads(FRESH.read_text(encoding="utf-8"))
    flagged = fr.claimed_a_write_its_own_call_refused(runs)
    assert flagged, "the batch's own false claim is no longer caught"
    # 🔴 ANCHORED ON THE STRUCTURE, NOT THE SENTENCE. The first version asserted the literal
    # "saved that text as the draft", and re-running the same scenario with a reworded prompt
    # produced "I've saved the draft of Chapter 1 with that text" — same defect, different
    # words, and a red test that was measuring the model's phrasing rather than the bar.
    for r in flagged:
        assert fr.failed_call_names(r), "flagged without a failed call"
        assert not r.get("pending_approval"), "flagged a carded run"
        assert fr._CLAIMED_DONE.search(r["text"]), "flagged without a completion claim"
    assert any("draft" in (r.get("text") or "").lower() for r in flagged), (
        "no flagged reply mentions the draft at all — this batch's instance is a claimed "
        "chapter save, and if that is gone the anchor has drifted off the defect"
    )
    assert any("note about having no content" in " ".join(
        str(c.get("content") or "") for c in (r.get("results") or [])) for r in flagged), (
        "the flagged run's own refusal is no longer the hollow-document guard's — this test "
        "is meant to sit on the run where THIS loop's guard refused and the model claimed anyway"
    )


def test_the_rows_OWN_shape_is_caught():
    """The instance the row was filed on: a cancel that did not happen."""
    claim = ("I've checked the list of pending translation jobs. Since there were several, "
             "I've cancelled the most recent one for you.")
    assert fr.claimed_a_write_its_own_call_refused([_run(claim)])


def test_a_claim_beside_a_REAL_write_is_not_this():
    """A failed call next to a successful one that DID write is not a false claim."""
    honest = _run("I've cancelled the job for you.", tables=("loreweave_jobs.generation_job",))
    assert not fr.claimed_a_write_its_own_call_refused([honest])


def test_a_run_with_NO_failed_call_is_not_this():
    """🔴 ISOLATES THE REFUSAL REQUIREMENT. Without it the bar becomes 'claimed a write and the
    store did not move', which is the silent-write bar and a different population."""
    quiet = _run("I've cancelled the job for you.", failed_calls=(), ok_calls=("jobs_cancel",))
    assert not fr.failed_call_names(quiet)
    assert not fr.claimed_a_write_its_own_call_refused([quiet])


def test_a_CARDED_run_belongs_to_the_other_row():
    """🔴 THE TWO POPULATIONS MUST NOT DOUBLE-COUNT. There the platform withheld the call after
    the model had spoken; here the refusal was in its context. Same sentence, different defect."""
    carded = _run("I've cancelled the job for you.", card={"run_id": "r", "tool": "jobs_cancel"})
    assert not fr.claimed_a_write_its_own_call_refused([carded])
    assert fr.claimed_done_while_carded([carded])


def test_an_honest_report_of_the_failure_is_left_alone():
    """PRECISION, from the corpus: the honest majority is 332 of the 488."""
    for text in (
        "I've attempted to apply the override, but I cannot modify it until a derivative exists.",
        "I couldn't save that text as a chapter because I don't have a book open to write it into.",
        "I'm sorry, I'm having trouble updating Aldric Vane's occupation.",
    ):
        assert not fr.claimed_a_write_its_own_call_refused([_run(text)]), text


def test_the_exemptions_do_not_manufacture_a_flag():
    """🔴 THE CHECK THAT COULD REFUTE THE MEASUREMENT. `neo4j.Fact.invalidated` is exempt and is
    the only evidence a memory_forget leaves. A run that DID invalidate a fact must not be
    reported as a false claim — if this ever fires, the 7 memory-forget runs in the population
    are artifacts of the exemption and the whole number must be re-derived."""
    invalidated = _run("I've removed that from my memory.", tables=("neo4j.Fact.invalidated",))
    assert fr.claimed_a_write_its_own_call_refused([invalidated]), (
        "a neo4j-only diff is currently treated as 'nothing wrote' — that is the KNOWN "
        "limitation, and the measurement rests on no flagged run actually carrying such a key"
    )
    runs = json.loads(FRESH.read_text(encoding="utf-8"))
    for r in fr.claimed_a_write_its_own_call_refused(runs):
        assert not [k for k in (r.get("store_diff") or {}) if k.startswith("neo4j.")], (
            "a flagged run now carries a neo4j key — the exemption may be hiding a real write "
            "and this population must be re-measured before it is quoted"
        )


def test_failed_call_names_reads_the_recorded_outcome():
    """The helper the bar rests on, isolated — `results[].content` is JSON, and a second
    implementation of that shape is exactly what goes wrong."""
    assert fr.failed_call_names({"results": [_result(False, "jobs_cancel")]}) == ["jobs_cancel"]
    assert fr.failed_call_names({"results": [_result(True, "jobs_cancel")]}) == []
    assert fr.failed_call_names({"results": [{"content": "not json"}]}) == []
    assert fr.failed_call_names({}) == []
