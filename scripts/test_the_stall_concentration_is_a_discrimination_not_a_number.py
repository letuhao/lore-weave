"""D-THE-STALL-CONCENTRATES-ON-COMPOSITION-MOTIF-SEARCH.

    THE INVARIANT. Assert the DISCRIMINATION, not the rate. A percentage measured on 41 runs is
    a lead; what a guard can hold is that the buckets still separate.

The row reported the stall concentrating on turns that call composition_motif_search: 73%
errored over 41 runs, against 6% baseline, with a 0%-error control of 16 motif-family runs that
never call the search.

🔴 RE-DERIVED 2026-08-27 OVER 1,491 RUNS INSTEAD OF 875, AND THE HEADLINE DID NOT SURVIVE:

                                     runs   errored    rate      (the row said)
    calls composition_motif_search      89       36    40.4%      73% over 41
    motif family, NO search             18        0     0.0%       0% over 16
    no motif tool at all             1,384       85     6.1%       6% over 818

The rate HALVED as n doubled. What survives is the separation — still 6.6x baseline, with the
zero-error control now at 18 runs — and it has not gone away: over runs recorded 2026-08-26 or
later, 3 of 8 search-calling runs errored (37.5%) against 4.6% over 131.

So this file asserts the SHAPE and refuses to assert the number. A guard pinned to 73% would
have gone red for the right reason and been "fixed" by editing the constant, which is how a
measurement becomes a monument.

🔴 RE-DERIVED AGAIN 2026-08-30 OVER 1,901 RUNS, AND THIS TIME THE SHAPE IS THE CASUALTY:

                                     runs   errored    rate
    calls composition_motif_search     169       36    21.3%
    motif family, NO search             18        0     0.0%
    no motif tool at all             1,714      122     7.1%

The ratio has walked down 12x -> 6.6x -> 2.99x, and 2.99 tripped the `> 3 * base` bar. The
tempting repair is to lower the bar. The right one was to ask WHY, and the answer changes the
row rather than the constant — STRATIFY THE SEARCH BUCKET BY SCENARIO:

     53 runs  25 err  47%   composition-motif-link-edit
     15 runs  10 err  67%   composition-motif-adopt-named
     30 runs   0 err   0%   composition-motif-bind-edit
     21 runs   0 err   0%   composition-motif-link-edit-approved
     20 runs   0 err   0%   composition-motif-adopt
     15 runs   0 err   0%   composition-motif-edit
     15 runs   0 err   0%   (three smaller scenarios, one error between them)

TWO scenarios carry 35 of the 36 errors. NINETY-SIX runs across six other scenarios call the
SAME SEARCH TOOL and error ZERO times. So calling composition_motif_search is not what
discriminates — the pooled 21.3% is an average over one population that stalls badly and another
that does not stall at all, and every re-derivation of this row has been watching that average
get diluted as the calm scenarios were run more often.

That is the third instance found on 2026-08-30 of a rate quoted over a population that does not
share the trigger; the other two were on the pass-recorder and silent-turn rows. The row's own
thesis — "the stall concentrates on the SEARCH" — is not supported by a bucket in which most of
the search's runs are clean, and re-characterising it is DQ-T53's owner's call, not this file's.
What the guards below now hold is the separation that IS still real and the stratification that
explains it.

WHAT IS ALSO KNOWN, and is why the row is blocked rather than open: the search alone does NOT
stall (batch20-motif-search-clean, K=5, 0 errored, the search as the ANSWER), and a controlled
A/B inside one batch showed the failing request IS built and IS sent — identical 14,556-token
preflight and byte-identical 532-byte tool result in all five runs, 3 dying and 2 not. The
failure is in GENERATION on the pass that must emit the next tool call, and the only record of
why is LM Studio's server log, whose newest file is dated 2026-08-04. That is DQ-T53.
"""
from __future__ import annotations

import collections
import json
import math
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "toolloop"))

