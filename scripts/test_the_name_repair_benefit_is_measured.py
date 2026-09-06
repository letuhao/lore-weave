"""D-THE-NAME-REPAIR-WORKS-AND-ITS-BENEFIT-IS-UNDEMONSTRATED.

    THE INVARIANT. A fix is a win only against the population it was written for, measured on
    both sides. "The mechanism fires" is not the same claim as "the mechanism helps".

`_name_like_dropped_ids` makes a refusal echo the NAMES the model passed where ids were
required. The mechanism was confirmed live; the improvement was not, and the row's own control
(c2-motif, 14 hours pre-fix) showed the model already recovering.

THE A/B, on the row's own failure mode — the turn ending with the model asking the AUTHOR for
ids instead of searching for them:

    batch          when   asked for ids   searches with a query   errored
    batch19-v5     PRE          5/5                 0                0
    c2-motif       PRE          0/5                 5                3
    c-motiflink2   POST         0/5                 3                4
    c-namerepair1  POST         0/5                 8                0   <- run for this row

Pooled PRE 5 of 10, POST 0 of 10, two-tailed Fisher p = 0.0325. Against the single batch the
fix's docstring cites, 5/5 vs 0/5, p = 0.0079.

🔴 THE ROW SAID THE FAILING POPULATION WAS NOT REPRODUCIBLE, and it is — the mistake is
instructive. batch19-v5 has no `-raw.json`, so the argument deltas are gone; but the BATCH file
carries the ANSWERS, and rep0's reads "I need the specific IDs … rather than just their names …
Could you provide the IDs", on 5 of 5. Looking for the deltas and concluding absence when the
answer carried the finding is the same shape as that row's own method_note.

🔴 THE CONTROL THAT WEAKENS IT STAYS ON THE RECORD. The pre-fix population is heterogeneous —
5/5 stuck in one batch and 0/5 in another, hours apart — so the pooled rate is an average over
the widest possible spread. The DIRECTION is consistent across all four arms with no
counter-example; the EFFECT SIZE is not established.
"""
from __future__ import annotations

import collections
import json
import pathlib
import sys
from math import comb

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "toolloop"))
EVID = ROOT / "docs" / "eval" / "toolloop" / "2026-08-14"

ASKED = ("provide the id", "need the specific id", "rather than just their names",
         "could you provide")


def _runs(name: str, tool: str = "composition_motif_link_edit"):
    p = EVID / name
    if not p.exists():
        pytest.skip(f"{name} is not on disk")
    d = json.loads(p.read_text(encoding="utf-8"))
    if isinstance(d, list):
        return d, "text"
    return [r for t in d["tools"] if t["tool"] == tool for r in t["runs"]], "answer"


def _asked(runs, key):
    return sum(1 for r in runs if any(s in (r.get(key) or "").lower() for s in ASKED))


def _q_searches(runs):
    n = 0
    for r in runs:
        names, args = {}, collections.defaultdict(str)
        for ev in (r.get("tool_calls") or []):
            cid = ev.get("toolCallId")
            if ev.get("type") == "TOOL_CALL_START" and ev.get("toolCallName"):
                names[cid] = ev["toolCallName"]
            if ev.get("type") == "TOOL_CALL_ARGS":
                args[cid] += str(ev.get("delta") or "")
        for cid, nm in names.items():
            if nm != "composition_motif_search":
                continue
            try:
                a = json.loads(args.get(cid) or "{}")
            except Exception:
                a = {}
            if a.get("q"):
                n += 1
    return n


def _fisher(a, b, c, d):
    n, r1, c1 = a + b + c + d, a + b, a + c

    def p(x):
        return comb(r1, x) * comb(n - r1, c1 - x) / comb(n, c1)
    obs = p(a)
    return sum(p(x) for x in range(max(0, c1 - (n - r1)), min(r1, c1) + 1) if p(x) <= obs + 1e-12)


def test_the_PRE_FIX_failure_is_on_disk_after_all():
    """The row said it was not reproducible. It is — in the ANSWERS, not the argument deltas."""
    runs, key = _runs("batch19-v5.json")
    assert len(runs) == 5
    assert _asked(runs, key) == 5, "the pre-fix arm no longer shows the failure — re-derive"
    assert _q_searches(runs) == 0


def test_the_POST_FIX_arm_does_not_ask_the_author():
    runs, key = _runs("c-namerepair1-raw.json")
    assert len(runs) == 5
    assert _asked(runs, key) == 0
    assert _q_searches(runs) >= 5, "the model is not searching with the name it was handed"
    assert sum(1 for r in runs if r.get("error")) == 0, "the clean arm is no longer clean"


