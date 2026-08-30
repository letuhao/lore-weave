"""A selection rate must be measured over turns where a selection was possible.

    THE INVARIANT. `selection_rate.derive()` answers "how often does the model PICK this tool".
    A bare confirmation — "Yes, go ahead and do it." — makes no request, so its zero says nothing
    about preference. Counting it as a non-selection measures the turn, not the model.

🔴 MEASURED 2026-08-30, AFTER IT MOVED A TOOL ACROSS THE VERDICT BAR.

    composition_arc_apply   20/20 on its single-turn arm
                             0/17 on confirmation arms   ("Yes, go ahead and do it.", every one)
                             0/5  on a genuine arm that asked and was not answered
        pooled                20/47 = 0.426   BELOW the DQ-T51 bar of 0.4507
        choice-offering only  20/25 = 0.800   comfortably above it

Nothing about the tool changed. The rate GATES VERDICTS — below the bar a zero is excused as a
lost draw, at or above it a zero is evidence about the tool — so the dilution silently rewrote
what `proven` means for it. `selection_rate`'s own `_history` note records this same shape from a
different cause: "a tool moving across the bar with no behaviour having changed".

THE RULE NEEDS BOTH HALVES, AND EACH ALONE IS MEASURABLY WRONG — the two anti-vacuity tests below
pin exactly that, because a fix that kept only one half would still pass a naive version of this
file.
"""
from __future__ import annotations

import json
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "toolloop"))
sys.path.insert(0, str(ROOT / "services" / "chat-service"))

try:
    import selection_rate as sr
except Exception as e:  # pragma: no cover
    pytest.skip(f"selection_rate not importable: {e}", allow_module_level=True)

BASELINE = ROOT / "contracts" / "unreachable-scenario-turns-baseline.json"
CONFIRM = "Yes, go ahead and do it."


@pytest.fixture(scope="module")
def derived():
    return sr.derive()


class TestTheDilutedRateIsGone:
    def test_arc_apply_is_measured_over_turns_that_asked_for_it(self, derived):
        r = derived["rates"].get("composition_arc_apply")
        assert r, "composition_arc_apply left the census entirely"
        assert r["runs"] == 25, (
            f"the denominator is {r['runs']}, not 25 — confirmation turns are back in it "
            "(47 = 25 real attempts + 22 turns that could not have called anything)")
        assert r["rate"] >= sr.LOTTERY_BELOW, (
            f"rate {r['rate']} is below the {sr.LOTTERY_BELOW:.4f} bar again — a tool with a "
            "20/20 arm is being classified by turns that offered no choice")

    def test_the_exclusion_actually_happened(self, derived):
        assert derived["choiceless_runs_excluded"] >= 100, (
            f"only {derived['choiceless_runs_excluded']} runs excluded — the rule is not firing")

    def test_no_POSITIVE_observation_was_dropped(self, derived):
        """🔴 THE HALF THAT MUST NOT BE TRADED. Excluding turns is only honest if none of them
        was a run where the tool WAS called; otherwise this inflates every rate it touches."""
        from fe_runner import called_names  # noqa: PLC0415
        want = derived["_want"]
        choiceless = sr._choiceless_ids()
        dropped_positives = []
        for f in sorted((ROOT / "docs" / "eval" / "toolloop").rglob("*-raw.json")):
            try:
                d = json.loads(f.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                continue
            if not isinstance(d, list):
                continue
            for run in d:
                if not isinstance(run, dict) or run.get("error"):
                    continue
                tool = want.get(run.get("scenario"))
                if tool and sr._offered_no_choice(run, choiceless) \
                        and tool in (called_names(run) or []):
                    dropped_positives.append((run.get("scenario"), tool))
        assert not dropped_positives, (
            "a run where the tool WAS called is being excluded — the rate is being biased "
            f"upward: {dropped_positives[:5]}")


class TestNeitherHalfOfTheRuleIsEnoughAlone:
    """ANTI-VACUITY. Both were tried; both are refuted by the corpus."""

    def test_the_declaration_alone_would_delete_a_REAL_non_selection(self):
        """The id `composition-arc-apply` is declared choiceless for its p4-confirm arm, but the
        SAME id also has a genuine 'Apply arc template …' arm. Ids are reused across files."""
        assert "composition-arc-apply" in sr._choiceless_ids()
        genuine = {"scenario": "composition-arc-apply",
                   "prompt": "Apply arc template — use one of my library arc templates on "
                             "this book."}
        assert not sr._offered_no_choice(genuine, sr._choiceless_ids()), (
            "a real request is being dropped because another scenario reuses its id")

    def test_the_empty_surface_alone_would_delete_five_POSITIVES(self):
        """An empty `answerable_tools` does not prove the tool was absent — the baseline already
        records this scenario as a measured FALSE POSITIVE of that gate, and the tool is called
        5 of 5 on it."""
        doc = json.loads(BASELINE.read_text(encoding="utf-8"))
        over = doc.get("overridden_by_live_evidence") or {}
        assert any("extract-cannot-be-handed" in k for k in over), (
            "the override that makes this test meaningful has left the baseline")
        run = {"scenario": "extract-cannot-be-handed-a-model-authored-document",
               "prompt": "Here are my notes: Aldric Vane is a warden of Hollow Keep, and Mira "
                         "Solene runs the archive there. Add everything in here to my glossary."}
        assert not sr._offered_no_choice(run, sr._choiceless_ids()), (
            "a scenario whose tool IS called 5/5 is being excluded on an empty-surface signal")


class TestTheBarItselfIsUntouched:
    def test_the_bar_is_still_derived_from_power_not_from_the_data(self):
        assert sr.LOTTERY_BELOW == pytest.approx(1.0 - 0.05 ** (1 / 5))
        assert sr.LOTTERY_BELOW == pytest.approx(0.4507, abs=5e-5)

    def test_the_crossings_are_UPWARD_so_no_verdict_got_easier(self, derived):
        """Crossing upward makes a zero EVIDENCE rather than an excused lost draw. A downward
        crossing would retire a row by side effect, which is what DQ-T51 warned against."""
        assert derived["lottery_count"] <= 20, (
            f"{derived['lottery_count']} tools in the lottery band — the exclusion is adding "
            "tools to it, which means something crossed DOWNWARD")
