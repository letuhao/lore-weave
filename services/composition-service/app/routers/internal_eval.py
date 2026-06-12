"""A-EVAL — internal pairwise-judge endpoint (service-to-service, X-Internal-Token).

Hosts the longer-form pairwise comparator (engine/eval_judge) so the host eval
script stays a single POST→verdict and reuses the proven composition LLMClient +
gateway path (the only host-accessible LLM is the chat-service's stateful AG-UI
SSE). The judge PROMPT is server-controlled — this is a pairwise comparator, not
a generic LLM proxy. `user_id` rides in the body (no JWT on internal routes) so
the gateway can resolve the caller's BYOK judge model, mirroring persist-pass2.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.clients.llm_client import LLMClient
from app.deps import get_llm_client_dep
from app.engine.eval_judge import pairwise_judge
from app.engine.promise_audit import (
    audit_promises, extract_tracked_promises, score_promise_coverage,
)
from app.middleware.internal_auth import require_internal_token

router = APIRouter(prefix="/internal/composition/eval",
                   dependencies=[Depends(require_internal_token)])


class PairwiseJudgeRequest(BaseModel):
    user_id: UUID
    model_source: str = Field(min_length=1, max_length=50)
    model_ref: str = Field(min_length=1, max_length=200)
    draft_a: str = Field(min_length=1, max_length=60000)
    draft_b: str = Field(min_length=1, max_length=60000)
    source_language: str = "auto"


@router.post("/pairwise-judge")
async def pairwise_judge_endpoint(
    body: PairwiseJudgeRequest,
    llm: LLMClient = Depends(get_llm_client_dep),
) -> dict:
    """Compare two chapter drafts → {better: '1'|'2'|'tie', why, defects_1,
    defects_2}. Never raises on LLM/parse failure (returns a 'tie' + error)."""
    return await pairwise_judge(
        llm, user_id=str(body.user_id), model_source=body.model_source,
        model_ref=body.model_ref, draft_a=body.draft_a, draft_b=body.draft_b,
        source_language=body.source_language,
    )


class PromiseAuditRequest(BaseModel):
    user_id: UUID
    model_source: str = Field(min_length=1, max_length=50)
    model_ref: str = Field(min_length=1, max_length=200)
    arc_text: str = Field(min_length=1, max_length=120000)
    source_language: str = "auto"


@router.post("/promise-audit")
async def promise_audit_endpoint(
    body: PromiseAuditRequest,
    llm: LLMClient = Depends(get_llm_client_dep),
) -> dict:
    """FD-1 S4b — re-detect narrative promises in one arc's PROSE → {introduced,
    resolved, dropped, *_count, dropped_rate}. Ledger-BLIND (re-detects from text,
    not narrative_thread) so the eval can run it over both the ledger-ON and
    ledger-OFF arms apples-to-apples. Never raises on LLM/parse failure."""
    return await audit_promises(
        llm, user_id=str(body.user_id), model_source=body.model_source,
        model_ref=body.model_ref, arc_text=body.arc_text,
        source_language=body.source_language,
    )


# ── EVAL v2 — fixed-promise-set coverage (FD-8 follow-up) ──

class PromiseExtractRequest(BaseModel):
    user_id: UUID
    model_source: str = Field(min_length=1, max_length=50)
    model_ref: str = Field(min_length=1, max_length=200)
    premise: str = Field(min_length=1, max_length=8000)
    plan_text: str = Field(default="", max_length=40000)
    source_language: str = "auto"


@router.post("/promise-extract")
async def promise_extract_endpoint(
    body: PromiseExtractRequest,
    llm: LLMClient = Depends(get_llm_client_dep),
) -> dict:
    """FD-8 v2 — derive the FIXED tracked-promise set from the SPEC (premise +
    outline), NOT from generated prose, so the eval scores both arms against the
    same set. Returns {promises: [str]} ([] on failure)."""
    promises = await extract_tracked_promises(
        llm, user_id=str(body.user_id), model_source=body.model_source,
        model_ref=body.model_ref, premise=body.premise, plan_text=body.plan_text,
        source_language=body.source_language,
    )
    return {"promises": promises}


class PromiseCoverageRequest(BaseModel):
    user_id: UUID
    model_source: str = Field(min_length=1, max_length=50)
    model_ref: str = Field(min_length=1, max_length=200)
    promises: list[str] = Field(min_length=1, max_length=50)
    arc_text: str = Field(min_length=1, max_length=120000)
    source_language: str = "auto"


@router.post("/promise-coverage")
async def promise_coverage_endpoint(
    body: PromiseCoverageRequest,
    llm: LLMClient = Depends(get_llm_client_dep),
) -> dict:
    """FD-8 v2 — score one arc's prose against the FIXED promise set → per-promise
    {paid|progressing|abandoned|absent} + pay/sustained/abandon rates with a stable
    denominator (the fixed set). Separates ABANDONED (a real drop) from PROGRESSING
    (sustained tension at the cutoff). Never raises."""
    return await score_promise_coverage(
        llm, user_id=str(body.user_id), model_source=body.model_source,
        model_ref=body.model_ref, promises=body.promises, arc_text=body.arc_text,
        source_language=body.source_language,
    )
