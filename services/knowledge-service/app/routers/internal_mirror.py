"""The glossary→KG mirror: the probe, and the repair.

    GET  /internal/projects/{project_id}/glossary-mirror-drift    — measure
    POST /internal/projects/{project_id}/glossary-mirror-repair   — close

D-GLOSSARY-KG-MIRROR-HAS-NO-RECONCILER: the KG is the glossary's projection, delivered
at-least-once with no reconciliation. The GET is the check that reports the divergence, so
that "the mirror is 40% incomplete" stops being something a person can only discover by
hand-querying two databases during an unrelated investigation.

**Neither route writes the graph.** The repair hands the missing ids back to the SSOT,
which re-publishes them through the outbox the consumer already reads — the one path that
is proven and idempotent. Repairing from this end would give the mirror a second writer,
which adds a divergence class rather than closing one.

GET is the dry run and POST is the fix, deliberately, rather than a `dry_run` flag
defaulting to true — which is how an operator runs a repair, reads "0 repaired", and
concludes the divergence was already closed.

Tenancy: same convention as the sibling `/internal` routes — a trusted service
authenticates with `X-Internal-Token` and passes only the project id; the owning user and
book are resolved server-side from `knowledge_projects`, so there is nothing to spoof.

Cost: one paged read from glossary-service plus one bounded graph lookup per mirrorable
entity. Operator-triggered, not a hot path — and `entity_cap` bounds it and SAYS SO when
it bites (`truncated: true` means the reported divergence is a lower bound).
"""

from __future__ import annotations

import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.clients.glossary_client import get_glossary_client
from app.config import settings
from app.db.pool import get_knowledge_pool
from app.middleware.internal_auth import require_internal_token
from app.mirror.glossary_mirror import DEFAULT_ENTITY_CAP, detect_mirror_drift

logger = logging.getLogger(__name__)

# One repair call re-emits at most this many events. The glossary endpoint enforces its
# own cap of 500; this is the lower, operator-facing one — a repair is a burst of outbox
# rows the relay ships together, and 17 (the acceptance book's whole divergence) fits
# comfortably inside it.
MAX_REPAIRS_PER_CALL = 100

router = APIRouter(
    prefix="/internal/projects",
    tags=["Internal"],
    dependencies=[Depends(require_internal_token)],
)


@router.get("/{project_id}/glossary-mirror-drift")
async def glossary_mirror_drift(
    project_id: UUID,
    entity_cap: Annotated[int, Query(ge=1, le=20000)] = DEFAULT_ENTITY_CAP,
) -> dict:
    row = await get_knowledge_pool().fetchrow(
        "SELECT book_id, user_id FROM knowledge_projects WHERE project_id = $1 LIMIT 1",
        project_id,
    )
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="project not found",
        )

    if not settings.neo4j_uri:
        # Track 1 (no graph). There is no mirror to diverge from, and reporting every
        # entity as missing would be a false alarm rather than a measurement.
        return {
            "project_id": str(project_id),
            "book_id": str(row["book_id"]),
            "skipped": "neo4j_unavailable",
        }

    from app.db.neo4j import neo4j_session

    async with neo4j_session() as session:
        drift = await detect_mirror_drift(
            session=session,
            glossary_client=get_glossary_client(),
            project_id=project_id,
            book_id=row["book_id"],
            user_id=row["user_id"],
            entity_cap=entity_cap,
        )

    if drift is None:
        # The truth side is unreachable. 503 rather than a zero-divergence 200: a
        # detector that reports "all clear" when it could not look is worse than one
        # that reports nothing at all.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="glossary truth unreachable — divergence not measured",
        )
    return drift.as_dict()


@router.post("/{project_id}/glossary-mirror-repair")
async def glossary_mirror_repair(
    project_id: UUID,
    entity_cap: Annotated[int, Query(ge=1, le=20000)] = DEFAULT_ENTITY_CAP,
    max_repairs: Annotated[int, Query(ge=1, le=500)] = MAX_REPAIRS_PER_CALL,
) -> dict:
    """Detect, then ask glossary-service to re-emit what is missing.

    GET is the dry run and POST is the fix — deliberately, rather than a `dry_run` flag
    defaulting to true, which is how an operator runs a repair, sees "0 repaired", and
    concludes the divergence was already closed.

    This service does NOT write the graph. It hands the missing ids back to the SSOT,
    which re-publishes them through the outbox the consumer already reads. That path is
    proven and idempotent; a second writer into the mirror would add a divergence class
    rather than close one.

    Convergence is EVENTUAL. The relay ships the outbox rows asynchronously, so the
    response reports what was re-emitted, never a new divergence count — re-detect after
    the relay has run. Reporting a fresh zero here would be measuring the repair with the
    repair.
    """
    row = await get_knowledge_pool().fetchrow(
        "SELECT book_id, user_id FROM knowledge_projects WHERE project_id = $1 LIMIT 1",
        project_id,
    )
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="project not found",
        )
    if not settings.neo4j_uri:
        return {
            "project_id": str(project_id),
            "book_id": str(row["book_id"]),
            "skipped": "neo4j_unavailable",
        }

    from app.db.neo4j import neo4j_session

    client = get_glossary_client()
    async with neo4j_session() as session:
        drift = await detect_mirror_drift(
            session=session, glossary_client=client, project_id=project_id,
            book_id=row["book_id"], user_id=row["user_id"], entity_cap=entity_cap,
        )
    if drift is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="glossary truth unreachable — nothing repaired",
        )

    if not drift.missing_ids:
        return {
            "project_id": str(project_id), "book_id": str(row["book_id"]),
            "detected_missing": 0, "requested": 0, "reemitted": 0,
            "note": "nothing to repair",
        }

    # Bounded per call, and it SAYS which ids it left. An unbounded repair turns one
    # operator action into an outbox burst the relay then ships all at once.
    requested = drift.missing_ids[:max_repairs]
    deferred = drift.missing_ids[max_repairs:]

    result = await client.reemit_mirror(row["book_id"], requested)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="glossary re-emit failed — divergence NOT repaired",
        )

    return {
        "project_id": str(project_id),
        "book_id": str(row["book_id"]),
        "detected_missing": drift.missing,
        "requested": len(requested),
        "reemitted": result.get("reemitted", 0),
        "skipped_ids": result.get("skipped_ids", []),
        "failed_ids": result.get("failed_ids", []),
        "deferred_ids": deferred,
        # Not a hedge — a statement about the substrate. The projection has always been
        # eventually consistent; the repair rides the same relay as every organic event.
        "note": "re-emitted through the outbox; re-run the drift probe after the relay "
                "has shipped to see the new count",
    }
