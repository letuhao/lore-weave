"""P14-SUPPLIER-NOT-ON-SURFACE — R1 forced the tool the request names and nothing it needs.

🔴 THE DEFECT. R1 answerability guarantees that a tool whose own declared vocabulary answers the
request reaches the wire "whatever the budget, the domain selection or the rail decided". It stopped
at depth 1. A user names a GOAL, not an intermediate step, so a supplier is matched only by
accident — and every tool in P14 failed on an id whose supplier the request's words do not describe.

MEASURED 2026-08-23, from chat-service's own per-pass wire log:

    plan_bootstrap_apply       requires proposal_id   advertised on 21 passes
    plan_bootstrap_propose     emits proposal_id      advertised on  ZERO

and the platform ALREADY DECLARES the pairing as data — contracts/agent-runtime-tool-contracts.json
holds `argument_emitters: {plan_bootstrap_apply: {proposal_id: plan_bootstrap_propose}}`. The answer
was on disk and was not used to put the supplier on the wire. The model ran
composition_package_tree -> plan_compile -> composition_list_outline: it compiled the plan and then
read the outline, because the step between them was never offered.

The tiers refute the tempting explanation. "The hot-seed budget favours writes over reads" fits two
of the four measured pairs and fails the other two: plan apply/propose are BOTH Tier A, and
composition_arc_template_get/_list are BOTH Tier R. It is depth, not tier.

AND IT HAS TO BE TRANSITIVE, which composition_reference_update proves: reference_id comes from
composition_find_references, which was already on every one of 40 passes and itself refused for its
OWN missing entity_id. A one-hop fix would have looked correct on the other instances and left that
turn dying one call later.

DECLARED DATA ONLY — the suppliers come from the registry map, never from a name or a prefix, so the
surface can only widen where the platform has already written down who supplies what.
"""
from __future__ import annotations

import pytest

from app.services.stream_service import _advertise_discovery_tools

CONSUMER = "plan_bootstrap_apply"
SUPPLIER = "plan_bootstrap_propose"


def _td(name: str, *, synonyms: list[str] | None = None, required: list[str] | None = None,
        tier: str = "A") -> dict:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": f"{name} does a thing.",
            "parameters": {"type": "object",
                           "properties": {a: {"type": "string"} for a in (required or [])},
                           "required": list(required or [])},
            "_meta": {"synonyms": list(synonyms or []), "tier": tier},
        },
    }


def _advertised(catalog: dict, request_text: str, **kw) -> set[str]:
    out = _advertise_discovery_tools(catalog, [], [], request_text=request_text, **kw)
    return {(t.get("function") or {}).get("name") for t in out}


@pytest.fixture()
def catalog() -> dict:
    return {
        CONSUMER: _td(CONSUMER, synonyms=["create the chapters", "make the plan real"],
                      required=["book_id", "proposal_id"]),
        SUPPLIER: _td(SUPPLIER, synonyms=["preview the chapters"], required=["book_id", "run_id"]),
    }


def test_forcing_a_tool_also_forces_the_supplier_of_its_required_id(catalog):
    """🔴 THE DEFECT. The request names the consumer and only the consumer."""
    names = _advertised(catalog, "Create the chapters — make the plan real for this book.")
    assert CONSUMER in names, "R1 no longer forces the tool the request names — re-anchor this test"
    assert SUPPLIER in names, (
        "R1 put the tool on the wire and left the only tool that can supply its required "
        "proposal_id off it, so the model is offered a move it cannot make"
    )


def test_it_reads_the_DECLARED_map_and_not_the_name(catalog):
    """THE CONTROL that keeps this honest. plan_bootstrap_propose is not pulled in because it looks
    like a sibling of plan_bootstrap_apply — rename the declaration's target and the supplier must
    stop arriving. A prefix rule would pass this test by accident and would also drag in every
    unrelated plan_* tool."""
    from app.services import stream_service

    original = stream_service._tool_contract_registry
    stream_service._tool_contract_registry = lambda: {"argument_emitters": {}}
    try:
        names = _advertised(catalog, "Create the chapters — make the plan real for this book.")
    finally:
        stream_service._tool_contract_registry = original
    assert CONSUMER in names
    assert SUPPLIER not in names, (
        "the supplier arrived with an EMPTY declaration map, so it is being inferred from "
        "something other than the registry — a name, a prefix, or the catalog's shape"
    )


