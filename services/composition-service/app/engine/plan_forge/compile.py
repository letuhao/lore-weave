"""Compile NovelSystemSpec to LW platform artifacts and PlanningPackage."""

from __future__ import annotations

from typing import Any


def compile_artifacts(spec: dict[str, Any], arc_id: str = "arc_2") -> dict[str, Any]:
    arc = next((a for a in spec.get("arcs", []) if a["id"] == arc_id), None)
    arc_events = [e for e in spec.get("events", []) if e.get("arc_id") == arc_id]

    glossary_seeds: list[dict[str, Any]] = []
    for ch in spec.get("layers", {}).get("characters", []):
        glossary_seeds.append(
            {
                "name": ch["name"],
                "kind_code": "character",
                "attributes": {
                    "role": ch["role"],
                    "traits": ", ".join(ch.get("traits", [])),
                    "baseline_notes": ch.get("baseline_notes", ""),
                },
            }
        )
    for mech in spec.get("layers", {}).get("mechanics", []):
        glossary_seeds.append(
            {
                "name": mech["name"],
                "kind_code": "concept",
                "attributes": {
                    "rules": "; ".join(mech.get("rules", [])[:5]),
                },
            }
        )

    planner_state_init = {"PA": 0, "HA": 100, "CD": 0, "THR": 0, "tier": "baseline"}
    if arc and arc.get("exit_state"):
        pass  # exit state is end-of-arc; package uses entry
    for ev in arc_events:
        for d in ev.get("var_deltas", []):
            if d["variable"] == "HA" and "100" in d.get("delta", ""):
                planner_state_init["HA"] = 100

    outline_skeleton = [
        {"kind": "arc", "title": arc["title"] if arc else arc_id, "arc_id": arc_id}
    ]
    chapters = []
    for i, ev in enumerate(arc_events, start=1):
        chapters.append(
            {
                "title": ev["title"],
                "ordinal": i,
                "event_id": ev["id"],
            }
        )
        outline_skeleton.append(
            {
                "kind": "chapter",
                "title": ev["title"],
                "ordinal": i,
                "parent_arc": arc_id,
                "event_id": ev["id"],
            }
        )

    premise_parts = [
        f"Arc: {arc['title']}" if arc else arc_id,
        f"Theme: {arc['theme']}" if arc else "",
        "Key events:",
    ]
    for ev in arc_events:
        premise_parts.append(f"- {ev['title']}: {ev.get('goal') or ev['synopsis'][:120]}")
    canon_parts = spec.get("charter", {}).get("consistency_anchors", [])[:4]
    constraints = [
        "HA must stay high until PA escalation events",
        "Preserve dry humor in early events",
        "THR: show phenomena only, no explanation",
    ]
    constraints.extend(spec.get("charter", {}).get("forbids", [])[:2])

    premise = "\n".join(p for p in premise_parts if p)[:4000]

    package = {
        "arc_id": arc_id,
        "premise": premise,
        "canon": "\n".join(canon_parts),
        "planner_state": planner_state_init,
        "constraints": constraints,
        "events": [
            {
                "id": e["id"],
                "synopsis": e["synopsis"],
                "planner_notes": e.get("planner_notes", []),
                "var_deltas": e.get("var_deltas", []),
            }
            for e in arc_events
        ],
        "genre_tags": ["xianxia", "cultivation", "psychological"],
        "chapters": chapters,
    }

    return {
        "glossary_seeds": glossary_seeds,
        "outline_skeleton": outline_skeleton,
        "planner_state_init": planner_state_init,
        "planning_package": package,
        "working_memory_charter": {
            "goal": arc["theme"] if arc else "Plan arc",
            "phases": [e["title"] for e in arc_events],
            "checklist": spec.get("charter", {}).get("consistency_anchors", []),
            "language": "vi",
        },
    }


def mock_pipeline_result(package: dict[str, Any]) -> dict[str, Any]:
    """Fixture-quality PipelineResult without live LLM."""
    chapters = package.get("chapters", [])
    scenes = []
    for ch in chapters:
        scenes.append(
            {
                "chapter_ordinal": ch["ordinal"],
                "chapter_title": ch["title"],
                "scenes": [
                    {
                        "title": f"{ch['title']} — scene 1",
                        "synopsis": next(
                            (e["synopsis"] for e in package.get("events", []) if e["id"] == ch.get("event_id")),
                            "",
                        )[:300],
                        "tension": 30 + ch["ordinal"] * 8,
                        "present_entity_ids": ["protagonist"],
                    }
                ],
            }
        )
    return {
        "mock": True,
        "arc_id": package["arc_id"],
        "premise_chars": len(package["premise"]),
        "chapter_count": len(chapters),
        "scene_count": len(scenes),
        "cast": [{"name": "[TBD]", "role": "protagonist", "is_new": False}],
        "canon_excerpt": package["canon"][:200],
        "scenes_by_chapter": scenes,
    }
