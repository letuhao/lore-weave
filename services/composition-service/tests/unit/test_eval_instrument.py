"""Teeth for the seeded-defect instrument (spec §S10).

The instrument's own failure mode is the one it was built to fix: a suite that reports a
clean green while measuring nothing. `eval_a2_canon.py` gates on the detector FIRING across
five scenarios of one class, with no control — a result produced identically by a working
canon loop and by an engine that revises every scene unconditionally.

So these tests attack the scorer and the gate, not the engine.
"""
from __future__ import annotations

import pytest

from app.eval.defects import DEFECTS, MIN_CLASSES, DefectClass, Observation, Outcome
from app.eval.gate import main as gate_main
from app.eval.suite import missing_fields, observe, score_class, score_suite

#: A SCORABLE class — a blind one would score ERROR and make every assertion below vacuous.
_CANON = next(d for d in DEFECTS if not d.blocked_on)
_FIRES = Observation(fields={"status": "checked", "iterations": 1})
_QUIET = Observation(fields={"status": "checked", "iterations": 0})


# ── the property the old harness could not express ────────────────────────────────────────

def test_a_detector_that_also_fires_on_the_clean_control_is_not_detection():
    """THE test. `eval_a2_canon.py` would report this as 5/5 PASS."""
    r = score_class(_CANON, seeded=_FIRES, control=_FIRES)
    assert not r.detected
    assert r.over_flagged
    assert "OVER-FLAGS" in r.verdict()


def test_fired_on_the_defect_and_quiet_on_the_control_is_detection():
    r = score_class(_CANON, seeded=_FIRES, control=_QUIET)
    assert r.detected and r.verdict() == "detected"


def test_quiet_everywhere_is_a_miss_not_a_pass():
    r = score_class(_CANON, seeded=_QUIET, control=_QUIET)
    assert not r.detected and r.missed and "MISSED" in r.verdict()


def test_an_inverted_detector_is_named_as_such():
    """Quiet on the defect, loud on the clean run — the worst case, and one that a
    fires-count would score as 0/1 without saying why."""
    r = score_class(_CANON, seeded=_QUIET, control=_FIRES)
    assert "INVERTED" in r.verdict()


# ── an outage must never read as a clean engine ───────────────────────────────────────────

def test_a_failed_run_is_its_own_outcome():
    """Folding ERROR into QUIET scores an outage as a detector that correctly stayed silent —
    a MISS on the seeded run, a PASS on the control. Either number is fiction."""
    assert observe(_CANON, Observation(failed=True)) is Outcome.ERROR
    r = score_class(_CANON, seeded=Observation(failed=True), control=_QUIET)
    assert r.errored and not r.detected and "ERROR" in r.verdict()


def test_an_errored_variant_contributes_no_confusion_pair():
    """Scoring it either way invents a data point in the 2x2 the report is built on."""
    clean = score_suite([(_CANON, _FIRES, _QUIET)]).confusion
    assert clean.n == 2
    errored = score_suite([(_CANON, Observation(failed=True), _QUIET)]).confusion
    assert errored.n == 1, "the failed run leaked into the confusion matrix"


def test_over_flagging_is_visible_as_a_number_not_just_a_verdict():
    """`fp` is the count the old harness had no way to produce."""
    cm = score_suite([(_CANON, _FIRES, _FIRES)]).confusion
    assert cm.tp == 1 and cm.fp == 1
    assert "over-flagged 1" in score_suite([(_CANON, _FIRES, _FIRES)]).summary()


# ── the registry must stay able to measure ────────────────────────────────────────────────

def test_the_registry_carries_enough_classes_to_catch_a_new_regression():
    assert len(DEFECTS) >= MIN_CLASSES


@pytest.mark.parametrize("d", DEFECTS, ids=lambda d: d.code)
def test_every_class_has_a_distinct_control_and_a_provenance(d: DefectClass):
    assert d.control.strip(), "a seeded hit alone cannot prove the detector is specific"
    assert d.control.strip() != d.seeded.strip()
    assert d.provenance.strip(), "an invented defect drifts from the engine and rots"


