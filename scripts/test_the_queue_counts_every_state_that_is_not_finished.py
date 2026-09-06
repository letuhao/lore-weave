"""The queue that ends the run must count every row that is not finished.

    THE INVARIANT. `DEFECT_STATES` says what a row MAY say. Exactly one place decides which of
    those means FINISHED, and every consumer asks it. A state nobody classified must raise, never
    fall quietly out of the queue.

🔴 MEASURED 2026-08-30. `goal_prompt_all_defects.py` selected work with `state != "open"` and
skipped the rest. Of the 209 defect rows, 25 sat at `proven`:

    defects_open       24     all DQ-blocked
    defects_proven     25     INVISIBLE to the queue and to --check
    defects_fixed     138
    defects_withdrawn  21
    defects_superseded  1

So `--check` reported "every open defect is DQ-blocked; NEXT would point at a decision, not work"
while 25 rows had never been resolved either way — and the queue's own header said "nothing is
excluded". `proven` is not `fixed`, and this goal's bar is `fixed`.

THE LEDGER WAS NOT HIDING THEM. `progress` carries `defects_proven: 25` directly beside
`defects_open: 24`. Only the QUEUE was, which is the worse place: `recompute_progress` already
records this exact class — 57 open defects absorbed into a remainder bucket while the headline
read 14 against an actual 71 — and its remedy (a closed set, an unrecognised state RAISES, no
remainder to fall into) was never applied to the generator that ends the run.

And the generator's own `_open_dq_names` docstring states the rule it was breaking on a different
axis: "A queue that reports no work while work exists is worse than a wrong queue: nobody looks
again."

WHAT THIS DOES NOT DO. It does not decide what those 25 rows deserve. Three sampled — T7-D1,
T7-D2, T7-D3 — are demonstrably fixed in `tool_discovery.py` and merely unmarked, but marking a
row `fixed` without proving it is exactly what this loop forbids. That disposition is an owner
decision and is filed as its own question.
"""
from __future__ import annotations

import json
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "toolloop"))

import gate  # noqa: E402
import goal_prompt_all_defects as g  # noqa: E402

LEDGER = json.loads((ROOT / "contracts" / "tool-deep-dive-ledger.json").read_text("utf-8"))


@pytest.fixture
def pinned(tmp_path, monkeypatch):
    """The ledger, PINNED, so the expectation and `g.rows()` read the same bytes.

    🔴 THESE TESTS WERE RACY AND IT COST A RED SUITE. The module reads the ledger once at import
    and `g.rows()` re-reads it from disk; a ledger edit between the two — routine in this loop,
    which closes rows while a suite runs — made them disagree and two guards failed spuriously.
    A guard that goes red because the file it measures was edited is measuring the clock.
    """
    doc = json.loads((ROOT / "contracts" / "tool-deep-dive-ledger.json").read_text("utf-8"))
    p = tmp_path / "pinned.json"
    p.write_text(json.dumps(doc), encoding="utf-8")
    monkeypatch.setattr(g, "LEDGER", p)
    return doc


class TestTheVocabularyHasExactlyOneHome:
    def test_terminal_and_open_partition_the_closed_set(self):
        assert set(gate.DEFECT_TERMINAL_STATES) | set(gate.DEFECT_OPEN_STATES) \
            == set(gate.DEFECT_STATES)
        assert not set(gate.DEFECT_TERMINAL_STATES) & set(gate.DEFECT_OPEN_STATES)

    def test_a_NEW_state_token_defaults_to_OPEN_not_to_silence(self):
        """FAIL LOUD, NOT QUIET. OPEN is the remainder on purpose: the next token added lands in
        the queue instead of vanishing from it, which is how `proven` disappeared."""
        assert "proven" in gate.DEFECT_OPEN_STATES
        assert "open" in gate.DEFECT_OPEN_STATES
        for s in ("fixed", "withdrawn", "superseded"):
            assert s in gate.DEFECT_TERMINAL_STATES

    def test_the_queue_does_not_keep_its_own_copy_of_the_rule(self):
        src = (ROOT / "scripts" / "toolloop" / "goal_prompt_all_defects.py").read_text("utf-8")
        assert "gate.DEFECT_OPEN_STATES" in src, (
            "the generator is deciding what counts as work by itself again")
        # Anchored on the CODE form, not the words: the fix's own comment quotes the old
        # predicate to explain it, and a looser pattern matched that prose and failed green.
        assert 'v.get("state") != "open"' not in src, (
            "the generator is back to hard-coding a single state as the whole of the work")


