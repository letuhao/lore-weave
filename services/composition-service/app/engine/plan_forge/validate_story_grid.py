"""D-PLANFORGE-STORY-GRID-POC — Story Grid structural rules, scored against the
same story-plan-v1 fixture the 7 core PlanForge rules (validate.run_rules)
already pass.

Per docs/specs/2026-07-05-narrative-forge/00_METHODOLOGY.md decision #3: Story
Grid is NOT a swap-in for the current 7 rules. It requires its OWN POC, scored
side-by-side against the same fixtures the 7 rules already pass, before
adoption is even considered. This module IS that POC — it is deliberately NOT
imported by validate.run_rules / validate_golden. Wiring it into the real
gate is a follow-up decision for whoever reads the POC's findings, not assumed
here.

Story Grid (Shawn Coyne, "The Story Grid") is operationalized as two
mechanically-checkable rules against the CURRENT NovelSystemSpec schema (event
var_deltas, arc metadata) — no new spec fields were added, to keep the "same
fixtures" comparison honest:

- sg_value_shift_per_scene: Story Grid's foundational unit test — a scene that
  doesn't turn a value at stake isn't a scene, full stop. Checked as: does
  every event in the arc under test carry at least one var_delta?
- sg_negative_turn_exists: Story Grid rejects a monotonically-positive arc —
  the value at stake must swing both ways (a cost alongside a gain), or
  there's no real dramatic tension. Checked as: does the arc's var_deltas
  include at least one cost-coded variable (CD, or a decreasing HA) alongside
  at least one gain-coded one (PA)?

Other Story Grid concepts — the Five Commandments' beat sequencing (Inciting
Incident / Progressive Complications / Crisis / Climax / Resolution) and
genre-level obligatory scenes — are NOT operationalized here. They need a
beat_type/scene-role field the spec does not carry yet; that is a real,
named scope boundary, not a silently skipped one.
"""

from __future__ import annotations

from typing import Any

_COST_CODED_VARIABLES = {"CD"}
_GAIN_CODED_VARIABLES = {"PA"}


def run_story_grid_rules(spec: dict[str, Any], arc_id: str = "arc_2") -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []

    arc_events = [e for e in spec.get("events", []) if e.get("arc_id") == arc_id]
    no_shift = [e["id"] for e in arc_events if not e.get("var_deltas")]
    results.append(
        {
            "rule": "sg_value_shift_per_scene",
            "pass": not no_shift,
            "detail": (
                f"events_without_value_shift={no_shift}"
                if no_shift
                else f"checked={len(arc_events)}"
            ),
        }
    )

    deltas = [d for e in arc_events for d in e.get("var_deltas", []) if isinstance(d, dict)]
    has_cost = any(d.get("variable") in _COST_CODED_VARIABLES for d in deltas)
    has_ha_decrease = any(
        d.get("variable") == "HA" and str(d.get("delta", "")).startswith("-") for d in deltas
    )
    has_gain = any(d.get("variable") in _GAIN_CODED_VARIABLES for d in deltas)
    results.append(
        {
            "rule": "sg_negative_turn_exists",
            "pass": (has_cost or has_ha_decrease) and has_gain,
            "detail": f"has_cost={has_cost or has_ha_decrease} has_gain={has_gain}",
        }
    )

    return results


def format_story_grid_report(
    core_rules: list[dict[str, Any]], sg_rules: list[dict[str, Any]]
) -> str:
    lines = ["# Story Grid POC — side-by-side vs core PlanForge rules", ""]
    lines.append("## Core rules (existing 7, unchanged baseline)")
    lines.append("")
    for r in core_rules:
        status = "PASS" if r["pass"] else "FAIL"
        lines.append(f"- `{r['rule']}`: {status} — {r.get('detail', '')}")
    lines.append("")
    lines.append("## Story Grid rules (POC, not wired into the real gate)")
    lines.append("")
    for r in sg_rules:
        status = "PASS" if r["pass"] else "FAIL"
        lines.append(f"- `{r['rule']}`: {status} — {r.get('detail', '')}")
    lines.append("")
    sg_fail = [r for r in sg_rules if not r["pass"]]
    if sg_fail:
        lines.append(
            f"**Finding: Story Grid surfaces {len(sg_fail)} gap(s) the current 7 rules do not check.**"
        )
    else:
        lines.append(
            "**Finding: Story Grid rules pass; no gap beyond the current 7 rules found on this fixture.**"
        )
    return "\n".join(lines)
