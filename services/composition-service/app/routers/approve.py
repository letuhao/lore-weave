"""C27 (dị bản M4) — derivative-chapter approval → delta flywheel router.

POST /v1/composition/works/{project_id}/chapters/{chapter_id}/approve

When the writer APPROVES a chapter of a DERIVATIVE (dị bản) Work, dispatch the
EXISTING knowledge extraction trigger scoped to the derivative's OWN delta
partition (G2) so the next scene's pack (C25) is enriched by what the dị bản
itself established — the flywheel.

LOCKED invariants (delegated to app.engine.delta_flywheel):
  • DELTA-ONLY WRITE (G2): extraction targets the derivative's OWN project_id
    (= this route's `project_id`), NEVER the source/base, NEVER null.
  • PROJECT-SCOPE GUARD before dispatch (a null delta project widens the write to
    ALL projects → DeltaScopeError → 409, never a silent dispatch).
  • FORWARD-FROM-BRANCH write-order: a pre-branch chapter is inherited base, not
    delta → skipped (thinner delta, graceful — a clean 200, not an error).
  • REUSE the existing extract-item trigger — no new extraction engine.

AUTH: resolves the Work by project_id (un-user-scoped — PM-9) → EDIT grant on the
book (approving is an authoring action; the gate is the ONLY access decision, the
repo never filters on the caller) → forwards the JWT for the book-draft read
and uses the internal token for the extract-item dispatch (SEC2: ownership is
verified by the Work load + grant gate before any internal call).
"""

from __future__ import annotations

import logging
import uuid
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.clients.book_client import BookClient, BookClientError
from app.clients.knowledge_client import KnowledgeClient
from app.db.repositories.derivatives import DerivativesRepo
from app.db.repositories.works import WorksRepo
from app.deps import (
    get_book_client_dep,
    get_derivatives_repo,
    get_grant_client_dep,
    get_knowledge_client_dep,
    get_works_repo,
)
from app.engine.delta_flywheel import DeltaScopeError, plan_flywheel_dispatch
from app.engine.prose_doc import tiptap_doc_to_text
from app.grant_client import GrantClient, GrantLevel
from app.grant_deps import InsufficientGrant, authorize_book
from app.middleware.jwt_auth import get_bearer_token, get_current_user
from app.packer.pack import OwnershipError, build_derivative_context

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/composition")


class ApproveChapterBody(BaseModel):
    """The extraction model to run the delta flywheel under. AI-FREE: composition
    does NOT pick a model — the caller (FE) supplies a provider-registry-resolved
    user_model ref, exactly like generate/critique. No hardcoded model name here."""

    model_source: str = Field(default="user_model")
    model_ref: str = Field(min_length=1, max_length=200)


async def _gate_book(grant: GrantClient, book_id: UUID, caller: UUID, need: GrantLevel) -> None:
    try:
        await authorize_book(grant, book_id, caller, need)
    except OwnershipError:
        raise HTTPException(status_code=404, detail="book not found")
    except InsufficientGrant:
        raise HTTPException(status_code=403, detail="insufficient access")


