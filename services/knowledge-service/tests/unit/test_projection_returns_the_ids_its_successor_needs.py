"""The projection must hand back the node ids, because counts cannot be chained.

🔴 THE RUN THIS PINS. kg_propose_edge, K=5, 2026-08-23 (p4-approve-pilot). Its documented
prerequisite `kg_project_entities_to_nodes` created both endpoints and returned
`{nodes_created: 2, nodes_existing: 0, entities_seen: 2, skipped: 0}` — no ids. kg_propose_edge
REQUIRES source_entity_id and target_entity_id, so the model had nothing to pass and invented
one, using the SAME value for both endpoints:

    source_entity_id = target_entity_id = "66966666-6666-6666-6666-666666666666"

The tool's own check caught it ("they identify DIFFERENT things and can never be the same id") —
a good message about the wrong problem. And the platform's fabricated-id guard could not help:
it tests SYNTAX, and a repdigit UUID parses fine.

The loop already held each Entity and discarded it into `_`. A supplier that cannot supply its
successor's required arguments is not a chain.
"""
from dataclasses import FrozenInstanceError

import pytest

from app.extraction.anchor_loader import NODES_RETURNED_CAP, ProjectionResult


def test_a_projection_result_carries_the_ids_not_only_counts():
    r = ProjectionResult(
        created=2, existing=0, seen=2,
        nodes=({"entity_id": "e1", "name": "Aldric Vane", "kind": "character"},
               {"entity_id": "e2", "name": "Mira Solene", "kind": "character"}),
    )
    ids = [n["entity_id"] for n in r.nodes]
    assert ids == ["e1", "e2"], "the successor needs the ids, and counts are not ids"
    # the two endpoints must be DISTINGUISHABLE — the measured failure was one id used twice
    assert len(set(ids)) == 2


def test_the_default_is_empty_and_not_truncated():
    r = ProjectionResult()
    assert r.nodes == ()
    assert r.nodes_truncated is False


def test_truncation_is_reported_rather_than_silently_short():
    """`entity_ids=None` projects a whole glossary; a short list must SAY it is short."""
    r = ProjectionResult(created=100, existing=0, seen=100,
                         nodes=tuple({"entity_id": f"e{i}"} for i in range(NODES_RETURNED_CAP)),
                         nodes_truncated=True)
    assert len(r.nodes) == NODES_RETURNED_CAP
    assert r.nodes_truncated is True


def test_the_cap_is_a_payload_bound_not_a_work_limit():
    """created+existing may exceed the returned list: the write is not capped, the payload is."""
    r = ProjectionResult(created=100, existing=0, seen=100,
                         nodes=tuple({"entity_id": f"e{i}"} for i in range(NODES_RETURNED_CAP)),
                         nodes_truncated=True)
    assert r.created > len(r.nodes)


def test_the_result_is_still_frozen():
    r = ProjectionResult()
    with pytest.raises(FrozenInstanceError):
        r.nodes = ({"entity_id": "x"},)  # type: ignore[misc]
