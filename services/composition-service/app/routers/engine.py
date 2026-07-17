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
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi import status as http_status
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field, StringConstraints

from app.clients.book_client import BookClient, BookClientError
from app.clients.glossary_client import GlossaryClient
from app.clients.knowledge_client import KnowledgeClient
from app.clients.llm_client import LLMClient
from app.config import settings
from app.worker.events import enqueue_job
from app.db.repositories import ChapterJobInFlightError, ReferenceViolationError
from app.db.repositories.canon_rules import CanonRulesRepo
from app.db.repositories.generation_corrections import (
    GenerationCorrectionsRepo, count_changed_blocks,
)
from app.clients.model_name import resolve_model_name
from app.db.repositories.generation_jobs import GenerationJobsRepo
from app.db.repositories.grounding_pins import GroundingPinsRepo
from app.db.repositories.style_voice import StyleProfileRepo, VoiceProfileRepo
from app.db.repositories.narrative_thread import NarrativeThreadRepo
from app.db.repositories.motif_application import MotifApplicationRepo
from app.db.repositories.motif_repo import MotifRepo
from app.db.repositories.motif_retrieve import MotifRetriever
from app.db.pool import get_pool
from app.db.repositories.outline import OutlineRepo
from app.db.repositories.references import ReferencesRepo, reference_embed_model
from app.db.repositories.scene_links import SceneLinksRepo
from app.db.repositories.works import WorksRepo
from app.clients.embedding_client import EmbeddingClient
from app.deps import (
    get_book_client_dep, get_canon_rules_repo, get_derivatives_repo,
    get_embedding_client_dep, get_generation_corrections_repo, get_generation_jobs_repo,
    get_glossary_client_dep, get_grant_client_dep, get_grounding_pins_repo,
    get_knowledge_client_dep, get_llm_client_dep, get_motif_application_repo_opt,
    get_motif_repo_opt, get_narrative_thread_repo,
    get_outline_repo, get_references_repo, get_scene_links_repo,
    get_structure_repo, get_style_profile_repo, get_voice_profile_repo, get_works_repo,
)
from app.db.repositories.derivatives import DerivativesRepo
from app.db.repositories.structure import StructureRepo
from app.db.models import CorrectionKind
from app.engine.adaptive_k import adaptive_k
from app.engine.chapter_gen import build_chapter_pack_node, union_cast
from app.engine.prose_doc import text_to_tiptap_doc
from app.engine.stitch import prepend_scene_headings, stitch_chapter
from app.engine.canon_reflect import run_canon_reflect
from app.engine.narrative_thread import detect_and_update_threads
from app.engine.compress import compress
from app.engine.cowrite import (
    SELECTION_MAX_CHARS, build_messages, build_selection_messages,
    estimate_prompt_tokens, stream_draft,
)
from app.engine.critic import judge_prose
from app.engine.critic_override import (
    critique_overrides,
    evaluate_override_gate as co_evaluate_override_gate,
)
from app.engine.select import diverge, select_draft
from app.reasoning import ReasoningSignals, score_effort
from loreweave_context import scale_by_window
from loreweave_llm import infer_reasoning_control, resolve_reasoning
from app.middleware.jwt_auth import get_bearer_token, get_current_user
from app.packer import budget as B
from app.grant_client import GrantClient, GrantLevel
from app.grant_deps import InsufficientGrant, authorize_book
from app.packer.pack import OwnershipError, PackRequest, build_derivative_context, pack
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
    # Chapter-assembly mode override (B1). None → the per-scene endpoint always
    # assembles per scene; an explicit 'chapter' here 409-redirects to the chapter
    # endpoint (B2). Literal → a bad value 422s at request validation.
    assembly_mode: Literal["per_scene", "chapter"] | None = None


class SelectionEditBody(BaseModel):
    # T3.2 — selection-scoped edit. The Literal makes a bad operation a 422 at
    # request validation (before any job/stream), mirroring GenerateBody.mode; the
    # engine's build_selection_messages ALSO raises on an unregistered op (defense
    # in depth — the LOOM-39 missing-enum lesson).
    operation: Literal["rewrite", "expand", "describe"]
    selection: Annotated[str, StringConstraints(min_length=1, max_length=SELECTION_MAX_CHARS)]
    # PO: couple grounding to the compose panel's active scene. Optional — a free
    # selection may sit in a chapter with no scene node → voice-only grounding.
    scene_context: UUID | None = None
    model_source: Literal["user_model", "platform_model"]
    model_ref: UUID
    guide: str = ""
    max_output_tokens: int = Field(default=_MAX_OUTPUT_DEFAULT, ge=1, le=8192)
    reasoning: Literal["off", "auto", "low", "medium", "high"] = "auto"
    model_kind: str | None = None
    model_name: str | None = None


class GenerateChapterBody(BaseModel):
    # B2 chapter single-pass: no outline_node_id (chapter-scoped) and no
    # assembly_mode (this endpoint IS chapter). Mirrors GenerateBody otherwise.
    model_source: Literal["user_model", "platform_model"]
    model_ref: UUID
    operation: str = "draft_chapter"
    guide: str = ""
    # None → settings.chapter_gen_max_tokens (a whole chapter is one long pass,
    # larger than the per-scene default). An explicit value still caps at 8192.
    max_output_tokens: int | None = Field(default=None, ge=1, le=8192)
    reasoning: Literal["off", "auto", "low", "medium", "high"] = "auto"
    model_kind: str | None = None
    model_name: str | None = None
    idempotency_key: str | None = None
    # MED-2: write the assembled chapter to the book-service draft (best-effort).
    # Eval / dry-run callers set False to get just the generated text.
    persist: bool = True


class StitchBody(BaseModel):
    # B3 stitch pass: no outline_node_id, no assembly_mode (stitch is the
    # per_scene+stitch step). Mirrors GenerateChapterBody.
    model_source: Literal["user_model", "platform_model"]
    model_ref: UUID
    max_output_tokens: int | None = Field(default=None, ge=1, le=8192)
    reasoning: Literal["off", "auto", "low", "medium", "high"] = "auto"
    model_kind: str | None = None
    model_name: str | None = None
    idempotency_key: str | None = None
    persist: bool = True


class PersistJobBody(BaseModel):
    # M4 Option A accept-step. Optional override for the book-draft commit message;
    # defaults to an "AI chapter draft (<mode>, accepted)" label.
    commit_message: Annotated[str, StringConstraints(max_length=500)] | None = None


class ScenePromoteProseBody(BaseModel):
    # M3 (WS-B3 prose-persist-on-promote): the chosen take's ghost PLAIN TEXT for a
    # promoted derivative scene. Persisted scene-scoped in the DERIVATIVE project's
    # synthetic-job store (never the shared book draft). `text` is bounded so an
    # oversized body 422s at the boundary; empty/whitespace is rejected in-handler
    # with EMPTY_SCENE_PROSE (a structurally-present but blank scene is skipped, not
    # written). `idempotency_key` is optional (the persist is already idempotent on
    # node_id; the key is trace-only).
    text: Annotated[str, StringConstraints(max_length=200_000)]
    idempotency_key: Annotated[str, StringConstraints(max_length=200)] | None = None
    # S5-B4 (D-S5-BRANCHDIFF-CORRESPONDENCE) — the CANON scene this take is an alternate
    # of, so the branch-diff can pair this derivative scene to its canon counterpart
    # (the promoted scene gets a fresh dense story_order that can't be paired by order).
    anchor_node_id: UUID | None = None


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


class CorrectionBody(BaseModel):
    # The human-gate action (§2). accept-as-is is intentionally NOT a kind — it
    # is the reranker's own pick, mining it is self-reinforcement (H2).
    kind: CorrectionKind
    # pick_different → which candidate the author chose instead of the winner.
    chosen_candidate_index: int | None = Field(default=None, ge=0)
    # regenerate → the author's steering text. Stored, never on the wire (§5).
    # Capped to the row model's _Long bound so an oversized value 422s here
    # rather than committing the row+event and then 500ing on read-back validation
    # (/review-impl MED#1).
    guidance: Annotated[str, StringConstraints(max_length=20000)] | None = None
    # edit → the author's edited prose (drives the change-magnitude + opt-in raw).
    edited_text: str | None = None
    # §8.3 optional chain: the regenerated job that superseded this one (if known).
    regenerated_to_job_id: UUID | None = None


async def _gate_work(works, grant, user_id, project_id, need=GrantLevel.EDIT):
    """Resolve the Work by project (un-user-scoped — 25 PM-9) and gate the
    caller's E0 grant on its book (PM-8: access is decided HERE, never in the
    repos). Default EDIT — prose-gen/spend tier (E0-4c); reads pass VIEW.
    none→404 (no oracle), under-tier→403. pack()'s own authorize_book stays as
    the defense-in-depth chokepoint on the packing paths."""
    work = await works.get(project_id)
    if work is None:
        raise HTTPException(status_code=404, detail="work not found")
    try:
        await authorize_book(grant, work.book_id, user_id, need)
    except OwnershipError:
        raise HTTPException(status_code=404, detail="work not found")
    except InsufficientGrant:
        raise HTTPException(status_code=403, detail="insufficient access")
    return work


async def _load_work_node(works, outline, grant, user_id, project_id, node_id,
                          need=GrantLevel.EDIT):
    work = await _gate_work(works, grant, user_id, project_id, need)
    node = await outline.get_node(node_id)
    if node is None or str(node.project_id) != str(project_id):
        raise HTTPException(status_code=404, detail="scene not found")
    return work, node


async def _maybe_detect_narrative_threads(
    work, *, llm, repo, user_id, project_id, scene_text,
    opened_at_node, model_source, model_ref, source_language,
) -> None:
    """FD-1 (narrative_thread S2): best-effort promise-ledger producer over a
    just-generated passage. Gated per-Work on `narrative_thread_enabled` (default
    OFF → zero cost). NEVER raises into the generate path (advisory, F1). Extracted
    so the gate + best-effort-swallow wiring is unit-testable (review-impl MED#1)."""
    if not (work.settings or {}).get("narrative_thread_enabled"):
        return
    try:
        await detect_and_update_threads(
            llm, repo, user_id=user_id, project_id=project_id,
            scene_text=scene_text, opened_at_node=opened_at_node,
            drafter_source=model_source, drafter_ref=str(model_ref),
            source_language=source_language,
            max_open=settings.narrative_thread_max_open_per_scene,
        )
    except Exception:  # noqa: BLE001 — advisory; must not fail the generate
        logger.warning("narrative_thread S2 producer failed (advisory)", exc_info=True)


async def _open_promise_count(work, *, repo, project_id) -> int | None:
    """FD-1 S4a — the advisory unpaid-promise DEBT count (§7) after a generated
    chapter. None when narrative_thread is off (no read); best-effort — never
    raises into the generate path. Extracted so the gate/swallow is unit-testable."""
    if not (work.settings or {}).get("narrative_thread_enabled"):
        return None
    try:
        return await repo.count_open(project_id)
    except Exception:  # noqa: BLE001 — advisory; must not fail the generate
        logger.warning("open_promise_count read failed (advisory)", exc_info=True)
        return None


def _scene_marker_rows(scenes: Any) -> list[dict[str, Any]] | None:
    """F4 — shape outline scene nodes into the `[{id, title}]` rows
    `text_to_tiptap_doc` matches sceneId markers against. Best-effort: any
    surprise shape returns None (persist proceeds without markers, never blocks)."""
    try:
        return [{"id": str(s.id), "title": s.title} for s in (scenes or [])] or None
    except Exception:  # noqa: BLE001 — advisory; must never fail a persist
        logger.warning("scene-marker shaping failed (advisory)", exc_info=True)
        return None


