"""KM6-M3 — `kg_sync_apply` descriptor effect + preview (third class-C action).

Sync applies per-child keep_mine/take_theirs decisions to bring a project schema in line
with its upstream template (forward-only, M3 — overwrite/deprecate, no retro-recompute).
Optimistic-concurrency is intrinsic to `OntologyMutationsRepo.sync_apply`: the proposal
carries `base_source_hash` (the upstream content_hash the agent saw in
`kg_sync_available`); if upstream has moved since, the repo raises `SyncConflictError` →
re-proposable. Preview renders the CURRENT diff state so the human confirms against now.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.db.repositories.graph_schemas import GraphSchemasRepo
from app.db.repositories.ontology_mutations import (
    OntologyMutationsRepo,
    SchemaNotWritableError,
    SyncConflictError,
)

__all__ = [
    "SyncDecisionParam",
    "SyncApplyParams",
    "SyncDrift",
    "SyncNoSchema",
    "apply_sync",
    "preview_sync",
]


class SyncDrift(Exception):
    """Upstream moved since the proposal was read (SyncConflict) → re-proposable (422)."""


class SyncNoSchema(Exception):
    """The project has no active schema to sync (or it became non-writable) → 422."""


class SyncDecisionParam(BaseModel):
    node_type: str
    code: str
    parent_code: str | None = None
    choice: str = Field(pattern="^(keep_mine|take_theirs)$")


class SyncApplyParams(BaseModel):
    """Opaque mint params: the upstream hash the agent saw + the per-child decisions."""

    base_source_hash: str
    decisions: list[SyncDecisionParam] = Field(default_factory=list)


async def apply_sync(
    schemas: GraphSchemasRepo,
    mutations: OntologyMutationsRepo,
    project_id: str,
    params: SyncApplyParams,
) -> dict:
    """Resolve the project's active schema then apply the sync decisions. Raises
    SyncDrift (re-proposable) or SyncNoSchema. Re-adoption between mint and confirm
    surfaces as SyncDrift too (the new schema's source_hash won't match base)."""
    active = await schemas.active_project_schema(project_id)
    if active is None:
        raise SyncNoSchema("the project has no active schema to sync — propose again")
    try:
        return await mutations.sync_apply(
            active.schema_id,
            base_source_hash=params.base_source_hash,
            decisions=[d.model_dump() for d in params.decisions],
        )
    except SyncConflictError:
        raise SyncDrift("the upstream template moved since you proposed — propose again")
    except SchemaNotWritableError:
        raise SyncNoSchema("the project schema is no longer writable — propose again")


async def preview_sync(
    schemas: GraphSchemasRepo,
    mutations: OntologyMutationsRepo,
    project_id: str,
    params: SyncApplyParams,
) -> dict:
    """Non-consuming current-state render: the live diff vs the proposed decisions, plus
    a drift flag when upstream has moved since the proposal's base_source_hash."""
    active = await schemas.active_project_schema(project_id)
    if active is None:
        return {
            "descriptor": "kg_sync_apply",
            "title": "Sync from template",
            "destructive": False,
            "drift": True,
            "preview_rows": [
                {"label": "status", "value": "no active schema",
                 "note": "the project has no schema to sync — propose again"},
            ],
        }
    diff = await mutations.sync_diff(active.schema_id)
    current_hash = diff.get("source_hash_current")
    drift = current_hash != params.base_source_hash
    take = sum(1 for d in params.decisions if d.choice == "take_theirs")
    rows = [
        {"label": "source", "value": diff.get("source_ref") or "—"},
        {"label": "upstream has updates", "value": "yes" if diff.get("has_updates") else "no"},
        {"label": "take-theirs decisions", "value": str(take)},
        {"label": "keep-mine decisions", "value": str(len(params.decisions) - take)},
    ]
    if drift:
        rows.append({"label": "⚠ drift", "value": "yes",
                     "note": "the upstream moved since you proposed — confirming will be rejected"})
    return {
        "descriptor": "kg_sync_apply",
        "title": "Sync project ontology from its template",
        "destructive": True,  # take_theirs overwrites/deprecates project rows
        "drift": drift,
        "preview_rows": rows,
    }
