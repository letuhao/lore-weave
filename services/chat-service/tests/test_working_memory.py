"""Unit tests for the interview-roleplay working_memory model (M1).

Validates: the Pydantic WorkingMemory model round-trips, `remaining()` derives
correctly, charter required fields are enforced, and a serialized instance
conforms to the cross-service JSON Schema contract
(contracts/agent-control/working_memory.schema.json).
"""
from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest
from pydantic import ValidationError

from app.models import WorkingMemory, WorkingMemoryCharter, WorkingMemoryState

# contracts/agent-control/working_memory.schema.json — repo root is 3 parents up
# from this file: tests/ -> chat-service/ -> services/ -> <root>. (Moved from
# contracts/interview/ at the Agent Control Plane extraction, 2026-07-16.)
_SCHEMA_PATH = (
    Path(__file__).resolve().parents[3]
    / "contracts"
    / "agent-control"
    / "working_memory.schema.json"
)


def _charter(**over) -> WorkingMemoryCharter:
    base = dict(
        goal="Senior backend interview",
        phases=["warmup", "technical", "behavioral", "wrap"],
        checklist=["system design", "conflict story", "REST vs gRPC"],
        time_budget_min=60,
        language="vi",
    )
    base.update(over)
    return WorkingMemoryCharter(**base)


def test_working_memory_round_trips():
    wm = WorkingMemory(charter=_charter())
    dumped = wm.model_dump()
    again = WorkingMemory.model_validate(dumped)
    assert again.charter.goal == "Senior backend interview"
    assert again.version == 1
    # state defaults: empty progress
    assert again.state.covered == []
    assert again.state.phase == ""


def test_remaining_is_derived_from_checklist_minus_covered():
    wm = WorkingMemory(
        charter=_charter(),
        state=WorkingMemoryState(phase="technical", covered=["REST vs gRPC", "system design"]),
    )
    assert wm.remaining() == ["conflict story"]


def test_remaining_full_when_nothing_covered():
    wm = WorkingMemory(charter=_charter())
    assert wm.remaining() == ["system design", "conflict story", "REST vs gRPC"]


def test_charter_requires_goal_and_phases():
    with pytest.raises(ValidationError):
        WorkingMemoryCharter(phases=["a"], language="vi")  # missing goal
    with pytest.raises(ValidationError):
        WorkingMemoryCharter(goal="g", phases=[], language="vi")  # phases min_length=1


def test_instance_conforms_to_json_schema_contract():
    schema = json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))
    wm = WorkingMemory(
        charter=_charter(),
        state=WorkingMemoryState(phase="technical", covered=["REST vs gRPC"], elapsed_min=23),
    )
    # model_dump(mode="json") gives JSON-native types (no UUID/datetime here, but
    # keeps the contract check honest for future fields).
    jsonschema.validate(instance=wm.model_dump(mode="json"), schema=schema)


def test_schema_rejects_unknown_charter_field():
    schema = json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))
    bad = {
        "version": 1,
        "charter": {
            "goal": "g",
            "phases": ["warmup"],
            "checklist": [],
            "language": "vi",
            "surprise": "not allowed",  # additionalProperties: false
        },
        "state": {"phase": "", "covered": []},
    }
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance=bad, schema=schema)


def test_parse_tolerates_a_rubric_carrying_seed():
    # LOW-2 (review-impl fix): roleplay's freeze() emits a top-level `rubric` sidecar
    # (A0.3). chat's WorkingMemory (extra='ignore') must PARSE such a seed and simply
    # drop the rubric — the anchor doesn't need it; /evaluate reads rubric separately.
    from app.services.working_memory import parse_working_memory

    seed = {
        "version": 1,
        "charter": {"goal": "g", "phases": ["warmup"], "checklist": [], "language": "en"},
        "state": {"phase": "", "covered": []},
        "rubric": {"dimensions": ["clarity"]},
    }
    wm = parse_working_memory(seed)
    assert wm is not None, "a rubric-carrying seed must parse (not None)"
    assert wm.charter.goal == "g"
    assert not hasattr(wm, "rubric")  # dropped by extra='ignore' — anchor never sees it


def test_question_target_survives_parse_into_the_charter():
    # RV-M4: question_target MUST survive parse — the model defaults to extra='ignore', so an
    # UNDECLARED field would be silently dropped and the anchor could never enforce the wrap.
    # Declaring it on WorkingMemoryCharter (A4) is what keeps it.
    from app.services.working_memory import parse_working_memory

    seed = {
        "version": 1,
        "charter": {"goal": "g", "phases": ["warmup"], "checklist": [], "language": "en",
                    "question_target": 5},
        "state": {"phase": "", "covered": []},
    }
    wm = parse_working_memory(seed)
    assert wm is not None
    assert wm.charter.question_target == 5  # carried through — NOT dropped
    # an older charter without it is still valid (additive) and defaults to None.
    old = parse_working_memory({"version": 1, "charter": {"goal": "g", "phases": ["w"],
                                "checklist": [], "language": "en"}, "state": {"phase": "", "covered": []}})
    assert old is not None and old.charter.question_target is None