async def _persist_chapter_draft(
    book: BookClient, book_id: UUID, chapter_id: UUID, bearer: str,
    text: str, commit_message: str,
    scenes: list[dict[str, Any]] | None = None,
) -> tuple[bool, int | None, str | None]:
    """B3/MED-2 — BEST-EFFORT write of an AI-assembled chapter into the
    book-service draft. Returns (persisted, draft_version, error_code) and NEVER
    raises: a persist failure (concurrent edit 409, outage) must not discard the
    generated text, which is already durable in generation_job.result (the
    cross-store best-effort rule). The body is a Tiptap doc built to match
    book-service's own shape (prose_doc.text_to_tiptap_doc) — book's PATCH stores
    it verbatim with no text→doc conversion. With `scenes` ([{id, title}]), a
    `### <scene title>` line in the text becomes a heading node carrying
    `attrs.sceneId` (F4 D-SCENEMARKER-EMIT) so the chapter lands pre-anchored."""
    try:
        current = await book.get_draft(book_id, chapter_id, bearer)
        updated = await book.patch_draft(
            book_id, chapter_id, bearer,
            body=text_to_tiptap_doc(text, scenes),
            expected_draft_version=current.get("draft_version"),
            body_format="json", commit_message=commit_message,
        )
        return True, updated.get("draft_version"), None
    except BookClientError as exc:
        logger.warning("chapter draft persist failed (best-effort, kept in job): %s", exc)
        return False, None, exc.code or "BOOK_DRAFT_PERSIST_FAILED"
    except Exception:  # noqa: BLE001 — /review-impl Cycle-2 #2: honor "NEVER raises".
        # A non-BookClientError (raw httpx timeout/connect error) must NOT escape:
        # the text is already durable in generation_job.result, and an escape would
        # leave the job stuck `running` (feeding the #1 lockout). Best-effort = swallow.
        logger.warning("chapter draft persist raised (best-effort, kept in job)", exc_info=True)
        return False, None, "BOOK_DRAFT_PERSIST_FAILED"


@router.post("/works/{project_id}/generate")
async def generate(
    project_id: UUID,
    body: GenerateBody,
    user_id: UUID = Depends(get_current_user),
    bearer: str = Depends(get_bearer_token),
    works: WorksRepo = Depends(get_works_repo),
    outline: OutlineRepo = Depends(get_outline_repo),
    structures: StructureRepo | None = Depends(get_structure_repo),
    motif_apps: MotifApplicationRepo | None = Depends(get_motif_application_repo_opt),  # X-7 motif lens
    motifs: MotifRepo | None = Depends(get_motif_repo_opt),  # X-7 motif lens
    scene_links: SceneLinksRepo = Depends(get_scene_links_repo),
    canon: CanonRulesRepo = Depends(get_canon_rules_repo),
    jobs: GenerationJobsRepo = Depends(get_generation_jobs_repo),
    book: BookClient = Depends(get_book_client_dep),
    glossary: GlossaryClient = Depends(get_glossary_client_dep),
    knowledge: KnowledgeClient = Depends(get_knowledge_client_dep),
    llm: LLMClient = Depends(get_llm_client_dep),
    narrative_threads: NarrativeThreadRepo = Depends(get_narrative_thread_repo),
    grounding_pins: GroundingPinsRepo = Depends(get_grounding_pins_repo),
    style_profiles: StyleProfileRepo = Depends(get_style_profile_repo),
    voice_profiles: VoiceProfileRepo = Depends(get_voice_profile_repo),
    references: ReferencesRepo = Depends(get_references_repo),
    embedder: EmbeddingClient = Depends(get_embedding_client_dep),
    derivatives: DerivativesRepo = Depends(get_derivatives_repo),
    grant: GrantClient = Depends(get_grant_client_dep),
) -> Any:  # StreamingResponse (cowrite) | JSONResponse (auto)
    work, node = await _load_work_node(
        works, outline, grant, user_id, project_id, body.outline_node_id)

    # B2 — this is the PER-SCENE endpoint. An explicit assembly_mode='chapter'
    # override here is a caller mistake (chapter assembly has its own endpoint),
    # so 409-redirect rather than silently producing a per-scene draft. A work
    # whose DEFAULT is 'chapter' does NOT block per-scene co-write here: the mode
    # selects the autonomous entrypoint, not whether co-writing a scene is allowed.
    if body.assembly_mode == "chapter":
        raise HTTPException(status_code=409, detail={
            "code": "USE_CHAPTER_ENDPOINT",
            "detail": "this work assembles by chapter; "
                      "POST /v1/composition/works/{project_id}/chapters/{chapter_id}/generate"})
    assembly_mode = "per_scene"  # echoed below — this endpoint always assembles per scene

    # S2 — bind the compress primitive over the drafter model + the Work's source
    # language; pack() calls it only when the raw story-so-far exceeds budget.
    _src_lang = from_settings(work.settings).source_language

    # Model-context-aware budget scaling — a flat pack/compress budget tuned for a
    # mid-size window must not cap a genuinely bigger model at the same number
    # (resolved once per request; best-effort, unresolvable ⇒ the flat defaults).
    _context_length = await llm.resolve_context_length(body.model_source, str(body.model_ref))
    _pack_budget = scale_by_window(settings.pack_token_budget, _context_length)
    _compress_chars = scale_by_window(settings.compress_max_input_chars, _context_length)

    async def _compress_fn(older: list[str], timeline_texts: list[str], plan: str) -> str:
        return await compress(
            llm, user_id=str(user_id), model_source=body.model_source,
            model_ref=str(body.model_ref), prose=older, timeline=timeline_texts,
            plan=plan, source_language=_src_lang,
            max_input_chars=_compress_chars,
        )

    # C25 — dị bản two-project merge inputs (base project + branch + fresh
    # overrides); empty for a non-derivative Work.
    deriv = await build_derivative_context(
        work, works_repo=works, derivatives_repo=derivatives)
    # Retrieve (M4 packer) — raises OwnershipError (404) / BookClientError (502).
    try:
        pc = await pack(
            PackRequest(user_id=user_id, project_id=project_id, book_id=work.book_id,
                        node=node.model_dump(mode="python"), bearer=bearer, guide=body.guide,
                        settings=work.settings,
                        # M1 — make the pack op-aware: `adapt_scene` (on a derivative)
                        # fires gather_source_scene; every other op is byte-unchanged.
                        operation=body.operation,
                        source_project_id=deriv.source_project_id,
                        branch_point=deriv.branch_point, overrides=deriv.overrides,
                        pov_anchor=deriv.pov_anchor),
            book=book, glossary=glossary, knowledge=knowledge, canon_repo=canon,
            outline_repo=outline, scene_links_repo=scene_links,
            structure_repo=structures,  # 23 BA12 — the arc lens
            motif_application_repo=motif_apps,  # X-7 — the motif lens (scene beats)
            motif_repo=motifs,  # X-7 — ditto; BOTH must ride or the lens is dormant
            budget_tokens=_pack_budget,
            jobs_repo=jobs,  # S1 state-reinjection fallback source (prior generated scenes)
            compress_fn=_compress_fn,  # S2 long-chapter state compression
            narrative_threads_repo=narrative_threads,  # FD-1 S3 open-promise re-injection
            grounding_pins_repo=grounding_pins,  # T3.4 — generation honors per-scene pins
            style_profile_repo=style_profiles,  # T3.5 — density/pace
            voice_profile_repo=voice_profiles,  # T3.5 — present-character voices
            references_repo=references,  # T3.6 — author reference shelf
            embedding_client=embedder,  # T3.6 — provider-registry embed
            need=GrantLevel.EDIT,  # E0-4c: prose-gen is a write/spend → EDIT tier
        )
    except OwnershipError:
        raise HTTPException(status_code=404, detail="book not found")
    except InsufficientGrant:
        raise HTTPException(status_code=403, detail="insufficient access")
    except BookClientError:
        raise HTTPException(status_code=502, detail={"code": "BOOK_SERVICE_UNAVAILABLE"})

    messages = build_messages(pc.prompt, pc.profile, body.operation, body.guide)
    counter = B.default_counter()
    prompt_estimate = estimate_prompt_tokens(messages, counter)
    # Budget pre-check (local advisory): refuse if the prompt alone blows the cap.
    prompt_ceiling = _pack_budget * 2
    if prompt_estimate > prompt_ceiling:
        raise HTTPException(status_code=413, detail={
            "code": "PROMPT_TOO_LARGE", "estimate": prompt_estimate, "ceiling": prompt_ceiling})

    # Resolve the reasoning ("thinking") directive (auto-reasoning, §integration).
    # Signals are cheap things we already have: the operation, the scene's tension
    # + present entities, and the active canon load (count + any reveal_gate).
    # NOTE: canon counts are PROJECT-LEVEL (all active rules), not scene-windowed —
    # a deliberate conservative approximation that biases early scenes toward more
    # thinking; precise per-scene scoping is a tuning follow-up (D-AUTO-REASONING-SCENE-SIGNALS).
    active_rules = await canon.list_active(project_id)
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

    # M4 — the worker decouples ONLY the AUTO compute (diverge→converge→reflect);
    # the cowrite STREAM path stays inline (a worker can't stream to the client).
    worker_auto = settings.composition_worker_enabled and body.mode == "auto"
    job_input: dict[str, Any] = {
        "model_source": body.model_source, "model_ref": str(body.model_ref),
        "operation": body.operation, "prompt_estimate": prompt_estimate,
        "reasoning": reasoning.source, "reasoning_effort": reasoning.effort,
    }
    if worker_auto:
        # Serialize the bearer-resolved context (the worker has no user bearer to
        # re-run pack()) + the scene signals the auto compute needs. worker_op is
        # the canonical dispatch key (operation is the free-form prose op).
        sdict = work.settings or {}
        c_src, c_ref = sdict.get("critic_model_source"), sdict.get("critic_model_ref")
        distinct = bool(c_ref and c_src and str(c_ref) != str(body.model_ref))
        job_input.update({
            "worker_op": "generate",
            "packed_prompt": pc.prompt, "scene_sort_order": pc.scene_sort_order,
            "present_entity_ids": [str(e) for e in (node.present_entity_ids or [])],
            "beat_role": node.beat_role, "tension": node.tension,
            "outline_node_id": str(node.id), "guide": body.guide,
            "max_out": body.max_output_tokens,
            "reasoning_passthrough": reasoning.passthrough,
            "grounding_available": pc.grounding_available,
            "reinjected_promise_count": pc.reinjected_promise_count,
            "assembly_mode": assembly_mode,
            "reflect_max_iters": max(0, min(3, int(sdict.get("reflect_max_iters", 1) or 1))),
            "critic_source": str(c_src) if distinct else None,
            "critic_ref": str(c_ref) if distinct else None,
        })

    job, created = await jobs.create(
        project_id, created_by=user_id, operation=body.operation, outline_node_id=node.id,
        mode=body.mode, status="pending" if worker_auto else "running",
        input=job_input,
        idempotency_key=body.idempotency_key,
    )
    # S2: cancel OTHER in-flight jobs for this node — only when we actually
    # created a new one (an idempotent replay must NOT cancel the original
    # still-streaming job). Exclude the new job itself. /review-impl M6 MED#1.
    if created:
        for active in await jobs.list_active_for_node(project_id, node.id):
            if str(active.id) != str(job.id):
                await jobs.update_status(active.id, "cancelled")

    # M4 worker auto path: the pack/cancel/reasoning all ran above (bearer); now
    # persist-input + enqueue + 202. GET /jobs/{id} polls the result. A same-key
    # replay returns the existing job (don't re-enqueue).
    if worker_auto:
        if not created:
            r = job.result or {}
            return JSONResponse({"job_id": str(job.id), "mode": "auto", "replay": True,
                                 "text": r.get("text", ""), "status": job.status,
                                 "winner_index": r.get("winner_index"), "k": r.get("k"),
                                 "candidates": r.get("candidates", []),
                                 "assembly_mode": assembly_mode})
        enqueued = await enqueue_job(
            settings.redis_url, job_id=str(job.id),
            user_id=str(user_id), project_id=str(project_id))
        return JSONResponse(
            status_code=http_status.HTTP_202_ACCEPTED,
            content={"job_id": str(job.id), "status": "pending",
                     "mode": "auto", "assembly_mode": assembly_mode,
                     "enqueued": "ok" if enqueued else "retriggerable"})

    # ── AUTO path (V1 A1): diverge→converge, NON-stream, returns the winner. The
    # co-write STREAM path is below. The rerank judge prefers the work's DISTINCT
    # critic model (anti-self-reinforcement §4); falls back to the drafter.
    if body.mode == "auto":
        if not created:  # idempotent replay → return the existing job, don't re-run
            r = job.result or {}
            return JSONResponse({"job_id": str(job.id), "mode": "auto", "replay": True,
                                 "text": r.get("text", ""), "status": job.status,
                                 "winner_index": r.get("winner_index"),
                                 "k": r.get("k"), "candidates": r.get("candidates", []),
                                 "assembly_mode": assembly_mode})
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
                # A3 — adaptive K from the scene's structural weight (beat_role +
                # tension the planner emitted). Hand-authored nodes (no beat_role/
                # tension) fall back to compose_diverge_k. NOTE: there is no
                # K-multiplied budget reservation in this path (the only pre-check
                # is the K-independent prompt-size 413 above; per-call spend is
                # gateway-side), so design HIGH#1's "compute K before the budget
                # reservation" is moot — verified against engine.py: just derive
                # and pass it.
                guide=body.guide,
                k=adaptive_k(node.beat_role, node.tension,
                             k_ceiling=settings.compose_diverge_k,
                             high_threshold=settings.plan_high_tension_threshold),
                prompt_est=prompt_estimate,
                max_tokens=body.max_output_tokens, temperature=settings.compose_diverge_temperature,
                reasoning_effort=None if reasoning.passthrough else reasoning.effort,
            )
        except Exception as exc:  # diverge produced nothing / transport — fail the job, 502
            logger.warning("auto select failed: %s", exc)
            await jobs.update_status(job.id, "failed")
            raise HTTPException(status_code=502, detail={"code": "GENERATE_FAILED"})
        w = sel.winner
        # ── A2-S3b: canon check→revise on the converged winner (D1). The SCORE
        # symbolic guard + the distinct LLM-judge confirm a `gone` cast member
        # portrayed as present; reflect repairs ≤N then escalates (hard-gate
        # signal on the job). Degrades to advisory on any knowledge/judge outage
        # (CC4/F1) — never blocks the generate.
        final_text = w.text
        # Default status=degraded so the except path below (canon reflect raised)
        # reads as "could not verify", not a false-green.
        canon = {"violations": [], "resolved": True, "iterations": 0, "status": "degraded"}
        revise_out_tokens = 0
        revise_finish: str | None = None
        try:
            cast_glossary_ids = [str(e) for e in (node.present_entity_ids or [])]
            final_text, reflect, revise_out_tokens = await run_canon_reflect(
                knowledge=knowledge, llm=llm,
                user_id=user_id, project_id=project_id,
                cast_glossary_ids=cast_glossary_ids,
                scene_sort_order=pc.scene_sort_order,
                draft=w.text, packed_prompt=pc.prompt, profile=pc.profile,
                drafter_source=body.model_source, drafter_ref=str(body.model_ref),
                judge_source=str(c_src) if distinct else None,
                judge_ref=str(c_ref) if distinct else None,
                prompt_estimate=prompt_estimate, max_output_tokens=body.max_output_tokens,
                # /review-impl #2 — clamp the per-work setting to a sane ceiling so
                # a typo'd/abusive reflect_max_iters can't fan out N revise LLM
                # calls per generate (the §10.1 backtrack budget bound).
                max_iters=max(0, min(3, int(sdict.get("reflect_max_iters", 1) or 1))),
                reasoning_effort=None if reasoning.passthrough else reasoning.effort,
            )
            canon = {
                "violations": [v.model_dump() for v in reflect.violations],
                "resolved": reflect.resolved, "iterations": reflect.iterations,
                "status": reflect.status,
            }
            revise_finish = reflect.revise_finish_reason
        except Exception:  # canon reflect must NEVER fail the generate (F1).
            logger.warning("A2-S3b canon reflect failed (advisory) — keeping winner", exc_info=True)
        # FD-1 (narrative_thread S2): best-effort promise-ledger producer — opens
        # new promises this scene plants + pays resolved ones (S3 re-injects them).
        await _maybe_detect_narrative_threads(
            work, llm=llm, repo=narrative_threads, user_id=user_id, project_id=project_id,
            scene_text=final_text, opened_at_node=node.id,
            model_source=body.model_source, model_ref=body.model_ref, source_language=_src_lang)
        total_out = w.metering.output_tokens + revise_out_tokens
        # D-COMP-TRUNCATION-SURFACING: authoritative truncation flag from the
        # drafter's stop reason (the winner draft is the cap-prone generation). A
        # canon-revise repair can ALSO truncate, so OR in its stop reason (cy16) —
        # else a cut-off repair is a silent green.
        truncated = (w.metering.finish_reason == "length") or (revise_finish == "length")
        await jobs.update_status(
            job.id, "completed",
            result={"text": final_text, "input_tokens": w.metering.input_tokens,
                    "output_tokens": total_out, "measured": w.metering.measured,
                    "k": len(sel.candidates), "winner_index": sel.winner_index,
                    "rerank_reason": sel.rerank_reason, "rerank_measured": sel.rerank_measured,
                    "candidates": [c.text for c in sel.candidates],
                    "truncated": truncated, "finish_reason": w.metering.finish_reason,
                    "canon": canon},
        )
        return JSONResponse({
            "job_id": str(job.id), "mode": "auto", "status": "completed", "text": final_text,
            "truncated": truncated, "finish_reason": w.metering.finish_reason,
            "winner_index": sel.winner_index, "k": len(sel.candidates),
            # The K candidate texts so the FE can show ALL options as cards (the
            # controlled-auto human gate, slice 3). They're already computed +
            # persisted in the job result; returning them here saves a GET /jobs.
            "candidates": [c.text for c in sel.candidates],
            "rerank_reason": sel.rerank_reason, "rerank_measured": sel.rerank_measured,
            "grounding_available": pc.grounding_available,
            # A2-S3b — the canon gate: `resolved=false` + violations means a
            # confirmed contradiction survived revision (D4 hard-gate signal for
            # the publish/commit path + the author).
            "canon": canon,
            "reasoning_source": reasoning.source, "reasoning_effort": reasoning.effort,
            "assembly_mode": assembly_mode,
            # FD-1 S4b — how many open promises S3 re-injected into this draft's
            # prompt (advisory; 0 when narrative_thread is off). Deterministic S3
            # fired-signal for the live-smoke.
            "reinjected_promise_count": pc.reinjected_promise_count,
        })

    async def event_gen():
        yield _sse({"type": "job", "job_id": str(job.id), "created": created,
                    "grounding_available": pc.grounding_available,
                    "reasoning_source": reasoning.source,
                    "reasoning_effort": reasoning.effort,
                    "assembly_mode": assembly_mode})
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
        # D-ENGINE-ERRORED-JOB-MARKED-COMPLETED: an LLMError with NO content (a
        # resolve failure metered at 0) still yields a terminal usage frame — but it
        # is a FAILURE, not a completed zero-token job (a retry/idempotency layer must
        # not treat it as done). Partial-content-then-error stays completed+truncated.
        if final is not None and not (final.get("error") and not final["text"]):
            m = final["metering"]
            # D-COMP-TRUNCATION-SURFACING: "length" ⇒ the model hit its max_tokens
            # cap. DISTINCT from `capped` (composition's own hard-cap abort, which
            # breaks BEFORE the DoneEvent so finish_reason stays None). Both mean the
            # output was cut — a consumer wanting "incomplete?" should treat
            # (capped OR truncated) as the signal; both are surfaced below.
            # A mid-stream error AFTER partial content also lands here (we keep the
            # partial work), but finish_reason is None on an error interruption — so OR
            # in the error to mark it truncated + surface the reason, else the abruptly
            # cut fragment renders as a clean, finished draft (review MED).
            stream_error = final.get("error")
            truncated = m.finish_reason == "length" or bool(stream_error)
            result = {"text": final["text"], "input_tokens": m.input_tokens,
                      "output_tokens": m.output_tokens, "measured": m.measured,
                      "capped": final.get("capped", False),
                      "truncated": truncated, "finish_reason": m.finish_reason}
            if stream_error:
                result["error"] = stream_error
            await jobs.update_status(job.id, "completed", result=result)
            yield _sse({"type": "done", "job_id": str(job.id), "status": "completed",
                        "output_tokens": m.output_tokens, "measured": m.measured,
                        "capped": final.get("capped", False),
                        "truncated": truncated, "finish_reason": m.finish_reason,
                        **({"error": stream_error} if stream_error else {})})
        else:
            err = final.get("error") if final is not None else None
            await jobs.update_status(
                job.id, "failed", result={"error": err} if err else None)
            yield _sse({"type": "done", "job_id": str(job.id), "status": "failed",
                        **({"error": err} if err else {})})

    return StreamingResponse(event_gen(), media_type="text/event-stream")


