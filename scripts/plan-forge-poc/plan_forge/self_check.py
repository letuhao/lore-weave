"""Self-check: coverage + fidelity + consistency audit without user specifying gaps."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from plan_forge.coverage import coverage_report_spec, load_coverage_context
from plan_forge.elaborate import consistency_audit
from plan_forge.eval_fidelity import evaluate_spec_fidelity, load_fidelity_config, suggest_fixes


_GAP_PRIORITY: dict[str, int] = {
    "polish_baseline": 1,
    "polish_character": 2,
    "char_baseline": 3,
    "char_trait": 4,
    "char_mundane": 5,
    "polish_bullets": 6,
    "synopsis_": 7,
    "arc2_syn": 8,
    "mech_": 9,
    "polish_mechanic": 10,
}


def _gap_priority(gap_id: str) -> int:
    for prefix, prio in _GAP_PRIORITY.items():
        if gap_id.startswith(prefix):
            return prio
    return 50


def run_self_check(
    spec: dict[str, Any],
    fixture_path: Path,
    fidelity_path: Path,
) -> dict[str, Any]:
    section_map, fidelity_cfg = load_coverage_context(fixture_path, fidelity_path)
    coverage = coverage_report_spec(spec, section_map, fidelity_cfg)
    fidelity = evaluate_spec_fidelity(spec, fidelity_cfg)
    audit = consistency_audit(spec)

    ranked_gaps = sorted(
        fidelity.get("gaps") or [],
        key=lambda g: _gap_priority(g.get("id", "")),
    )
    suggestions = suggest_fixes(ranked_gaps)

    for c in audit.get("critical") or []:
        ranked_gaps.append({"id": "audit_critical", "pass": False, "detail": c})

    return {
        "fidelity_score": fidelity.get("score"),
        "gate_pass": fidelity.get("gate_pass"),
        "gaps": ranked_gaps,
        "ranked_gaps": ranked_gaps,
        "suggestions": suggestions,
        "audit": audit,
        "coverage": coverage,
        "section_map": section_map,
        "fidelity_cfg": fidelity_cfg,
    }