def test_the_pooled_difference_is_significant():
    pre = sum(_asked(*_runs(n)) for n in ("batch19-v5.json", "c2-motif-raw.json"))
    post = sum(_asked(*_runs(n)) for n in ("c-motiflink2-raw.json", "c-namerepair1-raw.json"))
    assert (pre, post) == (5, 0), (pre, post)
    assert _fisher(5, 5, 0, 10) < 0.05


def test_the_WEAKENING_control_is_still_true():
    """🔴 ANTI-VACUITY ON THE HONESTY. The pre-fix population is heterogeneous and that is why
    this is p=0.03 and not more. If c2-motif ever stops showing 0/5, the caveat changes and the
    row must be re-derived rather than kept."""
    runs, key = _runs("c2-motif-raw.json")
    assert _asked(runs, key) == 0, (
        "the pre-fix control no longer disagrees with the pre-fix baseline — the heterogeneity "
        "this row records has changed"
    )


def test_the_blank_search_population_is_absent_from_the_corpus():
    """Re-derived with arguments REASSEMBLED PER CALL ID, which is the row's own method_note.

    🔴 RE-ANCHORED 2026-08-30, AND THE OLD BAR WAS THE MISTAKE THIS LOOP SPENT TODAY LEARNING.
    It read `assert blank <= 10` — an ABSOLUTE COUNT of offending calls, checked against a corpus
    that grows every time a batch runs. The count reached 20 and the guard went red without
    anything getting worse: today's three motif-link timeout batches each ran
    `composition-motif-adopt` five more times, and that scenario blank-searches every single
    time. A numerator asserted against a moving denominator measures the CORPUS, not the defect —
    the same error corrected today on two ledger rows, where 270 runs were really 15 and 285 were
    really 22.

    WHAT IS ACTUALLY INVARIANT, and what is asserted instead:
      * blank searches stay CONFINED to `composition-motif-adopt`, whose prompt names no target,
      * that scenario blanks at essentially 100% — 20 of 20, unchanged from the original 5 of 5,
      * and its NAMED sibling `composition-motif-adopt-named` is 0 of 15, which is the control
        that makes the confinement a discrimination rather than an accident of one scenario
        being rare.
    """
    blank = withq = 0
    offenders = collections.Counter()
    searched_runs = collections.Counter()
    blanked_runs = collections.Counter()
    for f in sorted((ROOT / "docs" / "eval" / "toolloop").rglob("*-raw.json")):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(d, list):
            continue
        for r in d:
            if not isinstance(r, dict):
                continue
            names, args = {}, collections.defaultdict(str)
            for ev in (r.get("tool_calls") or []):
                cid = ev.get("toolCallId")
                if ev.get("type") == "TOOL_CALL_START" and ev.get("toolCallName"):
                    names[cid] = ev["toolCallName"]
                if ev.get("type") == "TOOL_CALL_ARGS":
                    args[cid] += str(ev.get("delta") or "")
            run_searched = run_blanked = False
            for cid, nm in names.items():
                if not nm.endswith("_search"):
                    continue
                run_searched = True
                try:
                    a = json.loads(args.get(cid) or "{}")
                except Exception:
                    a = {}
                if a.get("q") or a.get("query") or a.get("text"):
                    withq += 1
                else:
                    blank += 1
                    run_blanked = True
                    offenders[r.get("scenario")] += 1
            if run_searched:
                searched_runs[r.get("scenario")] += 1
                if run_blanked:
                    blanked_runs[r.get("scenario")] += 1

    # ANTI-VACUITY: a corpus with no searches in it would satisfy everything below.
    assert withq >= 300, withq

    # THE CONFINEMENT. One scenario, and it is the one whose prompt names no target.
    assert set(offenders) <= {"composition-motif-adopt"}, dict(offenders)

    # THE RATE, not the count. This scenario has always blanked on every run it searched on.
    adopt = "composition-motif-adopt"
    assert searched_runs[adopt] >= 20, (
        f"only {searched_runs[adopt]} runs of {adopt} searched — the population shrank and the "
        "rate below is no longer meaningful")
    assert blanked_runs[adopt] == searched_runs[adopt], (
        f"{adopt} now blanks on {blanked_runs[adopt]} of {searched_runs[adopt]} runs rather than "
        "all of them — the behaviour this row describes has CHANGED, in either direction, and the "
        "row must be re-derived rather than kept")

    # THE CONTROL that makes the confinement a discrimination: same tool, prompt names a target.
    named = "composition-motif-adopt-named"
    assert searched_runs[named] >= 10, (
        f"the named control has only {searched_runs[named]} searching runs — too few to control "
        "anything")
    assert blanked_runs[named] == 0, (
        f"the NAMED sibling has started blank-searching ({blanked_runs[named]} of "
        f"{searched_runs[named]}) — naming the target no longer prevents it, which is a bigger "
        "finding than this row and needs its own investigation")