@router.post("/works/{project_id}/selection-edit")
async def selection_edit(
    project_id: UUID,
    body: SelectionEditBody,
    user_id: UUID = Depends(get_current_user),
    bearer: str = Depends(get_bearer_token),
    works: WorksRepo = Depends(get_works_repo),
    outline: OutlineRepo = Depends(get_outline_repo),
    structures: StructureRepo | None = Depends(get_structure_repo),
    motif_apps: MotifApplicationRepo | None = Depends(get_motif_application_repo_opt),  # X-7 motif lens
    motifs: MotifRepo | None = Depends(get_motif_repo_opt),  # X-7 motif lens
    scene_links: SceneLinksRepo = Depends(get_scene_links_repo),
    canon: CanonRulesRepo = Depends(get_canon_rules_repo),
    jobs: GenerationJobsRepo = Depends(get_generation_jobs_repo),
    book: BookClient = Depends(get_book_client_dep),
    glossary: GlossaryClient = Depends(get_glossary_client_dep),
    knowledge: KnowledgeClient = Depends(get_knowledge_client_dep),
    llm: LLMClient = Depends(get_llm_client_dep),
    narrative_threads: NarrativeThreadRepo = Depends(get_narrative_thread_repo),
    grounding_pins: GroundingPinsRepo = Depends(get_grounding_pins_repo),
    style_profiles: StyleProfileRepo = Depends(get_style_profile_repo),
    voice_profiles: VoiceProfileRepo = Depends(get_voice_profile_repo),
    references: ReferencesRepo = Depends(get_references_repo),
    embedder: EmbeddingClient = Depends(get_embedding_client_dep),
    derivatives: DerivativesRepo = Depends(get_derivatives_repo),
    grant: GrantClient = Depends(get_grant_client_dep),
) -> Any:
    """T3.2 — selection-scoped edit (rewrite/expand/describe) over the author's
    highlighted prose. Decoupled from outline_node_id (AH-1): a selection may sit
    in a chapter with no scene node, so this never requires one. Grounds on the
    BookProfile voice ALWAYS; on the scene pack when `scene_context` resolves to a
    valid node (degrades to voice-only on any pack failure — never 404s on the
    grounding source). Streams the replacement (same SSE as cowrite); the FE
    replaces the Tiptap range on Accept (no server persistence until then)."""
    work = await _gate_work(works, grant, user_id, project_id)
    profile = from_settings(work.settings)
    _src_lang = profile.source_language
    # T3.5 — the EFFECTIVE profile the prompt is built from. Upgraded to the packer's
    # STYLED profile (density/pace + present-character voices) when a scene_context is
    # supplied and the pack succeeds; stays the settings profile (neutral style) for a
    # context-less edit or a degraded pack.
    eff_profile = profile

    # Model-context-aware budget scaling — resolved once per request regardless of
    # whether scene_context grounding runs, since prompt_ceiling below always needs it.
    _context_length = await llm.resolve_context_length(body.model_source, str(body.model_ref))
    _pack_budget = scale_by_window(settings.pack_token_budget, _context_length)
    _compress_chars = scale_by_window(settings.compress_max_input_chars, _context_length)

    grounding = ""
    node = None
    if body.scene_context is not None:
        cand = await outline.get_node(body.scene_context)
        if cand is not None and str(cand.project_id) == str(project_id):
            node = cand

            async def _compress_fn(older: list[str], timeline_texts: list[str], plan: str) -> str:
                return await compress(
                    llm, user_id=str(user_id), model_source=body.model_source,
                    model_ref=str(body.model_ref), prose=older, timeline=timeline_texts,
                    plan=plan, source_language=_src_lang,
                    max_input_chars=_compress_chars)

            try:
                # C25 — dị bản two-project merge inputs (best-effort, like the pack).
                deriv = await build_derivative_context(
                    work, works_repo=works, derivatives_repo=derivatives)
                pc = await pack(
                    PackRequest(user_id=user_id, project_id=project_id, book_id=work.book_id,
                                node=node.model_dump(mode="python"), bearer=bearer, guide=body.guide,
                                settings=work.settings,
                                source_project_id=deriv.source_project_id,
                                branch_point=deriv.branch_point, overrides=deriv.overrides,
                        pov_anchor=deriv.pov_anchor),
                    book=book, glossary=glossary, knowledge=knowledge, canon_repo=canon,
                    outline_repo=outline, scene_links_repo=scene_links,
                    structure_repo=structures,  # 23 BA12 — the arc lens
                    motif_application_repo=motif_apps,  # X-7 — the motif lens
                    motif_repo=motifs,  # X-7 — ditto; BOTH or dormant
                    budget_tokens=_pack_budget, jobs_repo=jobs,
                    compress_fn=_compress_fn, narrative_threads_repo=narrative_threads,
                    grounding_pins_repo=grounding_pins,  # T3.4 — honor per-scene pins
                    style_profile_repo=style_profiles,  # T3.5 — density/pace
                    voice_profile_repo=voice_profiles,  # T3.5 — present-character voices
                    references_repo=references,  # T3.6 — author reference shelf
                    embedding_client=embedder)  # T3.6 — provider-registry embed
                grounding = pc.prompt
                eff_profile = pc.profile  # T3.5 — selection edit honors style & voice
            except Exception:  # noqa: BLE001 — grounding is best-effort: a pack
                # failure of ANY kind degrades to voice-only, never 500s the edit
                # (the docstring's "never fails on the grounding source").
                logger.warning("selection-edit grounding pack failed — voice-only", exc_info=True)
                grounding = ""

    # build_selection_messages RAISES on an unregistered op; the Literal field above
    # already 422s a bad value, so this is the defense-in-depth backstop (LOOM-39).
    messages = build_selection_messages(
        body.selection, eff_profile, body.operation, body.guide, grounding)
    prompt_estimate = estimate_prompt_tokens(messages, B.default_counter())
    prompt_ceiling = _pack_budget * 2
    if prompt_estimate > prompt_ceiling:
        raise HTTPException(status_code=413, detail={
            "code": "PROMPT_TOO_LARGE", "estimate": prompt_estimate, "ceiling": prompt_ceiling})

    signals = ReasoningSignals(
        operation=body.operation, n_canon_rules=0, n_present_entities=0,
        has_reveal_gate=False, tension=None, guide=body.guide)
    control = infer_reasoning_control(body.model_kind, body.model_name)
    reasoning = resolve_reasoning(
        user_pref=body.reasoning, model_control=control, auto_effort=score_effort(signals),
        auto_source=str(work.settings.get("reasoning_engine", "rule_based")))

    # /review-impl HIGH: outline_node_id is DELIBERATELY None even when a scene
    # grounded the edit. The scene is GROUNDING only, not a draft association — the
    # node-join consumers (chapter_scene_drafts/prior_scene_drafts → stitch + S1
    # state-reinjection; outline.chapter_scene_gate → publish-gate canon count) take
    # the LATEST completed job per scene node, so a node-tagged selection edit (a
    # rewritten fragment, no canon block) would masquerade as the scene's draft and
    # corrupt the stitch / reinjection / gate. The scene id stays in `input` for
    # traceability only.
    if settings.composition_worker_enabled:
        # M4 — batch/poll variant: the endpoint already built the message list
        # (selection + voice/scene grounding, bearer-resolved); persist it + enqueue
        # → 202. The worker drains stream_draft to the final text (no streaming) and
        # stores the result; the FE polls GET /jobs/{id} then replaces the range on
        # Accept. outline_node_id stays None (same HIGH rationale above).
        job, _created = await jobs.create(
            project_id, created_by=user_id, operation=body.operation, outline_node_id=None,
            mode="cowrite", status="pending",
            input={"model_source": body.model_source, "model_ref": str(body.model_ref),
                   "operation": body.operation, "worker_op": "selection_edit",
                   "selection_edit": True,
                   "scene_context": str(node.id) if node is not None else None,
                   "messages": messages, "prompt_estimate": prompt_estimate,
                   "max_out": body.max_output_tokens,
                   "reasoning": reasoning.source, "reasoning_effort": reasoning.effort,
                   "reasoning_passthrough": reasoning.passthrough,
                   "grounding_available": bool(grounding)})
        enqueued = await enqueue_job(
            settings.redis_url, job_id=str(job.id),
            user_id=str(user_id), project_id=str(project_id))
        return JSONResponse(
            status_code=http_status.HTTP_202_ACCEPTED,
            content={"job_id": str(job.id), "status": "pending", "selection_edit": True,
                     "enqueued": "ok" if enqueued else "retriggerable"})

    job, created = await jobs.create(
        project_id, created_by=user_id, operation=body.operation,
        outline_node_id=None,
        mode="cowrite", status="running",
        input={"model_source": body.model_source, "model_ref": str(body.model_ref),
               "operation": body.operation, "selection_edit": True,
               "scene_context": str(node.id) if node is not None else None,
               "prompt_estimate": prompt_estimate,
               "reasoning": reasoning.source, "reasoning_effort": reasoning.effort})

    async def event_gen():
        yield _sse({"type": "job", "job_id": str(job.id), "created": created,
                    "grounding_available": bool(grounding),
                    "reasoning_source": reasoning.source,
                    "reasoning_effort": reasoning.effort})
        final: dict[str, Any] | None = None
        async for ev in stream_draft(
            llm.sdk, user_id=str(user_id), model_source=body.model_source,
            model_ref=str(body.model_ref), messages=messages,
            prompt_token_estimate=prompt_estimate, max_output_tokens=body.max_output_tokens,
            hard_cap_output=body.max_output_tokens * 2,
            reasoning_effort=None if reasoning.passthrough else reasoning.effort,
        ):
            if ev["type"] == "usage":
                final = ev
            else:
                yield _sse(ev)
        # D-ENGINE-ERRORED-JOB-MARKED-COMPLETED (see draft-scene handler): an errored
        # terminal frame with no content is a FAILURE, not a completed zero-token job.
        if final is not None and not (final.get("error") and not final["text"]):
            m = final["metering"]
            # Partial-content-then-error keeps the work but must be flagged truncated + carry the
            # reason (else the cut edit looks clean — review MED).
            stream_error = final.get("error")
            truncated = m.finish_reason == "length" or bool(stream_error)
            result = {"text": final["text"], "input_tokens": m.input_tokens,
                      "output_tokens": m.output_tokens, "measured": m.measured,
                      "truncated": truncated, "finish_reason": m.finish_reason,
                      "selection_edit": True}
            if stream_error:
                result["error"] = stream_error
            await jobs.update_status(job.id, "completed", result=result)
            yield _sse({"type": "done", "job_id": str(job.id), "status": "completed",
                        "output_tokens": m.output_tokens, "measured": m.measured,
                        "truncated": truncated, "finish_reason": m.finish_reason,
                        **({"error": stream_error} if stream_error else {})})
        else:
            err = final.get("error") if final is not None else None
            await jobs.update_status(
                job.id, "failed", result={"error": err} if err else None)
            yield _sse({"type": "done", "job_id": str(job.id), "status": "failed",
                        **({"error": err} if err else {})})

    return StreamingResponse(event_gen(), media_type="text/event-stream")


