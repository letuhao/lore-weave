"""K7.5 + K7.6 — User data export + GDPR erasure under /v1/knowledge/user-data.

Two endpoints:
  - GET    /v1/knowledge/user-data/export   → JSON bundle of all
                                                knowledge-service-owned data
  - DELETE /v1/knowledge/user-data           → atomic erasure of same

Both are JWT-authenticated via the router-level dep. user_id is sourced
ONLY from the JWT sub claim — never query string or body — so a caller
can't trick the route into exporting / deleting another user's data.

Track 1 scope: knowledge-service tables only (`knowledge_projects` +
`knowledge_summaries`). Cross-service GDPR cascade (chapters, chat,
glossary, billing) is Track 3 and lives on a future cross-service
orchestrator, not this route.

Snapshot consistency on export: the projects list and summaries list
are read in two separate connections, NOT a single transaction. A
concurrent edit between the two reads could yield a bundle where the
summaries reference projects that were just deleted (or vice versa).
Track 1 accepts this — the user is exporting their own data
interactively, not racing themselves. Track 3's streaming export will
add a REPEATABLE READ snapshot.
"""

import logging
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.db.repositories.projects import ProjectsRepo
from app.db.repositories.summaries import SummariesRepo
from app.db.repositories.user_data import UserDataRepo
from app.deps import get_projects_repo, get_summaries_repo, get_user_data_repo
from app.middleware.jwt_auth import get_current_user

logger = logging.getLogger(__name__)

__all__ = ["router"]

router = APIRouter(
    prefix="/v1/knowledge/user-data",
    tags=["public"],
    dependencies=[Depends(get_current_user)],
)


# ── response models ──────────────────────────────────────────────────────


class DeleteCounts(BaseModel):
    summaries: int
    projects: int


class DeleteResponse(BaseModel):
    deleted: DeleteCounts


# ── endpoints ────────────────────────────────────────────────────────────


@router.get("/export")
async def export_user_data(
    user_id: UUID = Depends(get_current_user),
    projects_repo: ProjectsRepo = Depends(get_projects_repo),
    summaries_repo: SummariesRepo = Depends(get_summaries_repo),
) -> JSONResponse:
    projects = await projects_repo.list_all_for_user(user_id)

    # Hard fail on overflow rather than silently truncating. The repo
    # fetches LIMIT EXPORT_HARD_CAP + 1 so we can detect the boundary
    # cleanly. 507 Insufficient Storage isn't a perfect fit (it's a
    # WebDAV code) but it's the closest standard match for "the
    # response your request would generate exceeds my limits."
    if len(projects) > ProjectsRepo.EXPORT_HARD_CAP:
        raise HTTPException(
            status_code=status.HTTP_507_INSUFFICIENT_STORAGE,
            detail=(
                f"export exceeds {ProjectsRepo.EXPORT_HARD_CAP} project rows; "
                "streaming export not yet supported"
            ),
        )

    summaries = await summaries_repo.list_all_for_user(user_id)
    # Same hard-fail philosophy as projects: a silently-truncated export
    # bundle would violate GDPR's "complete copy" requirement. list_all_for_user
    # fetches LIMIT cap+1 so we can detect the boundary.
    if len(summaries) > SummariesRepo.EXPORT_HARD_CAP:
        raise HTTPException(
            status_code=status.HTTP_507_INSUFFICIENT_STORAGE,
            detail=(
                f"export exceeds {SummariesRepo.EXPORT_HARD_CAP} summary rows; "
                "streaming export not yet supported"
            ),
        )

    now = datetime.now(timezone.utc)
    bundle = {
        # schema_version lets future imports + Track 3 cross-service
        # merge tools detect format. Bump on every breaking change.
        "schema_version": 1,
        "user_id": str(user_id),
        "exported_at": now.isoformat(),
        "projects": [p.model_dump(mode="json") for p in projects],
        "summaries": [s.model_dump(mode="json") for s in summaries],
    }

    # Filename embeds user_id + date for disambiguation when a user
    # downloads exports from multiple accounts on one device. user_id
    # is not a secret (the caller already authenticated as it).
    filename = f"loreweave-knowledge-export-{user_id}-{now.date().isoformat()}.json"

    # GDPR audit trail — export is a regulated data-subject request
    # and needs to be traceable after the fact. INFO level so it lands
    # in default prod logging without requiring debug filters.
    logger.info(
        "gdpr.export user_id=%s projects=%d summaries=%d",
        user_id,
        len(projects),
        len(summaries),
    )

    return JSONResponse(
        content=bundle,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.delete("", response_model=DeleteResponse)
async def delete_user_data(
    user_id: UUID = Depends(get_current_user),
    repo: UserDataRepo = Depends(get_user_data_repo),
) -> DeleteResponse:
    """Hard-delete every project + summary owned by the caller.

    Atomic across both tables (single transaction in UserDataRepo).
    Returns 200 with row counts as a receipt — the user clicked
    "delete my data" and deserves to see how much was deleted, which
    is why this isn't a 204.
    """
    counts = await repo.delete_all_for_user(user_id)
    # GDPR audit trail — erasure is the higher-risk counterpart to
    # export and must be logged with the counts so a later audit can
    # reconstruct what was destroyed for this user.
    logger.info(
        "gdpr.erasure user_id=%s projects=%d summaries=%d",
        user_id,
        counts["projects"],
        counts["summaries"],
    )
    return DeleteResponse(deleted=DeleteCounts(**counts))
