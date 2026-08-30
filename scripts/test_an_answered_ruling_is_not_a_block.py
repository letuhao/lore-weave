"""D-THE-QUEUE-CALLED-AN-ANSWERED-RULING-A-BLOCK.

    THE INVARIANT. A deferred question that carries the owner's ruling does not block anything.
    The ruling is the answer; flipping a status word is bookkeeping.

🔴 MEASURED 2026-08-30, and it cost the loop a full stop. `_open_dq_names` treated every DQ with
`state == "open"` as waiting on the owner. Four rulings — DQ-T44, DQ-T53, DQ-T58, DQ-T64 — had
their answers written into `answer_2026_08_28` while `state` still read `open`, because writing a
ruling and updating a status word are two separate acts and nobody is obliged to do the second.

So every row those four block read as DQ-blocked, and the generator printed:

    NEXT. No unblocked work. Every open row waits on a decision above; take those first.

while SEVEN rows had a ruling sitting ready to build. Working those four produced a shipped
glossary recycle-bin filter (restore went 0-of-5 to 5-of-5 called), an arc refusal that names
chapters, and two rulings returned corrected with the measurements that refuted their premises.

A queue that reports NO WORK while work exists is worse than a queue that is merely wrong: a
wrong one gets argued with, an empty one gets believed and nobody looks again.
"""
from __future__ import annotations

import importlib.util
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
LEDGER = json.loads((ROOT / "contracts" / "tool-deep-dive-ledger.json").read_text(encoding="utf-8"))


def _gen():
    spec = importlib.util.spec_from_file_location(
        "goalgen", ROOT / "scripts" / "toolloop" / "goal_prompt_all_defects.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


G = _gen()


class TestARulingReleasesItsRows:
    def test_an_answered_dq_does_not_block_even_while_state_is_open(self):
        led = {"deferred_questions": {
            "DQ-X": {"state": "open", "question": "?", "answer_2026_08_28": "OWNER: do the thing"},
        }}
        assert G._open_dq_names(led) == set(), (
            "a question with the owner's ruling written on it is still counted as blocking — "
            "which is exactly how four rulings went unbuilt")

    def test_an_UNANSWERED_open_dq_still_blocks(self):
        """🔴 THE HALF THAT MUST NOT BE TRADED. If this stopped holding, every genuinely open
        question would be treated as work and the loop would build mechanisms nobody ruled on."""
        led = {"deferred_questions": {"DQ-Y": {"state": "open", "question": "?"}}}
        assert G._open_dq_names(led) == {"DQ-Y"}

    def test_a_recommendation_is_NOT_a_ruling(self):
        """Every DQ this loop files carries `my_recommendation`. Mistaking one for an answer would
        release every row on the loop's own opinion — the precise thing the standing rule forbids
        ('never decide or close one yourself to unblock a defect')."""
        led = {"deferred_questions": {
            "DQ-Z": {"state": "open", "question": "?", "my_recommendation": "I would do X"},
        }}
        assert G._open_dq_names(led) == {"DQ-Z"}

    def test_a_closed_dq_is_still_not_blocking(self):
        led = {"deferred_questions": {"DQ-W": {"state": "answered", "question": "?"}}}
        assert G._open_dq_names(led) == set()


class TestItMatchesTheREALLedger:
    """ANTI-VACUITY. The synthetic cases above would pass against a ledger where no ruling exists;
    these read the file the queue is actually derived from."""

    def test_the_four_rulings_are_recognised(self):
        """All four CARRY a ruling — that is what `_has_ruling` answers, and it is why they were
        invisible as work. Whether a ruling still RELEASES its rows is a separate question, and
        three of these were later sent back corrected; see TestARulingSENTBACKIsAQuestionAgain."""
        dqs = LEDGER["deferred_questions"]
        for name in ("DQ-T44", "DQ-T53", "DQ-T58", "DQ-T64"):
            assert G._has_ruling(dqs[name]), (
                f"{name} carries an answer_* field and is not seen as ruled")
        assert "DQ-T53" not in G._open_dq_names(LEDGER), (
            "DQ-T53's ruling was carried out and carries no correction, so it must not block")

    def test_questions_with_no_ruling_are_still_blocking(self):
        dqs = LEDGER["deferred_questions"]
        unruled = [k for k, v in dqs.items()
                   if isinstance(v, dict) and v.get("state") == "open" and not G._has_ruling(v)]
        assert len(unruled) >= 10, (
            f"only {len(unruled)} open questions are unruled — if this collapses, the release rule "
            "has widened past answered rulings and is freeing rows nobody decided")
        assert set(unruled) <= G._open_dq_names(LEDGER)

class TestARulingSENTBACKIsAQuestionAgain:
    """🔴 THE OTHER DIRECTION, and it bit within the hour of the first fix shipping.

    The standing rule is "if it cannot be built, the question goes BACK CORRECTED with the
    measurement showing why". Three rulings were returned that way on 2026-08-30 — DQ-T44 (three
    of its five families are not live surfaces), DQ-T58 (its premise was refuted by the
    before-measurement), DQ-T64 (its own equivalence condition failed). Releasing rows on those
    would park a row at the head of the queue as WORK whose only completion is building the thing
    the measurement just showed must not be built.
    """

    def test_a_returned_ruling_blocks_again(self):
        led = {"deferred_questions": {"DQ-R": {
            "state": "open", "question": "?", "answer_2026_08_28": "OWNER: do X",
            "returned_corrected": "2026-08-30 — X cannot be built, here is the measurement",
        }}}
        assert G._open_dq_names(led) == {"DQ-R"}

    def test_the_three_returned_rulings_block_in_the_REAL_ledger(self):
        for name in ("DQ-T44", "DQ-T58", "DQ-T64"):
            q = LEDGER["deferred_questions"][name]
            assert "returned_corrected" in q, f"{name} lost its correction marker"
            assert name in G._open_dq_names(LEDGER), f"{name} is releasing rows despite a correction"

    def test_a_ruling_that_was_ACTED_ON_still_releases(self):
        """ANTI-OVERREACH. DQ-T53's ruling was carried out — the owner re-enabled logging and the
        re-run was executed — so it carries no correction and must NOT block. If every answered
        question started blocking, the first fix would be undone."""
        assert "returned_corrected" not in LEDGER["deferred_questions"]["DQ-T53"]
        assert "DQ-T53" not in G._open_dq_names(LEDGER)

