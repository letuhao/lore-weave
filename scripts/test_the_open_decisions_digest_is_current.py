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

    def test_the_digest_names_EVERY_open_question_and_no_others(self):
        """🔴 RE-POINTED AT THE RULE, 2026-09-01, after the absolute floor went red for the RIGHT
        reason. It asserted `>= 10` sections, and the owner ruled on TWELVE questions in one
        round: the open set legitimately fell to four, so the floor started reporting healthy
        progress as a broken generator.

        A number that only holds while the backlog is large is not the invariant. The invariant
        is that the digest and the ledger agree — which stays sharp at four open questions and
        at forty, and still goes red if the generator emits nothing."""
        import json

        body = _norm(DIGEST.read_text(encoding="utf-8"))
        assert "## All open questions" in body
        ledger = json.loads(
            (pathlib.Path(__file__).resolve().parents[1]
             / "contracts" / "tool-deep-dive-ledger.json").read_text(encoding="utf-8"))
        # 🔴 THE SHIPPED PREDICATE, NOT A COPY OF IT. `state == "open"` is NOT what "waiting on
        # the owner" means here: a ruling arrives in an `answer_*` field and flipping `state` is
        # separate bookkeeping nobody is obliged to do, so a question can be state-open and
        # already answered. Re-implementing that rule made this guard demand DQ-T53 — which is
        # answered — and a guard that copies the logic it checks cannot fail when that logic
        # changes.
        import scripts.toolloop.goal_prompt_all_defects as _g

        open_qs = _g._open_dq_names(ledger)
        listed = {ln.split("###", 1)[1].split("—")[0].strip()
                  for ln in body.splitlines() if ln.startswith("### DQ-T")}
        # 🔴 AND NOW THERE ARE NONE — 64 answered, 4 withdrawn, 0 open. The vacuity
        # worry was right and the floor was the wrong instrument for it: an empty digest
        # would indeed satisfy `listed == open_qs` for free, but demanding that questions
        # stay open turns the owner finishing the queue into a red test. So keep the
        # anti-vacuity and make it CROSS-DERIVED: the generator says nothing is open, and
        # the raw ledger states must independently agree. If they ever disagree, one of the
        # two is wrong and that is a real finding rather than an empty pass.
        if not open_qs:
            qs = ledger.get("deferred_questions") or {}
            assert qs, "the ledger holds no questions at all — this read the wrong file"
            unfinished = sorted(q for q, v in qs.items()
                                if v.get("state") not in ("answered", "withdrawn"))
            assert not unfinished, (
                f"the generator reports NO open questions while {len(unfinished)} are "
                f"neither answered nor withdrawn: {unfinished[:5]} — the predicate and the "
                "ledger disagree")
            assert not listed, (
                f"the digest still names {sorted(listed)[:5]} as open while the ledger has "
                "none — the digest is stale, which is the whole point of this guard")
            return
        assert listed == open_qs, (
            f"the digest and the ledger disagree. Only in the digest: {sorted(listed - open_qs)}; "
            f"only in the ledger: {sorted(open_qs - listed)}")

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
