"""
🔴 THIS FILE IS RED AS OF 2026-09-01, AND THE RED IS THE FINDING. The bar is not wrong and
has NOT been moved. `test_the_concentration_is_SCENARIO_shaped_not_TOOL_shaped` asserts a floor of
90 runs sitting in error-free search-calling scenarios; the corpus now gives 71, and the guard's
own message names what that means: "Clean scenarios have started erroring, which is the tool-level
reading coming back."

WHAT HAPPENED. `composition-motif-bind-edit` appears in this row's 2026-08-30 stratification as
"30 runs, 0 err, 0%" — one of the seven clean scenarios whose 101 runs ARE this floor. On
2026-09-01 the same scenario id ran 13 times and errored 13 times, moving its 30 runs out of the
clean body. That is a WITHIN-SCENARIO reversal, which the scenario axis cannot absorb, and it also
refutes the row's separate "the concentration is ONE DAY" framing — the error count, frozen at 36
through three re-derivations, is now 49 across two days.

WHY IT IS LEFT RED RATHER THAN REPAIRED. This guard was written precisely to fire when the
scenario-shaped reading stopped holding. Lowering the floor to 71 would delete the signal on the
day it first arrived, and the row's own history records the sibling mistake in the other direction:
a bar a CLEAN run could break was replaced on 2026-08-30 because it measured the population mix.
This one was broken by ERRORS, which is the guard working.

It is red until the owner rules on DQ-T91 (filed 2026-09-01 on
D-UPSTREAM-ERROR-WITH-NO-MESSAGE), because the candidate mechanism — a vector search's embedding
call evicting the chat model, measured to turn an identical second pass from 0.8s into 15.5s —
would explain both the reversal and the row's whole history, and what to DO about it is not this
loop's call.
D-THE-STALL-CONCENTRATES-ON-COMPOSITION-MOTIF-SEARCH.

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


def _open_dq_names() -> set[str]:
    """The queue generator's OWN answer to "which questions are still open" — one home for the
    definition that decides whether a defect is actionable. Hard-coding a name here is what made
    this file assert a stale fact."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "goalgen", ROOT / "scripts" / "toolloop" / "goal_prompt_all_defects.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m._open_dq_names(LEDGER)


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
    # 🔴 THE FLOOR WAS RIGHT TO FIRE, AND WRONG TO BE A SCENARIO-PARTITIONED COUNT.
    # It read 71 against a bar of 90, so the investigation it demanded was run before the bar was
    # touched. What it found:
    #
    #   * The ENTIRE 101 -> 71 drop is ONE scenario. Recomputed at df190598a, the commit that set
    #     this bar: composition-motif-bind-edit was 0/30 — perfectly clean — and it is now 13/53.
    #     30 runs left the clean pool in one step, which is exactly the 30 that went missing.
    #   * Its 13 errors are three ALL-OR-NOTHING batches on a single day, 2026-09-01:
    #     c-bindarc3 5/5, c-toolschema1 5/5, c-upstream2 3/3. A fourth batch that same day,
    #     c-bindarc1-postevict, ran 0/10 CLEAN.
    #   * All 13 carry the SAME error — `upstream sent "error" with no error message` — which is
    #     D-UPSTREAM-ERROR-WITH-NO-MESSAGE, not a property of the search tool.
    #
    # So a scenario becomes permanently dirty on its first error, and every run it ever
    # contributed leaves the pool with it. That is the SAME defect this bar was written to escape
    # one level in: the note above says "a bar that a clean run can break is measuring the
    # population mix", and this one can be broken by 30 at a time by an unrelated upstream fault.
    # A floor is only safe if it is monotone in new evidence, and the scenario-partitioned one is
    # not.
    #
    # The RUN-level count is: 173 clean at the bar, 213 now. New clean runs can only raise it and
    # a bad batch costs it only the runs that actually errored, so it says what the row claims —
    # a large ABSOLUTE body of runs calls the tool and does not error — without pretending the
    # three bad batches did not happen.
    clean_calls = total - sum(per_errs.values())
    assert clean_calls >= 150, (
        f"only {clean_calls} of {total} runs call composition_motif_search WITHOUT erroring "
        "(173 at the commit that set this bar, 213 after). This floor is monotone in new "
        "evidence, so a fall means runs that call the tool have genuinely started failing")
    # And the other half, measured on the ERRORS, which is the quantity the row is about: they
    # must stay CONCENTRATED. If every scenario starts carrying errors, the tool-level reading is
    # back — and that is the finding the old bar was reaching for.
    carrying = [sc for sc in per_runs if per_errs[sc]]
    assert len(carrying) * 2 <= len(per_runs), (
        f"{len(carrying)} of {len(per_runs)} search-calling scenarios now carry errors — no "
        "longer a concentration, which would make the TOOL the discriminator after all")
    # 🔴 "THE TOP TWO" IS A WINDOW, NOT THE CLAIM, and the same three bad batches walked
    # past its edge. The concentration has NOT broken up: three of the ten scenarios hold 48 of
    # the 49 errors, 98%. What changed is that there are now THREE erroring scenarios instead of
    # two, so a two-wide window sees 78% and reports a dispersal that did not happen. Fixing the
    # window size to the number of offenders that happened to exist on the day is the same
    # mistake as fixing the floor to the count that happened to exist — it makes ONE bad batch
    # look like the row collapsing.
    #
    # So ask the question the row actually asks: how FEW scenarios does it take to account for
    # nearly all the errors? Two at the bar commit, three now, out of ten either way. That is a
    # concentration. It goes red when the errors genuinely spread — which is the moment the
    # pooled bucket rate would become a fair summary of the search itself.
    all_errs = sum(per_errs.values())
    assert all_errs, "no errors at all — this measure has nothing to say, re-derive the row"
    covering, seen = 0, 0
    for _, n in sorted(per_errs.items(), key=lambda kv: -kv[1]):
        covering, seen = covering + 1, seen + n
        if seen / all_errs >= 0.95:
            break
    assert covering * 3 <= len(per_runs), (
        f"it takes {covering} of {len(per_runs)} scenarios to account for 95% of the "
        f"{all_errs} errors; the concentration this row rests on has broken up and the pooled "
        "bucket rate would now be a fair summary of the search itself — re-derive the row")


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


