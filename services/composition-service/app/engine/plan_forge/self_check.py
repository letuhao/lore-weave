"""Self-check: coverage + fidelity + consistency audit without user specifying gaps."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.engine.plan_forge.coverage import coverage_report_spec, load_coverage_context
from app.engine.plan_forge.elaborate import consistency_audit
from app.engine.plan_forge.eval_fidelity import evaluate_spec_fidelity, load_fidelity_config, suggest_fixes


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


def run_self_check_on_document(
    spec: dict[str, Any],
    document_markdown: str,
    fidelity_cfg: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """27 PF-19 — self-check a spec against ITS OWN source document.

    `run_self_check` below reads `story-plan-v1.md`, so every user's ranked gaps were "how does your
    plan differ from the POC's novel". That is a fixture constant with extra steps (DA-14).

    `fidelity_cfg` is OPTIONAL and defaults to none: fidelity scoring is only meaningful against a
    per-run rubric, and there is no honest score to report without one. `fidelity.score` comes back
    `None` rather than a number computed from somebody else's rubric — absent, not zero.
    """
    from app.engine.plan_forge.coverage import build_section_map_from_text

    section_map = build_section_map_from_text(document_markdown)
    cfg = fidelity_cfg or {}
    coverage = coverage_report_spec(spec, section_map, cfg)
    fidelity = evaluate_spec_fidelity(spec, cfg) if fidelity_cfg else {"score": None, "gaps": []}
    audit = consistency_audit(spec)

    ranked_gaps = sorted(
        fidelity.get("gaps") or [],
        key=lambda g: _gap_priority(g.get("id", "")),
    )
    suggestions = suggest_fixes(ranked_gaps)
    return {
        "coverage": coverage,
        "fidelity": fidelity,
        "audit": audit,
        "ranked_gaps": ranked_gaps,
        "suggestions": suggestions,
    }


def run_self_check(
    spec: dict[str, Any],
    fixture_path: Path,
    fidelity_path: Path,
) -> dict[str, Any]:
    """Fixture form — REGRESSION HARNESS ONLY (09 §8b). Production must not call this: it scores a
    user's spec against the POC's document + rubric."""
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