@router.post("/works/{project_id}/chapters/{chapter_id}/approve")
async def approve_chapter(
    project_id: UUID,
    chapter_id: UUID,
    body: ApproveChapterBody,
    user_id: UUID = Depends(get_current_user),
    bearer: str = Depends(get_bearer_token),
    works: WorksRepo = Depends(get_works_repo),
    derivatives: DerivativesRepo = Depends(get_derivatives_repo),
    book: BookClient = Depends(get_book_client_dep),
    knowledge: KnowledgeClient = Depends(get_knowledge_client_dep),
    grant: GrantClient = Depends(get_grant_client_dep),
) -> dict[str, Any]:
    """Approve a derivative chapter → flywheel its extraction into the delta.

    Returns `{dispatched, reason, project_id, ...}`. A non-derivative or a
    pre-branch (out-of-order) chapter is a clean `dispatched=false` 200 — never an
    error. A real derivative chapter with a null delta project → 409 (the GUARD)."""
    # PM-9: composition_work is per-book — resolve by project_id (no user filter).
    # ACCESS is the EDIT gate on the row's book just below; a no-grant caller gets
    # the same uniform 404 there (anti-oracle — nothing returned before the gate).
    work = await works.get(project_id)
    if work is None:
        raise HTTPException(status_code=404, detail="work not found")
    # Approving (committing a chapter into the dị bản) is an authoring action.
    await _gate_book(grant, work.book_id, user_id, GrantLevel.EDIT)

    # Resolve the derivative context (base project + branch) — the SAME path C25's
    # packer uses (reuse, no re-implementation). source_project_id non-None ⟺ this
    # Work is a derivative whose source resolved.
    deriv = await build_derivative_context(
        work, works_repo=works, derivatives_repo=derivatives,
    )

    # Disambiguate "not a derivative" from "derivative whose source is unresolvable"
    # (source Work deleted): the Work ITSELF carries source_work_id when it is a
    # derivative, but build_derivative_context degrades source_project_id to None if
    # the source lookup fails. Without this, a real derivative whose source vanished
    # would be SILENTLY mislabeled `not_a_derivative` and never flywheel — the delta
    # quietly stops enriching with no signal (adversary minor). Surface it instead.
    if work.source_work_id is not None and deriv.source_project_id is None:
        logger.warning(
            "C27 flywheel: derivative work=%s has an unresolvable source (work_id=%s) — "
            "cannot scope the base; refusing to dispatch (delta not enriched)",
            work.project_id, work.source_work_id,
        )
        return {
            "dispatched": False,
            "reason": "source_unresolved",
            "project_id": str(work.project_id) if work.project_id else None,
        }

    # The chapter's reading position (the forward-from-branch axis). Best-effort —
    # an unresolvable sort_order is conservatively treated as forward (not skipped).
    try:
        sort_orders = await book.get_chapter_sort_orders([chapter_id])
        chapter_sort_order = sort_orders.get(str(chapter_id))
    except BookClientError:
        chapter_sort_order = None

    # Decide go/no-go. delta_project_id is the derivative's OWN project (this route's
    # project_id) — NEVER the source. The GUARD inside raises on a null delta.
    try:
        decision = plan_flywheel_dispatch(
            delta_project_id=work.project_id,
            source_project_id=deriv.source_project_id,
            branch_point=deriv.branch_point,
            chapter_sort_order=chapter_sort_order,
        )
    except DeltaScopeError as exc:
        # A real, forward-of-branch derivative chapter whose delta project is null —
        # refuse rather than dispatch into null/all-projects (the C23 leak).
        raise HTTPException(
            status_code=409,
            detail={"code": "DELTA_PROJECT_UNSCOPED", "detail": str(exc)},
        )

    if not decision.dispatch:
        # Clean no-op: a canon/greenfield Work, or a pre-branch chapter (thinner
        # delta). Never extract into the source/canon partition.
        return {
            "dispatched": False,
            "reason": decision.reason,
            "project_id": str(work.project_id) if work.project_id else None,
        }

    # Fetch the approved chapter's prose for extraction (JWT-forward; book-service
    # enforces ownership). Flatten the Tiptap draft to plain text.
    try:
        draft = await book.get_draft(work.book_id, chapter_id, bearer)
    except BookClientError:
        raise HTTPException(status_code=502, detail={"code": "BOOK_SERVICE_UNAVAILABLE"})
    chapter_text = tiptap_doc_to_text(draft.get("body"))
    if not chapter_text:
        # Nothing to extract → a clean no-op (don't dispatch an empty extraction).
        return {
            "dispatched": False,
            "reason": "empty_chapter",
            "project_id": str(work.project_id),
        }

    # Dispatch the EXISTING extraction trigger into the DERIVATIVE's delta project.
    # delta_project_id is asserted non-null above; assert once more locally so a
    # future refactor can't drop the guard (type-narrows for mypy too).
    assert decision.delta_project_id is not None
    result = await knowledge.extract_item(
        user_id=user_id,
        project_id=decision.delta_project_id,  # the DELTA partition (G2)
        source_id=str(chapter_id),
        chapter_text=chapter_text,
        model_source=body.model_source,
        model_ref=body.model_ref,
        job_id=uuid.uuid4(),
    )
    if result is None:
        # Knowledge outage — the approval itself succeeds (the chapter is approved);
        # the flywheel just didn't enrich this round (it re-arms on re-approval).
        logger.warning(
            "C27 flywheel: extract-item returned None for chapter=%s delta_project=%s "
            "(knowledge unavailable) — approval stands, delta not enriched",
            chapter_id, decision.delta_project_id,
        )
        return {
            "dispatched": False,
            "reason": "knowledge_unavailable",
            "project_id": str(decision.delta_project_id),
        }

    logger.info(
        "C27 flywheel: approved derivative chapter=%s → extracted into delta "
        "project=%s (entities=%s events=%s facts=%s)",
        chapter_id, decision.delta_project_id,
        result.get("entities_merged"), result.get("events_merged"),
        result.get("facts_merged"),
    )
    return {
        "dispatched": True,
        "reason": decision.reason,
        "project_id": str(decision.delta_project_id),
        "source_project_id": str(decision.source_project_id),
        "extraction": result,
    }
