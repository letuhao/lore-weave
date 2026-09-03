"""D-A-TIER-A-SCENARIO-THAT-NEVER-APPROVES-CANNOT-MOVE-ITS-STORE.

    THE INVARIANT. "unchanged" is a statement about the TOOL only if a write was ever permitted.

composition_motif_link_edit is Tier A, scenarios-c2-motif.json sets `approve: null`, and the
batch ran with approvals `none`. Every correct call was therefore recorded
{kind: tool_approval, tier: A, pending: true, call_outcome: deferred} and the run ended
left_suspended. `wrote 0/5` said nothing about the tool: the store could not move because
nobody ever approved the write.

The cost was not just a missing number. The ledger's blocked reason for that tool read "it
never called composition_motif_search AT ALL", while the recorded runs show, identically on 3
of 3 complete runs, the model calling motif_search twice and re-calling motif_link_edit with
BOTH real UUIDs, where it was deferred at the gate. An unreadable bar was read as evidence and
the tool was blamed. (That occurrence is corrected in place under
OBS-MODEL-WILL-NOT-LOOK-UP-AN-ID.)

🔴 THE OBVIOUS VERSION OF THIS FIX IS WRONG, TWICE OVER, and both wrong versions were caught by
controls rather than by review.

  * Excluding suspended runs from the DENOMINATOR: wrong, because a run can approve one card,
    write, and still end on a later one — c-surfrec2 recorded "WROTE 4/5" with 2 suspended.
  * Asking whether the BATCH wrote anything: wrong, and a live run refuted it on the spot.
    In c-nowrite1, 2 runs called jobs_cancel and stopped on its card while the other 3 never
    called it at all and wandered into translation_start_job, which wrote. "WROTE 3/5" was
    perfectly true and had nothing to do with the tool under test.

So the annotation is scoped to THE TOOL THE BARS ARE READ FOR: every run that CALLED it ended
on a card, and none of those runs' stores moved. Re-derived over the corpus, the two triggers
are not the same question — 37 scenario-batches for the batch-wide rule, 34 for this one, 27
shared. The 10 the batch-wide rule adds are runs where the tool was never called, where the
silence IS informative and refusing would be wrong.

The COLUMN keeps its meaning. Another tool's write is a real write; what is annotated is what
the column can and cannot say about the tool under test.
"""
from __future__ import annotations

import collections
import io
import json
import pathlib
import sys
from contextlib import redirect_stdout

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "toolloop"))

import fe_runner as fr  # noqa: E402

SC = [{"id": "s", "expect_tool": "jobs_cancel"}]
NEEDLE = "THE STORE BAR CANNOT SEE jobs_cancel"


def _render(runs, sc=None) -> str:
    buf = io.StringIO()
    with redirect_stdout(buf):
        fr.report(runs, sc or SC, len(runs))
    return buf.getvalue()


def _run(called=("jobs_cancel",), **kw):
    return {"scenario": "s", "surfaces": [], "results": [],
            "tool_calls": [{"type": "TOOL_CALL_START", "toolCallName": c} for c in called],
            **kw}


def test_called_it_and_always_stopped_on_a_card_is_ANNOTATED():
    out = _render([_run(pending_approval={"tier": "A"}, store_diff={}) for _ in range(5)])
    assert NEEDLE in out
    assert "no write was ever permitted" in out


def test_ANOTHER_TOOLS_write_does_not_silence_the_annotation():
    """The live refutation, as a guard. 2 runs called the tool and stopped; 3 never called it
    and wrote through a different tool. The column says WROTE 3/5 and is right; the annotation
    must still fire."""
    runs = [_run(pending_approval={"tier": "A"}, store_diff={}) for _ in range(2)]
    runs += [_run(called=("translation_start_job",),
                  store_diff={"loreweave_translation.chapter_segments": {}}) for _ in range(3)]
    out = _render(runs)
    assert "WROTE 3/5" in out, "the column must keep reporting the store"
    assert NEEDLE in out, "the annotation was silenced by a write from a different tool"