@pytest.mark.parametrize("d", DEFECTS, ids=lambda d: d.code)
def test_no_detector_is_a_constant(d: DefectClass):
    """A detector reading fields that no longer exist degrades to a constant, which is
    invisible in the source and reports a clean green forever."""
    empty = Observation(fields={})
    saturated = Observation(fields={
        "status": "checked", "iterations": 9, "scenes_covered": 9,
        "target_words": 900, "actual_words": 1, "finish_reason": "length",
        "unresolved_refs": 3,
    })
    assert d.detector(empty) != d.detector(saturated)


def test_no_two_classes_share_a_detector():
    ids = [id(d.detector) for d in DEFECTS]
    assert len(set(ids)) == len(ids), "two classes sharing a detector inflate the class count"


# ── the gate itself ───────────────────────────────────────────────────────────────────────

def test_the_gate_passes_on_the_real_registry(capsys):
    assert gate_main() == 0
    assert "PASS" in capsys.readouterr().out


def test_the_gate_reds_when_the_registry_is_degenerate(monkeypatch, capsys):
    """Injected rather than asserted: a gate whose red path is never exercised is the same
    unproven claim it exists to reject."""
    import app.eval.gate as gate

    monkeypatch.setattr(gate, "DEFECTS", DEFECTS[:1])
    assert gate.main() == 1
    assert "MIN_CLASSES" in capsys.readouterr().out


def test_the_gate_reds_on_a_class_with_no_control(monkeypatch, capsys):
    import app.eval.gate as gate
    from dataclasses import replace

    monkeypatch.setattr(gate, "DEFECTS",
                        tuple([replace(DEFECTS[0], control="")] + list(DEFECTS[1:])))
    assert gate.main() == 1
    assert "no control" in capsys.readouterr().out


def test_the_gate_reds_on_a_constant_detector(monkeypatch, capsys):
    import app.eval.gate as gate
    from dataclasses import replace

    monkeypatch.setattr(gate, "DEFECTS",
                        tuple([replace(DEFECTS[0], detector=lambda o: True)] + list(DEFECTS[1:])))
    assert gate.main() == 1
    assert "reads nothing that varies" in capsys.readouterr().out


# ── blindness: an instrument that cannot see must not report an engine defect ──────────────

def test_a_blind_class_is_never_scored_as_a_miss():
    """The finding this section exists for. Three of the five classes read fields with ZERO
    occurrences in the service, so their detectors are permanently quiet — and quiet on a
    seeded defect scores MISSED, which reads as "the engine has this defect" when the truth
    is "the instrument cannot see it". A false negative dressed as a finding."""
    blind = next(d for d in DEFECTS if d.blocked_on)
    r = score_class(blind, seeded=_FIRES, control=_QUIET)
    assert not r.detected and not r.missed
    assert "BLIND" in r.verdict() and blind.blocked_on in r.verdict()


def test_a_blind_class_contributes_no_confusion_pair():
    blind = next(d for d in DEFECTS if d.blocked_on)
    assert score_suite([(blind, _FIRES, _QUIET)]).confusion.n == 0


def test_the_summary_denominator_is_scorable_classes_and_names_the_blind_ones():
    """Dividing by every registered class would let adding a blind class quietly lower the
    score; hiding them entirely would let it quietly raise it. Both bury the blindness."""
    runs = [(d, _FIRES, _QUIET) for d in DEFECTS]
    s = score_suite(runs).summary()
    scorable = len([d for d in DEFECTS if not d.blocked_on])
    assert f"/{scorable} scorable" in s
    assert "BLIND" in s


def test_an_observation_missing_a_declared_read_is_an_error_not_a_quiet_detector():
    """`Observation.fields` is a freeform dict, so a key typo would otherwise be a silent
    QUIET — scoring as "the engine did not have this defect"."""
    scorable = next(d for d in DEFECTS if not d.blocked_on)
    assert observe(scorable, Observation(fields={})) is Outcome.ERROR
    assert missing_fields(scorable, Observation(fields={})) == list(scorable.reads)


# ── the gate must catch a NEW silently-blind class ────────────────────────────────────────

