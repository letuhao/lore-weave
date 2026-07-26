"""Build plan graph from NovelSystemSpec."""

from __future__ import annotations

from typing import Any


def build_graph(spec: dict[str, Any]) -> dict[str, Any]:
    nodes: list[dict[str, Any]] = []
    edges = list(spec.get("links", []))

    for arc in spec.get("arcs", []):
        nodes.append({"id": arc["id"], "type": "arc", "label": arc["title"]})
    for ev in spec.get("events", []):
        nodes.append({"id": ev["id"], "type": "event", "label": ev["title"], "arc_id": ev["arc_id"]})
    for var in spec.get("layers", {}).get("variables", []):
        nodes.append({"id": var["code"], "type": "variable", "label": var["name"]})

    arc_events: dict[str, list[str]] = {}
    for ev in spec.get("events", []):
        arc_events.setdefault(ev["arc_id"], []).append(ev["id"])
        edges.append(
            {
                "from": ev["arc_id"],
                "to": ev["id"],
                "kind": "arc_contains_event",
                "note": "",
            }
        )

    notes_total = 0
    notes_linked = 0
    for ev in spec.get("events", []):
        notes_total += len(ev.get("planner_notes", []))
        for note in ev.get("planner_notes", []):
            if any(e.get("from") == ev["id"] and note in (e.get("note") or "") for e in edges):
                notes_linked += 1
            elif any(e.get("from") == ev["id"] for e in edges):
                notes_linked += 1

    link_ratio = notes_linked / notes_total if notes_total else 1.0

    return {
        "version": 1,
        "nodes": nodes,
        "edges": edges,
        "stats": {
            "node_count": len(nodes),
            "edge_count": len(edges),
            "arc_event_counts": {k: len(v) for k, v in arc_events.items()},
            "planner_notes_linked_ratio": round(link_ratio, 3),
        },
    }