@router.post("/works/{project_id}/chapters/{chapter_id}/generate")
async def generate_chapter(
    project_id: UUID,
    chapter_id: UUID,
    body: GenerateChapterBody,
    user_id: UUID = Depends(get_current_user),
    bearer: str = Depends(get_bearer_token),
    works: WorksRepo = Depends(get_works_repo),
    outline: OutlineRepo = Depends(get_outline_repo),
    structures: StructureRepo | None = Depends(get_structure_repo),
    motif_apps: MotifApplicationRepo | None = Depends(get_motif_application_repo_opt),  # X-7 motif lens
    motifs: MotifRepo | None = Depends(get_motif_repo_opt),  # X-7 motif lens
    scene_links: SceneLinksRepo = Depends(get_scene_links_repo),
    canon: CanonRulesRepo = Depends(get_canon_rules_repo),
    jobs: GenerationJobsRepo = Depends(get_generation_jobs_repo),
    book: BookClient = Depends(get_book_client_dep),
    glossary: GlossaryClient = Depends(get_glossary_client_dep),
    knowledge: KnowledgeClient = Depends(get_knowledge_client_dep),
    llm: LLMClient = Depends(get_llm_client_dep),
    narrative_threads: NarrativeThreadRepo = Depends(get_narrative_thread_repo),
    grounding_pins: GroundingPinsRepo = Depends(get_grounding_pins_repo),
    style_profiles: StyleProfileRepo = Depends(get_style_profile_repo),
    voice_profiles: VoiceProfileRepo = Depends(get_voice_profile_repo),
    references: ReferencesRepo = Depends(get_references_repo),
    embedder: EmbeddingClient = Depends(get_embedding_client_dep),
    derivatives: DerivativesRepo = Depends(get_derivatives_repo),
    grant: GrantClient = Depends(get_grant_client_dep),
) -> Any:
    """B2 chapter single-pass (assembly_mode='chapter'): generate a WHOLE chapter
    in ONE drafter pass from its A3 decompose plan (scene nodes), grounded at the
    chapter reading position, then run a chapter-level canon check+reflect over
    the union cast. Non-stream JSON (like the auto path). The synthetic pack node
    is in-memory only — never persisted (MED-1)."""
    work = await _gate_work(works, grant, user_id, project_id)

    scenes = await outline.scenes_for_chapter(project_id, chapter_id)
    if not scenes:
        raise HTTPException(status_code=400, detail={
            "code": "NO_CHAPTER_PLAN", "detail": "chapter has no scene plan; decompose it first"})

    # Chapter-level intent/title from the kind='chapter' outline node (the scenes'
    # shared parent). Defensive: empty if absent / not a chapter (hand-authored).
    chapter_intent, chapter_title = "", ""
    parent_id = scenes[0].parent_id
    if parent_id is not None:
        parent = await outline.get_node(parent_id)
        if parent is not None and parent.kind == "chapter":
            chapter_intent, chapter_title = parent.goal, parent.title

    # Chapter reading position (book sort_order) → story_order (strictly-prior
    # context) + the canon position. pack() re-resolves it from chapter_id.
    chapter_sort = (await book.get_chapter_sort_orders([chapter_id])).get(str(chapter_id))
    pack_node = build_chapter_pack_node(
        chapter_id=chapter_id, chapter_sort=chapter_sort,
        chapter_intent=chapter_intent, chapter_title=chapter_title, scenes=scenes)

    _src_lang = from_settings(work.settings).source_language

    # Model-context-aware budget scaling — a flat pack/compress budget tuned for a
    # mid-size window must not cap a genuinely bigger model at the same number.
    _context_length = await llm.resolve_context_length(body.model_source, str(body.model_ref))
    _pack_budget = scale_by_window(settings.pack_token_budget, _context_length)
    _compress_chars = scale_by_window(settings.compress_max_input_chars, _context_length)

    async def _compress_fn(older: list[str], timeline_texts: list[str], plan: str) -> str:
        return await compress(
            llm, user_id=str(user_id), model_source=body.model_source,
            model_ref=str(body.model_ref), prose=older, timeline=timeline_texts,
            plan=plan, source_language=_src_lang,
            max_input_chars=_compress_chars)

    # C25 — dị bản two-project merge inputs (base project + branch + fresh
    # overrides); empty for a non-derivative Work.
    deriv = await build_derivative_context(
        work, works_repo=works, derivatives_repo=derivatives)
    try:
        pc = await pack(
            PackRequest(user_id=user_id, project_id=project_id, book_id=work.book_id,
                        node=pack_node, bearer=bearer, guide=body.guide,
                        settings=work.settings, chapter_sort_hint=chapter_sort,
                        source_project_id=deriv.source_project_id,
                        branch_point=deriv.branch_point, overrides=deriv.overrides,
                        pov_anchor=deriv.pov_anchor),
            book=book, glossary=glossary, knowledge=knowledge, canon_repo=canon,
            outline_repo=outline, scene_links_repo=scene_links,
            structure_repo=structures,  # 23 BA12 — the arc lens
            motif_application_repo=motif_apps,  # X-7 — the motif lens (scene beats)
            motif_repo=motifs,  # X-7 — ditto; BOTH must ride or the lens is dormant
            budget_tokens=_pack_budget, jobs_repo=jobs,
            compress_fn=_compress_fn,
            narrative_threads_repo=narrative_threads,  # FD-1 S3 open-promise re-injection
            grounding_pins_repo=grounding_pins,  # T3.4 — generation honors per-scene pins
            style_profile_repo=style_profiles,  # T3.5 — density/pace
            voice_profile_repo=voice_profiles,  # T3.5 — present-character voices
            references_repo=references,  # T3.6 — author reference shelf
            embedding_client=embedder,  # T3.6 — provider-registry embed
            need=GrantLevel.EDIT)  # E0-4c: prose-gen is a write/spend → EDIT tier
    except OwnershipError:
        raise HTTPException(status_code=404, detail="book not found")
    except InsufficientGrant:
        raise HTTPException(status_code=403, detail="insufficient access")
    except BookClientError:
        raise HTTPException(status_code=502, detail={"code": "BOOK_SERVICE_UNAVAILABLE"})

    messages = build_messages(pc.prompt, pc.profile, body.operation, body.guide)
    prompt_estimate = estimate_prompt_tokens(messages, B.default_counter())
    prompt_ceiling = _pack_budget * 2
    if prompt_estimate > prompt_ceiling:
        raise HTTPException(status_code=413, detail={
            "code": "PROMPT_TOO_LARGE", "estimate": prompt_estimate, "ceiling": prompt_ceiling})

    active_rules = await canon.list_active(project_id)
    signals = ReasoningSignals(
        operation=body.operation, n_canon_rules=len(active_rules),
        n_present_entities=len(pack_node["present_entity_ids"]),
        has_reveal_gate=any(r.scope == "reveal_gate" for r in active_rules),
        tension=None, guide=body.guide)
    control = infer_reasoning_control(body.model_kind, body.model_name)
    reasoning = resolve_reasoning(
        user_pref=body.reasoning, model_control=control, auto_effort=score_effort(signals),
        auto_source=str(work.settings.get("reasoning_engine", "rule_based")))

    # Size the output budget from the plan (scene count) so a multi-scene chapter
    # gets room instead of a flat cap that silently truncates long-form; clamp to
    # the ceiling. An explicit body override still wins.
    max_out = body.max_output_tokens or min(
        len(scenes) * settings.chapter_gen_per_scene_tokens, settings.chapter_gen_max_tokens)

    if settings.composition_worker_enabled:
        # M4 (Option A) — resolve the bearer context (pack, chapter_sort, critic)
        # HERE, persist it in job.input behind the chapter in-flight guard, enqueue
        # → 202. The worker runs diverge(k=1) + canon-reflect + stores the result;
        # persistence to the book draft is the separate bearer accept-step
        # (POST /jobs/{id}/persist). Same guard + idempotency as the inline path.
        sdict = work.settings or {}
        c_src, c_ref = sdict.get("critic_model_source"), sdict.get("critic_model_ref")
        distinct = bool(c_ref and c_src and str(c_ref) != str(body.model_ref))
        job_input = {
            "model_source": body.model_source, "model_ref": str(body.model_ref),
            "operation": body.operation, "worker_op": "chapter_generate",
            "assembly_mode": "chapter", "chapter_id": str(chapter_id),
            "packed_prompt": pc.prompt, "scene_sort_order": pc.scene_sort_order,
            "present_entity_ids": [str(e) for e in pack_node["present_entity_ids"]],
            "prompt_estimate": prompt_estimate, "max_out": max_out, "guide": body.guide,
            "reasoning": reasoning.source, "reasoning_effort": reasoning.effort,
            "reasoning_passthrough": reasoning.passthrough,
            "grounding_available": pc.grounding_available,
            "reinjected_promise_count": pc.reinjected_promise_count,
            "reflect_max_iters": max(0, min(3, int(sdict.get("reflect_max_iters", 1) or 1))),
            "critic_source": str(c_src) if distinct else None,
            "critic_ref": str(c_ref) if distinct else None,
        }
        try:
            job, created = await jobs.create_chapter_job_guarded(
                project_id, chapter_id, created_by=user_id, operation=body.operation,
                mode="auto", status="pending", input=job_input,
                idempotency_key=body.idempotency_key,
                stale_secs=settings.chapter_inflight_stale_secs,
                model_name=await resolve_model_name(
                    body.model_source, str(body.model_ref) if body.model_ref else None))
        except ChapterJobInFlightError as exc:
            raise HTTPException(status_code=409, detail={
                "code": "CHAPTER_JOB_IN_FLIGHT", "active_job_id": exc.active_job_id})
        if not created:  # idempotent replay
            r = job.result or {}
            return JSONResponse({"job_id": str(job.id), "mode": "auto", "replay": True,
                                 "text": r.get("text", ""), "status": job.status,
                                 "canon": r.get("canon"), "assembly_mode": "chapter"})
        enqueued = await enqueue_job(
            settings.redis_url, job_id=str(job.id),
            user_id=str(user_id), project_id=str(project_id))
        return JSONResponse(
            status_code=http_status.HTTP_202_ACCEPTED,
            content={"job_id": str(job.id), "status": "pending", "mode": "auto",
                     "assembly_mode": "chapter",
                     "enqueued": "ok" if enqueued else "retriggerable"})

    # Idempotency keyed on the caller's key (design LOW-1: key on chapter_id +
    # assembly_mode in the value the caller builds). Chapter jobs aren't
    # node-scoped, so the per-scene S2 cancel doesn't apply; instead an in-flight
    # guard (Cycle-2) rejects a concurrent chapter-level job for the same chapter
    # with 409 — generate and stitch both write this chapter's draft, so two at
    # once double-spend the LLM and race the persist. Same-key replay is honored.
    try:
        job, created = await jobs.create_chapter_job_guarded(
            project_id, chapter_id, created_by=user_id, operation=body.operation,
            mode="auto", status="running",
            input={"model_source": body.model_source, "model_ref": str(body.model_ref),
                   "operation": body.operation, "prompt_estimate": prompt_estimate,
                   "assembly_mode": "chapter", "chapter_id": str(chapter_id),
                   "reasoning": reasoning.source, "reasoning_effort": reasoning.effort},
            idempotency_key=body.idempotency_key,
            stale_secs=settings.chapter_inflight_stale_secs,
            model_name=await resolve_model_name(
                body.model_source, str(body.model_ref) if body.model_ref else None))
    except ChapterJobInFlightError as exc:
        raise HTTPException(status_code=409, detail={
            "code": "CHAPTER_JOB_IN_FLIGHT", "active_job_id": exc.active_job_id})
    if not created:  # idempotent replay → return the existing job, don't re-run
        r = job.result or {}
        return JSONResponse({"job_id": str(job.id), "mode": "auto", "replay": True,
                             "text": r.get("text", ""), "status": job.status,
                             "canon": r.get("canon"), "assembly_mode": "chapter"})

    sdict = work.settings or {}
    c_src, c_ref = sdict.get("critic_model_source"), sdict.get("critic_model_ref")
    distinct = bool(c_ref and c_src and str(c_ref) != str(body.model_ref))
    try:
        cands = await diverge(
            llm, user_id=str(user_id), model_source=body.model_source,
            model_ref=str(body.model_ref), packed_prompt=pc.prompt, profile=pc.profile,
            operation=body.operation, guide=body.guide, k=1, prompt_est=prompt_estimate,
            max_tokens=max_out, temperature=settings.compose_diverge_temperature,
            reasoning_effort=None if reasoning.passthrough else reasoning.effort)
    except Exception as exc:  # no candidate / transport — fail the job, 502
        logger.warning("chapter draft failed: %s", exc)
        await jobs.update_status(job.id, "failed")
        raise HTTPException(status_code=502, detail={"code": "GENERATE_FAILED"})
    winner = cands[0]

    # Chapter-level A2 canon check→reflect over the union cast at the chapter
    # position (the per-scene guard runs at the same at_order for every scene, so
    # this is equivalent-granularity — plan CANON-SAFETY). Degrades to advisory on
    # any knowledge/judge outage, never blocks (F1).
    final_text = winner.text
    canon_v: dict[str, Any] = {"violations": [], "resolved": True, "iterations": 0,
                               "status": "degraded"}
    revise_out_tokens = 0
    revise_finish: str | None = None
    try:
        final_text, reflect, revise_out_tokens = await run_canon_reflect(
            knowledge=knowledge, llm=llm, user_id=user_id, project_id=project_id,
            cast_glossary_ids=[str(e) for e in pack_node["present_entity_ids"]],
            scene_sort_order=pc.scene_sort_order, draft=winner.text,
            packed_prompt=pc.prompt, profile=pc.profile,
            drafter_source=body.model_source, drafter_ref=str(body.model_ref),
            judge_source=str(c_src) if distinct else None,
            judge_ref=str(c_ref) if distinct else None,
            prompt_estimate=prompt_estimate, max_output_tokens=max_out,
            max_iters=max(0, min(3, int(sdict.get("reflect_max_iters", 1) or 1))),
            reasoning_effort=None if reasoning.passthrough else reasoning.effort)
        canon_v = {"violations": [v.model_dump() for v in reflect.violations],
                   "resolved": reflect.resolved, "iterations": reflect.iterations,
                   "status": reflect.status}
        revise_finish = reflect.revise_finish_reason
    except Exception:  # canon reflect must NEVER fail the generate (F1).
        logger.warning("chapter canon reflect failed (advisory) — keeping draft", exc_info=True)

    # FD-1 (narrative_thread S2): best-effort promise-ledger producer over the
    # whole-chapter draft. opened_at_node=None — the chapter pass uses a synthetic
    # in-memory node (never persisted), so the thread is project-scoped (FK nullable).
    await _maybe_detect_narrative_threads(
        work, llm=llm, repo=narrative_threads, user_id=user_id, project_id=project_id,
        scene_text=final_text, opened_at_node=None,
        model_source=body.model_source, model_ref=body.model_ref,
        source_language=from_settings(work.settings).source_language)

    # FD-1 S4a — advisory unpaid-promise DEBT count (§7) at chapter end (the
    # detector just ran). None when off; best-effort. Uses count_open (a true
    # COUNT, not a capped list — review-impl MED#1).
    open_promise_count = await _open_promise_count(
        work, repo=narrative_threads, project_id=project_id)

    # MED-2 — best-effort persist of the assembled chapter to the book draft.
    persisted, draft_version, persist_error = False, None, None
    if body.persist:
        persisted, draft_version, persist_error = await _persist_chapter_draft(
            book, work.book_id, chapter_id, bearer, final_text, "AI chapter draft (chapter mode)",
            scenes=_scene_marker_rows(scenes))

    # NOTE (D-COMP-TRUNCATION-SURFACING): a reliable "was the output cut at the
    # cap?" flag needs the gateway's finish_reason — a char_estimate heuristic is
    # too biased (over-counts EN → false positives ~75% budget, under-counts CJK →
    # misses) to ship. The plan-sized `max_output_tokens` (returned below) is the
    # deterministic anti-truncation lever; accurate surfacing is deferred.
    total_out = winner.metering.output_tokens + revise_out_tokens
    # D-COMP-TRUNCATION-SURFACING: "length" ⇒ the single-pass chapter draft hit the
    # cap (the deterministic plan-sized max_out is the prevention; this is the signal).
    # A canon-revise repair can also truncate → OR in its stop reason (cy16).
    truncated = (winner.metering.finish_reason == "length") or (revise_finish == "length")
    await jobs.update_status(
        job.id, "completed",
        result={"text": final_text, "input_tokens": winner.metering.input_tokens,
                "output_tokens": total_out, "measured": winner.metering.measured,
                "truncated": truncated, "finish_reason": winner.metering.finish_reason,
                "canon": canon_v, "assembly_mode": "chapter", "chapter_id": str(chapter_id),
                "persisted": persisted, "draft_version": draft_version,
                "open_promise_count": open_promise_count})
    return JSONResponse({
        "job_id": str(job.id), "mode": "auto", "status": "completed", "text": final_text,
        "truncated": truncated, "finish_reason": winner.metering.finish_reason,
        "canon": canon_v, "grounding_available": pc.grounding_available,
        "reasoning_source": reasoning.source, "reasoning_effort": reasoning.effort,
        "assembly_mode": "chapter", "persisted": persisted, "draft_version": draft_version,
        "persist_error": persist_error, "max_output_tokens": max_out,
        "open_promise_count": open_promise_count,  # FD-1 S4a advisory debt flag
        "reinjected_promise_count": pc.reinjected_promise_count})  # FD-1 S4b S3 fired-signal


