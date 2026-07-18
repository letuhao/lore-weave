"""Section map and coverage reports for PlanForge fidelity POC."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

from app.engine.plan_forge.eval_fidelity import (
    evaluate_analyze_fidelity,
    evaluate_spec_fidelity,
    format_fidelity_report,
    load_fidelity_config,
    suggest_fixes,
)


def _excerpt_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def build_section_map_from_text(text: str) -> list[dict[str, Any]]:
    """Parse ## 1.x / 2.x / 3.x and ### Event N headings into section records.

    27 PF-19 — takes the TEXT, so the caller can pass the RUN'S OWN document. It used to take only a
    path, and every caller passed `story-plan-v1.md`: so a user's "what is missing from my plan" was
    computed against the POC's novel. `build_section_map(path)` is kept for the regression harness,
    which legitimately does read that fixture off disk.
    """
    lines = text.splitlines()
    headers: list[tuple[str, str, int]] = []

    for i, line in enumerate(lines, start=1):
        stripped = line.strip()
        m_num = re.match(r"^## (\d+\.\d+)\s+(.+)$", stripped)
        if m_num:
            headers.append((m_num.group(1), m_num.group(2).strip(), i))
            continue
        m_event = re.match(r"^### Event (\d+)\s+—\s+(.+)$", stripped)
        if m_event:
            sid = f"event_{m_event.group(1)}"
            headers.append((sid, m_event.group(2).strip(), i))
            continue
        m_arc = re.match(r"^## Arc (\d+)\s+—\s+(.+)$", stripped)
        if m_arc:
            sid = f"arc_{m_arc.group(1)}"
            headers.append((sid, m_arc.group(2).strip(), i))

    sections: list[dict[str, Any]] = []
    for idx, (section_id, title, start) in enumerate(headers):
        end = headers[idx + 1][2] - 1 if idx + 1 < len(headers) else len(lines)
        body = "\n".join(lines[start:end]).strip()
        sections.append(
            {
                "section_id": section_id,
                "title": title,
                "line_start": start,
                "line_end": end,
                "excerpt": body[:2000],
                "excerpt_hash": _excerpt_hash(body),
            }
        )
    return sections


def _section_ids_for_kind(section_map: list[dict[str, Any]], prefix: str) -> list[str]:
    return [s["section_id"] for s in section_map if s["section_id"].startswith(prefix)]


def coverage_report_analyze(
    analyze: dict[str, Any],
    section_map: list[dict[str, Any]],
    fidelity_cfg: dict[str, Any],
) -> dict[str, Any]:
    fidelity = evaluate_analyze_fidelity(analyze, fidelity_cfg)
    arc2_events = [e for e in analyze.get("events", []) if e.get("arc_id") == "arc_2"]
    event_sections = _section_ids_for_kind(section_map, "event_")
    covered_events = sum(1 for e in arc2_events if e.get("source_refs") or e.get("source_excerpt"))
    section_coverage = {
        "event_sections_in_source": len(event_sections),
        "arc2_events_in_analyze": len(arc2_events),
        "events_with_provenance": covered_events,
    }
    gaps = list(fidelity.get("gaps") or [])
    if len(arc2_events) < len(event_sections):
        gaps.append(
            {
                "id": "coverage_arc2_events",
                "pass": False,
                "detail": f"analyze has {len(arc2_events)} events, source has {len(event_sections)}",
            }
        )
    return {
        **fidelity,
        "section_coverage": section_coverage,
        "gaps": gaps,
        "suggestions": suggest_fixes(gaps),
    }


def coverage_report_spec(
    spec: dict[str, Any],
    section_map: list[dict[str, Any]],
    fidelity_cfg: dict[str, Any],
) -> dict[str, Any]:
    fidelity = evaluate_spec_fidelity(spec, fidelity_cfg)
    gaps = list(fidelity.get("gaps") or [])
    return {
        **fidelity,
        "section_map_size": len(section_map),
        "gaps": gaps,
        "suggestions": suggest_fixes(gaps),
    }


def write_fidelity_artifacts(
    out_dir: Path,
    *,
    analyze_report: dict[str, Any] | None = None,
    spec_report: dict[str, Any] | None = None,
    elaboration_report: dict[str, Any] | None = None,
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "analyze": analyze_report,
        "spec": spec_report,
        "elaboration": elaboration_report,
    }
    (out_dir / "fidelity_report.json").write_text(
        __import__("json").dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    md = format_fidelity_report(
        analyze_result=analyze_report,
        spec_result=spec_report,
        elaboration_result=elaboration_report,
    )
    (out_dir / "fidelity_report.md").write_text(md, encoding="utf-8")

    gate = {
        "phase_a_pass": bool(spec_report and spec_report.get("gate_pass")),
        "fidelity_score": spec_report.get("score") if spec_report else None,
    }
    if elaboration_report:
        gate["phase_b_pass"] = bool(elaboration_report.get("gate_pass"))
        gate["elaboration_score"] = elaboration_report.get("score")
    (out_dir / "fidelity_gate.json").write_text(
        __import__("json").dumps(gate, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def build_section_map(md_path: Path) -> list[dict[str, Any]]:
    """Path form — the regression harness reads the POC fixture off disk. Production reads the run's
    own `document` artifact and calls `build_section_map_from_text`."""
    return build_section_map_from_text(md_path.read_text(encoding="utf-8"))


def load_coverage_context(fixture: Path, fidelity_path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    return build_section_map(fixture), load_fidelity_config(fidelity_path)