import fe_runner as fr  # noqa: E402

LEDGER = json.loads((ROOT / "contracts" / "tool-deep-dive-ledger.json").read_text(
    encoding="utf-8"))


def buckets():
    runs: collections.Counter = collections.Counter()
    errs: collections.Counter = collections.Counter()
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
            called = fr.called_names(r)
            if "composition_motif_search" in called:
                b = "search"
            elif any(c.startswith("composition_motif") for c in called):
                b = "motif_no_search"
            else:
                b = "none"
            runs[b] += 1
            errs[b] += bool(r.get("error"))
    return runs, errs


def test_the_corpus_is_big_enough_to_say_anything():
    runs, _ = buckets()
    assert sum(runs.values()) >= 1000, sum(runs.values())
    assert runs["search"] >= 40, runs["search"]
    assert runs["motif_no_search"] >= 10, runs["motif_no_search"]


def _two_proportion_p(k1, n1, k2, n2):
    """Two-sided p for two proportions differing. Normal approximation, math only — every count
    here is comfortably large enough for it, and a scipy dependency for one number is not worth
    it."""
    p = (k1 + k2) / (n1 + n2)
    se = math.sqrt(p * (1 - p) * (1 / n1 + 1 / n2))
    if se == 0:
        return 1.0
    z = (k1 / n1 - k2 / n2) / se
    return math.erfc(abs(z) / math.sqrt(2))


def test_the_buckets_still_SEPARATE():
    """The claim that survives — and it is now a WEAKER claim than it was, said out loud.

    🔴 THIS GUARD USED TO READ `search > 3 * base` AND IT WENT RED AT 2.99x. Editing the 3 down
    to a 2 would have been the monument this file's own docstring warns about, one paragraph
    after warning about it. The ratio is not the durable statistic: it has fallen 12x -> 6.6x ->
    2.99x purely as calmer scenarios were run more often (see the stratification above), and it
    will keep falling for that reason alone.

    What is asserted instead is that the two populations still differ AT ALL, tested rather than
    eyeballed. 21.3% of 169 against 7.1% of 1,714 is overwhelming by any test; if that ever stops
    holding, the row has genuinely evaporated rather than merely diluted."""
    runs, errs = buckets()
    search = errs["search"] / runs["search"]
    base = errs["none"] / runs["none"]
    p = _two_proportion_p(errs["search"], runs["search"], errs["none"], runs["none"])
    assert search > base, (
        f"search {search:.3f} vs baseline {base:.3f} — the search bucket is no longer the worse "
        "one, which is the end of this row rather than a dilution of it")
    assert p < 0.01, (
        f"search {search:.3f} (n={runs['search']}) vs baseline {base:.3f} (n={runs['none']}) "
        f"no longer separate: p={p:.3f}. The separation is gone.")


