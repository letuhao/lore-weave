"""Engine router (§5) — generate (stream) · suggest-cast · jobs · critique · dismiss.

POST /generate streams a draft via SSE: retrieve (M4 pack) → budget pre-check →
S2 cancel-in-flight for the node + idempotency → stream tokens → meter real usage
→ persist the job. Critique runs the advisory judge_prose with the work-settings
critic model (enforced distinct from the drafter, §4). CC2: critique re-resolves
ACTIVE canon at call time. CC4: a critic failure degrades, never blocks.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from app.clients.book_client import BookClient, BookClientError
from app.clients.glossary_client import GlossaryClient
from app.clients.knowledge_client import KnowledgeClient
from app.clients.llm_client import LLMClient
from app.config import settings
from app.db.repositories.canon_rules import CanonRulesRepo
from app.db.repositories.generation_jobs import GenerationJobsRepo
from app.db.repositories.outline import OutlineRepo
from app.db.repositories.scene_links import SceneLinksRepo
from app.db.repositories.works import WorksRepo
from app.deps import (
    get_book_client_dep, get_canon_rules_repo, get_generation_jobs_repo,
    get_glossary_client_dep, get_knowledge_client_dep, get_llm_client_dep,
    get_outline_repo, get_scene_links_repo, get_works_repo,
)
from app.engine.cowrite import build_messages, estimate_prompt_tokens, stream_draft
from app.engine.critic import judge_prose
from app.engine.select import select_draft
from app.reasoning import ReasoningSignals, score_effort
from loreweave_llm import infer_reasoning_control, resolve_reasoning
from app.middleware.jwt_auth import get_bearer_token, get_current_user
from app.packer import budget as B
from app.packer.pack import OwnershipError, PackRequest, pack
from app.packer.profile import from_settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/v1/composition")

_MAX_OUTPUT_DEFAULT = 1024


def _sse(data: dict[str, Any]) -> str:
    return f"data: {json.dumps(data, default=str)}\n\n"


class GenerateBody(BaseModel):
    outline_node_id: UUID
    # Literals → a bad value is a 422 at request validation, BEFORE any job is
    # created or the stream opens (else StreamRequest would ValidationError mid-
    # stream / mode would hit the DB CHECK → 500). /review-impl M6 MED#2.
    model_source: Literal["user_model", "platform_model"]
    model_ref: UUID
    operation: str = "draft_scene"
    mode: Literal["cowrite", "auto"] = "cowrite"
    guide: str = ""
    max_output_tokens: int = Field(default=_MAX_OUTPUT_DEFAULT, ge=1, le=8192)
    # Author reasoning preference. "auto" → the capability-aware resolver decides
    # (adaptive model → pass through; effort model → rule-based scorer; non-
    # reasoning → no-op). off/low/medium/high are explicit overrides. The
    # model_* hints (from the FE's selected user-model) let the resolver pick the
    # strategy per registered model — a UX policy, not an authz boundary.
    reasoning: Literal["off", "auto", "low", "medium", "high"] = "auto"
    model_kind: str | None = None
    model_name: str | None = None
    idempotency_key: str | None = None


class CritiqueBody(BaseModel):
    # Optional: an advisory critique may run before a revision exists (the FE
    # critiques the just-generated passage). When present it anchors the
    # critique for calibration.
    target_revision_id: UUID | None = None
    passage: str | None = None  # FE sends the accepted prose; falls back to job result


class DismissBody(BaseModel):
    rule_id: str


class SuggestCastBody(BaseModel):
    guide: str = ""


async def _load_work_node(works, outline, user_id, project_id, node_id):
    work = await works.get(user_id, project_id)
    if work is None:
        raise HTTPException(status_code=404, detail="work not found")
    node = await outline.get_node(user_id, node_id)
    if node is None or str(node.project_id) != str(project_id):
        raise HTTPException(status_code=404, detail="scene not found")
    return work, node


@router.post("/works/{project_id}/generate")
async def generate(
    project_id: UUID,
    body: GenerateBody,
    user_id: UUID = Depends(get_current_user),
    bearer: str = Depends(get_bearer_token),
    works: WorksRepo = Depends(get_works_repo),
    outline: OutlineRepo = Depends(get_outline_repo),
    scene_links: SceneLinksRepo = Depends(get_scene_links_repo),
    canon: CanonRulesRepo = Depends(get_canon_rules_repo),
    jobs: GenerationJobsRepo = Depends(get_generation_jobs_repo),
    book: BookClient = Depends(get_book_client_dep),
    glossary: GlossaryClient = Depends(get_glossary_client_dep),
    knowledge: KnowledgeClient = Depends(get_knowledge_client_dep),
    llm: LLMClient = Depends(get_llm_client_dep),
) -> Any:  # StreamingResponse (cowrite) | JSONResponse (auto)
    work, node = await _load_work_node(works, outline, user_id, project_id, body.outline_node_id)

    # Retrieve (M4 packer) — raises OwnershipError (404) / BookClientError (502).
    try:
        pc = await pack(
            PackRequest(user_id=user_id, project_id=project_id, book_id=work.book_id,
                        node=node.model_dump(mode="python"), bearer=bearer, guide=body.guide,
                        settings=work.settings),
            book=book, glossary=glossary, knowledge=knowledge, canon_repo=canon,
            outline_repo=outline, scene_links_repo=scene_links,
            budget_tokens=settings.pack_token_budget,
        )
    except OwnershipError:
        raise HTTPException(status_code=404, detail="book not found")
    except BookClientError:
        raise HTTPException(status_code=502, detail={"code": "BOOK_SERVICE_UNAVAILABLE"})

    messages = build_messages(pc.prompt, pc.profile, body.operation, body.guide)
    counter = B.default_counter()
    prompt_estimate = estimate_prompt_tokens(messages, counter)
    # Budget pre-check (local advisory): refuse if the prompt alone blows the cap.
    prompt_ceiling = settings.pack_token_budget * 2
    if prompt_estimate > prompt_ceiling:
        raise HTTPException(status_code=413, detail={
            "code": "PROMPT_TOO_LARGE", "estimate": prompt_estimate, "ceiling": prompt_ceiling})

    # Resolve the reasoning ("thinking") directive (auto-reasoning, §integration).
    # Signals are cheap things we already have: the operation, the scene's tension
    # + present entities, and the active canon load (count + any reveal_gate).
    # NOTE: canon counts are PROJECT-LEVEL (all active rules), not scene-windowed —
    # a deliberate conservative approximation that biases early scenes toward more
    # thinking; precise per-scene scoping is a tuning follow-up (D-AUTO-REASONING-SCENE-SIGNALS).
    active_rules = await canon.list_active(user_id, project_id)
    signals = ReasoningSignals(
        operation=body.operation,
        n_canon_rules=len(active_rules),
        n_present_entities=len(node.present_entity_ids or []),
        has_reveal_gate=any(r.scope == "reveal_gate" for r in active_rules),
        tension=node.tension,
        guide=body.guide,
    )
    control = infer_reasoning_control(body.model_kind, body.model_name)
    reasoning = resolve_reasoning(
        user_pref=body.reasoning, model_control=control,
        auto_effort=score_effort(signals),
        auto_source=str(work.settings.get("reasoning_engine", "rule_based")),
    )

    job, created = await jobs.create(
        user_id, project_id, operation=body.operation, outline_node_id=node.id,
        mode=body.mode, status="running",
        input={"model_source": body.model_source, "model_ref": str(body.model_ref),
               "operation": body.operation, "prompt_estimate": prompt_estimate,
               "reasoning": reasoning.source, "reasoning_effort": reasoning.effort},
        idempotency_key=body.idempotency_key,
    )
    # S2: cancel OTHER in-flight jobs for this node — only when we actually
    # created a new one (an idempotent replay must NOT cancel the original
    # still-streaming job). Exclude the new job itself. /review-impl M6 MED#1.
    if created:
        for active in await jobs.list_active_for_node(user_id, project_id, node.id):
            if str(active.id) != str(job.id):
                await jobs.update_status(user_id, active.id, "cancelled")

    # ── AUTO path (V1 A1): diverge→converge, NON-stream, returns the winner. The
    # co-write STREAM path is below. The rerank judge prefers the work's DISTINCT
    # critic model (anti-self-reinforcement §4); falls back to the drafter.
    if body.mode == "auto":
        if not created:  # idempotent replay → return the existing job, don't re-run
            return JSONResponse({"job_id": str(job.id), "mode": "auto", "replay": True,
                                 "text": (job.result or {}).get("text", ""), "status": job.status})
        sdict = work.settings or {}
        c_src, c_ref = sdict.get("critic_model_source"), sdict.get("critic_model_ref")
        distinct = bool(c_ref and c_src and str(c_ref) != str(body.model_ref))
        try:
            sel = await select_draft(
                llm, llm, user_id=str(user_id),
                drafter_source=body.model_source, drafter_ref=str(body.model_ref),
                judge_source=str(c_src) if distinct else body.model_source,
                judge_ref=str(c_ref) if distinct else str(body.model_ref),
                packed_prompt=pc.prompt, profile=pc.profile, operation=body.operation,
                guide=body.guide, k=settings.compose_diverge_k, prompt_est=prompt_estimate,
                max_tokens=body.max_output_tokens, temperature=settings.compose_diverge_temperature,
                reasoning_effort=None if reasoning.passthrough else reasoning.effort,
            )
        except Exception as exc:  # diverge produced nothing / transport — fail the job, 502
            logger.warning("auto select failed: %s", exc)
            await jobs.update_status(user_id, job.id, "failed")
            raise HTTPException(status_code=502, detail={"code": "GENERATE_FAILED"})
        w = sel.winner
        await jobs.update_status(
            user_id, job.id, "completed",
            result={"text": w.text, "input_tokens": w.metering.input_tokens,
                    "output_tokens": w.metering.output_tokens, "measured": w.metering.measured,
                    "k": len(sel.candidates), "winner_index": sel.winner_index,
                    "rerank_reason": sel.rerank_reason, "rerank_measured": sel.rerank_measured,
                    "candidates": [c.text for c in sel.candidates]},
        )
        return JSONResponse({
            "job_id": str(job.id), "mode": "auto", "status": "completed", "text": w.text,
            "winner_index": sel.winner_index, "k": len(sel.candidates),
            "rerank_reason": sel.rerank_reason, "rerank_measured": sel.rerank_measured,
            "grounding_available": pc.grounding_available,
            "reasoning_source": reasoning.source, "reasoning_effort": reasoning.effort,
        })

    async def event_gen():
        yield _sse({"type": "job", "job_id": str(job.id), "created": created,
                    "grounding_available": pc.grounding_available,
                    "reasoning_source": reasoning.source,
                    "reasoning_effort": reasoning.effort})
        if not created:
            # Idempotent replay — don't re-stream; report the existing job.
            yield _sse({"type": "done", "job_id": str(job.id), "status": job.status, "replay": True})
            return
        final: dict[str, Any] | None = None
        async for ev in stream_draft(
            llm.sdk, user_id=str(user_id), model_source=body.model_source,
            model_ref=str(body.model_ref), messages=messages,
            prompt_token_estimate=prompt_estimate, max_output_tokens=body.max_output_tokens,
            hard_cap_output=body.max_output_tokens * 2,
            # passthrough (adaptive model) → omit, let the model self-decide.
            reasoning_effort=None if reasoning.passthrough else reasoning.effort,
        ):
            if ev["type"] == "usage":
                final = ev
            else:
                yield _sse(ev)
        if final is not None:
            m = final["metering"]
            await jobs.update_status(
                user_id, job.id, "completed",
                result={"text": final["text"], "input_tokens": m.input_tokens,
                        "output_tokens": m.output_tokens, "measured": m.measured,
                        "capped": final.get("capped", False)},
            )
            yield _sse({"type": "done", "job_id": str(job.id), "status": "completed",
                        "output_tokens": m.output_tokens, "measured": m.measured,
                        "capped": final.get("capped", False)})
        else:
            await jobs.update_status(user_id, job.id, "failed")
            yield _sse({"type": "done", "job_id": str(job.id), "status": "failed"})

    return StreamingResponse(event_gen(), media_type="text/event-stream")


@router.post("/works/{project_id}/scenes/{node_id}/suggest-cast")
async def suggest_cast(
    project_id: UUID, node_id: UUID, body: SuggestCastBody,
    user_id: UUID = Depends(get_current_user),
    works: WorksRepo = Depends(get_works_repo),
    outline: OutlineRepo = Depends(get_outline_repo),
    glossary: GlossaryClient = Depends(get_glossary_client_dep),
) -> dict[str, Any]:
    work, node = await _load_work_node(works, outline, user_id, project_id, node_id)
    query = " ".join(str(x) for x in [node.goal, node.synopsis, node.title, body.guide] if x)
    bios = await glossary.select_for_context(work.book_id, user_id, query)
    suggested = [b["entity_id"] for b in bios if b.get("entity_id")]
    return {"suggested_entity_ids": suggested}


@router.get("/jobs/{job_id}")
async def get_job(
    job_id: UUID,
    user_id: UUID = Depends(get_current_user),
    jobs: GenerationJobsRepo = Depends(get_generation_jobs_repo),
) -> dict[str, Any]:
    job = await jobs.get(user_id, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return job.model_dump(mode="json")


@router.post("/jobs/{job_id}/critique")
async def critique(
    job_id: UUID, body: CritiqueBody,
    user_id: UUID = Depends(get_current_user),
    jobs: GenerationJobsRepo = Depends(get_generation_jobs_repo),
    works: WorksRepo = Depends(get_works_repo),
    canon: CanonRulesRepo = Depends(get_canon_rules_repo),
    llm: LLMClient = Depends(get_llm_client_dep),
) -> dict[str, Any]:
    job = await jobs.get(user_id, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    work = await works.get(user_id, job.project_id)
    if work is None:
        raise HTTPException(status_code=404, detail="work not found")

    settings_dict = work.settings or {}
    critic_src = settings_dict.get("critic_model_source")
    critic_ref = settings_dict.get("critic_model_ref")
    drafter_ref = (job.input or {}).get("model_ref")
    # Anti-self-reinforcement: the critic MUST be a distinct model. No critic
    # configured, or same as the drafter → skip the critique (advisory) + warn.
    if not critic_ref or not critic_src or str(critic_ref) == str(drafter_ref):
        return {"critic": None, "warning": "critique skipped: no distinct critic model configured"}

    passage = body.passage if body.passage is not None else (job.result or {}).get("text", "")
    # CC2: re-resolve the ACTIVE canon at critique time — a deleted/archived rule
    # is never enforced.
    rules = await canon.list_active(user_id, job.project_id)
    active_rules = [{"rule_id": str(r.id), "text": r.text} for r in rules]

    critic = await judge_prose(
        llm, user_id=str(user_id), model_source=str(critic_src), model_ref=str(critic_ref),
        passage=passage, active_rules=active_rules, present_facts=[],
        profile=from_settings(settings_dict),
    )
    await jobs.update_status(user_id, job_id, job.status, critic=critic,
                             target_revision_id=body.target_revision_id)
    return {"critic": critic}


@router.post("/jobs/{job_id}/dismiss-violation")
async def dismiss_violation(
    job_id: UUID, body: DismissBody,
    user_id: UUID = Depends(get_current_user),
    jobs: GenerationJobsRepo = Depends(get_generation_jobs_repo),
) -> dict[str, Any]:
    job = await jobs.get(user_id, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    critic = dict(job.critic or {})
    violations = critic.get("violations") or []
    found = False
    for v in violations:
        if isinstance(v, dict) and str(v.get("rule_id")) == body.rule_id:
            v["dismissed"] = True
            found = True
    if not found:
        raise HTTPException(status_code=404, detail="violation not found")
    critic["violations"] = violations
    await jobs.update_status(user_id, job_id, job.status, critic=critic)
    return {"critic": critic}
