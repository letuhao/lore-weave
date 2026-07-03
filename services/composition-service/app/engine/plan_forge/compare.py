"""Compare rules-based vs LLM NovelSystemSpec."""

from __future__ import annotations

from typing import Any


def _normalize_event_title(title: str) -> str:
    t = (title or "").strip().lower()
    if t.startswith("[") and "]" in t:
        t = t.split("]", 1)[-1].strip()
    if "—" in t:
        left, right = t.split("—", 1)
        if "event" in left:
            t = right.strip()
    return t


def _event_keys(events: list[dict[str, Any]]) -> set[str]:
    return {e.get("id", e.get("title", "")) for e in events}


def _event_title_keys(events: list[dict[str, Any]]) -> set[str]:
    return {_normalize_event_title(e.get("title", "")) for e in events if e.get("title")}


def _var_codes(spec: dict[str, Any]) -> set[str]:
    return {v["code"] for v in spec.get("layers", {}).get("variables", [])}


def compare_specs(rules: dict[str, Any], llm: dict[str, Any]) -> dict[str, Any]:
    rules_events = rules.get("events", [])
    llm_events = llm.get("events", [])
    rules_arc2 = [e for e in rules_events if e.get("arc_id") == "arc_2"]
    llm_arc2 = [e for e in llm_events if e.get("arc_id") == "arc_2"]

    rules_anchors = set(rules.get("charter", {}).get("consistency_anchors", []))
    llm_anchors = set(llm.get("charter", {}).get("consistency_anchors", []))

    rules_arc2_kind = next((a.get("arc_kind") for a in rules.get("arcs", []) if a.get("id") == "arc_2"), None)
    llm_arc2_kind = next((a.get("arc_kind") for a in llm.get("arcs", []) if a.get("id") == "arc_2"), None)

    overlap_events = _event_keys(rules_arc2) & _event_keys(llm_arc2)
    union_events = _event_keys(rules_arc2) | _event_keys(llm_arc2)
    event_overlap = len(overlap_events) / len(union_events) if union_events else 1.0

    overlap_titles = _event_title_keys(rules_arc2) & _event_title_keys(llm_arc2)
    union_titles = _event_title_keys(rules_arc2) | _event_title_keys(llm_arc2)
    title_overlap = len(overlap_titles) / len(union_titles) if union_titles else 1.0

    overlap_anchors = rules_anchors & llm_anchors
    union_anchors = rules_anchors | llm_anchors
    anchor_overlap = len(overlap_anchors) / len(union_anchors) if union_anchors else 1.0

    var_overlap = len(_var_codes(rules) & _var_codes(llm)) / max(len(_var_codes(rules) | _var_codes(llm)), 1)

    return {
        "rules_arc2_events": len(rules_arc2),
        "llm_arc2_events": len(llm_arc2),
        "event_id_overlap_ratio": round(event_overlap, 3),
        "event_title_overlap_ratio": round(title_overlap, 3),
        "only_in_rules_events": sorted(_event_keys(rules_arc2) - _event_keys(llm_arc2)),
        "only_in_llm_events": sorted(_event_keys(llm_arc2) - _event_keys(rules_arc2)),
        "only_in_rules_titles": sorted(_event_title_keys(rules_arc2) - _event_title_keys(llm_arc2)),
        "only_in_llm_titles": sorted(_event_title_keys(llm_arc2) - _event_title_keys(rules_arc2)),
        "anchor_overlap_ratio": round(anchor_overlap, 3),
        "variable_overlap_ratio": round(var_overlap, 3),
        "rules_arc2_kind": rules_arc2_kind,
        "llm_arc2_kind": llm_arc2_kind,
        "arc2_kind_match": rules_arc2_kind == llm_arc2_kind,
    }


def format_compare_report(metrics: dict[str, Any]) -> str:
    lines = [
        "# PlanForge — Rules vs LLM Comparison",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Rules Arc 2 events | {metrics['rules_arc2_events']} |",
        f"| LLM Arc 2 events | {metrics['llm_arc2_events']} |",
        f"| Event ID overlap | {metrics['event_id_overlap_ratio']:.0%} |",
        f"| Event title overlap | {metrics['event_title_overlap_ratio']:.0%} |",
        f"| Anchor overlap | {metrics['anchor_overlap_ratio']:.0%} |",
        f"| Variable overlap | {metrics['variable_overlap_ratio']:.0%} |",
        f"| Arc 2 kind match | {metrics['arc2_kind_match']} (rules={metrics['rules_arc2_kind']}, llm={metrics['llm_arc2_kind']}) |",
        "",
        "## Only in rules",
        "",
    ]
    for eid in metrics["only_in_rules_events"]:
        lines.append(f"- `{eid}`")
    lines.extend(["", "## Only in LLM", ""])
    for eid in metrics["only_in_llm_events"]:
        lines.append(f"- `{eid}`")
    return "\n".join(lines)
