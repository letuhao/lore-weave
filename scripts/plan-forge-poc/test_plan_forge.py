"""PlanForge POC unit tests."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from plan_forge.compile import compile_artifacts, mock_pipeline_result
from plan_forge.compare import compare_specs
from plan_forge.coverage import build_section_map, coverage_report_spec, load_coverage_context
from plan_forge.decompose import build_graph
from plan_forge.elaborate import consistency_audit, section_excerpts_for_elaboration
from plan_forge.eval_chat_hil import aggregate_metrics, measure_turn
from plan_forge.eval_fidelity import evaluate_spec_fidelity, load_fidelity_config
from plan_forge.interpret import detect_intent, interpret_rules
from plan_forge.ingest import ingest_file
from plan_forge.self_check import run_self_check
from plan_forge.spec_index import build_spec_index, search_index, spec_slice_for_paths
from plan_forge.links import build_links_from_events, normalize_planner_notes
from plan_forge.propose import propose_spec
from plan_forge.propose_llm import analyze_document, materialize_from_analyze, propose_spec_llm
from plan_forge.refine import accept_refine, frozen_paths_intact, refine_spec
from plan_forge.validate import run_rules, validate_golden

FIXTURE = ROOT / "fixtures" / "story-plan-v1.md"
GOLDEN = ROOT / "fixtures" / "story-plan-v1.expectations.yaml"
FIDELITY = ROOT / "fixtures" / "story-plan-v1.fidelity.yaml"
MOCK_ANALYZE = ROOT / "fixtures" / "llm_mock_analyze.json"
MOCK_SPEC = ROOT / "fixtures" / "llm_mock_spec.json"


class MockLMStudioClient:
    def __init__(self, analyze: dict, spec: dict, *, refine_analyze: dict | None = None, refine_spec: dict | None = None) -> None:
        self._analyze = analyze
        self._spec = spec
        self._refine_analyze = refine_analyze
        self._refine_spec = refine_spec
        self.calls: list[str] = []

    def health_check(self) -> dict:
        return {"data": [{"id": "mock-model"}]}

    def chat(self, *, step: str, system: str, user: str, temperature: float = 0.2, max_tokens: int = 8000) -> str:
        self.calls.append(step)
        if step in ("analyze", "analyze_repair"):
            return json.dumps(self._analyze)
        if step in ("materialize", "materialize_repair"):
            return json.dumps(self._spec)
        if step in ("refine_analyze", "refine_analyze_repair"):
            return json.dumps(self._refine_analyze or self._analyze)
        if step in ("refine_spec", "refine_spec_repair"):
            return json.dumps(self._refine_spec or self._spec)
        raise ValueError(f"unexpected step: {step}")


@pytest.fixture
def pipeline_artifacts():
    doc = ingest_file(FIXTURE)
    spec = propose_spec(doc)
    graph = build_graph(spec)
    compiled = compile_artifacts(spec, arc_id="arc_2")
    return doc, spec, graph, compiled


def test_ingest_seven_sections():
    doc = ingest_file(FIXTURE)
    assert len(doc["sections"]) == 7
    kinds = {s["kind"] for s in doc["sections"]}
    assert "character_seed" in kinds
    assert "planner_variables" in kinds
    assert "arc_overview" in kinds


def test_propose_four_variables(pipeline_artifacts):
    _, spec, _, _ = pipeline_artifacts
    codes = {v["code"] for v in spec["layers"]["variables"]}
    assert codes == {"PA", "HA", "CD", "THR"}


def test_arc2_discovery_and_events(pipeline_artifacts):
    _, spec, _, _ = pipeline_artifacts
    arc2 = next(a for a in spec["arcs"] if a["id"] == "arc_2")
    assert arc2["arc_kind"] == "discovery"
    arc2_events = [e for e in spec["events"] if e["arc_id"] == "arc_2"]
    assert len(arc2_events) >= 5


def test_planning_package_premise_under_4k(pipeline_artifacts):
    _, spec, _, compiled = pipeline_artifacts
    pkg = compiled["planning_package"]
    assert len(pkg["premise"]) <= 4000
    assert "khám phá" in pkg["premise"].lower() or "discovery" in pkg["premise"].lower()


def test_mock_pipeline(pipeline_artifacts):
    _, _, _, compiled = pipeline_artifacts
    result = mock_pipeline_result(compiled["planning_package"])
    assert result["mock"] is True
    assert result["chapter_count"] >= 5


def test_golden_validation_passes(pipeline_artifacts):
    doc, spec, graph, compiled = pipeline_artifacts
    validation = validate_golden(spec, compiled["planning_package"], graph, doc, GOLDEN)
    assert validation["all_pass"] is True
    assert all(validation["criteria"].values())


def test_negative_thr_early_explain(pipeline_artifacts):
    _, spec, _, compiled = pipeline_artifacts
    bad = json.loads(json.dumps(spec))
    for ev in bad["events"]:
        if ev["id"] == "arc_2_event_4":
            ev["synopsis"] = "THR được giải thích là tiền kiếp với Mị Đế"
    rules = run_rules(bad, compiled["planning_package"])
    thr_rule = next(r for r in rules if r["rule"] == "thr_no_early_explain")
    assert thr_rule["pass"] is False


def test_propose_llm_mock_normalizes_string_notes():
    analyze = json.loads(MOCK_ANALYZE.read_text(encoding="utf-8"))
    spec_raw = json.loads(MOCK_SPEC.read_text(encoding="utf-8"))
    client = MockLMStudioClient(analyze, spec_raw)
    spec, returned_analyze = propose_spec_llm(FIXTURE, client=client)
    assert returned_analyze["version"] == 1
    assert client.calls == ["analyze", "materialize"]
    arc2 = [e for e in spec["events"] if e["arc_id"] == "arc_2"]
    assert all(isinstance(e["planner_notes"], list) for e in arc2)
    codes = {v["code"] for v in spec["layers"]["variables"]}
    assert codes == {"PA", "HA", "CD", "THR"}
    arc2_kind = next(a for a in spec["arcs"] if a["id"] == "arc_2")
    assert arc2_kind["arc_kind"] == "discovery"
    notes_rule = next(r for r in run_rules(spec) if r["rule"] == "notes_linked")
    assert notes_rule["pass"] is True


def test_compare_title_overlap_beats_id_overlap(pipeline_artifacts):
    _, rules_spec, _, _ = pipeline_artifacts
    analyze = json.loads(MOCK_ANALYZE.read_text(encoding="utf-8"))
    spec_raw = json.loads(MOCK_SPEC.read_text(encoding="utf-8"))
    client = MockLMStudioClient(analyze, spec_raw)
    llm_spec, _ = propose_spec_llm(FIXTURE, client=client)
    metrics = compare_specs(rules_spec, llm_spec)
    assert metrics["event_id_overlap_ratio"] == 0.0
    assert metrics["event_title_overlap_ratio"] > 0.0


def test_links_from_string_planner_notes():
    events = [
        {
            "id": "ev_2_1",
            "arc_id": "arc_2",
            "planner_notes": "Dry humor. HA = 100.",
            "var_deltas": [],
        }
    ]
    normalize_planner_notes(events)
    links = build_links_from_events(events)
    assert any(l["to"] == "HA" for l in links)
    assert any(l["from"] == "ev_2_1" for l in links)


@pytest.mark.live
def test_llm_live_health_and_propose():
    from plan_forge.llm_client import LMStudioClient

    client = LMStudioClient()
    models = client.health_check()
    assert "data" in models
    spec, analyze = propose_spec_llm(FIXTURE, client=client)
    assert analyze.get("version") == 1
    assert len(spec.get("events", [])) >= 2
    assert {v["code"] for v in spec["layers"]["variables"]} >= {"PA", "HA", "CD", "THR"}


def test_frozen_paths_detects_arc_kind_change(pipeline_artifacts):
    _, spec, _, _ = pipeline_artifacts
    before = json.loads(json.dumps(spec))
    after = json.loads(json.dumps(spec))
    after["arcs"] = [{**a, "arc_kind": "power"} if a["id"] == "arc_2" else a for a in after["arcs"]]
    ok, fails = frozen_paths_intact(before, after, ["arcs"])
    assert ok is False
    assert any("arc_kind" in f for f in fails)


def test_accept_refine_rejects_arc_kind_regression(pipeline_artifacts):
    _, spec, _, compiled = pipeline_artifacts
    before = json.loads(json.dumps(spec))
    bad = json.loads(json.dumps(spec))
    bad["arcs"] = [{**a, "arc_kind": "power"} if a["id"] == "arc_2" else a for a in bad["arcs"]]
    revision = {
        "version": 1,
        "target": "spec",
        "instruction": "noop",
        "frozen_paths": ["arcs"],
        "scope": ["events"],
    }
    result = accept_refine(before, bad, revision, package=compiled["planning_package"])
    assert result.accepted is False


def test_refine_spec_adds_thu_nghiem_event(pipeline_artifacts):
    _, rules_spec, _, _ = pipeline_artifacts
    spec = json.loads(json.dumps(rules_spec))
    arc2 = [e for e in spec["events"] if e["arc_id"] == "arc_2"]
    spec["events"] = [e for e in spec["events"] if e.get("title") != "Event 3 — Thử Nghiệm"]
    assert not any("thử nghiệm" in e.get("title", "").lower() for e in spec["events"] if e["arc_id"] == "arc_2")

    refined = json.loads(json.dumps(spec))
    refined["events"] = list(refined["events"]) + [
        e for e in arc2 if "thử nghiệm" in e.get("title", "").lower()
    ]
    client = MockLMStudioClient({}, spec, refine_spec=refined)
    revision = {
        "version": 1,
        "target": "spec",
        "instruction": "Add Thử Nghiệm",
        "scope": ["events", "links"],
        "frozen_paths": ["variables", "arcs"],
        "expect_contains": ["Thử Nghiệm"],
    }
    out = refine_spec(spec, revision, client=client, source_checksum="abc")
    assert any("thử nghiệm" in e.get("title", "").lower() for e in out["events"] if e["arc_id"] == "arc_2")


def test_analyze_materialize_split(pipeline_artifacts):
    analyze = json.loads(MOCK_ANALYZE.read_text(encoding="utf-8"))
    spec_raw = json.loads(MOCK_SPEC.read_text(encoding="utf-8"))
    client = MockLMStudioClient(analyze, spec_raw)
    a, checksum = analyze_document(FIXTURE, client=client)
    spec = materialize_from_analyze(a, checksum, client=client)
    assert a["version"] == 1
    assert spec["version"] == 1
    assert client.calls == ["analyze", "materialize"]


def test_build_section_map_parses_events():
    sections = build_section_map(FIXTURE)
    ids = {s["section_id"] for s in sections}
    assert "1.3" in ids
    assert "event_3" in ids
    ev3 = next(s for s in sections if s["section_id"] == "event_3")
    assert "Thử Nghiệm" in ev3["title"]


def test_fidelity_score_on_rules_spec(pipeline_artifacts):
    _, spec, _, _ = pipeline_artifacts
    cfg = load_fidelity_config(FIDELITY)
    result = evaluate_spec_fidelity(spec, cfg)
    assert result["total"] > 0
    assert 0.0 <= result["score"] <= 1.0


def test_coverage_report_spec_has_suggestions(pipeline_artifacts):
    _, spec, _, _ = pipeline_artifacts
    section_map, cfg = load_coverage_context(FIXTURE, FIDELITY)
    report = coverage_report_spec(spec, section_map, cfg)
    assert "gaps" in report
    assert "suggestions" in report


def test_accept_refine_rejects_fidelity_regression(pipeline_artifacts):
    _, spec, _, compiled = pipeline_artifacts
    cfg = load_fidelity_config(FIDELITY)
    before = json.loads(json.dumps(spec))
    after = json.loads(json.dumps(spec))
    if after["layers"]["characters"]:
        after["layers"]["characters"][0]["traits"] = after["layers"]["characters"][0].get("traits", [])[:1]
    revision = {
        "version": 1,
        "target": "spec",
        "instruction": "shrink traits",
        "frozen_paths": ["variables"],
        "scope": ["layers"],
    }
    fb = evaluate_spec_fidelity(before, cfg)["score"]
    fa = evaluate_spec_fidelity(after, cfg)["score"]
    result = accept_refine(
        before,
        after,
        revision,
        package=compiled["planning_package"],
        fidelity_before=fb,
        fidelity_after=fa,
    )
    assert result.accepted is False


def test_consistency_audit_no_critical_on_rules_spec(pipeline_artifacts):
    _, spec, _, _ = pipeline_artifacts
    audit = consistency_audit(spec)
    assert isinstance(audit["critical"], list)


def test_section_excerpts_for_elaboration():
    section_map = build_section_map(FIXTURE)
    excerpts = section_excerpts_for_elaboration(section_map)
    assert any(k.startswith("1.") for k in excerpts)


def test_detect_intent_vague_messages():
    assert detect_intent("check lại phần nhân vật đi") == "recheck"
    assert detect_intent("mày sai chỗ Event 3 nè") == "complaint"
    assert detect_intent("ừ làm đi, sửa hết gap") == "handoff"


def test_spec_index_finds_event3(pipeline_artifacts):
    _, spec, _, _ = pipeline_artifacts
    section_map = build_section_map(FIXTURE)
    index = build_spec_index(spec, section_map)
    hits = search_index("Event 3 Thử Nghiệm sai", index)
    assert hits
    assert any("Thử" in h.get("label_vn", "") or "e2" in h.get("path", "") for h in hits)


def test_interpret_rules_complaint_event3(pipeline_artifacts):
    _, spec, _, _ = pipeline_artifacts
    section_map = build_section_map(FIXTURE)
    report = run_self_check(spec, FIXTURE, FIDELITY)
    interp = interpret_rules("mày sai chỗ Event 3 nè", spec, section_map, self_check_report=report)
    assert interp["intent"] == "complaint"
    assert interp.get("draft_revision")
    assert interp["apply_mode"] in ("auto", "confirm")


def test_self_check_returns_ranked_gaps(pipeline_artifacts):
    _, spec, _, _ = pipeline_artifacts
    report = run_self_check(spec, FIXTURE, FIDELITY)
    assert "ranked_gaps" in report
    assert "fidelity_score" in report


def test_polish_checks_on_en_spec(pipeline_artifacts):
    _, spec, _, _ = pipeline_artifacts
    cfg = load_fidelity_config(FIDELITY)
    bad = json.loads(json.dumps(spec))
    if bad["layers"]["characters"]:
        bad["layers"]["characters"][0]["baseline_notes"] = "English only notes without Vietnamese."
        bad["layers"]["characters"][0]["name"] = "Female Protagonist"
    result = evaluate_spec_fidelity(bad, cfg)
    polish_fails = [c for c in result["checks"] if c["id"].startswith("polish_") and not c["pass"]]
    assert polish_fails


def test_measure_turn_oracle():
    m = measure_turn(
        turn_id="t1",
        interpretation={"focus_paths": ["events[e2_3]"], "diagnosis": [{"gap_id": "polish_bullets_x"}]},
        apply_result={"accepted": True, "fidelity_before": 0.9, "fidelity_after": 0.95},
        oracle={"expect_focus_contains": ["e2_3"], "expect_gap_prefix": ["polish_bullets"]},
    )
    assert m["I1_scope"] is True
    assert m["I3_apply"] is True


def test_aggregate_metrics_pass():
    turns = [
        {"I1_scope": True, "I2_diagnosis": True, "I3_apply": True, "I4_context_budget": True},
        {"I1_scope": True, "I2_diagnosis": True, "I3_apply": True, "I4_context_budget": True},
    ]
    s = aggregate_metrics(turns)
    assert s["pass"] is True


def test_spec_slice_bounded(pipeline_artifacts):
    _, spec, _, _ = pipeline_artifacts
    section_map = build_section_map(FIXTURE)
    index = build_spec_index(spec, section_map)
    hits = search_index("nhân vật", index)
    paths = [h["path"] for h in hits[:2]]
    slice_ = spec_slice_for_paths(spec, paths, max_chars=2000)
    assert len(slice_) <= 2000
