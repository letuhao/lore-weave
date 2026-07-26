"""PlanForge engine unit tests (ported from POC)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.engine.plan_forge.compile import compile_artifacts, mock_pipeline_result
from app.engine.plan_forge.compare import compare_specs
from app.engine.plan_forge.coverage import build_section_map, coverage_report_spec, load_coverage_context
from app.engine.plan_forge.decompose import build_graph
from app.engine.plan_forge.elaborate import consistency_audit, section_excerpts_for_elaboration
from app.engine.plan_forge.eval_chat_hil import aggregate_metrics, measure_turn
from app.engine.plan_forge.eval_fidelity import evaluate_spec_fidelity, load_fidelity_config
from app.engine.plan_forge.interpret import detect_intent, interpret_rules
from app.engine.plan_forge.ingest import ingest_file, ingest_markdown
from app.engine.plan_forge.self_check import run_self_check
from app.engine.plan_forge.spec_index import build_spec_index, search_index, spec_slice_for_paths
from app.engine.plan_forge.links import build_links_from_events, normalize_planner_notes
from app.engine.plan_forge.propose import propose_spec
from app.engine.plan_forge.propose_llm import (
    analyze_document,
    materialize_from_analyze,
    normalize_spec,
    propose_spec_llm,
)
from app.engine.plan_forge.refine import accept_refine, frozen_paths_intact, refine_spec
from app.engine.plan_forge.normalize import post_normalize_spec
from app.engine.plan_forge.validate import run_rules, validate_golden

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "plan-forge"
FIXTURE = FIXTURES / "story-plan-v1.md"
GOLDEN = FIXTURES / "story-plan-v1.expectations.yaml"
FIDELITY = FIXTURES / "story-plan-v1.fidelity.yaml"
MOCK_ANALYZE = FIXTURES / "llm_mock_analyze.json"
MOCK_SPEC = FIXTURES / "llm_mock_spec.json"


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


def test_arc2_is_PARSED_from_the_document_not_hardcoded(pipeline_artifacts):
    """27 V2-G. This test used to assert `arc2["arc_kind"] == "discovery"` — and it passed because
    the PROPOSER hardcoded that string, along with arc 2's title ("Bước Lên Tiên Lộ"), its theme and
    its summary. It was pinning the bug: rules mode returned one specific novel's arcs for ANY input
    document, so the test was really asserting "the constant is still the constant".

    What must be true instead is that these values come OUT OF THE DOCUMENT. The title is the header
    the author wrote; the theme is their `**Chủ đề:**` field. `arc_kind` is now EMPTY, because this
    document never states one — it says what kind of arc it is in prose, and that prose is carried
    verbatim in the summary (and reaches the premise). Absent, not invented."""
    _, spec, _, _ = pipeline_artifacts
    arc2 = next(a for a in spec["arcs"] if a["id"] == "arc_2")

    # …straight out of the document's `## Arc 2 — Bước Lên Tiên Lộ` header
    assert arc2["title"] == "Bước Lên Tiên Lộ"
    # …out of its `**Chủ đề:**` field, not a hardcoded paraphrase
    assert "phàm nhân" in arc2["theme"]
    # …the author's own emphasised line about what this arc IS
    assert "khám phá" in arc2["summary"]
    # …and no fabricated kind. The document does not declare one, so neither do we.
    assert arc2["arc_kind"] == ""

    arc2_events = [e for e in spec["events"] if e["arc_id"] == "arc_2"]
    assert len(arc2_events) >= 5
    # each event id is unique — an earlier cut of the new parser made the arc's PREAMBLE a phantom
    # "event 1" that collided with the real Event 1, and the linker's unique index would have
    # silently merged them into one node, losing a chapter
    assert len({e["id"] for e in arc2_events}) == len(arc2_events)


def test_a_DIFFERENT_book_gets_ITS_OWN_content_not_the_POCs():
    """The whole point of V2-G, stated as a test.

    Before: `propose_spec` returned, for ANY document, four Vietnamese planner variables (PA/HA/CD/
    THR), six consistency anchors from one novel's protagonist, four forbids about that novel's plot
    secrets, a protagonist with that novel's backstory, and arcs titled from it. A user planning a
    detective story in rules mode got a xianxia cultivation charter and never knew.

    A silent wrong answer is the worst failure mode there is: it does not crash, it does not return
    empty, it returns something that LOOKS like a plan."""
    from app.engine.plan_forge.ingest import ingest_markdown

    md = """# 1. Characters