@router.post("/works/{project_id}/chapters/{chapter_id}/stitch")
async def stitch_chapter_endpoint(
    project_id: UUID,
    chapter_id: UUID,
    body: StitchBody,
    user_id: UUID = Depends(get_current_user),
    bearer: str = Depends(get_bearer_token),
    works: WorksRepo = Depends(get_works_repo),
    outline: OutlineRepo = Depends(get_outline_repo),
    structures: StructureRepo | None = Depends(get_structure_repo),
    canon: CanonRulesRepo = Depends(get_canon_rules_repo),
    jobs: GenerationJobsRepo = Depends(get_generation_jobs_repo),
    book: BookClient = Depends(get_book_client_dep),
    knowledge: KnowledgeClient = Depends(get_knowledge_client_dep),
    llm: LLMClient = Depends(get_llm_client_dep),
    grant: GrantClient = Depends(get_grant_client_dep),
) -> Any:
    """B3 per_scene+stitch: merge a chapter's done scene drafts into one seamless
    chapter (ONE LLM pass; degrade→raw concat), re-run the chapter-level canon
    guard, and best-effort persist to the book draft (MED-2). Gated on all scenes
    `done` (the publishable artifact). Non-stream JSON."""
    work = await _gate_work(works, grant, user_id, project_id)

    # Trigger guard: the stitch is the publishable artifact → require all scenes
    # done (mirrors the publish-gate's done==total). 409 otherwise.
    gate = await outline.chapter_scene_gate(project_id, chapter_id)
    if not (gate["scenes_total"] > 0 and gate["scenes_done"] == gate["scenes_total"]):
        raise HTTPException(status_code=409, detail={"code": "SCENES_NOT_DONE", "gate": gate})

    draft_rows = await jobs.chapter_scene_drafts(project_id, chapter_id)
    if not draft_rows:
        raise HTTPException(status_code=400, detail={
            "code": "NO_SCENE_DRAFTS", "detail": "no completed scene drafts to stitch"})
    # F4 (D-SCENEMARKER-EMIT) — each draft opens with its `### <scene title>` line;
    # the persist step (prose_doc) lifts these into sceneId-anchored heading nodes.
    drafts = prepend_scene_headings(draft_rows)

    scenes = await outline.scenes_for_chapter(project_id, chapter_id)
    chapter_intent = ""
    if scenes and scenes[0].parent_id is not None:
        parent = await outline.get_node(scenes[0].parent_id)
        if parent is not None and parent.kind == "chapter":
            chapter_intent = parent.goal
    profile = from_settings(work.settings)

    active_rules = await canon.list_active(project_id)
    signals = ReasoningSignals(
        operation="stitch_chapter", n_canon_rules=len(active_rules),
        n_present_entities=len(union_cast(scenes)),
        has_reveal_gate=any(r.scope == "reveal_gate" for r in active_rules),
        tension=None, guide="")
    control = infer_reasoning_control(body.model_kind, body.model_name)
    reasoning = resolve_reasoning(
        user_pref=body.reasoning, model_control=control, auto_effort=score_effort(signals),
        auto_source=str(work.settings.get("reasoning_engine", "rule_based")))
    # Size from the number of scene drafts being merged (the stitched chapter is
    # ~their combined length), clamped to the ceiling — long chapters need room.
    max_out = body.max_output_tokens or min(
        len(drafts) * settings.chapter_gen_per_scene_tokens, settings.stitch_max_tokens)

    if settings.composition_worker_enabled:
        # M4 (Option A) — resolve the bearer-only bits (chapter_sort, critic config)
        # HERE, persist them + the resolved context in job.input, enqueue → 202. The
        # worker runs stitch + canon-reflect + stores the result; persistence to the
        # book draft stays a separate bearer accept-step (GET /jobs/{id} polls). Same
        # in-flight guard + idempotency as the inline path.
        chapter_sort = (await book.get_chapter_sort_orders([chapter_id])).get(str(chapter_id))
        sdict = work.settings or {}
        c_src, c_ref = sdict.get("critic_model_source"), sdict.get("critic_model_ref")
        distinct = bool(c_ref and c_src and str(c_ref) != str(body.model_ref))
        job_input = {
            "model_source": body.model_source, "model_ref": str(body.model_ref),
            "operation": "stitch_chapter", "worker_op": "stitch_chapter",
            "assembly_mode": "per_scene_stitch",
            "chapter_id": str(chapter_id), "chapter_intent": chapter_intent,
            "cast_glossary_ids": [str(e) for e in union_cast(scenes)],
            "chapter_sort": chapter_sort, "max_out": max_out,
            "reasoning": reasoning.source,
            "reasoning_effort": None if reasoning.passthrough else reasoning.effort,
            "reflect_max_iters": max(0, min(3, int(sdict.get("reflect_max_iters", 1) or 1))),
            "critic_source": str(c_src) if distinct else None,
            "critic_ref": str(c_ref) if distinct else None,
        }
        try:
            job, created = await jobs.create_chapter_job_guarded(
                project_id, chapter_id, created_by=user_id, operation="stitch_chapter",
                mode="auto", status="pending", input=job_input,
                idempotency_key=body.idempotency_key,
                stale_secs=settings.chapter_inflight_stale_secs,
                model_name=await resolve_model_name(
                    body.model_source, str(body.model_ref) if body.model_ref else None))
        except ChapterJobInFlightError as exc:
            raise HTTPException(status_code=409, detail={
                "code": "CHAPTER_JOB_IN_FLIGHT", "active_job_id": exc.active_job_id})
        if not created:  # idempotent replay
            r = job.result or {}
            return JSONResponse({"job_id": str(job.id), "status": job.status,
                                 "mode": "auto", "replay": True,
                                 "text": r.get("text", ""), "canon": r.get("canon"),
                                 "assembly_mode": "per_scene_stitch"})
        enqueued = await enqueue_job(
            settings.redis_url, job_id=str(job.id),
            user_id=str(user_id), project_id=str(project_id))
        return JSONResponse(
            status_code=http_status.HTTP_202_ACCEPTED,
            content={"job_id": str(job.id), "status": "pending",
                     "enqueued": "ok" if enqueued else "retriggerable"})

    # In-flight guard (Cycle-2): reject a concurrent chapter-level job for this
    # chapter (a running generate or stitch) with 409 — both write this chapter's
    # draft. Same-key idempotent replay is honored before the guard.
    try:
        job, created = await jobs.create_chapter_job_guarded(
            project_id, chapter_id, created_by=user_id, operation="stitch_chapter",
            mode="auto", status="running",
            input={"model_source": body.model_source, "model_ref": str(body.model_ref),
                   "operation": "stitch_chapter", "assembly_mode": "per_scene_stitch",
                   "chapter_id": str(chapter_id), "reasoning": reasoning.source,
                   "reasoning_effort": reasoning.effort},
            idempotency_key=body.idempotency_key,
            stale_secs=settings.chapter_inflight_stale_secs,
            model_name=await resolve_model_name(
                body.model_source, str(body.model_ref) if body.model_ref else None))
    except ChapterJobInFlightError as exc:
        raise HTTPException(status_code=409, detail={
            "code": "CHAPTER_JOB_IN_FLIGHT", "active_job_id": exc.active_job_id})
    if not created:  # idempotent replay
        r = job.result or {}
        return JSONResponse({"job_id": str(job.id), "mode": "auto", "replay": True,
                             "text": r.get("text", ""), "status": job.status,
                             "canon": r.get("canon"), "assembly_mode": "per_scene_stitch"})

    # Stitch (degrade → raw concat). The raw concat is the safe fallback artifact.
    # Model-context-aware input sizing — a flat 24K-char cap tuned for a mid-size
    # model shouldn't cap a genuinely bigger model at the same number.
    _stitch_context_length = await llm.resolve_context_length(body.model_source, str(body.model_ref))
    _stitch_chars = scale_by_window(settings.stitch_max_input_chars, _stitch_context_length)
    stitched, stitch_finish = await stitch_chapter(
        llm, user_id=str(user_id), model_source=body.model_source, model_ref=str(body.model_ref),
        scene_drafts=drafts, chapter_intent=chapter_intent, profile=profile,
        max_tokens=max_out, max_input_chars=_stitch_chars,
        reasoning_effort=None if reasoning.passthrough else reasoning.effort)
    degraded = not stitched
    final_text = stitched or "\n\n".join(drafts)
    # D-COMP-TRUNCATION-SURFACING: "length" ⇒ the stitch pass hit the cap. Only
    # meaningful when NOT degraded (a raw concat has no model stop reason).
    truncated = (not degraded) and stitch_finish == "length"

    # Post-stitch canon re-check over the union cast at the chapter position (a
    # rewrite can re-introduce a gone character). Degrade-safe, never blocks (F1).
    chapter_sort = (await book.get_chapter_sort_orders([chapter_id])).get(str(chapter_id))
    sdict = work.settings or {}
    c_src, c_ref = sdict.get("critic_model_source"), sdict.get("critic_model_ref")
    distinct = bool(c_ref and c_src and str(c_ref) != str(body.model_ref))
    canon_v: dict[str, Any] = {"violations": [], "resolved": True, "iterations": 0,
                               "status": "degraded"}
    revise_finish: str | None = None
    try:
        final_text, reflect, _ = await run_canon_reflect(
            knowledge=knowledge, llm=llm, user_id=user_id, project_id=project_id,
            cast_glossary_ids=[str(e) for e in union_cast(scenes)],
            # A stitch has no single packed prompt — pass the chapter intent as the
            # revise context so a canon-repair has the chapter's goal to steer by,
            # not just the violations list (cy16; was "").
            scene_sort_order=chapter_sort, draft=final_text, packed_prompt=chapter_intent,
            profile=profile,
            drafter_source=body.model_source, drafter_ref=str(body.model_ref),
            judge_source=str(c_src) if distinct else None,
            judge_ref=str(c_ref) if distinct else None,
            prompt_estimate=0, max_output_tokens=max_out,
            max_iters=max(0, min(3, int(sdict.get("reflect_max_iters", 1) or 1))),
            reasoning_effort=None if reasoning.passthrough else reasoning.effort)
        canon_v = {"violations": [v.model_dump() for v in reflect.violations],
                   "resolved": reflect.resolved, "iterations": reflect.iterations,
                   "status": reflect.status}
        revise_finish = reflect.revise_finish_reason
    except Exception:
        logger.warning("stitch canon reflect failed (advisory) — keeping stitched draft", exc_info=True)
    # A canon-repair during the post-stitch re-check can itself truncate — OR its
    # stop reason into the stitch-pass flag so a cut-off repair isn't a silent green.
    truncated = truncated or (revise_finish == "length")

    persisted, draft_version, persist_error = False, None, None
    if body.persist:
        persisted, draft_version, persist_error = await _persist_chapter_draft(
            book, work.book_id, chapter_id, bearer, final_text, "AI chapter draft (stitch)",
            scenes=_scene_marker_rows(scenes))

    await jobs.update_status(
        job.id, "completed",
        result={"text": final_text, "canon": canon_v, "assembly_mode": "per_scene_stitch",
                "stitched": not degraded, "chapter_id": str(chapter_id),
                "truncated": truncated, "finish_reason": stitch_finish,
                "persisted": persisted, "draft_version": draft_version})
    return JSONResponse({
        "job_id": str(job.id), "mode": "auto", "status": "completed", "text": final_text,
        "canon": canon_v, "assembly_mode": "per_scene_stitch", "stitched": not degraded,
        "degraded": degraded, "truncated": truncated, "finish_reason": stitch_finish,
        "reasoning_source": reasoning.source,
        "reasoning_effort": reasoning.effort, "persisted": persisted,
        "draft_version": draft_version, "persist_error": persist_error,
        "max_output_tokens": max_out})


