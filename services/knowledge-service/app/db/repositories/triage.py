"""kg_triage_items repository (epic 2026-06-20, lane LH).

The KG **triage queue** -- extraction elements that don't match the resolved
schema are *parked* here (NOT written to Neo4j) and resolved human-gated,
grouped by `signature` so one resolution batch-applies to every pending item of
the same class. Spec: docs/specs/2026-06-20-knowledge-graph-customizable-
ontology.md s3.7 (schema) + s11 (workflow).

TENANCY (LOCKED -- worker-loaded-id-needs-parent-scoping): every row carries
``user_id`` (the project owner under resolve-to-owner) + ``project_id``, and
**every** query filters by BOTH. ``project_id`` is caller-supplied, so the
router MUST grant-check the project and pass the resolved owner as ``user_id``
before calling this repo -- exactly like `GraphSchemasRepo.resolve_for_project`.
This repo never returns or mutates a row outside ``(user_id, project_id)``.

Spec s11.2 item_type -> action table; s11.3 batch re-apply by signature; s11.4
endpoints.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import asyncpg

from app.db.ontology_models import TriageItem, TriageItemType, TriageStatus

# s11.2 -- the resolution actions valid for each item_type. KG-local actions
# (map / re_target / drop_edge / close_previous / dismiss) are Edit-gated and
# applied here; schema-mutating actions (add_to_vocab / add_to_schema /
# widen_target_kinds / set_multi_active) are Manage-gated and bump the schema
# version (the actual schema write is LC's ontology_mutations -- compose-point
# D-KG-LH-LC-SCHEMA-WRITE); glossary hand-off actions (promote/demote) move the
# item to `pending_glossary` (no KG->glossary write -- M1).
SUGGESTED_ACTIONS: dict[TriageItemType, list[str]] = {
    "unknown_vocab_value": ["map", "add_to_vocab", "dismiss"],
    "unknown_edge_type": ["map", "add_to_schema", "dismiss"],
    "edge_kind_mismatch": ["re_target", "widen_target_kinds", "drop_edge"],
    "edge_cardinality_conflict": ["close_previous", "set_multi_active", "dismiss"],
    "unknown_node_kind": [
        "promote_to_glossary_kind",
        "demote_to_attribute",
        "map",
        "dismiss",
    ],
    # D-KG-LF-PROPOSE-EDGE-INBOX — an agent-drafted on-schema edge. `dismiss`
    # rejects it; `place_edge` (E2) places it into Neo4j as a CLASS-C confirm
    # action: the MCP tool MINTS a DESC_TRIAGE_PROPOSED_EDGE confirm-token (never
    # writes — INV-K1), the human redeems it at /v1/kg/actions/confirm, and the
    # effect writes the edge via the central write path + marks the item resolved.
    "proposed_edge": ["dismiss", "place_edge"],
}

# Action -> resolved-status classification (spec s11.2/s11.4).
#  - GLOSSARY_HANDOFF_ACTIONS: cross-service, user-initiated -> `pending_glossary`
#    (return `needs_glossary`, never a KG->glossary write).
#  - SCHEMA_MUTATING_ACTIONS: Manage-gated, bump schema_version (write owned by LC).
#  - everything else: KG-local, Edit-gated -> `resolved`.
GLOSSARY_HANDOFF_ACTIONS = frozenset({"promote_to_glossary_kind", "demote_to_attribute"})
SCHEMA_MUTATING_ACTIONS = frozenset(
    {"add_to_vocab", "add_to_schema", "widen_target_kinds", "set_multi_active"}
)


def _as_jsonb(value: Any) -> dict[str, Any]:
    """asyncpg returns jsonb as str (no codec) or dict; normalize to dict."""
    if value is None:
        return {}
    if isinstance(value, str):
        return json.loads(value)
    return dict(value)


def _row_to_item(row: asyncpg.Record) -> TriageItem:
    d = dict(row)
    d["source"] = _as_jsonb(d.get("source"))
    d["payload"] = _as_jsonb(d.get("payload"))
    res = d.get("resolution")
    d["resolution"] = _as_jsonb(res) if res is not None else None
    return TriageItem.model_validate(d)


_ITEM_COLS = """
  triage_id, user_id, project_id, source, item_type, payload, signature,
  status, resolution, schema_version, created_at, resolved_at, resolved_by
