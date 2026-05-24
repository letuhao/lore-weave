"""P3 D-P3-INDEX-PRUNE-ENDPOINT — admin maintenance endpoints.

Hosts cross-service admin/janitor ops that don't fit any single
extraction-domain router. Today: prune orphaned summary vector indexes
from Neo4j (created lazily by `ensure_summary_indexes` per
(project, embedding_model) pair; orphaned when the project's selection
changes OR the project is deleted).

Authentication: X-Internal-Token (service-to-service).
"""

from __future__ import annotations

import logging
from typing import Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from app.db.neo4j import neo4j_session
from app.db.neo4j_helpers import (
    drop_summary_index,
    list_summary_vector_indexes,
)
from app.db.pool import get_knowledge_pool
from app.middleware.internal_auth import require_internal_token

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/internal/admin",
    tags=["Internal", "Admin"],
    dependencies=[Depends(require_internal_token)],
)


class OrphanIndex(BaseModel):
    """One orphaned summary vector index. `reason` distinguishes the two
    classes (project_deleted vs embedding_model_changed) so an operator
    can audit before approving a non-dry-run prune."""
    index_name: str
    level: Literal["chapter", "part", "book"]
    project_id: str            # 32-hex (no dashes — as stored in the index name)
    embedding_model_uuid: str  # 32-hex
    reason: Literal["project_deleted", "embedding_model_changed", "project_model_unset"]


class PruneSummaryIndexesResponse(BaseModel):
    """Result envelope.

    `dry_run=True` → orphans listed, no DROP fired. `dry_run=False` →
    orphans dropped (idempotent; tolerates concurrent drops).
    """
    dry_run: bool
    total_summary_indexes: int
    orphan_indexes: list[OrphanIndex]
    dropped_count: int  # always 0 when dry_run=True


@router.post(
    "/summary-indexes/prune",
    response_model=PruneSummaryIndexesResponse,
    summary="P3 — prune orphaned per-(project, embedding_model) summary vector indexes",
    description=(
        "Enumerates Neo4j summary vector indexes (created lazily by "
        "`ensure_summary_indexes` on first summary write for a project + "
        "embedding_model pair); flags any whose namespace no longer matches "
        "an active project selection. Default `dry_run=true` returns the "
        "orphan list without dropping. Set `dry_run=false` to actually DROP. "
        "Orphan reasons: `project_deleted` (no row in knowledge_projects), "
        "`embedding_model_changed` (project's current embedding_model differs "
        "from the index's), `project_model_unset` (project exists but "
        "embedding_model column is NULL — indexes unusable for Mode-3 query)."
    ),
)
async def prune_summary_indexes(
    dry_run: bool = Query(
        default=True,
        description="When true (default), only enumerate orphans. When false, DROP them.",
    ),
) -> PruneSummaryIndexesResponse:
    # 1. Enumerate all summary vector indexes from Neo4j.
    async with neo4j_session() as session:
        indexes = await list_summary_vector_indexes(session)

        if not indexes:
            return PruneSummaryIndexesResponse(
                dry_run=dry_run,
                total_summary_indexes=0,
                orphan_indexes=[],
                dropped_count=0,
            )

        # 2. Resolve current embedding_model per project (hex without dashes).
        #    Single batched query keyed on the hex form so the index parser
        #    output joins directly.
        unique_proj_hex = {idx["project_id"] for idx in indexes}
        current_models = await _current_embedding_models(unique_proj_hex)

        # 3. Classify each index.
        orphans: list[OrphanIndex] = []
        for idx in indexes:
            proj_hex = idx["project_id"]
            emb_hex = idx["embedding_model_uuid"]
            current = current_models.get(proj_hex, _SENTINEL_MISSING)
            if current is _SENTINEL_MISSING:
                reason = "project_deleted"
            elif current is None:
                reason = "project_model_unset"
            elif current != emb_hex:
                reason = "embedding_model_changed"
            else:
                continue  # active — keep
            orphans.append(OrphanIndex(
                index_name=idx["name"],
                level=idx["level"],  # type: ignore[arg-type]
                project_id=proj_hex,
                embedding_model_uuid=emb_hex,
                reason=reason,  # type: ignore[arg-type]
            ))

        # 4. Drop if requested. Idempotent — `DROP INDEX … IF EXISTS`.
        dropped = 0
        if not dry_run:
            for orphan in orphans:
                await drop_summary_index(session, orphan.index_name)
                dropped += 1

    logger.info(
        "p3 admin prune-summary-indexes dry_run=%s total=%d orphans=%d dropped=%d",
        dry_run, len(indexes), len(orphans), dropped,
    )
    return PruneSummaryIndexesResponse(
        dry_run=dry_run,
        total_summary_indexes=len(indexes),
        orphan_indexes=orphans,
        dropped_count=dropped,
    )


# Sentinel distinguishing "project row missing" from "project row exists
# but embedding_model column is NULL" — both are orphans but the operator
# audit needs different reasons.
_SENTINEL_MISSING: object = object()


async def _current_embedding_models(
    proj_hex_set: set[str],
) -> dict[str, str | None]:
    """Return {project_id_hex: embedding_model_hex_or_None} for every
    proj_hex in `proj_hex_set` that exists in knowledge_projects.

    Missing projects are absent from the dict (caller distinguishes via
    `_SENTINEL_MISSING`). knowledge_projects.embedding_model is the
    provider-registry user_model UUID with hyphens; we strip them so the
    output matches the index name's `e<32hex>` segment.
    """
    pool = get_knowledge_pool()
    rows = await pool.fetch(
        """
        SELECT
            REPLACE(LOWER(project_id::text), '-', '') AS proj_hex,
            REPLACE(LOWER(embedding_model::text), '-', '') AS emb_hex
        FROM knowledge_projects
        WHERE REPLACE(LOWER(project_id::text), '-', '') = ANY($1::text[])
        """,
        list(proj_hex_set),
    )
    result: dict[str, str | None] = {}
    for row in rows:
        emb = row["emb_hex"]
        # embedding_model is nullable; REPLACE(NULL, ...) = NULL → preserve.
        result[row["proj_hex"]] = emb if emb else None
    return result