@router.post("/works/{project_id}/scenes/{node_id}/suggest-cast")
async def suggest_cast(
    project_id: UUID, node_id: UUID, body: SuggestCastBody,
    user_id: UUID = Depends(get_current_user),
    works: WorksRepo = Depends(get_works_repo),
    outline: OutlineRepo = Depends(get_outline_repo),
    structures: StructureRepo | None = Depends(get_structure_repo),
    glossary: GlossaryClient = Depends(get_glossary_client_dep),
    grant: GrantClient = Depends(get_grant_client_dep),
) -> dict[str, Any]:
    work, node = await _load_work_node(
        works, outline, grant, user_id, project_id, node_id, GrantLevel.VIEW)
    query = " ".join(str(x) for x in [node.goal, node.synopsis, node.title, body.guide] if x)
    bios = await glossary.select_for_context(work.book_id, user_id, query)
    suggested = [b["entity_id"] for b in bios if b.get("entity_id")]
    return {"suggested_entity_ids": suggested}


@router.get("/works/{project_id}/scenes/{node_id}/suggest-motifs")
async def suggest_motifs(
    project_id: UUID, node_id: UUID,
    limit: int = Query(default=5, ge=1, le=20),
    user_id: UUID = Depends(get_current_user),
    works: WorksRepo = Depends(get_works_repo),
    outline: OutlineRepo = Depends(get_outline_repo),
    grant: GrantClient = Depends(get_grant_client_dep),
) -> dict[str, Any]:
    """BE-M4 — ranked motif candidates for a chapter node, each with a `match_reason`
    breakdown (tension/genre/precondition/semantic). The GUI twin of the agent-only
    `composition_motif_suggest_for_chapter` — it replaces the FE's flat `list(scope=all,100)`
    behind SwapMotifPopover (spec 33 §2.5: a GG-1 Determinism gap in one hook). VIEW-gated on
    the Work's book; a node from another Work → uniform 404 (per-tool IDOR)."""
    work, node = await _load_work_node(
        works, outline, grant, user_id, project_id, node_id, GrantLevel.VIEW)
    retriever = MotifRetriever(get_pool())
    # Two-space retrieval (2026-07-17 tenancy re-design): the caller's OWN BYOK embed model
    # (from the Work settings) ranks their STRICTLY-PRIVATE motifs in their own space
    # (section='mine'); shared motifs rank in the platform space (section='library'). None ⇒
    # private motifs degrade to genre+tension (the platform never embeds private content).
    candidates = await retriever.retrieve(
        user_id, book_id=work.book_id, project_id=project_id,
        genre_tags=list(getattr(work, "genre_tags", []) or []),
        language=getattr(work, "language", None) or "en",
        beat_role=None, tension=getattr(node, "tension_target", None), limit=limit,
        user_model=reference_embed_model(getattr(work, "settings", None)),
    )
    return {"candidates": [
        {"motif": c.motif.model_dump(mode="json"), "score": c.score, "match_reason": c.match_reason}
        for c in candidates
    ]}