def test_a_tool_with_no_declared_emitter_widens_nothing(catalog):
    """Most tools declare no emitter, and for them this must be a strict no-op: the surface may only
    grow where the platform has already written down who supplies what."""
    catalog["book_list"] = _td("book_list", synonyms=["list my books"], required=[], tier="R")
    names = _advertised(catalog, "List my books.")
    assert names & {"book_list"}, "the answerable tool itself is missing — re-anchor"
    assert CONSUMER not in names and SUPPLIER not in names, (
        "forcing a tool with no declared emitter pulled in unrelated tools"
    )


def test_a_declaration_cycle_does_not_hang(catalog):
    """A registry that says A needs B and B needs A must terminate. Bounded by a hop cap and a seen
    set; asserted rather than assumed, because the loop runs on every advertise pass of every turn."""
    from app.services import stream_service

    original = stream_service._tool_contract_registry
    stream_service._tool_contract_registry = lambda: {"argument_emitters": {
        CONSUMER: {"proposal_id": SUPPLIER},
        SUPPLIER: {"run_id": CONSUMER},
    }}
    try:
        names = _advertised(catalog, "Create the chapters — make the plan real for this book.")
    finally:
        stream_service._tool_contract_registry = original
    assert {CONSUMER, SUPPLIER} <= names


# ── DEPTH ≥ 2 ────────────────────────────────────────────────────────────────────────────────
#
# 🔴 THE FILE'S OWN DOCSTRING DEMANDED THIS AND NOTHING ASSERTED IT. It says "AND IT HAS TO BE
# TRANSITIVE, which composition_reference_update proves: reference_id comes from
# composition_find_references, which was already on every one of 40 passes and itself refused for
# its OWN missing entity_id. A one-hop fix would have looked correct on the other instances and
# left that turn dying one call later."
#
# Measured 2026-09-03: replacing the arming loop's `_pending = _next` with `_pending = []` — the
# original D-R1-STOPPED-AT-DEPTH-1 defect, restored exactly — left all four tests in this file
# GREEN. The transitivity was implemented, documented in three places, and guarded by nothing.
# P14's invariant is the word TRANSITIVELY; a suite that cannot tell one hop from two is not
# enforcing it.
CONSUMER2 = "composition_reference_update"
MID = "composition_find_references"
ROOT_SUPPLIER = "glossary_search"


@pytest.fixture()
def deep_catalog() -> dict:
    return {
        CONSUMER2: _td(CONSUMER2, synonyms=["update the reference", "fix the reference"],
                       required=["book_id", "reference_id"]),
        MID: _td(MID, synonyms=["find references"], required=["book_id", "entity_id"], tier="R"),
        ROOT_SUPPLIER: _td(ROOT_SUPPLIER, synonyms=["search the glossary"], required=["book_id"],
                           tier="R"),
    }


def _with_emitters(mapping, fn):
    from app.services import stream_service
    original = stream_service._tool_contract_registry
    stream_service._tool_contract_registry = lambda: {"argument_emitters": mapping}
    try:
        return fn()
    finally:
        stream_service._tool_contract_registry = original


def test_the_arming_is_TRANSITIVE_not_one_hop(deep_catalog):
    """The request names only the consumer. Its supplier needs a supplier of its own, and that
    second hop is the one composition_reference_update died on in production."""
    names = _with_emitters(
        {CONSUMER2: {"reference_id": MID}, MID: {"entity_id": ROOT_SUPPLIER}},
        lambda: _advertised(deep_catalog, "Update the reference for this book."),
    )
    assert CONSUMER2 in names, "R1 no longer forces the tool the request names — re-anchor"
    assert MID in names, "depth 1 broke — the direct supplier is missing"
    assert ROOT_SUPPLIER in names, (
        "R1 stopped at depth 1: it offered composition_find_references, which itself cannot run "
        "without an entity_id, so the turn dies ONE CALL LATER than before instead of not at all"
    )


def test_the_transitive_walk_terminates_on_a_cycle(deep_catalog):
    """A declaration map is data and data can be wrong. Two tools naming each other must not spin
    the arming loop — `_seen` is what stops it, and a test that never exercises a cycle would not
    notice if that guard were removed."""
    names = _with_emitters(
        {CONSUMER2: {"reference_id": MID}, MID: {"entity_id": CONSUMER2}},
        lambda: _advertised(deep_catalog, "Update the reference for this book."),
    )
    assert CONSUMER2 in names and MID in names