class TestEveryUnfinishedRowIsQUEUED:
    def test_every_populated_non_terminal_state_is_in_the_queue(self, pinned):
        """Named for `proven` until 2026-08-31, and the rename is the finding.

        🔴 THE GUARD WENT VACUOUS BY SUCCEEDING. It asserted `proven` was non-empty — its own
        anti-vacuity floor — and the backlog it was written for drained to zero, so it went red
        for the best possible reason. Re-pointing it at whichever state happens to be populated
        today would just move the same trap; it now asks the general question instead: EVERY
        non-terminal state that any row actually holds must appear in the queue.

        That cannot go vacuous while any work exists, and it covers a state token added later —
        which is the direction `DEFECT_OPEN_STATES` was built to fail in.
        """
        rows, _ = g.rows()
        queued = {r[4] for r in rows}
        by_state: dict[str, set] = {}
        for k, v in (pinned["defects"] or {}).items():
            if isinstance(v, dict) and v.get("state") in gate.DEFECT_OPEN_STATES:
                by_state.setdefault(v["state"], set()).add(k)
        # 🔴 THE FLOOR OUTLIVED THE BACKLOG A SECOND TIME, and the answer to its own
        # question is now YES — every one of the defect rows is fixed, withdrawn,
        # cannot_reproduce or superseded, and `g.rows()` returns nothing. Demanding that
        # SOMETHING still be open is the same trap the docstring above describes, one level
        # further out: it makes finishing the work indistinguishable from breaking the
        # queue. The terminal state has its own invariant, and it is not vacuous — it goes
        # red if the queue lists anything at all while nothing is non-terminal.
        if not by_state:
            assert pinned["defects"], "the pin read a ledger with no defect rows at all"
            assert not queued, (
                f"every defect is terminal, yet the queue still lists {len(queued)} row(s): "
                f"{sorted(queued)[:5]}")
            return
        for state, names in sorted(by_state.items()):
            missing = sorted(names - queued)
            assert not missing, (
                f"{len(missing)} rows at `{state}` are absent from the queue that ends the run: "
                f"{missing[:5]}")

    def test_the_queue_total_equals_every_non_terminal_row(self, pinned):
        """ANTI-VACUITY AND ANTI-DRIFT IN ONE: the count is re-derived from the ledger rather than
        pinned, so it cannot rot, and it cannot pass by the queue being empty."""
        rows, _ = g.rows()
        expected = {k for k, v in (pinned["defects"] or {}).items()
                    if isinstance(v, dict) and v.get("state") in gate.DEFECT_OPEN_STATES}
        # 🔴 THE ANTI-VACUITY CHECK IS CROSS-DERIVED, NOT A FLOOR. This asserted `>= 40`
        # non-terminal rows, chosen when 47 were open. Draining them to 26 — the whole point of
        # the work — made my own guard red, and lowering the number to fit is exactly the move
        # this loop forbids. So the expectation now comes from `progress`, which gate.py computes
        # independently of this queue: if the two ever disagree, one of them is wrong, and that is
        # a real finding rather than a stale constant.
        prog = pinned.get("progress") or {}
        # 🔴 SUMMED OVER THE VOCABULARY, NOT OVER TWO NAMES I TYPED. This read
        # `defects_open + defects_proven`, which is the same hard-coding the file exists to
        # prevent, one level up: a non-terminal state added later would be counted by the queue
        # and not by this expectation, and the guard would fail with the queue in the right.
        want = sum(int(prog.get(f"defects_{s}", 0)) for s in gate.DEFECT_OPEN_STATES)
        # 🔴 "IS THAT TRUE?" — YES. Both derivations now say zero, which is the finished
        # state rather than a broken instrument, and the cross-derivation below is what
        # proves it: `expected` comes from the ledger, `want` from `progress`, and the queue
        # from `g.rows()`. Three independent readings agreeing on zero is a real assertion;
        # only a floor demanding work exist would fail here, and it would be wrong.
        if want == 0:
            assert not expected, (
                f"`progress` says no non-terminal defects but the ledger holds "
                f"{len(expected)}: {sorted(expected)[:5]}")
            assert not rows, (
                f"both derivations say zero but the queue holds {len(rows)} row(s)")
            return
        assert len(expected) == want, (
            f"the queue's non-terminal set is {len(expected)} but `progress` says {want} "
            "(defects_open + defects_proven) — the two derivations disagree")
        assert {r[4] for r in rows} == expected

    def test_a_terminal_row_is_NOT_queued(self, pinned):
        """The other half. A partition that put everything in OPEN would pass every test above."""
        rows, _ = g.rows()
        queued = {r[4] for r in rows}
        fixed = {k for k, v in (pinned["defects"] or {}).items()
                 if isinstance(v, dict) and v.get("state") == "fixed"}
        assert len(fixed) > 100, "the fixed population vanished — this assertion means nothing"
        assert not (queued & fixed), "a `fixed` row is being queued as work"