@router.get("/jobs/{job_id}")
async def get_job(
    job_id: UUID,
    user_id: UUID = Depends(get_current_user),
    jobs: GenerationJobsRepo = Depends(get_generation_jobs_repo),
    works: WorksRepo = Depends(get_works_repo),
    grant: GrantClient = Depends(get_grant_client_dep),
) -> dict[str, Any]:
    job = await jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    # By-id route: gate on the job's OWN project→book (PM-8; VIEW = read tier).
    # An UNBOUND job (BE-7c: project_id IS NULL) has no Work to gate on, so it can never
    # be read here — that is correct and deliberate. Its route is /motif-jobs/{job_id}.
    if job.project_id is None:
        raise HTTPException(status_code=404, detail="job not found")
    await _gate_work(works, grant, user_id, job.project_id, GrantLevel.VIEW)
    return job.model_dump(mode="json")


@router.get("/motif-jobs/{job_id}")
async def get_motif_job(
    job_id: UUID,
    user_id: UUID = Depends(get_current_user),
    jobs: GenerationJobsRepo = Depends(get_generation_jobs_repo),
) -> dict[str, Any]:
    """BE-7c — the OWNER-scoped job read.

    `GET /jobs/{job_id}` gates on the job's project→book grant (`_gate_work`). That is
    correct for Work-bound jobs and IMPOSSIBLE for the ones that aren't: a book/corpus
    motif-mine and an arc-import are enqueued with `project_id=None` — they are genuinely
    not Work-bound, so the row carries NO composition_work and the Work gate 404s FOREVER,
    after the user has already paid for the LLM run. This route gates on the actor stamp
    the row DOES carry (`created_by`) instead.

    ⚠ NEVER "fix" this by back-filling a synthetic project_id into a Work — that would
    mint a phantom Work row per mine. The job is genuinely user-scoped, not Work-scoped.
    ⚠ Missing and denied return the SAME 404, byte for byte (H13 — no enumeration oracle).
    A 403 here would confirm to a stranger that the job exists.
    """
    job = await jobs.get(job_id)
    if job is None or job.created_by != user_id:
        raise HTTPException(status_code=404, detail="job not found")
    return job.model_dump(mode="json")


@router.post("/jobs/{job_id}/persist")
async def persist_job(
    job_id: UUID,
    body: PersistJobBody,
    user_id: UUID = Depends(get_current_user),
    bearer: str = Depends(get_bearer_token),
    jobs: GenerationJobsRepo = Depends(get_generation_jobs_repo),
    works: WorksRepo = Depends(get_works_repo),
    outline: OutlineRepo = Depends(get_outline_repo),
    structures: StructureRepo | None = Depends(get_structure_repo),
    book: BookClient = Depends(get_book_client_dep),
    grant: GrantClient = Depends(get_grant_client_dep),
) -> dict[str, Any]:
    """M4 Option A — the accept/persist step for a WORKER-computed chapter result.

    The composition worker has only the internal-auth LLM (no user bearer), so it
    COMPUTES the chapter (stitch / chapter generate) and stores the text in
    ``generation_job.result`` with ``persisted: False``; this endpoint writes that
    text into the book-service draft with the CALLER's bearer. For the inline
    (flag-off) path the endpoint persisted directly, so this is a no-op there — it
    exists for the worker (202) path the FE polls then accepts.

    Guards: the job must be the caller's, ``completed``, and carry a
    ``chapter_id`` + ``text`` in its result (a per-scene draft has no chapter_id →
    422, never mis-persisted as a chapter). Idempotent: a job already
    ``persisted`` returns success without a second write (the cross-store
    best-effort rule — the text is durable in the job regardless)."""
    job = await jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    # By-id route: gate on the job's OWN project→book (PM-8; persist = EDIT tier).
    await _gate_work(works, grant, user_id, job.project_id, GrantLevel.EDIT)
    if job.status != "completed":
        raise HTTPException(status_code=409, detail={
            "code": "JOB_NOT_COMPLETED", "status": job.status})
    result = dict(job.result or {})
    chapter_id = result.get("chapter_id")
    text = result.get("text")
    if not chapter_id or not text:
        # A per-scene / non-chapter result is not a persistable chapter draft.
        raise HTTPException(status_code=422, detail={
            "code": "JOB_NOT_PERSISTABLE",
            "detail": "job result has no chapter_id/text to persist as a chapter draft"})
    if result.get("persisted"):  # idempotent — already written, don't double-PATCH
        return {"job_id": str(job.id), "persisted": True,
                "draft_version": result.get("draft_version"), "already": True}

    # C26 FIX 2 — the derivative override-critic GATE actually blocks accept here (it
    # was set/persisted but never consumed). A latest critic that flagged a slip
    # (needs_regeneration) refuses the accept with 409 + surfaces the findings so the
    # user regenerates. FAIL-OPEN once the regen cap is reached (regen_exhausted): the
    # gate stops blocking so a stubborn / false-positive slip can't lock the draft
    # forever — the finding is surfaced, accept proceeds. A job with no critic, a
    # compliant critic, or a canon (non-derivative) Work is never blocked.
    critic = job.critic or {}
    if critic.get("needs_regeneration") and not critic.get("regen_exhausted"):
        raise HTTPException(status_code=409, detail={
            "code": "OVERRIDE_SLIP_NEEDS_REGEN",
            "detail": "a derivative override slipped — regenerate before accepting, "
                      "or exhaust the regeneration cap to accept anyway",
            "regen_attempts": critic.get("regen_attempts"),
            "regen_cap": critic.get("regen_cap"),
            "derivative_findings": critic.get("derivative_findings") or [],
        })

    work = await works.get(job.project_id)
    if work is None:
        raise HTTPException(status_code=404, detail="work not found")

    assembly = result.get("assembly_mode", "chapter")
    msg = body.commit_message or f"AI chapter draft ({assembly}, accepted)"
    # F4 (D-SCENEMARKER-EMIT) — best-effort scene fetch for sceneId marker matching;
    # a fetch failure persists without markers, it never blocks the accept.
    scene_rows: list[dict[str, Any]] | None = None
    try:
        scene_rows = _scene_marker_rows(await outline.scenes_for_chapter(
            job.project_id, UUID(str(chapter_id))))
    except Exception:  # noqa: BLE001 — advisory; the accept must proceed
        logger.warning("scene-marker fetch failed (advisory) — persisting without markers",
                       exc_info=True)
    persisted, draft_version, persist_error = await _persist_chapter_draft(
        book, work.book_id, UUID(str(chapter_id)), bearer, text, msg, scenes=scene_rows)
    if persisted:
        # Stamp the result so a re-accept is idempotent + the job reflects the write.
        await jobs.update_status(
            job.id, job.status,
            result={**result, "persisted": True, "draft_version": draft_version})
    return {"job_id": str(job.id), "persisted": persisted,
            "draft_version": draft_version, "persist_error": persist_error}


