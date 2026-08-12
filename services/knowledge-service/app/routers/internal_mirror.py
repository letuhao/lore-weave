"""The glossary→KG mirror drift probe — read-only.

GET /internal/projects/{project_id}/glossary-mirror-drift

D-GLOSSARY-KG-MIRROR-HAS-NO-RECONCILER: the KG is the glossary's projection, delivered
at-least-once with no reconciliation. This is the check that reports the divergence, so
that "the mirror is 40% incomplete" stops being something a person can only discover by
hand-querying two databases during an unrelated investigation.

It DETECTS and never repairs. The repairer belongs on the emit side (re-publish through
the outbox, which is already idempotent and already proven); a second writer into the
graph would add a divergence class rather than close one.

Tenancy: same convention as the sibling `/internal` routes — a trusted service
authenticates with `X-Internal-Token` and passes only the project id; the owning user and
book are resolved server-side from `knowledge_projects`, so there is nothing to spoof.

Cost: one paged read from glossary-service plus one bounded graph lookup per mirrorable
entity. Operator-triggered, not a hot path — and `entity_cap` bounds it and SAYS SO when
it bites (`truncated: true` means the reported divergence is a lower bound).
"""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.clients.glossary_client import get_glossary_client
from app.config import settings
from app.db.pool import get_knowledge_pool
from app.middleware.internal_auth import require_internal_token
from app.mirror.glossary_mirror import DEFAULT_ENTITY_CAP, detect_mirror_drift

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/internal/projects",
    tags=["Internal"],
    dependencies=[Depends(require_internal_token)],
)


@router.get("/{project_id}/glossary-mirror-drift")
async def glossary_mirror_drift(
    project_id: UUID,
    entity_cap: int = Query(DEFAULT_ENTITY_CAP, ge=1, le=20000),
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