def test_the_gate_reds_on_a_class_that_reads_a_field_the_engine_never_emits(monkeypatch, capsys):
    import app.eval.gate as gate
    from dataclasses import replace

    ghost = replace(DEFECTS[0], code="ghost", reads=("no_such_field_anywhere",), blocked_on="")
    monkeypatch.setattr(gate, "DEFECTS", tuple(list(DEFECTS) + [ghost]))
    assert gate.main() == 1
    assert "permanently quiet" in capsys.readouterr().out


def test_the_gate_reds_on_a_stale_block(monkeypatch, capsys):
    """When the engine starts emitting the field, the block must be lifted — otherwise a
    scorable class stays excluded forever."""
    import app.eval.gate as gate
    from dataclasses import replace

    stale = replace(DEFECTS[0], code="stale", blocked_on="claims the engine cannot emit this")
    monkeypatch.setattr(gate, "DEFECTS", tuple(list(DEFECTS) + [stale]))
    assert gate.main() == 1
    assert "lift the block" in capsys.readouterr().out


def test_the_gate_reds_when_too_few_classes_are_scorable(monkeypatch, capsys):
    import app.eval.gate as gate
    from dataclasses import replace

    all_blind = tuple(replace(d, blocked_on=d.blocked_on or "blinded for the test") for d in DEFECTS)
    monkeypatch.setattr(gate, "DEFECTS", all_blind)
    assert gate.main() == 1
    assert "SCORABLE" in capsys.readouterr().out


# ── realised_words: the metric must not manufacture a finding ─────────────────────────────

def test_a_space_separated_draft_counts_by_whitespace():
    from app.engine.cowrite import realised_words

    phrase = "Nàng bước qua cổng đông lúc rạng đông"
    n, method = realised_words(phrase, "vi")
    assert n == len(phrase.split()) == 8 and method == "whitespace"


def test_a_spaceless_draft_is_estimated_and_says_so():
    """`.split()` on Chinese returns 1 for a whole paragraph. A shortfall detector fed that
    would report every CJK scene as ~99% short — a finding invented by the metric."""
    from app.engine.cowrite import realised_words

    zh = "她在黎明時分穿過東門，向守軍下達命令。"
    naive = len(zh.split())
    n, method = realised_words(zh, "zh")
    assert naive == 1, "the trap this guards against"
    assert n > 5 and method == "zh_chars_estimate"


def test_a_language_declared_spaceless_but_written_in_ascii_trusts_the_text():
    """A book tagged `zh` whose draft came back in English must not be counted as 0 words."""
    from app.engine.cowrite import realised_words

    n, method = realised_words("she crossed the gate at dawn", "zh")
    assert n == 6 and method == "whitespace"


def test_an_empty_draft_is_zero_not_an_estimate():
    from app.engine.cowrite import realised_words

    assert realised_words("", "vi") == (0, "empty")
    assert realised_words("   ", "zh") == (0, "empty")


def test_the_length_detector_fires_on_the_measured_mi_de_shortfall():
    """The bug this whole cycle started from: 900 asked, 445 delivered."""
    cls = next(d for d in DEFECTS if d.code == "length_directive_ignored")
    short = Observation(fields={"target_words": 900, "actual_words": 445,
                                "word_count_method": "whitespace"})
    ok = Observation(fields={"target_words": 900, "actual_words": 880,
                             "word_count_method": "whitespace"})
    assert cls.detector(short) and not cls.detector(ok)
    assert score_class(cls, seeded=short, control=ok).detected


def test_the_length_detector_stays_quiet_on_an_estimated_count():
    """Better to score nothing than to score a fiction — an estimate cannot support a 0.75
    threshold against a target whose own referent is ambiguous."""
    cls = next(d for d in DEFECTS if d.code == "length_directive_ignored")
    est = Observation(fields={"target_words": 900, "actual_words": 100,
                              "word_count_method": "zh_chars_estimate"})
    assert not cls.detector(est)


def test_the_length_class_is_no_longer_blind():
    cls = next(d for d in DEFECTS if d.code == "length_directive_ignored")
    assert not cls.blocked_on, "the generate response now emits actual_words"
