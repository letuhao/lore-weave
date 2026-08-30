"""The generated decision digest must match the ledger it claims to derive from.

    THE INVARIANT. `docs/sessions/OPEN_DECISIONS.md` is byte-identical to what
    `scripts/toolloop/dq_digest.py` produces from the ledger right now.

🔴 THIS GUARD EXISTS BECAUSE THE DIGEST'S OWN DOCSTRING NAMES THE FAILURE IT PREVENTS: "a
hand-written digest is stale the first time a question is answered, and a stale one is worse than
none because it gets believed." A GENERATED digest has exactly the same failure mode one step
later — it is generated once, committed, and then the ledger moves. Nothing about being machine-
produced keeps a file current; only regenerating it does.

The cost of drift here is not cosmetic. The digest is what the owner reads to decide 32 open
questions, and it is ranked by how many defects each ruling releases. A stale copy would show
rulings as outstanding after they were made, hide questions filed since, and — worst — carry the
pre-correction numbers for questions whose premises this loop measured and returned corrected.
DQ-T71's own question text still quotes "1.57%" against a re-derived 1.73%, and its second
direction is 2.5x larger than the question claims rather than smaller. A digest that lags is a
digest that hands those figures back as current.

THE SAME RULE THE `/goal-prompt` SKILL ENFORCES ON THE QUEUE IT EMITS, and for the same reason:
derived state has ONE home, and the fix for wrong output belongs in the generator, never in the
generated file. This test is what makes "do not hand-edit; re-run it" enforceable rather than a
request in a header comment.
"""
from __future__ import annotations

import importlib.util
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
DIGEST = ROOT / "docs" / "sessions" / "OPEN_DECISIONS.md"
GENERATOR = ROOT / "scripts" / "toolloop" / "dq_digest.py"


def _gen():
    spec = importlib.util.spec_from_file_location("dq_digest", GENERATOR)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _norm(s: str) -> str:
    """Compare CONTENT, not line endings. Repo files are CRLF and the generator writes LF; a
    guard that failed on that would be red for a reason nobody could act on."""
    return s.replace("\r\n", "\n")


class TestTheDigestIsNotStale:
    def test_the_committed_file_matches_what_the_generator_produces_now(self):
        assert DIGEST.exists(), (
            f"{DIGEST.relative_to(ROOT)} is missing — the owner has nothing to rule from")
        want = _norm(_gen().build())
        have = _norm(DIGEST.read_text(encoding="utf-8"))
        # The generated header carries today's date, so a digest regenerated on a later day
        # differs by that line alone. Compare everything else: a date-only difference means
        # current content, and is not what this guard is for.
        want_body = [ln for ln in want.splitlines() if not ln.startswith("*Generated ")]
        have_body = [ln for ln in have.splitlines() if not ln.startswith("*Generated ")]
        assert have_body == want_body, (
            "OPEN_DECISIONS.md no longer matches the ledger. Re-run:\n"
            "    python scripts/toolloop/dq_digest.py --out docs/sessions/OPEN_DECISIONS.md\n"
            "Do NOT hand-edit the file — the fix belongs in the generator or in the ledger.")

    def test_every_open_question_carries_a_recommendation(self):
        """🔴 THE STANDING RULE, made enforceable. 'Every open DQ gets a RECOMMENDATION from you
        and is DECIDED BY THE OWNER.' Without a guard this is satisfied by habit, and habit is
        what fails on the busiest day. A question reaching the owner with no recommendation
        forces them to do the loop's homework before they can rule."""
        g = _gen()
        import json
        led = json.loads((ROOT / "contracts" / "tool-deep-dive-ledger.json").read_text(
            encoding="utf-8"))
        dqs = led["deferred_questions"]
        missing = sorted(n for n in g._gen()._open_dq_names(led)
                         if not any("recommend" in str(k).lower() for k in dqs[n]))
        assert not missing, (
            f"{len(missing)} open question(s) reach the owner with no recommendation: {missing}")


class TestTheGuardCanActuallyFail:
    """🔴 ANTI-VACUITY. Both assertions above pass trivially against an empty or absent ledger,
    and a guard that cannot go red is decoration."""

    def test_the_digest_is_not_empty_and_names_real_questions(self):
        body = _norm(DIGEST.read_text(encoding="utf-8"))
        assert "## All open questions" in body
        assert body.count("### DQ-T") >= 10, (
            "the digest lists almost no questions — either the generator broke or the open set "
            "collapsed; both deserve a look rather than a green tick")

    def test_a_changed_digest_is_detected(self, tmp_path):
        """Prove the comparison bites: perturb the content and the same check must reject it."""
        want = _norm(_gen().build())
        tampered = want.replace("releases", "frees", 1)
        if tampered == want:  # nothing to perturb — the guard would be vacuous, say so
            pytest.skip("no 'releases' token to perturb; comparison unproven on this content")
        want_body = [ln for ln in want.splitlines() if not ln.startswith("*Generated ")]
        tampered_body = [ln for ln in tampered.splitlines() if not ln.startswith("*Generated ")]
        assert tampered_body != want_body, (
            "a byte-level change did not register — the comparison in the test above is inert")