class TestAnUnknownStateRaises:
    def test_a_row_the_vocabulary_cannot_classify_is_not_absorbed(self, tmp_path, monkeypatch):
        led = json.loads(json.dumps(LEDGER))
        led["defects"]["D-A-STATE-NOBODY-DECLARED"] = {"state": "mostly-done"}
        p = tmp_path / "ledger.json"
        p.write_text(json.dumps(led), encoding="utf-8")
        monkeypatch.setattr(g, "LEDGER", p)
        with pytest.raises(ValueError, match="not one of"):
            g.rows()


class TestOneBadRowCannotBreakTheWholeQueue:
    """🔴 MEASURED 2026-08-31: the generator that ENDS THE RUN crashed outright.

    `rows()` builds a sort key containing `queue_group`, and `out.sort()` compares that element
    across every row. The convention is an int 1-4 (or absent); one row filed with
    `queue_group="composition"` made the comparison `str < int` and raised TypeError, so the
    queue — and `--check` with it — produced nothing at all.

    A malformed priority must cost THAT ROW its ordering, never everyone else's queue. The state
    field is different and is deliberately strict: an unrecognised STATE raises, because it means
    nobody can say whether the row is work. A bad priority has an obvious safe default.
    """

    def test_a_string_queue_group_does_not_crash_the_queue(self, tmp_path, monkeypatch):
        led = json.loads(json.dumps(LEDGER))
        # 🔴 TWO ROWS, AND THAT IS THE WHOLE POINT. Tuple comparison only reaches the
        # queue_group element when the earlier ones TIE, so a single injected row sorts by
        # (blocked, rank) and never compares the bad value — the first version of this test did
        # exactly that and stayed GREEN with the fix removed. These two are identical up to the
        # priority, so the comparison must reach it.
        for nm, qg in (("D-A-ROW-WITH-A-STRING-PRIORITY", "composition"),
                       ("D-A-ROW-WITH-AN-INT-PRIORITY", 2)):
            led["defects"][nm] = {
                "state": "open", "defect_class": "instrument", "queue_group": qg,
                "invariant": "a bad priority must not break the queue",
            }
        p = tmp_path / "ledger.json"
        p.write_text(json.dumps(led), encoding="utf-8")
        monkeypatch.setattr(g, "LEDGER", p)
        rows, _ = g.rows()          # must not raise
        assert "D-A-ROW-WITH-A-STRING-PRIORITY" in {r[4] for r in rows}

    def test_the_ledger_on_disk_uses_the_int_convention(self):
        bad = {k: v.get("queue_group") for k, v in (LEDGER["defects"] or {}).items()
               if v.get("queue_group") is not None and not isinstance(v.get("queue_group"), int)}
        assert not bad, f"queue_group must be an int 1-4 or absent: {bad}"
