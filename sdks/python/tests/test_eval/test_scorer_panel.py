"""Q0-0b unit tests — JudgePanel + score_dump facade + FileSink.

These lock the parameterization (the disjoint exclusion now comes from a
JudgePanel, not inline env reads) AND that the facade reproduces the
metric-of-record exactly.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from loreweave_eval import (
    DEFAULT_EXTRACTOR_REF,
    DEFAULT_FILTER_REF,
    EvalResult,
    FileSink,
    JudgePanel,
    panel_from_env,
    panel_safety,
    score_dump,
)


# The session-105 clean baseline dump (gemma + phi4, 9 golden chapters).
# test_eval → tests → python → sdks → repo-root = parents[4].
_C74C = (
    Path(__file__).resolve().parents[4]
    / "services"
    / "knowledge-service"
    / "tests"
    / "quality"
    / "eval_runs"
    / "c74c-clean-rejudge"
)


def test_panel_from_env_defaults_match_historical_uuids() -> None:
    """With no env set, the exclusion set equals the old inline
    {_DEFAULT_EXTRACTOR_UUID, _DEFAULT_FILTER_UUID} — guarantees byte-identical
    behavior for callers that switch to the panel."""
    panel = panel_from_env(env={})
    assert panel.extractor_exclude_ref == DEFAULT_EXTRACTOR_REF
    assert panel.filter_exclude_ref == DEFAULT_FILTER_REF
    assert panel.excluded == {DEFAULT_EXTRACTOR_REF, DEFAULT_FILTER_REF}


def test_panel_from_env_honors_overrides() -> None:
    panel = panel_from_env(
        env={"KNOWLEDGE_EXTRACTOR_MODEL": "ext-x", "KNOWLEDGE_FILTER_MODEL": "filt-y"}
    )
    assert panel.excluded == {"ext-x", "filt-y"}
    assert panel.role_of("ext-x") == "extractor"
    assert panel.role_of("filt-y") == "filter"
    assert panel.role_of("someone-else") == "independent"


def test_panel_role_classification() -> None:
    panel = JudgePanel(extractor_exclude_ref="E", filter_exclude_ref="F")
    assert panel.role_of("E") == "extractor"
    assert panel.role_of("F") == "filter"
    assert panel.role_of("J") == "independent"
    assert panel.role_of("") == "independent"


@pytest.mark.skipif(not _C74C.is_dir(), reason="c74c baseline dump not present")
def test_score_dump_reproduces_metric_of_record() -> None:
    """score_dump over the c74c dump must reproduce the session-105 locked
    numbers: gemma+phi4 independent, disjoint median F1 = 0.869, CI ~[0.842,
    0.895]. n_boot pinned for determinism."""
    panel = panel_from_env(env={})  # historical defaults; neither judge excluded
    result = score_dump(_C74C, panel, n_boot=2000, variant_label="c74c")

    assert isinstance(result, EvalResult)
    assert result.n_judges_total == 2
    # gemma + phi4 are both independent (neither is the qwen extractor/filter).
    roles = {js.label: js.role for js in result.per_judge}
    assert roles == {"gemma": "independent", "phi4": "independent"}

    by_label = {js.label: js for js in result.per_judge}
    assert round(by_label["gemma"].macro_f1, 3) == 0.888
    assert round(by_label["phi4"].macro_f1, 3) == 0.851

    assert result.n_disjoint_judges == 2
    assert round(result.disjoint_median_f1, 3) == 0.869
    assert round(result.disjoint_ci_low, 3) == 0.842
    assert round(result.disjoint_ci_high, 3) == 0.895
    # Q3.5 — gemma + phi4 are both independent (neither is the qwen
    # extractor/filter), so the metric-of-record panel is safe.
    assert result.panel_safe is True


@pytest.mark.skipif(not _C74C.is_dir(), reason="c74c baseline dump not present")
async def test_filesink_writes_json(tmp_path: Path) -> None:
    panel = panel_from_env(env={})
    result = score_dump(_C74C, panel, n_boot=200, variant_label="c74c")
    path = await FileSink(tmp_path).write_eval_result(result)
    assert path.is_file()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["variant_label"] == "c74c"
    assert data["n_disjoint_judges"] == 2
    assert round(data["disjoint_median_f1"], 3) == 0.869
    assert len(data["per_judge"]) == 2


# ── S13: a defaulted exclusion set cannot be mistaken for a verified one ──────────────────

def test_a_DEFAULTED_exclusion_that_matched_nothing_is_reported_as_unverified():
    """The defect the spec names: `panel.py`'s hardcoded UUIDs "silently fail to exclude a
    deployment's real self-grader".

    Those refs are `user_model_id`s, and this repo's rule is that they are PER-MACHINE. So
    anywhere but the box they were minted on, the exclusion set matches nothing — and
    `panel_safety` reported `no generator in panel`, which is exactly what it reports for a
    genuinely clean panel. The two are now distinguishable.
    """
    panel = panel_from_env({})            # nothing configured → the hardcoded defaults
    assert panel.exclusion_is_defaulted is True
    safety = panel_safety(panel.excluded, ["judge-a", "judge-b"],
                          exclusion_is_defaulted=panel.exclusion_is_defaulted)
    assert safety.exclusion_unverified is True
    assert "HARDCODED" in safety.reason


def test_a_CONFIGURED_exclusion_is_not_flagged():
    """The control. Without it the assertion above passes for an implementation that flags
    every panel — which would be the permanent-amber failure, not a signal."""
    panel = panel_from_env({"KNOWLEDGE_EXTRACTOR_MODEL": "ext-x",
                            "KNOWLEDGE_FILTER_MODEL": "filt-y"})
    assert panel.exclusion_is_defaulted is False
    safety = panel_safety(panel.excluded, ["judge-a", "judge-b"],
                          exclusion_is_defaulted=panel.exclusion_is_defaulted)
    assert safety.exclusion_unverified is False


def test_safe_STAYS_TRUE_because_a_permanently_false_flag_is_ignored():
    """Deliberate, and the harder half of the decision.

    Flipping `safe` here would make it False for every deployment that has not configured the
    refs — i.e. the default state — and a flag that is always false stops being read. Then a
    REAL self-grader in the panel arrives wearing the same colour as every ordinary run. So
    `safe` keeps its meaning and `exclusion_unverified` carries the new fact.
    """
    panel = panel_from_env({})
    safety = panel_safety(panel.excluded, ["judge-a", "judge-b"],
                          exclusion_is_defaulted=panel.exclusion_is_defaulted)
    assert safety.safe is True
    assert safety.exclusion_unverified is True


def test_a_REAL_self_grader_still_reports_unsafe_and_is_not_masked():
    """The case the whole mechanism exists for must not be softened by the new axis."""
    panel = panel_from_env({})
    safety = panel_safety(panel.excluded,
                          [DEFAULT_EXTRACTOR_REF, "judge-b", "judge-c"],
                          exclusion_is_defaulted=panel.exclusion_is_defaulted)
    assert safety.safe is False
    assert safety.generators_in_panel == [DEFAULT_EXTRACTOR_REF]
    assert safety.exclusion_unverified is False, "an exclusion that FIRED is verified by that"
