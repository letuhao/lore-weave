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


@pytest.mark.skipif(not _C74C.is_dir(), reason="c74c baseline dump not present")
def test_filesink_writes_json(tmp_path: Path) -> None:
    panel = panel_from_env(env={})
    result = score_dump(_C74C, panel, n_boot=200, variant_label="c74c")
    path = FileSink(tmp_path).write_eval_result(result)
    assert path.is_file()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["variant_label"] == "c74c"
    assert data["n_disjoint_judges"] == 2
    assert round(data["disjoint_median_f1"], 3) == 0.869
    assert len(data["per_judge"]) == 2
