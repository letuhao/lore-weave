"""HIL evaluation metrics (M/D/C/R groups)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from plan_forge.compile import compile_artifacts
from plan_forge.decompose import build_graph
from plan_forge.ingest import ingest_file
from plan_forge.refine import (
    AcceptResult,
    arc2_event_titles,
    anchor_jaccard,
    events_removed_outside_scope,
)
from plan_forge.validate import run_rules, validate_golden


def _arc2_count(spec: dict[str, Any]) -> int:
    return len([e for e in spec.get("events", []) if e.get("arc_id") == "arc_2"])


def _link_count(spec: dict[str, Any]) -> int:
    return len(spec.get("links", []))


def _notes_ratio(rules: list[dict[str, Any]]) -> float:
    r = next((x for x in rules if x["rule"] == "notes_linked"), None)
    if not r:
        return 0.0
    detail = r.get("detail", "")
    if detail.startswith("ratio="):
        try:
            return float(detail.split("=", 1)[1])
        except ValueError:
            return 0.0
    return 1.0 if r.get("pass") else 0.0


def measure_round(
    *,
    label: str,
    before: dict[str, Any],
    after: dict[str, Any],
    revision: dict[str, Any],
    accept: AcceptResult,
    package: dict[str, Any] | None,
    criteria_before: dict[str, bool] | None = None,
    criteria_after: dict[str, bool] | None = None,
) -> dict[str, Any]:
    br = run_rules(before, package)
    ar = run_rules(after, package)
    titles_before = arc2_event_titles(before)
    titles_after = arc2_event_titles(after)
    has_thu = any("thử nghiệm" in t.lower() for t in titles_after)

    return {
        "label": label,
        "accepted": accept.accepted,
        "reasons": accept.reasons,
        "checks": accept.checks,
        "M": {
            "criteria_before": criteria_before,
            "criteria_after": criteria_after,
            "linter_before": {r["rule"]: r["pass"] for r in br if r["rule"] in ("vars_four", "arc2_discovery", "thr_no_early_explain", "notes_linked")},
            "linter_after": {r["rule"]: r["pass"] for r in ar if r["rule"] in ("vars_four", "arc2_discovery", "thr_no_early_explain", "notes_linked")},
        },
        "D": {
            "arc2_events_before": len(titles_before),
            "arc2_events_after": len(titles_after),
            "has_thu_nghiem": has_thu,
            "titles_after": titles_after,
        },
        "C": {
            "events_removed": events_removed_outside_scope(before, after, revision.get("scope") or []),
            "anchor_jaccard": round(anchor_jaccard(before, after), 3),
            "notes_linked_before": _notes_ratio(br),
            "notes_linked_after": _notes_ratio(ar),
        },
        "R": {
            "link_count_before": _link_count(before),
            "link_count_after": _link_count(after),
            "arc2_count_delta": _arc2_count(after) - _arc2_count(before),
        },
    }


def format_hil_report(
    rounds: list[dict[str, Any]],
    *,
    baseline: dict[str, Any],
    final: dict[str, Any],
    final_validation: dict[str, Any],
    token_stats: dict[str, Any] | None = None,
) -> str:
    lines = ["# PlanForge HIL Evaluation Report", ""]
    lines.append(f"**Final golden:** {'PASS' if final_validation.get('all_pass') else 'FAIL'}")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append(f"- Baseline arc_2 events: {_arc2_count(baseline)}")
    lines.append(f"- Final arc_2 events: {_arc2_count(final)}")
    lines.append(f"- Has Thử Nghiệm: {any('thử nghiệm' in t.lower() for t in arc2_event_titles(final))}")
    lines.append("")

    for rnd in rounds:
        lines.append(f"## Round: {rnd['label']}")
        lines.append("")
        lines.append(f"- **Accepted:** {rnd['accepted']}")
        if rnd["reasons"]:
            lines.append(f"- **Reject reasons:** {', '.join(rnd['reasons'])}")
        d = rnd["D"]
        lines.append(f"- arc_2 events: {d['arc2_events_before']} → {d['arc2_events_after']}")
        lines.append(f"- Thử Nghiệm present: {d['has_thu_nghiem']}")
        r = rnd["R"]
        lines.append(f"- links: {r['link_count_before']} → {r['link_count_after']}")
        lines.append("")

    lines.append("## Final criteria")
    lines.append("")
    for k, v in final_validation.get("criteria", {}).items():
        lines.append(f"- {k}: {'PASS' if v else 'FAIL'}")
    lines.append("")

    if token_stats:
        lines.append("## Token efficiency (A/B)")
        lines.append("")
        for k, v in token_stats.items():
            lines.append(f"- {k}: {v}")
        lines.append("")

    return "\n".join(lines)


def validate_spec_artifacts(
    spec: dict[str, Any],
    fixture_path: Path,
    golden_path: Path,
) -> dict[str, Any]:
    doc = ingest_file(fixture_path)
    graph = build_graph(spec)
    package = compile_artifacts(spec, arc_id="arc_2")["planning_package"]
    return validate_golden(spec, package, graph, doc, golden_path)
