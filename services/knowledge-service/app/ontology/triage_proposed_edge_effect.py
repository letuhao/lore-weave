"""E2 — `kg_triage_proposed_edge` descriptor effect + preview (Lane E, class-C).

An agent drafts an on-schema edge via `kg_propose_edge`, which PARKS it as a
`proposed_edge` triage item (NEVER a direct Neo4j write — INV-K1). Placing that
edge into the graph is class-C: the MCP `place_edge` action MINTS a
`DESC_TRIAGE_PROPOSED_EDGE` confirm-token; the human redeems it at
`POST /v1/kg/actions/confirm`, which runs this effect.

The token carries only the ``triage_id`` (+ project) — the authoritative edge
fields are re-fetched from the parked item at confirm time, so a tampered token
can't forge a different edge, and the item's own state is the drift anchor:
resolved/dismissed/missing since mint → 422 (re-propose). The write goes through
the SAME central path E1 uses (`Neo4jReapplyWriter` → `create_relation`), under
the project OWNER, then the item is marked resolved.

Mirrors `schema_edit_effect.py` (apply_* / preview_* shape, drift→422 exception).
Spec: docs/specs/2026-06-21-kg-deferred-clearance.md §5 (E2); INV-K1/INV-T3.
"""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, field_validator

from app.db.ontology_models import TriageItem
from app.db.repositories.triage import TriageRepo

__all__ = [
    "ProposedEdgeParams",
    "ProposedEdgeDrift",
    "ProposedEdgeNotFound",
    "ProposedEdgeWriteFailed",
    "apply_proposed_edge",
    "preview_proposed_edge",
]


class ProposedEdgeDrift(Exception):
    """Confirm-time re-validation failed: the triage item was already resolved /
    dismissed / is no longer a pending proposed_edge since mint → re-propose (422)."""


class ProposedEdgeNotFound(Exception):
    """The triage item the token targets does not exist for this owner+project (404)."""


class ProposedEdgeWriteFailed(Exception):
    """The central write path could not place the edge (endpoint missing / bad
    payload) — the item is left pending so the human can re-target/re-propose (409)."""


class ProposedEdgeParams(BaseModel):
    """Opaque params captured at mint (inside the HMAC) + re-validated at confirm.

    Only the ``triage_id`` is trusted as an addressing key; the edge fields are
    re-read from the parked item at confirm (so the token can't forge an edge)."""

    triage_id: str

    @field_validator("triage_id")
    @classmethod
    def _valid_uuid(cls, v: str) -> str:
        UUID(str(v))  # raises ValueError on a malformed id → 422 bad payload
        return str(v)


async def _load_pending_proposed_edge(
    triage: TriageRepo, owner: UUID, project_id: str, triage_id: UUID
) -> TriageItem:
    """Re-fetch + assert the item is a still-pending ``proposed_edge`` (drift gate)."""
    item = await triage.get_item(user_id=owner, project_id=project_id, triage_id=triage_id)
    if item is None:
        raise ProposedEdgeNotFound("the proposed edge no longer exists — propose again")
    if item.item_type != "proposed_edge":
        raise ProposedEdgeDrift("this triage item is not a proposed edge — propose again")
    if item.status != "pending":
        raise ProposedEdgeDrift("this proposed edge was already resolved — propose again")
    return item


async def apply_proposed_edge(
    triage: TriageRepo,
    *,
    owner: UUID,
    project_id: str,
    params: ProposedEdgeParams,
) -> dict:
    """Re-validate (drift), write the corrected edge via the central path under the
    OWNER, then mark the item resolved. Raises ProposedEdgeNotFound (404),
    ProposedEdgeDrift (422), or ProposedEdgeWriteFailed (409) — the router maps."""
    # Imported lazily so the module has no hard Neo4j import at collection time
    # (mirrors the router's lazy neo4j_session import).
    from app.db.neo4j import neo4j_session
    from app.ontology.triage_apply import Neo4jReapplyWriter, TriageApplyError

    triage_id = UUID(params.triage_id)
    item = await _load_pending_proposed_edge(triage, owner, project_id, triage_id)

    async with neo4j_session() as session:
        writer = Neo4jReapplyWriter(session, owner_user_id=str(owner))
        try:
            # `map` semantics here = place the parked edge verbatim (no re-code).
            await writer.reapply(item, action="map", params={})
        except TriageApplyError as exc:
            raise ProposedEdgeWriteFailed(str(exc)) from exc

    # Mark resolved AFTER the write. A concurrent resolve since the drift check →
    # resolve_item returns False → treat as drift (the edge is placed; the state
    # transition lost a race, the human re-checks).
    transitioned = await triage.resolve_item(
        user_id=owner,
        project_id=project_id,
        triage_id=triage_id,
        action="place_edge",
        params={},
        resolved_by=str(owner),
    )
    if not transitioned:
        raise ProposedEdgeDrift("this proposed edge was already resolved — propose again")

    payload = item.payload or {}
    return {
        "applied": True,
        "descriptor": "kg_triage_proposed_edge",
        "triage_id": str(triage_id),
        "subject_id": payload.get("source_entity_id") or payload.get("subject_id"),
        "object_id": payload.get("target_entity_id") or payload.get("object_id"),
        "predicate": payload.get("predicate"),
    }


async def preview_proposed_edge(
    triage: TriageRepo,
    *,
    owner: UUID,
    project_id: str,
    params: ProposedEdgeParams,
) -> dict:
    """Non-consuming current-state render of the edge that would be placed. Surfaces
    a ``drift`` flag when the item vanished / is no longer a pending proposed_edge."""
    triage_id = UUID(params.triage_id)
    item = await triage.get_item(user_id=owner, project_id=project_id, triage_id=triage_id)
    if item is None or item.item_type != "proposed_edge" or item.status != "pending":
        return {
            "descriptor": "kg_triage_proposed_edge",
            "title": "Place proposed edge",
            "destructive": False,
            "drift": True,
            "preview_rows": [
                {"label": "status", "value": "unavailable",
                 "note": "this proposed edge is gone or already resolved — propose again"},
            ],
        }
    payload = item.payload or {}
    subject = payload.get("source_entity_id") or payload.get("subject_id")
    obj = payload.get("target_entity_id") or payload.get("object_id")
    predicate = payload.get("predicate")
    rows = [
        {"label": "edge", "value": f"{subject} —{predicate}→ {obj}"},
        {"label": "predicate", "value": str(predicate)},
        {"label": "source", "value": str(subject)},
        {"label": "target", "value": str(obj)},
    ]
    if payload.get("valid_from") is not None:
        rows.append({"label": "valid_from", "value": str(payload.get("valid_from"))})
    return {
        "descriptor": "kg_triage_proposed_edge",
        "title": f"Place edge '{predicate}'",
        "destructive": False,
        "drift": False,
        "preview_rows": rows,
    }
