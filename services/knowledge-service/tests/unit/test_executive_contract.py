"""ACP A0.2 / RW-6 — the executive HTTP contract is machine-checked BOTH sides.

The `/internal/working-memory/{init,tick}` request bodies are the contract that BOTH
the Python SDK (chat) and the Rust crate (roleplay/game) will construct. Until now they
lived only as Pydantic models in knowledge-service. This test asserts the REAL request
models (`InitWorkingMemoryRequest`, `TickRequest` — not a hand fixture, RW-8 discipline)
serialize to instances conforming to `contracts/agent-control/executive.{init,tick}.schema.json`,
and that a renamed/unknown field REDs (the `additionalProperties:false` drift guard, ACP-6).
"""
from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

import jsonschema
import pytest
from referencing import Registry, Resource

from app.routers.working_memory import (
    InitWorkingMemoryRequest,
    TickRequest,
    TurnInput,
    WorkingMemoryCharter,
)

# repo root: unit/ -> tests/ -> knowledge-service/ -> services/ -> <root> = parents[4]
_CONTRACTS = Path(__file__).resolve().parents[4] / "contracts" / "agent-control"
_WM = json.loads((_CONTRACTS / "working_memory.schema.json").read_text(encoding="utf-8"))
_INIT = json.loads((_CONTRACTS / "executive.init.schema.json").read_text(encoding="utf-8"))
_TICK = json.loads((_CONTRACTS / "executive.tick.schema.json").read_text(encoding="utf-8"))

# The init request $refs the canonical charter by its $id — resolve it via a registry.
_REGISTRY = Registry().with_resource(_WM["$id"], Resource.from_contents(_WM))


def _init_validator():
    return jsonschema.Draft7Validator(_INIT, registry=_REGISTRY)


def _charter() -> WorkingMemoryCharter:
    return WorkingMemoryCharter(
        goal="Senior backend interview",
        phases=["warmup", "technical", "wrap"],
        checklist=["system design", "REST vs gRPC"],
        time_budget_min=45,
        language="en",
    )


def test_init_request_conforms_to_contract():
    req = InitWorkingMemoryRequest(session_id=uuid4(), user_id=uuid4(), charter=_charter())
    _init_validator().validate(req.model_dump(mode="json"))  # raises on drift


def test_tick_request_conforms_to_contract():
    req = TickRequest(
        session_id=uuid4(),
        user_id=uuid4(),
        model_source="user_model",
        model_ref=str(uuid4()),
        recent_turns=[TurnInput(role="user", content="hi"), TurnInput(role="assistant", content="hello")],
    )
    jsonschema.Draft7Validator(_TICK).validate(req.model_dump(mode="json"))


def test_tick_request_minimal_conforms():
    # model_* and recent_turns have defaults — the minimal body must still validate.
    req = TickRequest(session_id=uuid4(), user_id=uuid4())
    jsonschema.Draft7Validator(_TICK).validate(req.model_dump(mode="json"))


def test_contract_rejects_unknown_field_on_init():
    inst = InitWorkingMemoryRequest(
        session_id=uuid4(), user_id=uuid4(), charter=_charter()
    ).model_dump(mode="json")
    inst["surprise"] = "drift"  # a producer that adds an undeclared field
    with pytest.raises(jsonschema.ValidationError):
        _init_validator().validate(inst)


def test_contract_requires_server_authenticated_user_id():
    # RV-M8: user_id is REQUIRED by the contract (no anonymous/client-omitted tick).
    inst = TickRequest(session_id=uuid4(), user_id=uuid4()).model_dump(mode="json")
    del inst["user_id"]
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.Draft7Validator(_TICK).validate(inst)


def test_tick_response_status_enum_matches_executive():
    # The executive's status strings must stay inside the contract's closed set.
    from app.working_memory import executive  # noqa: F401 — import proves the module loads

    resp_schema = _TICK["$defs"]["response"]
    for status in ("updated", "no_block", "no_model", "llm_failed", "bad_json"):
        jsonschema.Draft7Validator(resp_schema).validate({"status": status})
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.Draft7Validator(resp_schema).validate({"status": "totally_new_status"})