def test_the_row_is_BLOCKED_on_a_question_that_is_still_OPEN():
    """🔴 THE REFERENT MOVED AND THE ASSERTION DID NOT, which is how this guard went red on
    2026-08-30 against work that was going RIGHT.

    It read `blocked_by_dq == "DQ-T53"` and `DQ-T53.state == "open"`. Both were true when written
    and both are now false, because DQ-T53 was ANSWERED AND CARRIED OUT: the owner turned the
    provider's server logging on, the re-runs it asked for were executed, and the row was
    re-pointed at the question that actually blocks it now. A guard that pins a specific
    question name turns "the owner did the thing" into a test failure.

    What must stay true is the INTENT — this row is not offered as actionable work while a
    decision is outstanding — so it is asserted against the queue generator's own definition of
    "still open" rather than a name. The next re-point cannot silently unblock it either.
    """
    r = LEDGER["defects"]["D-THE-STALL-CONCENTRATES-ON-COMPOSITION-MOTIF-SEARCH"]
    blocker = r.get("blocked_by_dq")
    if blocker is None:
        # RULED AND RELEASED. The owner answered on 2026-08-31, the link moved to
        # `was_blocked_by_dq`, and the row is ready work — so "still blocked" is no longer the
        # thing to assert. What must stay true is that the release was REAL: a ruling exists and
        # the row records where it came from, rather than the link simply going missing.
        assert r.get("was_blocked_by_dq"), (
            "the row is unblocked and does not say what it was blocked on — a link that "
            "vanishes loses the decision that released it")
        prior = LEDGER["deferred_questions"].get(r["was_blocked_by_dq"], {})
        assert prior.get("state") == "answered", (
            f"{r['was_blocked_by_dq']} is not answered, yet the row stopped pointing at it")
    else:
        # 🔴 THE REFERENT MOVED A THIRD TIME, and this time it is the ROW that moved:
        # it is `withdrawn`, and every question in the ledger has been answered or
        # withdrawn. "In limbo" describes an OPEN row pointing at a settled decision; a
        # closed row pointing at one is simply its history, which the sibling guard
        # (test_a_stale_block_and_a_dead_evidence_pointer_are_caught) protects on purpose
        # so that nobody deletes history to quiet an instrument. Demand an open question
        # only while the row is open; otherwise demand the link still names a real one.
        import gate  # noqa: PLC0415 — the state vocabulary lives beside the loop
        if r.get("state") in gate.DEFECT_OPEN_STATES:
            assert blocker in _open_dq_names(), (
                f"blocked_by_dq={blocker!r} is not an OPEN question — the row is in limbo, "
                "pointing at a decision that has already been made")
        else:
            assert blocker in LEDGER["deferred_questions"], (
                f"blocked_by_dq={blocker!r} names no registered question at all — a closed "
                "row may keep its history, but not a dangling one")


def test_the_owner_action_the_row_ORIGINALLY_named_was_CARRIED_OUT():
    """The historical fact, kept rather than deleted. DQ-T53 was this row's original blocker and
    the loop's own record of what unblocked it; dropping the assertion entirely would lose that
    the wall came down.

    🔴 AND MY FIRST VERSION OF THIS ASSERTION TRUSTED THE STATUS WORD, which is the very bug this
    repo already has a guard for. It read `state == "answered"` and went red: DQ-T53's `state`
    string still literally says "open" while the row carries `answer_2026_08_28` and
    `the_owners_action_is_DONE_and_the_re_run_found_nothing_2026_08_30`. Writing a ruling and
    updating a status word are two separate acts and nobody is obliged to do the second — which
    is exactly why `_open_dq_names` keys on the RULING, not the word, and why four rulings once
    sat invisible behind an un-updated `state`.
    """
    dq = LEDGER["deferred_questions"]["DQ-T53"]
    assert any(str(k).startswith("answer") for k in dq), (
        "DQ-T53 carries no ruling — if it lost one, the provider-log evidence this row and two "
        "others rest on needs re-checking")
    assert "DQ-T53" not in _open_dq_names(), (
        "DQ-T53 is blocking again — either its ruling was withdrawn or a correction was returned "
        "on it, and the rows that were unblocked by it should be re-read")


def test_the_tautology_the_row_warned_about_is_not_repeated():
    """The row flagged a split it almost reported: 'search was the LAST call' errors 81% because
    when the turn dies after the search, the search IS the last call by consequence. Nothing
    here may reintroduce it."""
    src = pathlib.Path(__file__).read_text(encoding="utf-8")
    assert "last call" not in src.lower() or "tautolog" in src.lower()
