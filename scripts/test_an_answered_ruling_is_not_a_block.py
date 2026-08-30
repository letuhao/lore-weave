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
        dqs = LEDGER["deferred_questions"]
        for name in ("DQ-T44", "DQ-T53", "DQ-T58", "DQ-T64"):
            q = dqs[name]
            assert G._has_ruling(q), f"{name} carries an answer_* field and is not seen as ruled"
            assert name not in G._open_dq_names(LEDGER), f"{name} still blocks its rows"

    def test_questions_with_no_ruling_are_still_blocking(self):
        dqs = LEDGER["deferred_questions"]
        unruled = [k for k, v in dqs.items()
                   if isinstance(v, dict) and v.get("state") == "open" and not G._has_ruling(v)]
        assert len(unruled) >= 10, (
            f"only {len(unruled)} open questions are unruled — if this collapses, the release rule "
            "has widened past answered rulings and is freeing rows nobody decided")
        assert set(unruled) <= G._open_dq_names(LEDGER)