@router.post("/works/{project_id}/scenes/{node_id}/prose")
async def persist_scene_prose(
    project_id: UUID,
    node_id: UUID,
    body: ScenePromoteProseBody,
    user_id: UUID = Depends(get_current_user),
    works: WorksRepo = Depends(get_works_repo),
    jobs: GenerationJobsRepo = Depends(get_generation_jobs_repo),
    grant: GrantClient = Depends(get_grant_client_dep),
) -> dict[str, Any]:
    """M3 (WS-B3 prose-persist-on-promote) — persist a promoted derivative scene's
    take PROSE, scene-scoped, in the DERIVATIVE project's synthetic-job store.

    The take ghost was generated on the canon project pre-promote and exists only
    client-side; the existing `POST /jobs/{id}/persist` is CHAPTER-only (422s a
    per-scene result), so it can't be reused. This writes a synthetic completed
    generation_job keyed by `node_id` (result={text}, input marker
    `{kind: promoted_scene_prose}`) so `prior_scene_drafts` / `chapter_scene_drafts`
    read it back — NO new table.

    SOURCE-CLOBBER GUARD (critical, CLAUDE.md COW/tenancy): the derivative SHARES the
    source book_id, so writing prose into book-service's chapter draft would clobber
    the shared SOURCE chapter. This endpoint writes ONLY composition's own DB — it
    never calls book.patch_draft / book.get_draft(shared_book_id, …).

    Auth/scope: EDIT grant on the book; `project_id` MUST be a DERIVATIVE owned by
    the caller (works.get is user-scoped → wrong-owner / missing = 404; a
    non-derivative is 409 — a canon project has no source to promote a take from).
    Empty/whitespace text → 422 EMPTY_SCENE_PROSE. Idempotent on `node_id`: a
    re-promote / double-submit overwrites the same scene's prose, never duplicates.

    Returns `{node_id, persisted: true, version}` (version = the per-node promote
    count, +1 each re-promote)."""
    # Empty/whitespace text is a no-write (the caller skips that scene) — 422 BEFORE
    # any auth round-trip side effect, mirroring the engine's request-validation posture.
    if not body.text.strip():
        raise HTTPException(status_code=422, detail={
            "code": "EMPTY_SCENE_PROSE",
            "detail": "scene prose is empty/whitespace — nothing to persist"})

    work = await works.get(project_id)
    if work is None:
        raise HTTPException(status_code=404, detail="work not found")
    # Persisting a promoted take into the derivative is an authoring write → EDIT.
    try:
        await authorize_book(grant, work.book_id, user_id, GrantLevel.EDIT)
    except OwnershipError:
        raise HTTPException(status_code=404, detail="book not found")
    except InsufficientGrant:
        raise HTTPException(status_code=403, detail="insufficient access")

    # DERIVATIVE-only: a take is promoted FROM the canon what-if INTO the derivative.
    # A non-derivative (canon/greenfield) project has no promote surface — reject so
    # this can never be mis-aimed at a canon project's scene store.
    if work.source_work_id is None:
        raise HTTPException(status_code=409, detail={
            "code": "NOT_A_DERIVATIVE",
            "detail": "scene-prose promote applies only to a derivative work"})

    # Write ONLY the synthetic-job store in the DERIVATIVE project (never the shared
    # book draft). Idempotent on node_id (delete-existing-promoted-then-insert under
    # a per-node lock). A node that is not the caller's scene in this project →
    # ReferenceViolationError → 404 (no existence oracle).
    try:
        _job, version = await jobs.upsert_promoted_scene_prose(
            project_id, node_id, body.text,
            created_by=user_id, idempotency_key=body.idempotency_key,
            anchor_node_id=body.anchor_node_id)
    except ReferenceViolationError:
        raise HTTPException(status_code=404, detail="scene not found")

    return {"node_id": str(node_id), "persisted": True, "version": version}


@router.post("/jobs/{job_id}/critique")
async def critique(
    job_id: UUID, body: CritiqueBody,
    user_id: UUID = Depends(get_current_user),
    bearer: str = Depends(get_bearer_token),
    jobs: GenerationJobsRepo = Depends(get_generation_jobs_repo),
    works: WorksRepo = Depends(get_works_repo),
    derivatives: DerivativesRepo = Depends(get_derivatives_repo),
    canon: CanonRulesRepo = Depends(get_canon_rules_repo),
    llm: LLMClient = Depends(get_llm_client_dep),
    glossary: GlossaryClient = Depends(get_glossary_client_dep),
    knowledge: KnowledgeClient = Depends(get_knowledge_client_dep),
    book: BookClient = Depends(get_book_client_dep),
    grant: GrantClient = Depends(get_grant_client_dep),
) -> dict[str, Any]:
    job = await jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    # By-id route: gate on the job's OWN project→book (PM-8; critique writes the
    # job's critic → EDIT tier).
    work = await _gate_work(works, grant, user_id, job.project_id, GrantLevel.EDIT)

    settings_dict = work.settings or {}
    passage = body.passage if body.passage is not None else (job.result or {}).get("text", "")

    # C26 (dị bản M3) — the DERIVATIVE critic dimension. Fires ONLY for a derivative
    # Work (source_work_id set, surfaced via C25's build_derivative_context); enforces
    # the active entity_override[] against the passage (override slip + delta internal
    # consistency). Deterministic + AI-free — so it runs INDEPENDENTLY of the LLM
    # critic-model gate below (a derivative with no distinct critic model still gets
    # override enforcement). Degrade-safe (returns [] on any failure — advisory).
    derivative_findings = await critique_overrides(
        work=work, user_id=user_id, passage=passage, bearer=bearer,
        works_repo=works, derivatives_repo=derivatives,
        glossary=glossary, knowledge=knowledge, book=book,
    )
    # C26 GATE — turn the (formerly advisory) derivative findings into an
    # accept/regenerate VERDICT with a bounded attempt cap. `prior_attempts` is read
    # back off the job's existing critic (each slipped critique burns one attempt via
    # the existing regenerate→re-critique loop; the cap fails OPEN to the human so a
    # stubborn / false-positive slip can't loop forever). Only computed for a
    # derivative that actually produced findings.
    prior_attempts = int((job.critic or {}).get("regen_attempts", 0) or 0)
    gate = (
        co_evaluate_override_gate(derivative_findings, prior_attempts=prior_attempts)
        if derivative_findings else None
    )

    critic_src = settings_dict.get("critic_model_source")
    critic_ref = settings_dict.get("critic_model_ref")
    drafter_ref = (job.input or {}).get("model_ref")
    # Anti-self-reinforcement: the critic MUST be a distinct model. No critic
    # configured, or same as the drafter → skip the LLM critique (advisory) + warn,
    # but STILL surface + persist the deterministic derivative findings + the GATE.
    if not critic_ref or not critic_src or str(critic_ref) == str(drafter_ref):
        critic = ({"derivative_findings": derivative_findings, **gate}
                  if derivative_findings else None)
        if critic is not None:
            await jobs.update_status(job_id, job.status, critic=critic,
                                     target_revision_id=body.target_revision_id)
        return {"critic": critic,
                "warning": "critique skipped: no distinct critic model configured"}

    # CC2: re-resolve the ACTIVE canon at critique time — a deleted/archived rule
    # is never enforced.
    rules = await canon.list_active(job.project_id)
    active_rules = [{"rule_id": str(r.id), "text": r.text} for r in rules]

    critic = await judge_prose(
        llm, user_id=str(user_id), model_source=str(critic_src), model_ref=str(critic_ref),
        passage=passage, active_rules=active_rules, present_facts=[],
        profile=from_settings(settings_dict),
    )
    # Fold the deterministic derivative findings + the GATE verdict into the critic
    # contract (alongside the LLM dims/violations) so the regeneration loop sees both.
    if derivative_findings:
        critic = {**critic, "derivative_findings": derivative_findings, **(gate or {})}
    elif prior_attempts:
        # FIX 3 (MED) — carry the regen-cap counter FORWARD on a clean LLM-critic run.
        # `critic` is COALESCE-replaced on write (generation_jobs.update_status), so a
        # clean critique BETWEEN two slips would otherwise DROP regen_attempts and the
        # next slip restarts the cap at 0 (a re-spend loop). Persist the prior count so
        # the cap keeps bounding the total ≤ REGEN_ATTEMPT_CAP across mixed critiques.
        critic = {**critic, "regen_attempts": prior_attempts}
    await jobs.update_status(job_id, job.status, critic=critic,
                             target_revision_id=body.target_revision_id)
    return {"critic": critic}


@router.post("/jobs/{job_id}/dismiss-violation")
async def dismiss_violation(
    job_id: UUID, body: DismissBody,
    user_id: UUID = Depends(get_current_user),
    jobs: GenerationJobsRepo = Depends(get_generation_jobs_repo),
    works: WorksRepo = Depends(get_works_repo),
    grant: GrantClient = Depends(get_grant_client_dep),
) -> dict[str, Any]:
    job = await jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    # By-id route: gate on the job's OWN project→book (PM-8; EDIT — it rewrites
    # the job's critic verdict).
    await _gate_work(works, grant, user_id, job.project_id, GrantLevel.EDIT)
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
    await jobs.update_status(job_id, job.status, critic=critic)
    return {"critic": critic}


@router.post("/jobs/{job_id}/correction", status_code=201)
async def correction(
    job_id: UUID, body: CorrectionBody,
    user_id: UUID = Depends(get_current_user),
    jobs: GenerationJobsRepo = Depends(get_generation_jobs_repo),
    works: WorksRepo = Depends(get_works_repo),
    corrections: GenerationCorrectionsRepo = Depends(get_generation_corrections_repo),
    grant: GrantClient = Depends(get_grant_client_dep),
) -> dict[str, Any]:
    """Capture a human-gate correction on a generation (V1 flywheel slice 1, §3).

    Records one of the genuine-author-choice actions (edit / pick_different /
    regenerate / reject) + emits `composition.generation_corrected` for the
    learning-service preference store. Verbatim prose is stored only when the
    work opted into `capture_correction_prose` (§5); the change magnitude +
    structural shape are always captured. `accept` is deliberately not an action
    here (H2 — it trains the reranker on its own pick)."""
    job = await jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    # By-id route: gate on the job's OWN project→book (PM-8; EDIT — it records a
    # correction + emits the learning event).
    work = await _gate_work(works, grant, user_id, job.project_id, GrantLevel.EDIT)

    result = job.result or {}
    winner_text: str = result.get("text", "") or ""
    candidates: list[Any] = result.get("candidates") or []

    chosen_index = body.chosen_candidate_index
    changed_blocks: int | None = None
    raw_before: str | None = None
    raw_after: str | None = None

    if body.kind == "edit":
        if body.edited_text is None:
            raise HTTPException(status_code=422, detail="edit requires edited_text")
        changed_blocks = count_changed_blocks(winner_text, body.edited_text)
        # A zero-change "edit" is an accept-as-is wearing an edit costume: mining
        # `edited ≻ winner` when edited==winner trains the reranker on its own pick
        # = the self-reinforcement §2/H2 forbids. Reject it at the source so the
        # circular signal never enters the store (/review-impl MED#3).
        if changed_blocks == 0:
            raise HTTPException(status_code=422, detail={
                "code": "EDIT_NO_CHANGE",
                "reason": "edited_text is identical to the generation (no correction signal)"})
    elif body.kind == "pick_different":
        if chosen_index is None:
            raise HTTPException(status_code=422, detail="pick_different requires chosen_candidate_index")
        if chosen_index >= len(candidates):
            # cowrite jobs have no candidate set; an out-of-range index is a bad request.
            raise HTTPException(status_code=422, detail={
                "code": "CANDIDATE_INDEX_OUT_OF_RANGE", "k": len(candidates)})

    # Raw-prose capture is OPT-IN per work (§5). Default: structural only.
    if bool(work.settings.get("capture_correction_prose", False)):
        if body.kind == "edit":
            raw_before, raw_after = winner_text, body.edited_text
        elif body.kind == "pick_different":
            raw_before = winner_text
            raw_after = str(candidates[chosen_index])
        elif body.kind in ("regenerate", "reject"):
            raw_before = winner_text  # the rejected/regenerated-from prose

    try:
        corr = await corrections.create(
            job.project_id, job_id, created_by=user_id,
            kind=body.kind, chosen_candidate_index=chosen_index,
            guidance=body.guidance, changed_blocks=changed_blocks,
            raw_before=raw_before, raw_after=raw_after,
            regenerated_to_job_id=body.regenerated_to_job_id,
            # event-only (not stored): the job's reranked winner + candidate count,
            # so slice-2 learning can reconstruct `j ≻ i` from the wire (LOW#4).
            winner_index=result.get("winner_index"),
            candidate_count=len(candidates) if candidates else None,
        )
    except ReferenceViolationError:
        # job/project mismatch slipped past the get() (cross-user / cross-project).
        raise HTTPException(status_code=404, detail="job not found")
    return corr.model_dump(mode="json")


@router.get("/works/{project_id}/correction-stats")
async def correction_stats(
    project_id: UUID,
    user_id: UUID = Depends(get_current_user),
    works: WorksRepo = Depends(get_works_repo),
    corrections: GenerationCorrectionsRepo = Depends(get_generation_corrections_repo),
    grant: GrantClient = Depends(get_grant_client_dep),
) -> dict[str, Any]:
    """The V1 eval-gate dashboard (§6): per-mode correction rates for this Work.

    Replaces the saturating auto-judge coherence-median with human-grounded
    correction rates (accept-as-is ↑, edit/pick/regenerate/reject ↓). Both modes
    are always present (zero-filled) for the auto-vs-cowrite A/B; the auto-judge
    script stays as the cold-start proxy until real corrections accumulate."""
    await _gate_work(works, grant, user_id, project_id, GrantLevel.VIEW)
    stats = await corrections.correction_stats(project_id)
    return stats.model_dump(mode="json")
