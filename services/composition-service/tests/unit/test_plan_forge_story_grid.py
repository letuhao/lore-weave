"""D-PLANFORGE-STORY-GRID-POC — scored against the same story-plan-v1 fixture
the 7 core PlanForge rules (validate.run_rules) already pass. See
app/engine/plan_forge/validate_story_grid.py module docstring for the design
rationale and scope boundary.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.engine.plan_forge.compile import compile_artifacts
from app.engine.plan_forge.decompose import build_graph
from app.engine.plan_forge.ingest import ingest_file
from app.engine.plan_forge.propose import propose_spec
from app.engine.plan_forge.validate import run_rules
from app.engine.plan_forge.validate_story_grid import (
    format_story_grid_report,
    run_story_grid_rules,
)

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "plan-forge"
FIXTURE = FIXTURES / "story-plan-v1.md"


@pytest.fixture
def pipeline_artifacts():
    doc = ingest_file(FIXTURE)
    spec = propose_spec(doc)
    graph = build_graph(spec)
    compiled = compile_artifacts(spec, arc_id="arc_2")
    return doc, spec, graph, compiled


def test_sg_value_shift_flags_scenes_without_delta(pipeline_artifacts):
    _, spec, _, _ = pipeline_artifacts
    results = run_story_grid_rules(spec)
    rule = next(r for r in results if r["rule"] == "sg_value_shift_per_scene")
    # Real gap found on the real fixture, not a contrived one: Event 3 (Thử
    # Nghiệm) and Event 7 (Quyết Định Tiếp Tục) parse with zero var_deltas —
    # neither of the 7 core rules checks for this.
    assert rule["pass"] is False
    assert "arc_2_event_3" in rule["detail"]
    assert "arc_2_event_7" in rule["detail"]


def test_sg_value_shift_passes_when_every_event_has_a_delta(pipeline_artifacts):
    _, spec, _, _ = pipeline_artifacts
    patched = json.loads(json.dumps(spec))
    for ev in patched["events"]:
        if ev["arc_id"] == "arc_2" and not ev.get("var_deltas"):
            ev["var_deltas"] = [
                {"variable": "PA", "delta": "+1", "reason": "synthetic", "coupled_to_realm": False}
            ]
    results = run_story_grid_rules(patched)
    rule = next(r for r in results if r["rule"] == "sg_value_shift_per_scene")
    assert rule["pass"] is True


def test_sg_negative_turn_exists_passes_on_baseline(pipeline_artifacts):
    _, spec, _, _ = pipeline_artifacts
    # Event 6's CD+1 (Corruption_Debt) is the cost turn alongside Event 2/5's
    # PA gains — baseline already tells a real story, not a power fantasy.
    results = run_story_grid_rules(spec)
    rule = next(r for r in results if r["rule"] == "sg_negative_turn_exists")
    assert rule["pass"] is True


def test_sg_negative_turn_fails_when_all_deltas_are_gains(pipeline_artifacts):
    _, spec, _, _ = pipeline_artifacts
    patched = json.loads(json.dumps(spec))
    for ev in patched["events"]:
        ev["var_deltas"] = [d for d in ev.get("var_deltas", []) if d.get("variable") != "CD"]
    results = run_story_grid_rules(patched)
    rule = next(r for r in results if r["rule"] == "sg_negative_turn_exists")
    assert rule["pass"] is False


def test_run_story_grid_rules_no_events_is_vacuously_no_gap():
    results = run_story_grid_rules({"events": []}, arc_id="arc_2")
    rule = next(r for r in results if r["rule"] == "sg_value_shift_per_scene")
    assert rule["pass"] is True
    assert rule["detail"] == "checked=0"


def test_run_story_grid_rules_scopes_to_requested_arc(pipeline_artifacts):
    _, spec, _, _ = pipeline_artifacts
    results = run_story_grid_rules(spec, arc_id="arc_1")
    rule = next(r for r in results if r["rule"] == "sg_value_shift_per_scene")
    # arc_1 has no parsed events in this fixture (context TBD) — vacuous pass.
    assert rule["pass"] is True
    assert rule["detail"] == "checked=0"


def test_format_story_grid_report_notes_gap_when_sg_fails(pipeline_artifacts):
    _, spec, _, compiled = pipeline_artifacts
    core = run_rules(spec, compiled["planning_package"])
    sg = run_story_grid_rules(spec)
    report = format_story_grid_report(core, sg)
    assert "Story Grid POC" in report
    assert "gap(s)" in report
    assert "sg_value_shift_per_scene" in report
    assert "sg_negative_turn_exists" in report


def test_format_story_grid_report_notes_no_gap_when_sg_all_pass(pipeline_artifacts):
    _, spec, _, compiled = pipeline_artifacts
    patched = json.loads(json.dumps(spec))
    for ev in patched["events"]:
        if ev["arc_id"] == "arc_2" and not ev.get("var_deltas"):
            ev["var_deltas"] = [
                {"variable": "PA", "delta": "+1", "reason": "synthetic", "coupled_to_realm": False}
            ]
    core = run_rules(patched, compiled["planning_package"])
    sg = run_story_grid_rules(patched)
    report = format_story_grid_report(core, sg)
    assert "no gap beyond the current 7 rules" in report