def test_a_run_that_GOT_PAST_a_card_and_wrote_silences_it():
    """PRECISION. If a run that called the tool moved the store, the bar CAN see it.

    🔴 THIS CASE ISOLATES THE STORE CLAUSE, AND THE FIRST VERSION DID NOT. Deleting
    `not any(store_diff)` from the shipped condition left all nine guards GREEN, because every
    other case here already fails the `all(pending)` test — the clause was carrying no weight
    that anything checked. EVERY run must call the tool AND suspend, so that the store is the
    only thing left to decide it."""
    runs = [_run(pending_approval={"tier": "A"},
                 store_diff={"loreweave_jobs.job_projection.owner": {}}) for _ in range(5)]
    assert all(r.get("pending_approval") for r in runs)
    assert NEEDLE not in _render(runs), (
        "a suspended run whose store DID move is a bar that CAN see the tool — the write "
        "landed before the card"
    )


def test_a_run_that_called_it_and_did_NOT_suspend_silences_it():
    """The boundary — `all(...)`. One run that reached a writable state and stayed quiet makes
    the silence a statement about the tool again, however weak."""
    runs = [_run(pending_approval={"tier": "A"}, store_diff={}) for _ in range(4)]
    runs.append(_run(store_diff={}))
    assert NEEDLE not in _render(runs)


def test_a_tool_that_was_NEVER_called_is_not_annotated():
    """PRECISION, and the 10 batches the batch-wide rule would wrongly have claimed. If the tool
    never ran, `unchanged` is about the model not reaching it — which the `tool called` column
    already says, and which is a real finding."""
    runs = [_run(called=("something_else",), pending_approval={"tier": "A"}, store_diff={})
            for _ in range(5)]
    assert NEEDLE not in _render(runs)


def test_an_ordinary_quiet_batch_still_says_unchanged():
    out = _render([_run(store_diff={}) for _ in range(5)])
    assert "unchanged" in out and NEEDLE not in out


def test_the_SUSPENDED_annotation_is_still_printed():
    """It already existed and is not replaced: the count of cards is a different fact from the
    bar being unreadable, and a reader wants both."""
    out = _render([_run(pending_approval={"tier": "A"}, store_diff={}) for _ in range(5)])
    assert "left SUSPENDED on a Tier-A approval card in 5/5" in out


def test_the_LIVE_batch_renders_it():
    """ANTI-VACUITY against the run that refuted the first design."""
    raw = ROOT / "docs" / "eval" / "toolloop" / "2026-08-14" / "c-nowrite1-raw.json"
    if not raw.exists():
        import pytest
        pytest.skip("the live batch is not on disk")
    runs = json.loads(raw.read_text(encoding="utf-8"))
    called = [r for r in runs if "jobs_cancel" in fr.called_names(r)]
    assert 0 < len(called) < len(runs), (
        "the live batch no longer shows the mixed shape this guard is about"
    )
    out = _render(runs, [{"id": "jobs-cancel-asked", "expect_tool": "jobs_cancel"}])
    assert NEEDLE in out and "WROTE" in out


def test_the_population_is_worth_a_guard():
    """ANTI-VACUITY on the size, under the rule that actually shipped."""
    scen = {}
    for f in (ROOT / "scripts" / "toolloop").glob("scenarios-*.json"):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        for s in d.get("scenarios", []):
            scen.setdefault(s["id"], s.get("expect_tool"))
    by = collections.defaultdict(list)
    for f in sorted((ROOT / "docs" / "eval" / "toolloop").rglob("*-raw.json")):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(d, list):
            continue
        for r in d:
            if isinstance(r, dict) and r.get("scenario"):
                by[(f.name, r["scenario"])].append(r)
    hit = 0
    for (_, sid), rs in by.items():
        want = scen.get(sid)
        if not want or len(rs) < 3:
            continue
        called = [r for r in rs if want in fr.called_names(r)]
        if called and all(r.get("pending_approval") for r in called) \
                and not any(r.get("store_diff") for r in called):
            hit += 1
    assert hit >= 10, f"only {hit} batches on disk match the shipped rule — re-derive the row"
