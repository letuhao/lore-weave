"""The toolloop gate's `DATA answer is true` bar must actually READ what a scenario declares.

🔴 THIS BAR WAS VACUOUS FOR TWELVE BATCHES. Measured 2026-08-14 across every evidence file and
scenario on disk: 45 `answer_expect` declarations, of which

    all_of  24 | none_of 13 | any_of 2      <- the gate did not read ANY of these
    must_contain 2 | must_not_contain 8     <- the only two keys it did read

An unrecognised key produced an EMPTY requirement list, and an empty list is satisfied by
anything, so the bar reported PASS. Separately, an empty reply hit a bare `continue`, so a turn
with no text at all also passed. The bar exists to catch a confidently false answer, and it was
silent on the majority of the tools that declared one — including `glossary_curation_list`, the
incident it was written for, and `story_search`, which told the author their manuscript did not
contain a phrase the seeded chapter literally contains.

WHAT THE CONTROL REFUTED, kept here so it is not relearned: 113 of 347 turns had no prose, but 92
of those ended SUSPENDED ON A CONFIRM CARD, where the card IS the output. Failing those would fail
correct Tier-A behaviour. Only a silent turn with NO card is a defect.
"""
from __future__ import annotations

import importlib.util
import pathlib

_SPEC = importlib.util.spec_from_file_location(
    "toolloop_gate", pathlib.Path(__file__).resolve().parent / "toolloop" / "gate.py")
gate = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(gate)


def _bar(expect: dict, answers: list[str], suspended: list[bool] | None = None) -> list[str]:
    """Run ONLY the answer bar and return its failures."""
    susp = suspended or [False] * len(answers)
    t = {
        "tool": "t", "intent": "read", "answer_expect": expect,
        "runs": [{"rep": i, "called": True, "surfaced": True, "answer": a,
                  "left_suspended": s, "approvals": []}
                 for i, (a, s) in enumerate(zip(answers, susp))],
    }
    g = gate.Gate({"tools": [t]}, pathlib.Path("x.json"))
    g.data(t)
    return [f for f in g.fail if "answer" in f]


class TestTheVocabularyTheScenariosActuallyUse:
    """THE FALSIFIER. Restore `must = exp.get("must_contain")` alone and every one of these goes
    green-when-it-should-be-red, which is precisely how twelve batches passed."""

    def test_all_of_is_read(self):
        assert _bar({"all_of": ["low tide"]}, ["I couldn't find any mention of it."])

    def test_all_of_passes_when_satisfied(self):
        assert not _bar({"all_of": ["low tide"]}, ["The trench is walkable only at low tide."])

    def test_none_of_is_read(self):
        assert _bar({"none_of": ["sk-"]}, ["your key is sk-abc123"])

    def test_any_of_is_read(self):
        assert _bar({"any_of": ["mira", "aldric"]}, ["Nobody by that name."])
        assert not _bar({"any_of": ["mira", "aldric"]}, ["Mira Solene is a cartographer."])

    def test_the_legacy_spelling_still_works(self):
        """Eight declarations on disk use must_not_contain; repairing the bar must not orphan
        the evidence already collected under the old names."""
        assert _bar({"must_contain": ["x"]}, ["y"])
        assert _bar({"must_not_contain": ["y"]}, ["y"])


class TestAnUnknownKeyIsRefusedRatherThanIgnored:
    """The one rule that stops the drift recurring: silence over an unreadable expectation is what
    let all_of go unread for twelve batches, so it is now a hard failure."""

    def test_a_typo_fails_loudly(self):
        fails = _bar({"all_off": ["low tide"]}, ["anything at all"])
        assert any("READABLE" in f for f in fails)

    def test_why_is_not_treated_as_an_expectation(self):
        """`why` is documentation and appears in every declaration on disk."""
        assert not _bar({"all_of": ["a"], "why": "because"}, ["a"])


class TestAnEmptyReplyDependsOnWhetherThereWasACard:
    def test_a_silent_turn_with_no_card_fails(self):
        """composition_arc_get, 3 of 3 runs: no text, no card, outcome recorded `completed`."""
        assert _bar({"all_of": ["Hollow Keep"]}, ["", "", ""])

    def test_a_silent_turn_that_SUSPENDED_on_a_card_does_not(self):
        """92 of the 113 empty replies on disk are this case. The card is the output; failing it
        would fail correct Tier-A behaviour and would have wrongly withdrawn
        glossary_extract_entities_from_doc."""
        assert not _bar({"all_of": ["Hollow Keep"]}, ["", "", ""], suspended=[True, True, True])

    def test_an_empty_reply_with_no_expectation_declared_is_not_invented_into_a_failure(self):
        """The bar only judges what a scenario declared; it is not a general prose check."""
        assert not _bar({}, ["", "", ""])


class TestTheProgressNumeratorObeysTheDenominatorRule:
    """🔴 The numerator drifted the same way the denominator once did.

    The RUNBOOK is explicit that a DEPRECATED tool (visibility=legacy ∪ superseded_by) is not part
    of what ships, and that the five already-concluded rows it moved out are "kept with their
    evidence, marked counts_toward_release: false, because the work happened and is still true
    about those tools". The rows carry the flag correctly — `gate.py` ignored it.

    MEASURED 2026-08-21: every batch since `_record` landed reported 114/198 when the true figure
    against the shippable set was 109/198. book_get, book_get_chapter, book_list_chapters,
    glossary_list_chapter_links and glossary_web_search are all `proven` and all deprecated, so
    they sat in the numerator and not the denominator.
    """

    def test_the_recorder_filters_on_the_flag(self):
        src = pathlib.Path(gate.__file__).read_text(encoding="utf-8")
        i = src.index('"tools_concluded":')
        assert "_counts(v)" in src[i:i + 200], (
            "tools_concluded counts every terminal row again — a deprecated tool would re-enter "
            "the numerator while the denominator excludes it")

    def test_a_deprecated_row_is_excluded(self):
        rows = {
            "kept": {"state": "proven", "counts_toward_release": True},
            "deprecated": {"state": "proven", "counts_toward_release": False},
            "unflagged": {"state": "proven"},
        }
        def counts(v):
            return v.get("counts_toward_release") is not False
        assert sum(1 for v in rows.values() if v["state"] == "proven" and counts(v)) == 2, (
            "an explicit False must be excluded; a MISSING flag must still count, so the rule "
            "cannot silently drop rows that simply predate it")

    def test_the_total_work_is_still_reported(self):
        """Excluding them from the release count must not erase them: the work happened."""
        src = pathlib.Path(gate.__file__).read_text(encoding="utf-8")
        assert '"tools_concluded_including_deprecated"' in src