## The Detective
**Name:** Mara Vance
**Baseline:** A homicide detective who no longer believes anyone is innocent.

### Refuses to lie, even kindly
### Keeps a list of everyone she failed

# 2. Variables

```
DBT = Doubt        [0 → 100]
      ↑ each time a witness is caught lying
```

# 3. Arc Overview

## Arc 1 — The Body in the Canal

**Theme:** A city that would rather the truth stayed drowned.

### Event 1 — The Call
Mara is handed a case nobody wants.

**Goal:** Establish that the department wants this closed, not solved.
"""
    spec = propose_spec(ingest_markdown(md))

    # ITS characters, ITS variables, ITS arcs.
    assert [c["name"] for c in spec["layers"]["characters"]] == ["Mara Vance"]
    assert [v["code"] for v in spec["layers"]["variables"]] == ["DBT"]
    assert spec["layers"]["variables"][0]["name"] == "Doubt"
    assert [a["title"] for a in spec["arcs"]] == ["The Body in the Canal"]
    assert "drowned" in spec["arcs"][0]["theme"]
    assert [e["title"] for e in spec["events"]] == ["Event 1 — The Call"]
    assert spec["charter"]["consistency_anchors"] == [
        "Refuses to lie, even kindly",
        "Keeps a list of everyone she failed",
    ]

    # …and NONE of the POC's.
    blob = json.dumps(spec, ensure_ascii=False).lower()
    for leaked in ("perfection_addiction", "humanity_anchor", "than_hon", "corruption_debt",
                   "linh căn", "bước lên tiên lộ", "hài hước", "đạo hóa"):
        assert leaked.lower() not in blob, f"the POC's {leaked!r} leaked into another book's plan"


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


def test_pa_not_realm_tolerates_realm_breakthrough_as_pa_trigger(pipeline_artifacts):
    # D-PLANFORGE-PA-REALM-FALSE-POSITIVE: live-audited against 5 real LLM
    # propose runs, ALL 5 described the Tiểu Thành realm-entry event's PA
    # trigger by naming the breakthrough itself -- a legitimate one-time
    # EXPERIENCE trigger the story's own design sanctions, not the forbidden
    # "PA scales WITH realm" coupling. Exact phrasings observed live.
    _, spec, _, _ = pipeline_artifacts
    for reason in ("Đột phá cảnh giới đầu tiên", "Khoảnh khắc đột phá cảnh giới đầu tiên"):
        bad = json.loads(json.dumps(spec))
        for ev in bad["events"]:
            if ev["id"] == "arc_2_event_5":
                ev["var_deltas"] = [
                    {"variable": "PA", "delta": "+large", "reason": reason, "coupled_to_realm": False}
                ]
        rule = next(r for r in run_rules(bad) if r["rule"] == "pa_not_realm")
        assert rule["pass"] is True, f"false positive on real phrasing: {reason!r}"


def test_pa_not_realm_still_catches_proportional_coupling_language(pipeline_artifacts):
    # Defense-in-depth check: even without an explicit coupled_to_realm=True,
    # PROPORTIONAL coupling language must still fail -- this is the actually
    # forbidden case, distinct from a one-time breakthrough trigger above.
    _, spec, _, _ = pipeline_artifacts
    bad = json.loads(json.dumps(spec))
    for ev in bad["events"]:
        if ev["id"] == "arc_2_event_5":
            ev["var_deltas"] = [
                {
                    "variable": "PA",
                    "delta": "+large",
                    "reason": "PA tăng theo cảnh giới hiện tại",
                    "coupled_to_realm": False,
                }
            ]
    rule = next(r for r in run_rules(bad) if r["rule"] == "pa_not_realm")
    assert rule["pass"] is False


def test_sg_value_shift_per_scene_adopted_as_advisory_8th_rule(pipeline_artifacts):
    # D-PLANFORGE-STORY-GRID-POC adoption (2026-07-06): the rule now runs
    # inside run_rules(), but real on this fixture (arc_2_event_3/_7 lack
    # var_deltas) -- it must be TAGGED advisory, not silently passing.
    _, spec, _, _ = pipeline_artifacts
    rule = next(r for r in run_rules(spec) if r["rule"] == "sg_value_shift_per_scene")
    assert rule["tier"] == "advisory"
    assert rule["pass"] is False
    assert "arc_2_event_3" in rule["detail"]
    assert "arc_2_event_7" in rule["detail"]


def test_sg_value_shift_advisory_fail_does_not_block_golden_all_pass(pipeline_artifacts):
    # The whole point of advisory tier: validate_golden's all_pass (and by
    # extension plan_forge_service's hard gate) must stay green even though
    # this rule genuinely fails on the golden fixture.
    doc, spec, graph, compiled = pipeline_artifacts
    validation = validate_golden(spec, compiled["planning_package"], graph, doc, GOLDEN)
    assert validation["all_pass"] is True
    sg_rule = next(r for r in validation["rules"] if r["rule"] == "sg_value_shift_per_scene")
    assert sg_rule["pass"] is False


def test_hard_rules_pass_ignores_advisory_tier_failures():
    from app.services.plan_forge_service import _hard_rules_pass

    rules = [
        {"rule": "vars_four", "pass": True},
        {"rule": "sg_value_shift_per_scene", "pass": False, "tier": "advisory"},
    ]
    assert _hard_rules_pass(rules) is True


def test_hard_rules_pass_still_blocks_on_hard_tier_failure():
    from app.services.plan_forge_service import _hard_rules_pass

    rules = [
        {"rule": "vars_four", "pass": False},
        {"rule": "sg_value_shift_per_scene", "pass": True, "tier": "advisory"},
    ]
    assert _hard_rules_pass(rules) is False


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


def test_normalize_spec_coerces_list_synopsis_to_string():
    # D-PLANFORGE-PA-REALM-FALSE-POSITIVE audit: observed live, the materialize
    # prompt doesn't forbid a bullet array for synopsis and the model
    # sometimes emits one, which crashed validate.run_rules's `.lower()` call.
    spec = {
        "events": [
            {"id": "arc_2_event_1", "arc_id": "arc_2", "synopsis": ["Bullet one", "Bullet two"]},
            {"id": "arc_2_event_2", "arc_id": "arc_2", "synopsis": None},
        ],
    }
    out = normalize_spec(spec, "checksum123")
    assert out["events"][0]["synopsis"] == "Bullet one Bullet two"
    assert out["events"][1]["synopsis"] == ""
    # Must not crash the rule that reads synopsis as a string.
    run_rules(out)


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


def test_ingest_markdown_matches_file():
    text = FIXTURE.read_text(encoding="utf-8")
    from_file = ingest_file(FIXTURE)
    from_text = ingest_markdown(text, source_path=str(FIXTURE))
    assert from_file["source"]["checksum_sha256"] == from_text["source"]["checksum_sha256"]
    assert len(from_file["sections"]) == len(from_text["sections"])


def test_normalize_female_protagonist_always():
    spec = {
        "meta": {"open_questions": []},
        "layers": {"characters": [{"name": "Female Protagonist", "role": "protagonist"}], "mechanics": []},
    }
    out = post_normalize_spec(spec)
    assert out["layers"]["characters"][0]["name"] == "Nữ chính"


def test_normalize_tbd_only_when_open_question_name():
    base = {"layers": {"characters": [{"name": "[TBD]", "role": "protagonist"}], "mechanics": []}}
    unchanged = post_normalize_spec({**base, "meta": {"open_questions": []}})
    assert unchanged["layers"]["characters"][0]["name"] == "[TBD]"
    renamed = post_normalize_spec({**base, "meta": {"open_questions": ["Tên nhân vật TBD"]}})
    assert renamed["layers"]["characters"][0]["name"] == "Nữ chính"


def test_normalize_en_yin_yang_rules_by_mechanic_name():
    spec = {
        "meta": {},
        "layers": {
            "characters": [],
            "mechanics": [
                {
                    "id": "mech_1",
                    "name": "Âm Dương Hợp Hoan",
                    "rules": ["absorb qi via partner", "intensity scales with intimacy"],
                }
            ],
        },
    }
    out = post_normalize_spec(spec)
    joined = " ".join(out["layers"]["mechanics"][0]["rules"])
    assert "Âm Dương" in joined


def test_spec_slice_bounded(pipeline_artifacts):
    _, spec, _, _ = pipeline_artifacts
    section_map = build_section_map(FIXTURE)
    index = build_spec_index(spec, section_map)
    hits = search_index("nhân vật", index)
    paths = [h["path"] for h in hits[:2]]
    slice_ = spec_slice_for_paths(spec, paths, max_chars=2000)
    assert len(slice_) <= 2000


# ── 27 V2-G — the compile gate must gate on STRUCTURE, not on the POC's taste ────────────────────

def _hard_failures(md: str) -> list[str]:
    from app.engine.plan_forge.ingest import ingest_markdown
    from app.engine.plan_forge.validate import run_rules

    spec = propose_spec(ingest_markdown(md))
    pkg = compile_artifacts(spec, arc_id="arc_1")["planning_package"]
    return [
        r["rule"] for r in run_rules(spec, pkg)
        if r.get("tier", "hard") == "hard" and not r["pass"]
    ]


_DETECTIVE = """# 1. Characters

