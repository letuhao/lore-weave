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


#: Each planning kind, and where it lands in a spec. The kinds are `ingest.SECTION_KIND_MAP`'s, so
#: the board speaks the same vocabulary as the honesty block the author already reads — but it is
#: computed from the SPEC, never from the document's headings.
#:
#: `(kind, dotted path, how to label one item)`. A path of `arcs`/`events` is top-level; anything else
#: is nested under `layers` or `charter` or `meta`.
#: Which cross-step counter belongs to which board kind. `propose_llm_async._attach_step_disagreement`
#: records where ANALYZE found more than the plan kept; this is how that reaches the author.
_DISAGREEMENT_KEY: dict[str, str] = {
    "character_seed": "characters",
    "mechanics": "mechanics",
    "planner_variables": "variables",
    "arc_overview": "arcs",
    "writing_principles": "style_constraints",
    "open_questions": "open_questions",
}

_BOARD_KINDS: list[tuple[str, str, str]] = [
    ("character_seed", "layers.characters", "name"),
    ("mechanics", "layers.mechanics", "name"),
    ("planner_variables", "layers.variables", "name"),
    ("arc_overview", "arcs", "title"),
    ("writing_principles", "charter.style_constraints", ""),
    ("open_questions", "meta.open_questions", ""),
    ("premise", "charter.premise_notes", ""),
]

_EVIDENCE_MAX = 6


def _dig(spec: dict[str, Any], path: str) -> list[Any]:
    node: Any = spec
    for part in path.split("."):
        if not isinstance(node, dict):
            return []
        node = node.get(part)
    return node if isinstance(node, list) else []


def spec_coverage_board(spec: dict[str, Any]) -> dict[str, Any]:
    """What the read RECOVERED, per planning kind — and, when a kind is empty, whether that is a
    fact about the book or a failure of the read.

    ## Why this is computed from the spec

    The coverage this module used to report came from `build_section_map_from_text`, which matches
    `## 1.x` / `### Event N` — the POC fixture's heading shape. That is the same format-binding as
    `ingest._parse_top_sections` (which read 6 of 17 real documents as nothing) and `validate.py`
    (which confesses it in its own docstring). This module's own history records where it ends up:
    *"every caller passed `story-plan-v1.md`: so a user's 'what is missing from my plan' was computed
    against the POC's novel."*

    A spec has no such binding. Both propose paths produce one, so `0 variables` is a **fact about
    what was recovered**, where `no section matched '## 2.x'` was only ever a fact about the matcher.

    ## Empty is two different things, and conflating them is the bug class

    A kind can be empty because the author has not written it yet, or because the read failed and
    took it with it. Those look identical in a count, and the second one is a silent degrade — the
    same shape as the bug `_note_empty_read` closed on the rules path. So the board carries the
    ingest honesty block through: when the read is flagged failed or left sections unclassified, an
    absent kind is reported as `unknown` (*the read did not get far enough to tell you*), never as a
    confident `absent`.

    ## It shows, it does not conclude

    Every present kind carries up to six *labels of what was actually found*, not just a number.
    Measured reason (POC §6f): when the loop offered three retrieved lines for the one kind it
    thought was missing, **all three were wrong** — tone and world rules, not state variables — and
    the author drops them in two seconds. A count would have hidden that; the labels do not. This
    function therefore never proposes a fix and never scores. It reports.
    """
    unread = ((spec.get("meta") or {}).get("ingest_unread") or {}) if isinstance(spec.get("meta"), dict) else {}
    read_failed = bool(unread.get("empty_read"))
    unclassified = list(unread.get("unclassified") or [])
    # The LLM path's equivalent: a step that had to be REGENERATED (a repetition loop) or REPAIRED
    # (unparseable output) produced an answer, but not cleanly. Added because the board could
    # otherwise only ever say `absent` on the path that is now the DEFAULT — the rules propose is
    # the only writer of `unclassified`, so the degrade signal did not exist where most runs go.
    degraded_steps = list(unread.get("degraded_steps") or [])
    # An unclassified section is material the matcher could not place — so anything it might have
    # contained is unaccounted for, and "absent" would be an overstatement. Same for a step the
    # model had to be asked twice for.
    read_incomplete = read_failed or bool(unclassified) or bool(degraded_steps)

    kinds: list[dict[str, Any]] = []
    for kind, path, label_key in _BOARD_KINDS:
        items = _dig(spec, path)
        if kind == "arc_overview":
            items = list(items) + _dig(spec, "events")
        labels: list[str] = []
        for it in items[:_EVIDENCE_MAX]:
            if isinstance(it, dict):
                labels.append(str(it.get(label_key) or it.get("title") or it.get("name") or "").strip())
            else:
                labels.append(str(it).strip())
        labels = [x for x in labels if x]
        # A kind can be PRESENT and still wrong. `status` answers "may I claim absence?"; it says
        # nothing about completeness, so a run that collapsed to one character reads exactly like a
        # book with one character. This is the only completeness signal available without ground
        # truth: the run's own two steps counted the same thing and disagreed.
        shrank = (unread.get("step_disagreement") or {}).get(_DISAGREEMENT_KEY.get(kind, ""))
        entry = {
            "kind": kind,
            "count": len(items),
            # `unknown` is NOT a third flavour of absent — it is the honest refusal to claim either.
            "status": "present" if items else ("unknown" if read_incomplete else "absent"),
            "evidence": labels,
        }
        if isinstance(shrank, dict):
            # Reported, never repaired: a shrink is not necessarily wrong (materialize legitimately
            # merges duplicates). The author is told what to look at.
            entry["shrank_from"] = shrank.get("analyze")
        kinds.append(entry)

    return {
        "version": 1,
        "kinds": kinds,
        "recovered": [k["kind"] for k in kinds if k["status"] == "present"],
        "absent": [k["kind"] for k in kinds if k["status"] == "absent"],
        "unknown": [k["kind"] for k in kinds if k["status"] == "unknown"],
        # Echoed, never re-derived: the author reviews the spec, and a spec that came out thin
        # because half the document was unreadable must not look like a spec for a young book.
        "read": {
            "failed": read_failed,
            "unclassified": unclassified,
            "degraded_steps": degraded_steps,
            "path": unread.get("path") or "rules",
            "step_disagreement": unread.get("step_disagreement") or {},
            "note": unread.get("note") or "",
        },
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
        # Kept for the regression harness that still reads the POC fixture. It is a count of
        # `## 1.x`-shaped headings and means nothing on a document not written that way — `board`
        # is what a caller should read.
        "section_map_size": len(section_map),
        "board": spec_coverage_board(spec),
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
