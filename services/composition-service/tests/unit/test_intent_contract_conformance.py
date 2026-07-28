"""The intent router and `contracts/api/composition-service/intent.v1.yaml` must agree.

Contract-first is a repo rule, but a contract nobody checks is a document, not a contract — it
drifts the first time a route is added in a hurry and then actively misleads whoever reads it next.
glossary-service enforces this with `TestOpenAPIRouteConformance`; composition-service has no such
gate, so this is the scoped version for the router being added.

It reads the YAML at RUNTIME, so a contract-only edit is caught even though nothing recompiles.

Also pinned here: the two closed sets that span the service boundary (`action` and `slot`). They are
the frontend-tool bug class — a closed-set arg whose enum lives on only one side lets a caller send a
value that validates nowhere, and the failure is a silent no-op rather than a 422.
"""
from __future__ import annotations

import pathlib

import pytest

yaml = pytest.importorskip("yaml")

from app.db.repositories.outline import OutlineRepo  # noqa: E402
from app.routers import intent as intent_router  # noqa: E402
from app.services.intent_fsm import slots  # noqa: E402
from app.services.intent_fsm.service import ACTIONS  # noqa: E402

# tests/unit/x.py → tests/ → composition-service/ → services/ → REPO ROOT
_CONTRACT = (pathlib.Path(__file__).resolve().parents[4]
             / "contracts" / "api" / "composition-service" / "intent.v1.yaml")


@pytest.fixture(scope="module")
def contract() -> dict:
    assert _CONTRACT.is_file(), f"missing contract: {_CONTRACT}"
    return yaml.safe_load(_CONTRACT.read_text(encoding="utf-8"))


def _routed() -> set[tuple[str, str]]:
    out = set()
    for r in intent_router.router.routes:
        for m in getattr(r, "methods", set()) - {"HEAD", "OPTIONS"}:
            out.add((r.path, m.lower()))
    return out


def _documented(contract: dict) -> set[tuple[str, str]]:
    return {(path, method)
            for path, ops in contract["paths"].items()
            for method in ops if method in ("get", "post", "put", "patch", "delete")}


def test_no_route_is_undocumented(contract):
    """A public route with no contract entry is how an API grows a surface nobody agreed to."""
    assert _routed() - _documented(contract) == set()


def test_no_documented_path_is_phantom(contract):
    """The inverse, and the one that rots quietly: a documented route that does not exist reads as
    shipped to anyone building against it."""
    assert _documented(contract) - _routed() == set()


def test_the_action_enum_matches_on_BOTH_sides(contract):
    """`action` is a closed set crossing a service boundary. The frontend-tool contract's rule
    exists because this exact drift shipped once: a value with no enum reached a resolver that
    silently no-opped, and the model then reported success it never had."""
    body = contract["paths"]["/v1/composition/intent/runs/{run_id}/answer"]["post"]
    schema = body["requestBody"]["content"]["application/json"]["schema"]
    assert set(schema["properties"]["action"]["enum"]) == set(ACTIONS)
    # …and the Pydantic model must actually reject anything outside it, not merely describe it.
    with pytest.raises(Exception):
        intent_router.Answer(action="approve")


def test_the_slot_enum_matches_the_registry_AND_the_merge(contract):
    """Three things have to agree, and the third is the one with teeth: a slot the contract
    advertises but the re-plan merge does not carry would be settled by a caller and then deleted by
    the next re-plan."""
    documented = contract["components"]["schemas"]["Slot"]["enum"]
    assert documented == list(slots.SLOT_ORDER), "contract and registry disagree on the slots"
    assert set(documented) <= set(OutlineRepo.INTENT_SLOTS), \
        "the contract advertises a slot the re-plan merge would silently destroy"


def test_the_status_enum_covers_every_state_the_machine_can_reach(contract):
    """A status the FSM can produce but the contract omits is a state a client cannot handle — and
    it will be reached, because these are the failure states."""
    from app.services.intent_fsm.service import _LIVE

    documented = set(contract["components"]["schemas"]["Status"]["enum"])
    assert set(_LIVE) | {"done", "cancelled", "failed"} == documented


def test_the_outcome_enum_keeps_offered_distinct_from_skipped(contract):
    """The instrument's acceptance rate is built on this difference: `offered` means the author has
    not answered, `skipped` means they passed. Folding them would flatter an abandoned run."""
    outcomes = contract["components"]["schemas"]["SlotRecord"]["properties"]["outcome"]["enum"]
    assert {"offered", "skipped", "applied", "absent", "proposal_failed"} == set(outcomes)