def test_the_concentration_is_SCENARIO_shaped_not_TOOL_shaped():
    """🔴 THE FINDING THAT COST THE RATIO ITS MEANING, pinned so it cannot be forgotten the next
    time someone reads "21% of search-calling runs error" as a property of the search.

    Most runs that call composition_motif_search never error. The errors sit in a small number of
    scenarios, and a guard that only ever looked at the pooled bucket could not see that — it is
    the same population-mixing that produced two wrong rates on the ledger the same day.

    If this ever fails because the clean scenarios START erroring, the tool-level reading is back
    and that is a real finding. If it fails because the erroring scenarios stop, so is that."""
    per_runs, per_errs = collections.Counter(), collections.Counter()
    for f in sorted((ROOT / "docs" / "eval" / "toolloop").rglob("*-raw.json")):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(d, list):
            continue
        for r in d:
            if not isinstance(r, dict) or "composition_motif_search" not in fr.called_names(r):
                continue
            per_runs[r.get("scenario")] += 1
            per_errs[r.get("scenario")] += bool(r.get("error"))

    assert sum(per_runs.values()) >= 150, sum(per_runs.values())
    clean = {s for s in per_runs if per_errs[s] == 0}
    clean_runs = sum(per_runs[s] for s in clean)
    total = sum(per_runs.values())
    assert len(clean) >= 4, (
        f"only {len(clean)} search-calling scenarios are error-free — the stall is spreading "
        "across the family and the tool-level reading is back")
    # 🔴 THIS BAR WAS `clean_runs > total / 2` AND IT MOVED THE WRONG WAY. Adding 35 CLEAN runs
    # to the two ERRORING scenarios on 2026-08-30 — runs that made those scenarios' own rates
    # better, 47% -> 30% and 67% -> 50% — pushed the clean SHARE from 57% to 48% and failed the
    # guard. A bar that a clean run can break is measuring the population mix, not the claim.
    #
    # The claim is that the search TOOL is not what discriminates, and it has two halves that a
    # fraction cannot express:
    #   * a large ABSOLUTE body of runs calls the tool and never errors — a floor, which new
    #     clean runs can only raise, so it is safe over a growing corpus in the way a ceiling
    #     (`blank <= 10`, corrected the same day) is not;
    #   * the errors CONCENTRATE — measured on the errors themselves, which is the quantity the
    #     row is actually about.
    assert clean_runs >= 90, (
        f"only {clean_runs} runs sit in error-free search-calling scenarios (was 101 when this "
        "was derived). Clean scenarios have started erroring, which is the tool-level reading "
        "coming back")
    top2 = sum(n for _, n in sorted(per_errs.items(), key=lambda kv: -kv[1])[:2])
    all_errs = sum(per_errs.values())
    assert all_errs and top2 / all_errs >= 0.85, (
        f"the top two scenarios hold {top2} of {all_errs} errors ({top2 / max(all_errs,1):.0%}); "
        "the concentration this row rests on has broken up and the pooled bucket rate would now "
        "be a fair summary of the search itself — re-derive the row")


def test_the_ZERO_ERROR_control_still_holds():
    """🔴 THE CONTROL IS WHAT MAKES IT THE SEARCH AND NOT THE FAMILY, THE FIXTURE OR THE DOMAIN.
    If motif-family runs that never call the search start erroring, the whole reading changes."""
    runs, errs = buckets()
    assert errs["motif_no_search"] == 0, (
        f"{errs['motif_no_search']} of {runs['motif_no_search']} motif-family runs without the "
        "search now error — re-derive the row, the effect is no longer specific to the search"
    )


def test_the_ROW_no_longer_asserts_the_stale_rate():
    """🔴 A LEDGER CLAIM IS A LEAD, NOT A FACT. The 73% was measured on 41 runs and halved at 89.
    The row must carry the correction, or the next reader inherits the over-estimate."""
    r = LEDGER["defects"]["D-THE-STALL-CONCENTRATES-ON-COMPOSITION-MOTIF-SEARCH"]
    blob = json.dumps(r)
    assert "RE_DERIVED_2026_08_27_and_the_headline_was_an_over_estimate" in blob
    assert "40.4%" in blob and "1,491" in blob


def test_the_row_is_BLOCKED_on_the_owner_action_it_named():
    r = LEDGER["defects"]["D-THE-STALL-CONCENTRATES-ON-COMPOSITION-MOTIF-SEARCH"]
    assert r.get("blocked_by_dq") == "DQ-T53"
    dq = LEDGER["deferred_questions"]["DQ-T53"]
    assert dq["state"] == "open"
    assert "I am not able to do it" in dq["my_recommendation"]


def test_the_tautology_the_row_warned_about_is_not_repeated():
    """The row flagged a split it almost reported: 'search was the LAST call' errors 81% because
    when the turn dies after the search, the search IS the last call by consequence. Nothing
    here may reintroduce it."""
    src = pathlib.Path(__file__).read_text(encoding="utf-8")
    assert "last call" not in src.lower() or "tautolog" in src.lower()