"""


class TriageGroup:
    """A signature group as returned by `list_grouped` (one row per signature)."""

    __slots__ = (
        "signature",
        "item_type",
        "count",
        "status",
        "sample_payload",
        "suggested_actions",
    )

    def __init__(
        self,
        *,
        signature: str,
        item_type: TriageItemType,
        count: int,
        status: TriageStatus,
        sample_payload: dict[str, Any],
        suggested_actions: list[str],
    ) -> None:
        self.signature = signature
        self.item_type = item_type
        self.count = count
        self.status = status
        self.sample_payload = sample_payload
        self.suggested_actions = suggested_actions


class TriageRepo:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    # -- park (called by LB extraction fail-soft; built now) --------------
    async def park(
        self,
        *,
        user_id: UUID,
        project_id: str,
        item_type: TriageItemType,
        signature: str,
        payload: dict[str, Any],
        source: dict[str, Any] | None = None,
        schema_version: int | None = None,
    ) -> TriageItem:
        """Insert a parked triage item (status='pending'). Idempotency is the
        caller's concern -- the extraction path (LB) may re-park the same element
        on re-run; we don't dedup here (the signature grouping collapses
        duplicates for the human, and re-apply is per-signature)."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                f"""
                INSERT INTO kg_triage_items
                  (user_id, project_id, source, item_type, payload, signature,
                   status, schema_version)
                VALUES ($1, $2, $3::jsonb, $4, $5::jsonb, $6, 'pending', $7)
                RETURNING {_ITEM_COLS}
                """,
                user_id,
                project_id,
                json.dumps(source or {}),
                item_type,
                json.dumps(payload),
                signature,
                schema_version,
            )
        return _row_to_item(row)

    # -- list grouped by signature (s11.4 GET, View-gated) ----------------
    async def list_grouped(
        self,
        *,
        user_id: UUID,
        project_id: str,
        status: TriageStatus = "pending",
        item_type: TriageItemType | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[TriageGroup], bool]:
        """One row per `signature` for ``(user_id, project_id, status)``: the
        count + a representative sample payload + the item_type + the valid
        resolution actions. Ordered by count DESC (worst offenders first) then
        signature for a stable cursor. Returns ``(groups, has_more)`` so the
        router can mint a `next_cursor` (offset-based)."""
        params: list[Any] = [user_id, project_id, status]
        type_clause = ""
        if item_type is not None:
            params.append(item_type)
            type_clause = f" AND item_type = ${len(params)}"
        params.append(limit + 1)
        limit_pos = len(params)
        params.append(offset)
        offset_pos = len(params)
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                f"""
                SELECT signature,
                       (array_agg(item_type ORDER BY created_at DESC))[1] AS item_type,
                       count(*) AS count,
                       (array_agg(payload ORDER BY created_at DESC))[1] AS sample_payload
                FROM kg_triage_items
                WHERE user_id = $1 AND project_id = $2 AND status = $3{type_clause}
                GROUP BY signature
                ORDER BY count DESC, signature ASC
                LIMIT ${limit_pos} OFFSET ${offset_pos}
                """,
                *params,
            )
        has_more = len(rows) > limit
        rows = rows[:limit]
        groups: list[TriageGroup] = []
        for r in rows:
            it: TriageItemType = r["item_type"]
            groups.append(
                TriageGroup(
                    signature=r["signature"],
                    item_type=it,
                    count=r["count"],
                    status=status,
                    sample_payload=_as_jsonb(r["sample_payload"]),
                    suggested_actions=SUGGESTED_ACTIONS.get(it, []),
                )
            )
        return groups, has_more

    async def list_pending_for_signature(
        self, *, user_id: UUID, project_id: str, signature: str
    ) -> list[TriageItem]:
        """All PENDING items of a signature (for the re-apply loop). Scoped."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                f"""
                SELECT {_ITEM_COLS} FROM kg_triage_items
                WHERE user_id = $1 AND project_id = $2 AND signature = $3
                  AND status = 'pending'
                ORDER BY created_at ASC
                """,
                user_id,
                project_id,
                signature,
            )
        return [_row_to_item(r) for r in rows]

    # -- resolve a whole signature (s11.3 batch, s11.4 POST) --------------
    async def resolve_signature(
        self,
        *,
        user_id: UUID,
        project_id: str,
        signature: str,
        action: str,
        params: dict[str, Any] | None,
        resolved_by: str,
        new_status: TriageStatus,
        schema_version: int | None = None,
    ) -> int:
        """Batch-mark every PENDING item of ``signature`` to ``new_status``
        (`resolved` or `pending_glossary`), writing the `resolution` record
        (action + params) and stamping `resolved_by`/`resolved_at`. Returns the
        number of affected rows. Scoped to ``(user_id, project_id)``.

        NOTE: the *Neo4j re-apply* of KG-local actions (re-creating valid edges
        from parked elements) is a SEPARATE step the router drives via
        `app.ontology.triage_apply.apply_resolved` -- this method only owns the
        PG state transition. For `pending_glossary` (glossary hand-off) there is
        no re-apply: the item waits until the kind appears in glossary.
        """
        resolution = {"action": action, "params": params or {}}
        now = datetime.now(timezone.utc)
        async with self._pool.acquire() as conn:
            affected = await conn.fetch(
                """
                UPDATE kg_triage_items
                SET status = $4,
                    resolution = $5::jsonb,
                    schema_version = COALESCE($6, schema_version),
                    resolved_at = $7,
                    resolved_by = $8
                WHERE user_id = $1 AND project_id = $2 AND signature = $3
                  AND status = 'pending'
                RETURNING triage_id
                """,
                user_id,
                project_id,
                signature,
                new_status,
                json.dumps(resolution),
                schema_version,
                now,
                resolved_by,
            )
        return len(affected)

    # -- single-item read + resolve (E2 proposed_edge confirm) ------------
    async def get_item(
        self, *, user_id: UUID, project_id: str, triage_id: UUID
    ) -> TriageItem | None:
        """Fetch ONE triage item by id, scoped to ``(user_id, project_id)``.

        Returns ``None`` when not found / not visible (no existence oracle). Used
        by the E2 proposed_edge confirm effect to re-fetch + drift-check the item
        at confirm time (resolved/dismissed since mint → 422)."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                f"""
                SELECT {_ITEM_COLS} FROM kg_triage_items
                WHERE triage_id = $3 AND user_id = $1 AND project_id = $2
                """,
                user_id,
                project_id,
                triage_id,
            )
        return _row_to_item(row) if row else None

    async def resolve_item(
        self,
        *,
        user_id: UUID,
        project_id: str,
        triage_id: UUID,
        action: str,
        params: dict[str, Any] | None,
        resolved_by: str,
    ) -> bool:
        """Mark ONE pending item resolved (E2 confirm write-through), scoped.

        Returns True if the row transitioned (was pending), False otherwise
        (already terminal / not found / not visible) — the effect maps False to a
        drift 422 (concurrently resolved since the writer placed the edge)."""
        resolution = {"action": action, "params": params or {}}
        now = datetime.now(timezone.utc)
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                UPDATE kg_triage_items
                SET status = 'resolved', resolution = $4::jsonb,
                    resolved_at = $5, resolved_by = $6
                WHERE triage_id = $3 AND user_id = $1 AND project_id = $2
                  AND status = 'pending'
                RETURNING triage_id
                """,
                user_id,
                project_id,
                triage_id,
                json.dumps(resolution),
                now,
                resolved_by,
            )
        return row is not None

    async def stamp_schema_version(
        self, *, user_id: UUID, project_id: str, signature: str, schema_version: int
    ) -> int:
        """Backfill ``schema_version`` onto the RESOLVED items of a signature (E3
        write-through). The schema-mutating resolve route sets schema_version=None;
        once the class-C confirm applies the schema change + computes the new
        version, this stamps it onto those items. Scoped to ``(user_id, project_id,
        signature)`` per the locked tenancy rule (every query filters by both keys).
        Returns rows affected."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                UPDATE kg_triage_items
                SET schema_version = $4
                WHERE user_id = $1 AND project_id = $2 AND signature = $3
                  AND status = 'resolved'
                RETURNING triage_id
                """,
                user_id,
                project_id,
                signature,
                schema_version,
            )
        return len(rows)

    # -- dismiss a single item (s11.4 POST, Edit-gated) -------------------
    async def dismiss(
        self, *, user_id: UUID, project_id: str, triage_id: UUID, resolved_by: str
    ) -> bool:
        """Dismiss ONE pending item by id, scoped to the owner+project. Returns
        True if a row was dismissed, False if not found / not visible / already
        terminal (so the router can map False -> 404, no existence oracle)."""
        now = datetime.now(timezone.utc)
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                UPDATE kg_triage_items
                SET status = 'dismissed', resolved_at = $4, resolved_by = $5
                WHERE triage_id = $3 AND user_id = $1 AND project_id = $2
                  AND status = 'pending'
                RETURNING triage_id
                """,
                user_id,
                project_id,
                triage_id,
                now,
                resolved_by,
            )
        return row is not None
