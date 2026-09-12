"""T17 — the one prose defect prompting could not fix.

A 2026-09-06 human-sim run reviewed five chapters through a four-lens Workflow. Three of the four
recurring defects closed when the model was asked to fix them. The fourth — the
``không phải X, mà là Y`` antithesis and ``sự``-stacked abstract nouns — did not, across two <!-- doc-language-gate: ok -- the Vietnamese construction is the literal subject here -- it is the pattern this module detects, and naming it in English would not identify what it matches -->
independent, increasingly specific attempts, and the second attempt reproduced the exact flagged
construction *inside brand-new content written to remove it*.

The hard part of detecting it is NOT finding the words. ``sự`` is an ordinary high-frequency <!-- doc-language-gate: ok -- the Vietnamese construction is the literal subject here -- it is the pattern this module detects, and naming it in English would not identify what it matches -->
Vietnamese word and ``không phải … mà là`` is a sentence careful authors write on purpose, so a <!-- doc-language-gate: ok -- the Vietnamese construction is the literal subject here -- it is the pattern this module detects, and naming it in English would not identify what it matches -->
presence detector would flag all Vietnamese prose ever written and tell a reader nothing — NV-7,
"the check fires on EVERYTHING, so firing means nothing". What the run observed was a RATE. These
tests therefore pin both directions: it must fire on the habit, and stay silent on ordinary prose
that uses the same words.
"""
# doc-language-gate: ok -- the Vietnamese constructions ARE this module's subject: they are the literal patterns it detects, so paraphrasing them into English would destroy the specification and the tests. Scoped to this file.

from __future__ import annotations

from app.engine.prose_tics import COVERED_LANGUAGES, detect_prose_tics

# Ordinary Vietnamese narration, long enough to rate. Contains NEITHER construction.
_PLAIN = "Trời mưa rất to và gió thổi mạnh qua những mái nhà cũ kỹ trong đêm tối. " * 25

# The habit, at the density the run measured (the construction in every scene, several times each).
_ANTITHESIS = "Nàng không phải là một người bình thường, mà là một thứ khác hẳn. " * 4
_ABSTRACT = "sự hoàn mỹ của sự tồn tại và sự tĩnh lặng của sự vĩnh hằng. " * 4


class TestItFiresOnTheHabit:
    def test_the_antithesis_at_the_measured_density_is_reported(self):
        report = detect_prose_tics(_ANTITHESIS + _PLAIN, "vi")
        assert report.analysed
        rules = {f.rule for f in report.findings}
        assert "vi.antithesis_khong_phai_ma_la" in rules

    def test_stacked_abstract_nouns_are_reported(self):
        report = detect_prose_tics(_ABSTRACT + _PLAIN, "vi")
        rules = {f.rule for f in report.findings}
        assert "vi.abstract_noun_su_stacking" in rules

    def test_a_finding_carries_verbatim_examples_so_it_can_be_CHECKED(self):
        """A rate with no excerpt asks the reader to trust the regex. The examples are what make
        the judgement falsifiable by a human who disagrees with it."""
        report = detect_prose_tics(_ANTITHESIS + _PLAIN, "vi")
        finding = next(f for f in report.findings if f.rule.endswith("khong_phai_ma_la"))
        assert finding.examples, "a finding with no excerpt cannot be verified"
        assert any("không phải" in e for e in finding.examples)
        assert finding.count >= 4
        assert finding.per_1000 > finding.threshold_per_1000

    def test_the_report_states_the_threshold_it_judged_against(self):
        """So a reader can disagree with the JUDGEMENT, not just the count."""
        report = detect_prose_tics(_ABSTRACT + _PLAIN, "vi")
        for f in report.findings:
            assert f.threshold_per_1000 > 0
            assert f.per_1000 > f.threshold_per_1000


    def test_a_finding_can_say_WHERE_it_is(self):
        """The repo's finding-locator gate caught this class carrying a finding it could not
        place, and it was right: the detector already had every match position and discarded
        them, handing the reader a rate and telling them to go looking."""
        report = detect_prose_tics(_ANTITHESIS + _PLAIN, "vi")
        finding = next(f for f in report.findings if f.rule.endswith("khong_phai_ma_la"))
        start, end = finding.first_span
        assert end > start, "a finding with no span cannot be jumped to"
        assert finding.locator.placed, "the locator reports UNLOCATED for a match it did find"
        # The span must actually point AT the construction, not merely be non-zero.
        assert "không phải" in (_ANTITHESIS + _PLAIN)[start:end]


class TestItStaysSilentOnOrdinaryProse:
    """NV-7 — the half that makes the other half mean anything."""

    def test_plain_narration_produces_no_findings(self):
        report = detect_prose_tics(_PLAIN, "vi")
        assert report.analysed
        assert report.findings == (), f"ordinary prose was flagged: {report.as_dict()}"

    def test_occasional_deliberate_use_is_NOT_flagged(self):
        """An author using the antithesis once in a long passage is writing, not ticcing. If this
        fired, the detector would punish good prose and be correctly ignored."""
        once = "Nàng không phải là kẻ yếu, mà là người đã chọn im lặng. " + _PLAIN
        report = detect_prose_tics(once, "vi")
        assert all(not f.rule.endswith("khong_phai_ma_la") for f in report.findings)

    def test_a_few_abstract_nouns_are_NOT_flagged(self):
        """`sự` is an ordinary word. Flagging its presence would flag the whole language."""
        some = "Nàng cảm nhận sự tĩnh lặng của căn phòng. " + _PLAIN
        report = detect_prose_tics(some, "vi")
        assert all(not f.rule.endswith("su_stacking") for f in report.findings)


class TestItNeverClaimsCoverageItLacks:
    def test_an_uncovered_language_says_so_rather_than_reporting_clean(self):
        """The silent-empty-result defect this whole remediation exists to close: a caller must be
        able to tell "no tics found" from "this language was never examined"."""
        report = detect_prose_tics("The rain fell hard against the old roofs all night. " * 25, "en")
        assert report.analysed is False
        assert report.findings == ()
        assert report.reason and "no tic rules" in report.reason
        assert "vi" in report.reason, "the reason should say what IS covered"

    def test_a_passage_too_short_to_rate_says_so(self):
        """One occurrence in 40 words is 25 per 1000 — a rate over a handful of words is noise,
        and reporting it as a finding would be a manufactured result."""
        report = detect_prose_tics("Nàng không phải là người thường, mà là thứ khác.", "vi")
        assert report.analysed is False
        assert "too short" in (report.reason or "")

    def test_the_covered_set_is_declared_and_non_empty(self):
        assert "vi" in COVERED_LANGUAGES
        assert "en" not in COVERED_LANGUAGES, "English has no rule set; do not imply one"

    def test_a_missing_language_is_treated_as_uncovered_not_as_vietnamese(self):
        report = detect_prose_tics(_ANTITHESIS + _PLAIN, None)
        assert report.analysed is False


class TestNormalisation:
    def test_decomposed_vietnamese_still_matches(self):
        """Vietnamese is stored in either normalisation form. A detector that only matched the
        composed form would silently miss half its corpus — and report it as clean."""
        import unicodedata
        decomposed = unicodedata.normalize("NFD", _ABSTRACT + _PLAIN)
        report = detect_prose_tics(decomposed, "vi")
        assert any(f.rule.endswith("su_stacking") for f in report.findings)

# doc-language-gate: end
