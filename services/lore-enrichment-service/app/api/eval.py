"""Internal eval-gate status route (RAID C15).

Read-only ``/internal/eval/{project_id}/gate-status`` — returns the LATEST
enrichment_eval_runs row for a (project, suite_version) and the derived
P2/P3-gate signal. This is the surface C16 (fabrication) / C17 (re-cook) read to
decide whether their higher-cost tier may activate: ``p2_p3_unlocked`` is True
ONLY when the latest run for the suite passed the gate.

``has_run=False`` is a valid state (no eval yet) → the gate stays BLOCKED
(p2_p3_unlocked=False) — fail-CLOSED, never a false-green when no eval exists.

Gated by the internal service token (server-to-server), mirroring
knowledge-service ``internal_benchmark`` (the persist pattern this eval mirrors).
``user_id`` is a trusted query param (the caller is another LoreWeave service).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.config import settings
from app.db.book_profile import get_book_profile
from app.db.repositories.eval_runs import EvalRunsRepo
from app.deps import get_db
from app.eval.judge_binding import make_judge_fn_for
from app.eval.judge_usefulness import JudgeSpec
from app.eval.runner import run_eval
from app.eval.scorers import ScorableProposal
from app.eval.suite import load_suite
from app.services.review import ProposalsRepo

__all__ = ["router", "GateStatusResponse", "RunEvalBody", "RunEvalResponse"]

logger = logging.getLogger("lore_enrichment.eval")


def _suite_path() -> Path:
    """Resolve the eval-suite TOML both in-container (shipped at /app/eval/ by the
    Dockerfile) and in the repo (repo-root eval/). First existing wins."""
    here = Path(__file__).resolve()
    candidates = [
        Path("/app/eval/enrichment-eval-suite.toml"),  # in-container (Dockerfile COPY)
        here.parents[4] / "eval" / "enrichment-eval-suite.toml",  # repo root
    ]
    for c in candidates:
        if c.is_file():
            return c
    raise FileNotFoundError(
        f"enrichment-eval-suite.toml not found (looked in {[str(c) for c in candidates]})"
    )


async def require_internal_token(
    x_internal_token: str | None = Header(default=None, alias="X-Internal-Token"),
) -> None:
    """Server-to-server guard. Rejects a missing/wrong token (401)."""
    if not x_internal_token or x_internal_token != settings.internal_service_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid internal token",
        )


router = APIRouter(
    prefix="/internal/eval",
    tags=["Internal"],
    dependencies=[Depends(require_internal_token)],
)


async def get_eval_runs_repo(pool=Depends(get_db)) -> EvalRunsRepo:
    return EvalRunsRepo(pool)


class GateStatusResponse(BaseModel):
    """Latest eval-run summary + the derived P2/P3 gate signal.

    ``p2_p3_unlocked`` is the load-bearing field: True ONLY when an eval has run
    for this suite AND it passed the gate. C16/C17 must NOT activate when this is
    False. ``has_run=False`` → unlocked=False (fail-closed)."""

    has_run: bool
    p2_p3_unlocked: bool
    suite_version: str
    passed: bool | None = None
    composite: float | None = None
    fleiss_kappa: float | None = None
    judge_ensemble_acceptable: bool | None = None
    run_id: str | None = None
    created_at: datetime | None = None


@router.get("/{project_id}/gate-status", response_model=GateStatusResponse)
async def gate_status(
    project_id: UUID,
    user_id: UUID = Query(..., description="project owner"),
    suite_version: str = Query("enrichment-v1"),
    repo: EvalRunsRepo = Depends(get_eval_runs_repo),
) -> GateStatusResponse:
    row = await repo.get_latest(
        user_id=user_id, project_id=project_id, suite_version=suite_version
    )
    if row is None:
        # No eval yet → gate stays BLOCKED (fail-closed).
        return GateStatusResponse(
            has_run=False, p2_p3_unlocked=False, suite_version=suite_version
        )
    return GateStatusResponse(
        has_run=True,
        p2_p3_unlocked=bool(row.passed),
        suite_version=row.suite_version,
        passed=row.passed,
        composite=row.composite,
        fleiss_kappa=row.fleiss_kappa,
        judge_ensemble_acceptable=row.judge_ensemble_acceptable,
        run_id=row.run_id,
        created_at=row.created_at,
    )


# ── eval RUN (LE-PROD-2 P3b) — score a project's proposals + persist the gate ──

class JudgeInput(BaseModel):
    """One ensemble judge: an opaque provider-registry ``model_ref`` (BYOK — owned
    by ``user_id``) + a label + a FAMILY (the gate needs ≥2 DISTINCT families)."""

    model_ref: UUID
    label: str = Field(min_length=1)
    family: str = Field(min_length=1)


class RunEvalBody(BaseModel):
    """Run the de-biased eval over a project's enriched proposals + persist the
    scorecard (which drives ``/gate-status`` → P2/P3 unlock).

    ``book_id`` resolves the per-book profile so the de-biased scorers/judge score
    the proposals on THEIR book's terms (slice D). ``judges`` are optional: with
    none, only the 4 deterministic sub-scores run and ``usefulness`` is 0 with
    ``acceptable=False`` → the gate stays BLOCKED (no false-green, fail-closed)."""

    user_id: UUID
    book_id: UUID | None = None
    judges: list[JudgeInput] = Field(default_factory=list)
    max_proposals: int = Field(default=100, ge=1, le=500)


class RunEvalResponse(BaseModel):
    run_id: str
    passed: bool
    p2_p3_unlocked: bool
    composite: float
    subscores: dict[str, float]
    fleiss_kappa: float | None
    judge_ensemble_acceptable: bool
    n_proposals: int


@router.post("/{project_id}/run", response_model=RunEvalResponse)
async def run_project_eval(
    project_id: UUID,
    body: RunEvalBody,
    pool: asyncpg.Pool = Depends(get_db),
) -> RunEvalResponse:
    """Score the project's non-rejected enriched proposals (de-biased by the book
    profile) + persist the scorecard so ``/gate-status`` reflects a real run.

    H0 / fail-closed: with no usable judges the usefulness sub-score is 0 and the
    gate stays BLOCKED — a passing gate REQUIRES a trustworthy judge ensemble."""
    rows, _total = await ProposalsRepo(pool).list(
        user_id=body.user_id, project_id=project_id, limit=body.max_proposals
    )
    rows = [r for r in rows if r.review_status != "rejected"]
    if not rows:
        raise HTTPException(
            status_code=422,
            detail="no enriched proposals to evaluate for this project",
        )
    props = [
        ScorableProposal.from_provenance_json(
            name=(r.canonical_name or r.target_ref or str(r.proposal_id)),
            entity_kind=r.entity_kind, origin=r.origin, technique=r.technique,
            confidence=float(r.confidence), review_status=r.review_status,
            provenance_json=r.provenance_json, source_refs_json=r.source_refs_json,
        )
        for r in rows
    ]

    profile = await get_book_profile(pool, body.book_id) if body.book_id else None
    suite = load_suite(_suite_path())

    judges = [
        JudgeSpec(label=j.label, model_ref=str(j.model_ref), family=j.family)
        for j in body.judges
    ]
    judge_fn_for = None
    if judges:
        judge_fn_for = make_judge_fn_for(
            settings.provider_registry_internal_url,
            settings.internal_service_token,
            {str(j.model_ref): str(body.user_id) for j in body.judges},
        )

    outcome = await run_eval(
        props, suite, judges=judges, judge_fn_for=judge_fn_for, profile=profile
    )
    sc = outcome.scorecard

    # run_id is timestamp-based (a route, not a resumable workflow — datetime is fine);
    # persist is idempotent on (project, suite_version, run_id).
    run_id = "run-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    await EvalRunsRepo(pool).persist(
        user_id=body.user_id, project_id=project_id, run_id=run_id,
        suite_version=sc.suite_version, baseline_version=sc.baseline_version,
        n_proposals=sc.n_proposals, subscores=sc.subscores, composite=sc.composite,
        fleiss_kappa=sc.fleiss_kappa,
        judge_ensemble_acceptable=sc.judge_ensemble_acceptable,
        passed=sc.passed, raw_report=sc.to_json(),
    )
    logger.info(
        "eval run %s project=%s n=%d composite=%.1f passed=%s",
        run_id, project_id, sc.n_proposals, sc.composite, sc.passed,
    )
    return RunEvalResponse(
        run_id=run_id, passed=sc.passed, p2_p3_unlocked=sc.passed,
        composite=sc.composite, subscores=sc.subscores, fleiss_kappa=sc.fleiss_kappa,
        judge_ensemble_acceptable=sc.judge_ensemble_acceptable,
        n_proposals=sc.n_proposals,
    )