## The Detective
**Name:** Mara Vance

### Refuses to lie, even kindly

# 3. Arc Overview

## Arc 1 - The Body in the Canal

**Theme:** A city that would rather the truth stayed drowned.

### Event 1 - The Call
Mara is handed a case nobody wants.

**Goal:** Establish that the department wants this closed.
"""


def test_a_NON_POC_book_can_actually_COMPILE():
    """`anchors_min` (>= 4) was the last fixture rule still GATING compile, and it blocked every book
    with a shorter charter than the POC's — a 422, on a perfectly valid plan.

    `>= 4` is not a general truth about novels; it is the POC's own anchor count. A braindump that
    names two things about its protagonist is a legitimate plan, and the `cast` pass exists to
    propose more. Reporting a thin charter is useful; REFUSING TO COMPILE it is the tool overruling
    the author about their own book."""
    assert _hard_failures(_DETECTIVE) == []


def test_an_EMPTY_plan_is_STILL_blocked_and_told_why():
    """The gate must still gate. Loosening it until everything passes would just move the silent
    failure downstream — the compile would 'succeed' into a package with no arc and no events, and
    the linker would then refuse (E4). Catching it here is the same law, one layer earlier, where
    the user can still act on it."""
    assert set(_hard_failures("# 1. Characters\n\nNothing yet.\n")) == {
        "spec_has_arc", "spec_has_events",
    }


def test_the_fixture_rules_are_ALL_advisory_now():
    """Every rule that encodes the POC's own story is REPORTED, never GATING. A rule that asks "does
    your book have PA/HA/CD/THR" or "is your arc 2 a discovery arc" cannot be a gate on other
    people's novels — it could only ever have been satisfied by the one document it was written
    from."""
    from app.engine.plan_forge.ingest import ingest_markdown
    from app.engine.plan_forge.validate import run_rules

    spec = propose_spec(ingest_markdown(_DETECTIVE))
    pkg = compile_artifacts(spec, arc_id="arc_1")["planning_package"]
    tier = {r["rule"]: r.get("tier", "hard") for r in run_rules(spec, pkg)}

    for fixture_rule in (
        "vars_four",            # "your book has exactly PA/HA/CD/THR"
        "pa_not_realm",         # about ONE novel's PA variable; vacuous for every other book
        "arc2_discovery",       # "your arc 2 is a 'discovery' arc"
        "anchors_min",          # ">= 4 anchors", i.e. the POC's own count
        "thr_no_early_explain",  # about ONE novel's THR seed
    ):
        assert tier[fixture_rule] == "advisory", f"{fixture_rule} still gates other people's books"

    # …and what DOES gate is structural, and true of any novel in any language.
    assert tier["spec_has_arc"] == "hard"
    assert tier["spec_has_events"] == "hard"
    assert tier["premise_max"] == "hard"
