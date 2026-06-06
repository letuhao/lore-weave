"""POST /internal/coref/detect — mui #1c K-detect trigger.

Runs a coreference-detection pass for one project: loads glossary-anchored KG
entities, scores likely-same clusters (name + structural), optionally LLM-
verifies, and proposes the survivors to glossary's merge-candidate inbox
(G-cand). NOTHING merges — the human confirms in glossary (L1).

Internal-token gated (the caller — a future FE "find duplicates" action via the
gateway, or an admin/job — validates ownership before issuing this). Best-effort
shape: a missing project / disabled feature returns an empty result, never 500s
on the degraded paths.
"""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.clients.glossary_client import GlossaryClient
from app.clients.llm_client import LLMClient
from app.config import settings
from app.db.neo4j import neo4j_session
from app.db.repositories.projects import ProjectsRepo
from app.deps import get_glossary_client, get_llm_client, get_projects_repo
from app.extraction import coref_detect
from app.middleware.internal_auth import require_internal_token

logger = logging.getLogger(__name__)

__all__ = ["router"]

router = APIRouter(
    prefix="/internal/coref",
    tags=["Internal"],
    dependencies=[Depends(require_internal_token)],
)


class CorefDetectRequest(BaseModel):
    user_id: UUID
    project_id: UUID
    # Optional kind scope; when omitted, all anchored kinds in the project.
    kinds: list[str] | None = Field(default=None)


class CorefDetectResponse(BaseModel):
    clusters_found: int = 0
    proposed: int = 0
    suppressed: int = 0
    skipped: int = 0


@router.post("/detect", response_model=CorefDetectResponse)
async def detect(
    req: CorefDetectRequest,
    projects_repo: ProjectsRepo = Depends(get_projects_repo),
    glossary_client: GlossaryClient = Depends(get_glossary_client),
    llm_client: LLMClient = Depends(get_llm_client),
) -> CorefDetectResponse:
    if not settings.coref_enabled:
        return CorefDetectResponse()
    project = await projects_repo.get(req.user_id, req.project_id)
    if project is None or project.book_id is None:
        return CorefDetectResponse()

    uid = str(req.user_id)
    pid = str(req.project_id)
    async with neo4j_session() as session:
        kinds = req.kinds or await coref_detect.load_anchored_kinds(
            session, user_id=uid, project_id=pid
        )
        if not kinds:
            return CorefDetectResponse()
        result = await coref_detect.detect_and_propose(
            session=session,
            glossary=glossary_client,
            llm=llm_client,
            user_id=uid,
            project_id=pid,
            book_id=project.book_id,
            kinds=kinds,
            score_floor=settings.coref_score_floor,
            name_weight=settings.coref_name_weight,
            struct_weight=settings.coref_struct_weight,
            max_pairs=settings.coref_max_pairs,
            max_bucket=settings.coref_max_bucket,
            max_candidates_per_kind=settings.coref_max_candidates_per_kind,
            min_mentions=settings.coref_min_mentions,
            llm_verify=settings.coref_llm_verify,
            judge_model=settings.coref_judge_model,
            judge_user=settings.coref_judge_user,
            judge_model_source=settings.coref_judge_model_source,
        )
    logger.info(
        "coref detect project=%s kinds=%d clusters=%d proposed=%d suppressed=%d skipped=%d",
        pid, len(kinds), result.clusters_found, result.proposed, result.suppressed, result.skipped,
    )
    return CorefDetectResponse(
        clusters_found=result.clusters_found,
        proposed=result.proposed,
        suppressed=result.suppressed,
        skipped=result.skipped,
    )
