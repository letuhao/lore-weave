"""D-THE-MOTIF-LINK-SCENARIO-TIMES-OUT-6-OF-10 — the capture must say which kind it caught.

    THE INVARIANT. A timeout the harness MANUFACTURED to prove its instrument is not an
    instance of the defect the instrument exists to catch, and a capture that cannot tell them
    apart will be counted as one.

🔴 MEASURED 2026-08-27 over every dead-turn capture on disk — 13 of them, and they are NOT all
the same thing:

    10   c-rail1 / c-rail2   gap between the two user rows 178.9s   ORGANIC (TURN_TIMEOUT=180)
     3   c-deadturn4         gap 0.7s                              FORCED, sub-second deadline

`c-deadturn4` is the batch that PROVED this instrument — the row records forcing three real
ReadTimeouts to show the capture fires. Every one of the thirteen otherwise carries an
IDENTICAL signature: two user rows, no assistant row, `agent-surface advertised` present,
`orphaned turn` present, error `ReadTimeout`. So counting captures across batches reads three
demonstrations as three more instances of the defect — which is what I did, for a minute,
before checking the gap.

WHAT THIS CORRECTS IN THE ROW'S OWN OPEN QUESTION. The row asks whether other long scenarios
carry the same residual timeout. The 13 captures look like three scenarios and are not: the
ten ORGANIC ones are all `translation-update-settings`. The question is still open, and the
number that appeared to answer it does not.
"""
from __future__ import annotations

import glob
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "toolloop"))

import fe_runner as fr  # noqa: E402


def _captures():
    out = []
    for fp in sorted(glob.glob(str(ROOT / "docs" / "eval" / "toolloop" / "**" / "*-raw.json"),
                               recursive=True)):
        try:
            runs = json.loads(pathlib.Path(fp).read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        if not isinstance(runs, list):
            continue
        for r in runs:
            if isinstance(r, dict) and isinstance(r.get("dead_turn"), dict):
                out.append((pathlib.Path(fp).name, r.get("scenario"), r["dead_turn"]))
    return out


def _verdict(dt):
    """🔴 THROUGH THE SHIPPED RULE, ALWAYS. The first version of this helper re-derived the gap
    itself and fell back to the stored field — so removing the field and hard-coding the
    threshold both left this suite GREEN, and neither falsifier proved anything. It now calls
    `retry_gap_verdict`, which is the code that runs in the capture."""
    return fr.retry_gap_verdict(dt.get("rows_by_role") or {})


def _gap(dt):
    return _verdict(dt).get("retry_gap_s")


def test_the_corpus_holds_BOTH_kinds_and_they_are_separable():
    """🔴 THE FALSIFIER, on the captures actually on disk. If this ever finds only one kind,
    the discrimination is untested and the guard below is decoration."""
    caps = _captures()
    assert len(caps) >= 13, f"only {len(caps)} captures — the corpus has shrunk"
    gaps = [(n, s, _gap(dt)) for n, s, dt in caps]
    assert all(g is not None for _, _, g in gaps), "a capture no longer carries its row times"
    forced = [(n, s) for n, s, dt in caps if not _verdict(dt).get("organic_timeout")]
    organic = [(n, s) for n, s, dt in caps if _verdict(dt).get("organic_timeout")]
    assert forced, "no FORCED capture found — the discrimination has nothing to separate"
    assert organic, "no ORGANIC capture found — likewise"
    assert all("deadturn" in n for n, _ in forced), forced
    assert {s for _, s in organic} == {"translation-update-settings"}, sorted({s for _, s in organic})


def test_the_two_kinds_are_INDISTINGUISHABLE_without_the_gap():
    """Why the field had to be added rather than left to a reader's judgement: every other
    signal in the capture is identical across both kinds."""
    caps = _captures()
    sigs = set()
    for _, _, dt in caps:
        lines = " ".join(str(x) for x in (dt.get("log_lines") or []))
        sigs.add((dt.get("user_rows"), dt.get("no_assistant_row"),
                  "agent-surface advertised" in lines, "orphaned turn" in lines))
    assert len(sigs) == 1, (
        f"the signatures now differ ({sigs}) — a reader could tell forced from organic without "
        f"the gap, and this guard's premise should be re-derived"
    )


def test_a_new_capture_RECORDS_the_gap_and_its_verdict():
    """The shipped fields, exercised on the shape the store returns rather than asserted about
    the source. A capture written from now on answers the question by itself."""
    organic = fr.retry_gap_verdict({"user": {"n": 2, "first": "2026-08-27 07:17:37.0+00",
                                             "last": "2026-08-27 07:20:36.0+00"}})
    assert organic == {"retry_gap_s": 179.0, "organic_timeout": True}, organic
    forced = fr.retry_gap_verdict({"user": {"n": 2, "first": "2026-08-27 01:00:00.0+00",
                                            "last": "2026-08-27 01:00:00.7+00"}})
    assert forced == {"retry_gap_s": 0.7, "organic_timeout": False}, forced
    assert fr.retry_gap_verdict({"user": {"n": 1, "first": "x", "last": "x"}}) == {}
    assert fr.retry_gap_verdict({}) == {}


def test_the_threshold_is_relative_to_the_BUDGET_not_a_constant():
    """A hard-coded 90 would silently mis-label every capture if TURN_TIMEOUT moved. The rule
    is 'at least half the budget the client actually gave it'."""
    rows = {"user": {"n": 2, "first": "2026-08-27 01:00:00.0+00",
                     "last": "2026-08-27 01:01:00.0+00"}}          # a 60s gap
    saved = fr.TURN_TIMEOUT
    try:
        fr.TURN_TIMEOUT = 180.0
        assert fr.retry_gap_verdict(rows)["organic_timeout"] is False, "60s of a 180s budget"
        fr.TURN_TIMEOUT = 60.0
        assert fr.retry_gap_verdict(rows)["organic_timeout"] is True, (
            "the SAME 60s gap must read ORGANIC against a 60s budget — a hard-coded threshold "
            "here mis-labels every capture the moment the budget moves"
        )
    finally:
        fr.TURN_TIMEOUT = saved
