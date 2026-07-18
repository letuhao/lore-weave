"""Compile NovelSystemSpec to LW platform artifacts and PlanningPackage.

The codegen backend emits what the IR says, never what the POC fixture said (DA-14).
`genre_tags` and `constraints` reach `cast_plan.propose_cast` through the `plan_pipeline`
worker, so a fixture constant here silently re-genres every book that compiles.
"""

from __future__ import annotations

from typing import Any

# `VariableDef` declares `range` as free text ("0-100") and carries no `initial`, so a
# variable needing a non-zero baseline (the fixture's HA started full) cannot be expressed.
# Every variable therefore starts at 0. BPS-21 tracks the contract change; nothing reads
# `planner_state` today, so the wrong baseline cannot currently affect generation.
_DEFAULT_VARIABLE_INITIAL = 0

# The charter is author-supplied and unbounded; constraints ride into every generation
# prompt, so cap them rather than let a long charter crowd out the premise.
_MAX_CONSTRAINTS = 12


def compile_artifacts(
    spec: dict[str, Any],
    arc_id: str,
    *,
    genre_tags: list[str] | None = None,
) -> dict[str, Any]:
    """Compile a validated `NovelSystemSpec` for ONE arc.

    `arc_id` is required: it once defaulted to the fixture's ``"arc_2"``, so a caller that
    forgot it silently compiled a different book's arc. `genre_tags` is caller-supplied
    because the spec has nowhere to declare a genre — absent, the package declares none
    rather than inventing one.
    """
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

    # Entry state = one slot per variable the SPEC declares (was the fixture's PA/HA/CD/THR,
    # plus a loop that could only ever re-assign HA=100 over its own default — a no-op).
    planner_state: dict[str, Any] = {
        v["code"]: _DEFAULT_VARIABLE_INITIAL
        for v in spec.get("layers", {}).get("variables", [])
    }
    planner_state["tier"] = "baseline"

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

    # The arc's SUMMARY reaches the premise too (27 V2-G).
    #
    # It never did, and nobody noticed, because the proposer used to HARDCODE both `theme` and
    # `summary` — two paraphrases of the same sentence, so dropping one lost nothing. Now that they
    # are parsed, they are different things: `theme` is the author's `**Theme:**` field, and
    # `summary` carries what they actually said about the arc in prose ("this is not a power arc; it
    # is a discovery-and-price arc"). That line is the single most load-bearing sentence in the
    # block — it is why they emphasised it — and it was going nowhere near the prompt.
    premise_parts = [
        f"Arc: {arc['title']}" if arc else arc_id,
        f"Theme: {arc['theme']}" if arc and arc.get("theme") else "",
        f"Summary: {arc['summary']}" if arc and arc.get("summary") else "",
        f"Kind: {arc['arc_kind']}" if arc and arc.get("arc_kind") else "",
        "Key events:",
    ]
    for ev in arc_events:
        premise_parts.append(f"- {ev['title']}: {ev.get('goal') or ev['synopsis'][:120]}")
    charter = spec.get("charter", {})
    canon_parts = charter.get("consistency_anchors", [])[:4]
    # The charter already carries both, and `propose.py` populates them from the plan doc;
    # `style_constraints` was dead schema while three fixture strings stood in its place.
    constraints = [
        *charter.get("style_constraints", []),
        *charter.get("forbids", []),
    ][:_MAX_CONSTRAINTS]

    premise = "\n".join(p for p in premise_parts if p)[:4000]

    package = {
        "arc_id": arc_id,
        # The arc's HUMAN title. It already existed on `outline_skeleton[0]` and was DISCARDED: the
        # linker (27 V2-E) receives only `package`, so without this it titled the book's arc with
        # 500 chars of the `premise` blob (which is "Arc: X / Theme: Y / Key events: ..." laid out
        # over several lines) — and that is what the Plan Hub, the arc picker and the navigator all
        # rendered as the arc's NAME. `premise` is the SUMMARY; this is the title.
        "arc_title": (arc["title"] if arc else arc_id),
        "premise": premise,
        "canon": "\n".join(canon_parts),
        "planner_state": planner_state,
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
        "genre_tags": list(genre_tags or []),
        "chapters": chapters,
    }

    # `planner_state_init` and `working_memory_charter` were emitted here and read by NOTHING
    # (verified across every service + the frontend); the latter hardcoded `language: "vi"`.
    # Dropped per DA-13. `outline_skeleton` stays — Phase E links it into `structure_node`.
    return {
        "glossary_seeds": glossary_seeds,
        "outline_skeleton": outline_skeleton,
        "planning_package": package,
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
