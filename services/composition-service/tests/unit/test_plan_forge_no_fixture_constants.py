"""BPS-20 / DA-14 — the codegen backend must emit what the IR says, never what the POC fixture said.

`compile.py` used to hardcode the POC novel's genre tags ("xianxia", "cultivation",
"psychological") and three of its story constraints ("Preserve dry humor in early events", …)
into EVERY book's PlanningPackage. Those are not dead data: `plan_forge_service` feeds
`package["genre_tags"]` into `pipe_input` -> the `plan_pipeline` worker ->
`cast_plan.propose_cast(premise, source_language, genre_tags)`. A romance thriller was
planned as cultivation fiction.

These tests compile a spec that shares NOTHING with the fixture, so any fixture string that
survives into the output is a leak by construction.
"""

from __future__ import annotations

import pytest

from app.engine.plan_forge.compile import compile_artifacts

# Every literal the old backend baked in. None may appear in output for an unrelated spec.
FIXTURE_LEAKS = [
    "xianxia",
    "cultivation",
    "psychological",
    "dry humor",
    "HA must stay high",
    "THR",
    "arc_2",
]


def _romance_spec() -> dict:
    """A spec with no overlap with the xianxia fixture — different genre, arc id, variables."""
    return {
        "version": "1",
        "meta": {"title": "Harbour Lights", "source_checksum": "x", "open_questions": []},
        "charter": {
            "consistency_anchors": ["The lighthouse is always visible from the pier"],
            "forbids": ["No supernatural elements"],
            "style_constraints": ["Close third person", "Present tense"],
        },
        "layers": {
            "characters": [
                {"name": "Mara", "role": "protagonist", "traits": ["guarded"], "baseline_notes": ""}
            ],
            "mechanics": [],
            "variables": [
                {"code": "TR", "name": "Trust", "range": "0-100", "transition_rules": []},
                {"code": "GR", "name": "Grief", "range": "0-100", "transition_rules": []},
            ],
        },
        "arcs": [{"id": "arc_1", "title": "The Return", "theme": "coming home", "arc_kind": "romance"}],
        "events": [
            {
                "id": "arc_1_event_1",
                "arc_id": "arc_1",
                "title": "Arrival",
                "synopsis": "Mara steps off the ferry.",
                "goal": "Establish the harbour",
                "var_deltas": [],
            },
            {
                "id": "arc_1_event_2",
                "arc_id": "arc_1",
                "title": "The Letter",
                "synopsis": "A letter surfaces.",
                "goal": "Raise the question",
                "var_deltas": [],
            },
        ],
        "links": [],
    }


@pytest.fixture
def compiled() -> dict:
    return compile_artifacts(_romance_spec(), arc_id="arc_1")


def test_no_fixture_string_survives_into_output(compiled):
    """DA-14 — nothing from the POC novel may appear when compiling an unrelated spec."""
    blob = repr(compiled).lower()
    leaked = [s for s in FIXTURE_LEAKS if s.lower() in blob]
    assert leaked == [], f"POC fixture constants leaked into codegen output: {leaked}"


def test_genre_tags_are_not_fabricated(compiled):
    """The spec declares no genre, so the package must not invent one."""
    assert compiled["planning_package"].get("genre_tags", []) == []


def test_genre_tags_pass_through_when_supplied():
    """When the caller knows the genre, it reaches the package verbatim."""
    out = compile_artifacts(_romance_spec(), arc_id="arc_1", genre_tags=["romance", "literary"])
    assert out["planning_package"]["genre_tags"] == ["romance", "literary"]


def test_constraints_come_from_the_charter(compiled):
    """`charter.style_constraints` + `charter.forbids` are the real, populated source
    (propose.py:307 fills style_constraints) — it was dead schema while fixture strings
    stood in its place."""
    constraints = compiled["planning_package"]["constraints"]
    assert "Close third person" in constraints
    assert "Present tense" in constraints
    assert "No supernatural elements" in constraints


def test_planner_state_derives_from_declared_variables(compiled):
    """BPS-21 — the state keys follow `layers.variables`, not the fixture's PA/HA/CD/THR."""
    state = compiled["planning_package"]["planner_state"]
    assert set(state) - {"tier"} == {"TR", "GR"}


def test_arc_id_is_required():
    """`arc_id` defaulted to the fixture's `"arc_2"`; a compile with no arc must not silently
    target a fixture arc."""
    with pytest.raises(TypeError):
        compile_artifacts(_romance_spec())  # type: ignore[call-arg]


def test_dead_payloads_are_gone(compiled):
    """E3/DA-13 — `planner_state_init` and `working_memory_charter` had no reader anywhere
    (the latter hardcoded `language: "vi"`). `outline_skeleton` stays: Phase E links it."""
    assert "planner_state_init" not in compiled
    assert "working_memory_charter" not in compiled
    assert "outline_skeleton" in compiled
