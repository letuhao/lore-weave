"""Worker-side batch operations (Phase 3 M4).

Each ``run_<op>`` runs ONE batch operation's LLM compute from the job's persisted
``input`` (the endpoint already resolved every bearer-authenticated dependency —
book chapters, cast, profile — into ``input``, because the worker has only the
internal-auth LLM client, never the user's bearer). The result dict is written to
``generation_job.result`` for the GET /jobs/{id} poll.

Foundation increment: decompose only. generate / selection-edit / chapter-gen /
stitch are added in the subsequent increments (they additionally need the pool +
clients for draft persistence + canon-reflect, threaded via the consumer).
"""

from __future__ import annotations

import dataclasses
import logging
from collections.abc import Awaitable, Callable
from typing import Any
from uuid import UUID

import asyncpg

from app.clients.llm_client import LLMClient
from app.config import settings
from app.worker.constants import SUPPORTED_OPERATIONS
from loreweave_context import scale_by_window

__all__ = [
    "UnsupportedOperationError",
    "SUPPORTED_OPERATIONS",
    "run_decompose",
    "run_stitch",
    "run_generate",
    "run_chapter_generate",
    "run_selection_edit",
    "run_quality_report",
    "run_promise_coverage",
    "run_plan_forge_propose",
    "run_plan_forge_refine",
]

logger = logging.getLogger("composition.worker.operations")


class UnsupportedOperationError(RuntimeError):
    """The job's operation has no worker handler (a config/enqueue bug — the
    endpoint should only enqueue operations the worker can run)."""


async def _maybe_narrative_threads(
    pool: asyncpg.Pool, llm: LLMClient, sdict: dict[str, Any], profile, *,
    user_id: str, project_id: str, scene_text: str, opened_at_node: str | None,
    model_source: str, model_ref: str,
    cancel_check: Callable[[], Awaitable[bool]] | None = None,
) -> None:
    """FD-1 narrative_thread S2 best-effort producer, gated per-work. Mirrors the
    inline ``_maybe_detect_narrative_threads`` — never raises into the compute
    (advisory). Shared by run_generate + run_chapter_generate."""
    if not sdict.get("narrative_thread_enabled"):
        return
    from app.db.repositories.narrative_thread import NarrativeThreadRepo
    from app.engine.narrative_thread import detect_and_update_threads
    try:
        await detect_and_update_threads(
            llm, NarrativeThreadRepo(pool),
            user_id=UUID(user_id), project_id=UUID(project_id),
            scene_text=scene_text,
            opened_at_node=UUID(opened_at_node) if opened_at_node else None,
            drafter_source=model_source, drafter_ref=model_ref,
            source_language=profile.source_language,
            max_open=settings.narrative_thread_max_open_per_scene,
            cancel_check=cancel_check,
        )
    except Exception:  # noqa: BLE001 — advisory; must not fail the generate
        logger.warning("narrative_thread S2 producer failed (advisory)", exc_info=True)


async def run_decompose(
    llm: LLMClient, *, user_id: str, input: dict[str, Any],
    cancel_check: Callable[[], Awaitable[bool]] | None = None,
) -> dict[str, Any]:
    """Run the decompose planner from the persisted, fully-resolved input. The
    endpoint stored chapters/cast/beats/profile so this needs NO bearer (only the
    internal-auth LLM). Returns ``dataclasses.asdict(result)`` for the poll."""
    # Local import: app.engine.plan pulls the engine graph — keep the worker's
    # module-import surface small + avoid any import cycle through the routers.
    from app.engine.plan import ChapterPlan, decompose

    chapters = [ChapterPlan(**c) for c in input["chapters"]]
    result = await decompose(
        llm,
        user_id=user_id,
        model_source=input["model_source"],
        model_ref=input["model_ref"],
        premise=input["premise"],
        arc_title=input["arc_title"],
        beats=input["beats"],
        chapters=chapters,
        cast=input["cast"],
        k_ceiling=input["k_ceiling"],
        high_threshold=input["high_threshold"],
        min_scenes=input["min_scenes"],
        max_scenes=input["max_scenes"],
        source_language=input["source_language"],
        thread_state=input.get("thread_state", False),  # Phase-0 slice-2 (default off ⇒ today's behavior)
        cancel_check=cancel_check,
    )
    return dataclasses.asdict(result)


async def run_plan_pipeline(
    pool: asyncpg.Pool, llm: LLMClient, *, user_id: str, input: dict[str, Any],
    cancel_check: Callable[[], Awaitable[bool]] | None = None,
) -> dict[str, Any]:
    """Run the multi-step planning pipeline (Stages 0-6) from the persisted input. The
    endpoint resolved book/chapters/genres into ``input``; the worker builds the
    retriever (pool) + glossary/KAL singletons (internal-auth) and runs end-to-end.
    Returns ``dataclasses.asdict(PipelineResult)`` for the poll."""
    from app.clients.glossary_client import get_glossary_client
    from app.clients.kal_client import get_kal_client
    from app.db.repositories.motif_retrieve import MotifRetriever
    from app.engine.plan import ChapterPlan
    from app.engine.planning_pipeline import run_planning_pipeline

    chapters = [ChapterPlan(**c) for c in input["chapters"]]
    result = await run_planning_pipeline(
        llm, MotifRetriever(pool), get_glossary_client(), get_kal_client(),
        user_id=user_id, book_id=UUID(input["book_id"]), project_id=UUID(input["project_id"]),
        premise=input["premise"], beats=input["beats"], chapters=chapters,
        genre_tags=input.get("genre_tags", []),
        model_source=input["model_source"], model_ref=input["model_ref"],
        k_ceiling=input["k_ceiling"], high_threshold=input["high_threshold"],
        min_scenes=input["min_scenes"], max_scenes=input["max_scenes"],
        source_language=input["source_language"], self_heal=input.get("self_heal", True),
        cancel_check=cancel_check,
    )
    return dataclasses.asdict(result)


async def run_self_heal_propose(
    llm: LLMClient, *, user_id: str, input: dict[str, Any],
    cancel_check: Callable[[], Awaitable[bool]] | None = None,
) -> dict[str, Any]:
    """Run the cheap-stack self-heal in PROPOSE mode (M6 review-gate) on the persisted
    chapter text + canon (resolved at the endpoint, which has the bearer/roster). Returns
    the EditProposals + stats for the poll; the accepted subset is spliced + written by the
    caller via the existing draft-write — this NEVER auto-writes (the human is the gate)."""
    from app.engine.self_heal import propose_self_heal

    text = input["chapter_text"]
    proposals, report = await propose_self_heal(
        llm, user_id=user_id,
        model_source=input["model_source"], model_ref=input["model_ref"],
        chapter=text, source_language=input.get("source_language", "auto"),
        canon=input.get("canon") or None,
        prefilter=bool(input.get("prefilter", True)),
        # comparative re-ranker is OPT-IN (default OFF) — it costs one extra LLM call PER
        # semantic proposal (pre-checking the ones it approves; it never drops). The FE exposes
        # a toggle; without it the cheap one-call auditor runs. Legacy vote/verify knobs ignored.
        rerank=bool(input.get("rerank", False)),
        cancel_check=cancel_check,
    )
    return {
        "proposals": [dataclasses.asdict(p) for p in proposals],
        "source_text": text,
        "chapter_id": input.get("chapter_id"),
        "draft_version": input.get("draft_version"),
        "stats": {
            "findings": report.rejudge_before,
            "located": report.located,
            "edits": report.edits_applied,
            "refuted": sum(1 for f in report.findings if f.skip_reason == "refuted"),
        },
    }


async def run_quality_report(
    llm: LLMClient, *, user_id: str, input: dict[str, Any],
    cancel_check: Callable[[], Awaitable[bool]] | None = None,
) -> dict[str, Any]:
    """Run the read-only Quality Report over the persisted chapter text + canon (both
    resolved at the endpoint). Surfaces the planner's advisory judges — the 4-dim critic
    (coherence/voice/pacing/canon) + the chapter's narrative THREADS (raised/resolved,
    reframed from the promise audit — the misleading per-chapter "dropped" is gone) — to
    the author. Diagnostic only: NOT applyable edits, so there is nothing to write back."""
    from app.engine.quality_report import build_quality_report

    report = await build_quality_report(
        llm, user_id=user_id,
        model_source=input["model_source"], model_ref=input["model_ref"],
        chapter=input["chapter_text"], source_language=input.get("source_language", "auto"),
        canon=input.get("canon") or None,
        cancel_check=cancel_check,
    )
    return {
        "report": report,
        "chapter_id": input.get("chapter_id"),
        "draft_version": input.get("draft_version"),
    }


async def run_promise_coverage(
    llm: LLMClient, *, user_id: str, input: dict[str, Any],
    cancel_check: Callable[[], Awaitable[bool]] | None = None,
) -> dict[str, Any]:
    """Run the book-level promise coverage (Q3) over the persisted plan_text + book_text
    (the endpoint rendered the outline plan + assembled every chapter's prose — it has the
    bearer/pool). Derives the tracked-promise set from the SPEC and scores the book against
    it. Diagnostic only — read-only counts/verdicts, nothing to write back."""
    from app.engine.quality_report import _COVERAGE_WINDOW_CHARS, build_promise_coverage

    # Model-context-aware window sizing — a flat 12K-char window tuned for a mid-size
    # model shouldn't cap a genuinely bigger model at the same number (fewer, larger
    # windows = fewer score calls + more surrounding context per verdict).
    context_length = await llm.resolve_context_length(input["model_source"], input["model_ref"])
    window_chars = scale_by_window(_COVERAGE_WINDOW_CHARS, context_length)

    coverage = await build_promise_coverage(
        llm, user_id=user_id,
        model_source=input["model_source"], model_ref=input["model_ref"],
        premise=input.get("premise", ""), plan_text=input.get("plan_text", ""),
        book_text=input["book_text"], source_language=input.get("source_language", "auto"),
        window_chars=window_chars,
        cancel_check=cancel_check,
    )
    return {"coverage": coverage, "chapters": input.get("chapters")}


async def run_stitch(
    pool: asyncpg.Pool, llm: LLMClient, knowledge, *, input: dict[str, Any],
    cancel_check: Callable[[], Awaitable[bool]] | None = None,
) -> dict[str, Any]:
    """Stitch a chapter's completed scene drafts into one chapter + re-run the
    chapter-level canon guard (Option A — the worker COMPUTES + stores the result;
    persistence to book-service stays a separate bearer 'accept' step, since the
    worker has no user bearer). Mirrors the inline stitch_chapter_endpoint compute
    half. The endpoint already resolved the bearer-only bits (chapter_sort, critic
    config) into ``input``; drafts + profile are re-read from the DB here."""
    from app.db.repositories.generation_jobs import GenerationJobsRepo
    from app.db.repositories.works import WorksRepo
    from app.engine.canon_reflect import run_canon_reflect
    from app.engine.stitch import prepend_scene_headings, stitch_chapter
    from app.packer.profile import from_settings

    user_id = input["user_id"]
    project_id = input["project_id"]
    chapter_id = input["chapter_id"]
    jobs_repo = GenerationJobsRepo(pool)
    works = WorksRepo(pool)

    work = await works.get(UUID(project_id))
    profile = from_settings(work.settings if work else None)
    rows = await jobs_repo.chapter_scene_drafts(
        UUID(project_id), UUID(chapter_id)
    )
    if not rows:
        raise ValueError("no completed scene drafts to stitch")
    # F4 — each draft opens with its `### <scene title>` line; the persist step
    # (prose_doc) lifts these into sceneId-anchored heading nodes.
    drafts = prepend_scene_headings(rows)

    max_out = input["max_out"]
    reasoning_effort = input.get("reasoning_effort")  # already None when passthrough

    # Model-context-aware input sizing — a flat 24K-char cap tuned for a mid-size
    # model shouldn't cap a genuinely bigger model at the same number.
    _stitch_context_length = await llm.resolve_context_length(input["model_source"], input["model_ref"])
    _stitch_chars = scale_by_window(settings.stitch_max_input_chars, _stitch_context_length)
    stitched, stitch_finish = await stitch_chapter(
        llm, user_id=user_id, model_source=input["model_source"], model_ref=input["model_ref"],
        scene_drafts=drafts, chapter_intent=input["chapter_intent"], profile=profile,
        max_tokens=max_out, max_input_chars=_stitch_chars,
        reasoning_effort=reasoning_effort, cancel_check=cancel_check,
    )
    degraded = not stitched
    final_text = stitched or "\n\n".join(drafts)
    truncated = (not degraded) and stitch_finish == "length"

    # Post-stitch canon re-check (degrade-safe, never blocks) — mirrors the endpoint.
    canon_v: dict[str, Any] = {"violations": [], "resolved": True, "iterations": 0,
                               "status": "degraded"}
    revise_finish: str | None = None
    try:
        final_text, reflect, _ = await run_canon_reflect(
            knowledge=knowledge, llm=llm, user_id=UUID(user_id), project_id=UUID(project_id),
            cast_glossary_ids=input.get("cast_glossary_ids") or [],
            scene_sort_order=input.get("chapter_sort"),
            draft=final_text, packed_prompt=input["chapter_intent"], profile=profile,
            drafter_source=input["model_source"], drafter_ref=input["model_ref"],
            judge_source=input.get("critic_source"), judge_ref=input.get("critic_ref"),
            prompt_estimate=0, max_output_tokens=max_out,
            max_iters=int(input.get("reflect_max_iters", 1) or 1),
            reasoning_effort=reasoning_effort, cancel_check=cancel_check,
        )
        canon_v = {"violations": [v.model_dump() for v in reflect.violations],
                   "resolved": reflect.resolved, "iterations": reflect.iterations,
                   "status": reflect.status}
        revise_finish = reflect.revise_finish_reason
    except Exception:  # noqa: BLE001 — canon reflect is advisory, never blocks
        logger.warning("stitch canon reflect failed (advisory) — keeping stitched draft", exc_info=True)
    truncated = truncated or (revise_finish == "length")

    return {
        "text": final_text, "canon": canon_v, "assembly_mode": "per_scene_stitch",
        "stitched": not degraded, "chapter_id": chapter_id, "truncated": truncated,
        "finish_reason": stitch_finish,
        # persistence is the separate bearer accept-step (Option A) — not done here.
        "persisted": False, "draft_version": None,
    }


async def run_generate(
    pool: asyncpg.Pool, llm: LLMClient, knowledge, *, input: dict[str, Any],
    cancel_check: Callable[[], Awaitable[bool]] | None = None,
) -> dict[str, Any]:
    """Run the AUTO per-scene draft (diverge→converge→canon-reflect) from the
    persisted, fully-resolved input. Mirrors the inline ``generate`` auto path
    (engine.py): the endpoint already ran ``pack()`` (bearer retrieval) and stored
    the packed prompt + scene signals in ``input``, so this needs only the
    internal-auth LLM + knowledge (canon-reflect). The result is stored on the job
    (NO book persistence — a per-scene auto draft isn't a chapter artifact; the FE
    accepts it into the editor). The cowrite STREAM path stays inline (a worker
    can't stream)."""
    from app.db.repositories.works import WorksRepo
    from app.engine.adaptive_k import adaptive_k
    from app.engine.canon_reflect import run_canon_reflect
    from app.engine.select import select_draft
    from app.packer.profile import from_settings

    user_id = input["user_id"]
    project_id = input["project_id"]
    work = await WorksRepo(pool).get(UUID(project_id))
    sdict = (work.settings if work else None) or {}
    profile = from_settings(work.settings if work else None)

    model_source = input["model_source"]
    model_ref = input["model_ref"]
    operation = input["operation"]
    guide = input.get("guide", "")
    packed_prompt = input["packed_prompt"]
    prompt_estimate = input["prompt_estimate"]
    max_out = input["max_out"]
    # reasoning: stored resolved — passthrough (adaptive model) → omit the effort.
    effort = input.get("reasoning_effort")
    effort_arg = None if input.get("reasoning_passthrough") else effort
    # critic_*: the DISTINCT critic (anti-self-reinforcement) or None. select falls
    # back to the drafter when there's no distinct critic; reflect keeps None.
    critic_source = input.get("critic_source")
    critic_ref = input.get("critic_ref")
    cast_glossary_ids = input.get("present_entity_ids") or []

    k = adaptive_k(
        input.get("beat_role"), input.get("tension"),
        k_ceiling=settings.compose_diverge_k,
        high_threshold=settings.plan_high_tension_threshold,
    )
    try:
        sel = await select_draft(
            llm, llm, user_id=user_id,
            drafter_source=model_source, drafter_ref=model_ref,
            judge_source=critic_source or model_source,
            judge_ref=critic_ref or model_ref,
            packed_prompt=packed_prompt, profile=profile, operation=operation, guide=guide,
            k=k, prompt_est=prompt_estimate, max_tokens=max_out,
            temperature=settings.compose_diverge_temperature, reasoning_effort=effort_arg,
            cancel_check=cancel_check,
        )
    except Exception as exc:  # noqa: BLE001 — mirror inline: diverge produced
        # nothing / transport → a TERMINAL job failure (run_job marks failed + ACK,
        # the user retries), NOT an infra redeliver-loop.
        raise ValueError(f"auto generate failed: {exc}") from exc

    w = sel.winner
    final_text = w.text
    canon: dict[str, Any] = {"violations": [], "resolved": True, "iterations": 0,
                             "status": "degraded"}
    revise_out_tokens = 0
    revise_finish: str | None = None
    try:
        final_text, reflect, revise_out_tokens = await run_canon_reflect(
            knowledge=knowledge, llm=llm, user_id=UUID(user_id), project_id=UUID(project_id),
            cast_glossary_ids=cast_glossary_ids, scene_sort_order=input.get("scene_sort_order"),
            draft=w.text, packed_prompt=packed_prompt, profile=profile,
            drafter_source=model_source, drafter_ref=model_ref,
            judge_source=critic_source, judge_ref=critic_ref,
            prompt_estimate=prompt_estimate, max_output_tokens=max_out,
            max_iters=int(input.get("reflect_max_iters", 1) or 1),
            reasoning_effort=effort_arg, cancel_check=cancel_check,
        )
        canon = {"violations": [v.model_dump() for v in reflect.violations],
                 "resolved": reflect.resolved, "iterations": reflect.iterations,
                 "status": reflect.status}
        revise_finish = reflect.revise_finish_reason
    except Exception:  # noqa: BLE001 — canon reflect must NEVER fail the generate (F1).
        logger.warning("generate canon reflect failed (advisory) — keeping winner", exc_info=True)

    # FD-1 narrative_thread S2: best-effort promise-ledger producer (gated per-work).
    await _maybe_narrative_threads(
        pool, llm, sdict, profile, user_id=user_id, project_id=project_id,
        scene_text=final_text, opened_at_node=input.get("outline_node_id"),
        model_source=model_source, model_ref=model_ref, cancel_check=cancel_check)

    # W5 (D-MOTIF-CONFORMANCE-ENGINE-WIRING): the sampled binary conformance judge over
    # the realized scene, IF the node has a bound motif + conformance is enabled. The
    # returned patch (critic.motif_conformance) is stashed under `_critic` for the
    # consumer to persist via update_status(critic=…). Advisory + degrade-safe (never
    # raises). Judge prefers the DISTINCT critic (anti-self-reinforcement) → drafter.
    from app.engine.motif_conformance_producer import maybe_conformance_patch
    critic_patch = await maybe_conformance_patch(
        pool, llm, user_id=user_id, project_id=project_id, profile=profile,
        final_text=final_text, outline_node_id=input.get("outline_node_id"),
        beat_role=input.get("beat_role"), tension=input.get("tension"),
        model_source=critic_source or model_source, model_ref=critic_ref or model_ref,
    )

    total_out = w.metering.output_tokens + revise_out_tokens
    truncated = (w.metering.finish_reason == "length") or (revise_finish == "length")
    return {
        "text": final_text, "input_tokens": w.metering.input_tokens,
        "output_tokens": total_out, "measured": w.metering.measured,
        "k": len(sel.candidates), "winner_index": sel.winner_index,
        "rerank_reason": sel.rerank_reason, "rerank_measured": sel.rerank_measured,
        "candidates": [c.text for c in sel.candidates],
        "truncated": truncated, "finish_reason": w.metering.finish_reason,
        "canon": canon, "assembly_mode": input.get("assembly_mode", "per_scene"),
        # echoed from the resolved input for the GET /jobs poll (the FE reads these
        # off the job result instead of the inline JSON response).
        "grounding_available": input.get("grounding_available"),
        "reasoning_source": input.get("reasoning"), "reasoning_effort": effort,
        "reinjected_promise_count": input.get("reinjected_promise_count"),
        "persisted": False,
        # W5: critic-merge patch for the consumer (popped off → the job's `critic`
        # column, NOT the result blob). None when conformance is off / not sampled /
        # no bound motif. The trace read (routers/conformance.py) surfaces it.
        "_critic": critic_patch,
    }


async def run_chapter_generate(
    pool: asyncpg.Pool, llm: LLMClient, knowledge, *, input: dict[str, Any],
    cancel_check: Callable[[], Awaitable[bool]] | None = None,
) -> dict[str, Any]:
    """Run the B2 single-pass chapter draft (``diverge`` k=1 → chapter-level
    canon-reflect over the union cast) from the persisted input. Mirrors the inline
    ``generate_chapter`` compute half. Option A: the worker COMPUTES + stores the
    result (``persisted=False``); persistence to the book draft is the separate
    bearer accept-step (``POST /jobs/{id}/persist``), since the worker has no user
    bearer. The endpoint already resolved chapter_sort/scenes/pack into ``input``."""
    from app.db.repositories.narrative_thread import NarrativeThreadRepo
    from app.db.repositories.works import WorksRepo
    from app.engine.canon_reflect import run_canon_reflect
    from app.engine.select import diverge
    from app.packer.profile import from_settings

    user_id = input["user_id"]
    project_id = input["project_id"]
    work = await WorksRepo(pool).get(UUID(project_id))
    sdict = (work.settings if work else None) or {}
    profile = from_settings(work.settings if work else None)

    model_source = input["model_source"]
    model_ref = input["model_ref"]
    operation = input["operation"]
    guide = input.get("guide", "")
    packed_prompt = input["packed_prompt"]
    prompt_estimate = input["prompt_estimate"]
    max_out = input["max_out"]
    effort = input.get("reasoning_effort")
    effort_arg = None if input.get("reasoning_passthrough") else effort
    critic_source = input.get("critic_source")
    critic_ref = input.get("critic_ref")
    cast_glossary_ids = input.get("present_entity_ids") or []
    chapter_id = input["chapter_id"]

    try:
        cands = await diverge(
            llm, user_id=user_id, model_source=model_source, model_ref=model_ref,
            packed_prompt=packed_prompt, profile=profile, operation=operation, guide=guide,
            k=1, prompt_est=prompt_estimate, max_tokens=max_out,
            temperature=settings.compose_diverge_temperature, reasoning_effort=effort_arg,
            cancel_check=cancel_check,
        )
    except Exception as exc:  # noqa: BLE001 — no candidate / transport → terminal fail
        raise ValueError(f"chapter generate failed: {exc}") from exc

    winner = cands[0]
    final_text = winner.text
    canon_v: dict[str, Any] = {"violations": [], "resolved": True, "iterations": 0,
                               "status": "degraded"}
    revise_out_tokens = 0
    revise_finish: str | None = None
    try:
        final_text, reflect, revise_out_tokens = await run_canon_reflect(
            knowledge=knowledge, llm=llm, user_id=UUID(user_id), project_id=UUID(project_id),
            cast_glossary_ids=cast_glossary_ids, scene_sort_order=input.get("scene_sort_order"),
            draft=winner.text, packed_prompt=packed_prompt, profile=profile,
            drafter_source=model_source, drafter_ref=model_ref,
            judge_source=critic_source, judge_ref=critic_ref,
            prompt_estimate=prompt_estimate, max_output_tokens=max_out,
            max_iters=int(input.get("reflect_max_iters", 1) or 1),
            reasoning_effort=effort_arg, cancel_check=cancel_check,
        )
        canon_v = {"violations": [v.model_dump() for v in reflect.violations],
                   "resolved": reflect.resolved, "iterations": reflect.iterations,
                   "status": reflect.status}
        revise_finish = reflect.revise_finish_reason
    except Exception:  # noqa: BLE001 — canon reflect must NEVER fail the generate (F1).
        logger.warning("chapter canon reflect failed (advisory) — keeping draft", exc_info=True)

    # FD-1 S2 producer over the whole-chapter draft. opened_at_node=None — the
    # chapter pass uses a synthetic in-memory node (project-scoped thread).
    await _maybe_narrative_threads(
        pool, llm, sdict, profile, user_id=user_id, project_id=project_id,
        scene_text=final_text, opened_at_node=None,
        model_source=model_source, model_ref=model_ref, cancel_check=cancel_check)

    # FD-1 S4a — advisory unpaid-promise DEBT count at chapter end (None when off).
    open_promise_count: int | None = None
    if sdict.get("narrative_thread_enabled"):
        try:
            open_promise_count = await NarrativeThreadRepo(pool).count_open(
                UUID(project_id))
        except Exception:  # noqa: BLE001 — advisory; must not fail the generate
            logger.warning("open_promise_count read failed (advisory)", exc_info=True)

    total_out = winner.metering.output_tokens + revise_out_tokens
    truncated = (winner.metering.finish_reason == "length") or (revise_finish == "length")
    return {
        "text": final_text, "input_tokens": winner.metering.input_tokens,
        "output_tokens": total_out, "measured": winner.metering.measured,
        "truncated": truncated, "finish_reason": winner.metering.finish_reason,
        "canon": canon_v, "assembly_mode": "chapter", "chapter_id": chapter_id,
        # Option A — persistence is the separate bearer accept-step, not done here.
        "persisted": False, "draft_version": None,
        "open_promise_count": open_promise_count,
        "grounding_available": input.get("grounding_available"),
        "reasoning_source": input.get("reasoning"), "reasoning_effort": effort,
        "reinjected_promise_count": input.get("reinjected_promise_count"),
        "max_output_tokens": max_out,
    }


async def run_selection_edit(llm: LLMClient, *, input: dict[str, Any]) -> dict[str, Any]:
    """Run the T3.2 selection-scoped edit (rewrite/expand/describe) as a batch job
    — drain ``stream_draft`` to the final text + metering (a worker can't stream to
    the client, so the FE polls GET /jobs/{id} instead). The endpoint already built
    the full message list (selection + voice/scene grounding) into ``input``, so
    this needs no pack / profile / knowledge. The FE replaces the Tiptap range on
    Accept; no server persistence (``persisted=False``)."""
    from app.engine.cowrite import stream_draft

    user_id = input["user_id"]
    messages = input["messages"]
    prompt_estimate = input["prompt_estimate"]
    max_out = input["max_out"]
    effort = input.get("reasoning_effort")
    effort_arg = None if input.get("reasoning_passthrough") else effort

    final: dict[str, Any] | None = None
    async for ev in stream_draft(
        llm.sdk, user_id=user_id,
        model_source=input["model_source"], model_ref=input["model_ref"],
        messages=messages, prompt_token_estimate=prompt_estimate,
        max_output_tokens=max_out, hard_cap_output=max_out * 2,
        reasoning_effort=effort_arg,
    ):
        if ev["type"] == "usage":
            final = ev
    if final is None:  # no usage frame → the stream produced nothing (terminal fail)
        raise ValueError("selection edit produced no output")
    if final.get("error") and not final["text"]:
        # D-ENGINE-ERRORED-JOB-MARKED-COMPLETED: stream_draft ALWAYS yields a terminal
        # frame, even after an LLMError. An error with NO content is a failure, not a
        # completed empty edit — raise so the worker marks the job failed (mirrors the
        # inline draft-scene handler; partial-content-then-error keeps its text).
        raise ValueError(f"selection edit failed: {final['error']}")

    m = final["metering"]
    # Partial-content-then-error: keep the drafted text but flag it truncated + carry the reason,
    # so a polling FE sees the edit was cut short (the worker path doesn't stream, so this result
    # is the ONLY interruption signal it gets — review MED).
    stream_error = final.get("error")
    out = {
        "text": final["text"], "input_tokens": m.input_tokens,
        "output_tokens": m.output_tokens, "measured": m.measured,
        "finish_reason": m.finish_reason,
        "truncated": m.finish_reason == "length" or bool(stream_error),
        "selection_edit": True,
        "grounding_available": input.get("grounding_available"),
        "reasoning_source": input.get("reasoning"), "reasoning_effort": effort,
        "persisted": False,
    }
    if stream_error:
        out["error"] = stream_error
    return out


async def run_plan_forge_propose(
    llm: LLMClient, *, user_id: str, input: dict[str, Any],
    cancel_check: Callable[[], Awaitable[bool]] | None = None,
) -> dict[str, Any]:
    """LLM ingest→analyze→materialize for PlanForge (async worker op)."""
    from app.engine.plan_forge.llm import ProviderPlanForgeLLM
    from app.engine.plan_forge.propose_llm_async import propose_spec_llm_async

    source = input.get("source_markdown") or ""
    if not source.strip():
        raise ValueError("source_markdown required")
    model_ref = input.get("model_ref") or ""
    if not model_ref:
        raise ValueError("model_ref required")
    io_log: list[dict[str, Any]] = []
    client = ProviderPlanForgeLLM(
        llm,
        user_id=user_id,
        model_source=input.get("model_source", "user_model"),
        model_ref=model_ref,
        io_log=io_log,
        cancel_check=cancel_check,
    )
    spec, analyze, logged = await propose_spec_llm_async(source, client)
    return {
        "status": "completed",
        "novel_system_spec": spec,
        "plan_analyze": analyze,
        "llm_io": logged,
        "source_checksum": spec.get("meta", {}).get("source_checksum"),
    }


async def run_plan_forge_refine(
    llm: LLMClient, *, user_id: str, input: dict[str, Any],
    cancel_check: Callable[[], Awaitable[bool]] | None = None,
) -> dict[str, Any]:
    """LLM surgical refine for PlanForge (async worker op)."""
    from app.engine.plan_forge.llm import ProviderPlanForgeLLM
    from app.engine.plan_forge.propose_llm_async import refine_and_accept_async

    spec = input.get("spec")
    revision = input.get("revision")
    if not isinstance(spec, dict) or not isinstance(revision, dict):
        raise ValueError("spec and revision required")
    model_ref = input.get("model_ref") or ""
    if not model_ref:
        raise ValueError("model_ref required")
    io_log: list[dict[str, Any]] = []
    client = ProviderPlanForgeLLM(
        llm,
        user_id=user_id,
        model_source=input.get("model_source", "user_model"),
        model_ref=model_ref,
        io_log=io_log,
        cancel_check=cancel_check,
    )
    return await refine_and_accept_async(
        spec,
        revision,
        client=client,
        source_checksum=input.get("source_checksum") or spec.get("meta", {}).get("source_checksum", ""),
        analyze=input.get("analyze"),
        package=input.get("package"),
        fidelity_before=input.get("fidelity_before"),
        fidelity_after=input.get("fidelity_after"),
    )


# ── 27 V2-C2 · the `plan_pass` worker op ─────────────────────────────────────────────────────────
async def run_plan_pass(
    pool: asyncpg.Pool, llm: LLMClient, *, user_id: str, input: dict[str, Any],
    cancel_check: Callable[[], Awaitable[bool]] | None = None,
) -> dict[str, Any]:
    """Run ONE compiler pass to its artifact (27 V2-C2).

    This op does the LLM compute and returns the artifact; it writes NOTHING. The finalize hook
    (`_finalize_plan_pass_job`) persists the artifact and records the pass in `pass_state` — the
    same split every other PlanForge op uses, and the reason a crashed worker cannot leave a pass
    half-recorded.

    The two things it must get right:

    **Inputs resolve BY POINTER** (PF-3). We compute the pass's input pointers from the run's
    CURRENT `pass_state`, load exactly those artifacts by id, and fingerprint exactly those ids. So
    the fingerprint we record is the one a later freshness check will recompute — if we resolved
    inputs one way and fingerprinted another, every pass would read as permanently stale.

    **A blocked pass does not run.** `assert_runnable` raises `UpstreamStale` (a ValueError ⇒ a
    BUSINESS error ⇒ the job fails cleanly and is ACKed) rather than burning tokens on a plan whose
    upstream a human has not accepted yet.
    """
    from app.db.repositories.plan_runs import PlanRunsRepo
    from app.services.plan_pass_adapters import PASS_ADAPTERS, PassContext
    from app.services.plan_pass_service import (
        PACKAGE_KIND, PASS_REGISTRY, assert_runnable, fingerprint, input_pointers, package_body,
    )

    book_id = UUID(str(input["book_id"]))
    run_id = UUID(str(input["run_id"]))
    pass_id = str(input["pass_id"])
    if pass_id not in PASS_REGISTRY:
        raise ValueError(f"unknown pass_id: {pass_id}")
    model_ref = input.get("model_ref") or ""
    if not model_ref:
        raise ValueError("model_ref required")

    spec = PASS_REGISTRY[pass_id]
    runs = PlanRunsRepo(pool)
    run = await runs.get_for_book(book_id, run_id)
    if run is None:
        raise ValueError(f"plan run {run_id} not found for book {book_id}")

    # The package is an INPUT (it is what `compile()` produced). A pass that reads it and does not
    # fingerprint it is fresh forever — re-compiling with a different arc or genre would leave
    # `motifs`/`cast` (which have no pass dependencies) pointing at a plan that no longer exists.
    #
    # ALWAYS LOAD IT — even for a pass that does not read it. The package is a property of the RUN,
    # not of the pass being run, and the PF-5 gate below has to recompute the fingerprints of this
    # pass's UPSTREAMS, which may well read it.
    #
    # Loading it only when `spec.reads_package` was a real bug, and only the full seven-pass smoke
    # could find it: `character_arcs` reads_package=False, but it depends on `cast` and `beats`,
    # which both DO. So their freshness was recomputed with `package_artifact_id=None`, their
    # fingerprints could not match what they had recorded, and they read as STALE — the worker
    # refused a pass that the service had just said (HTTP 200) was runnable. The two disagreed
    # because they were answering the question with different inputs.
    package_art = await runs.latest_artifact(book_id, run_id, PACKAGE_KIND)
    if spec.reads_package and package_art is None:
        raise ValueError(
            f"pass '{pass_id}' reads the planning package, but this run has none — compile first",
        )
    package_id = package_art.id if package_art else None

    params = dict(input.get("params") or {})
    force = bool(input.get("force"))
    assert_runnable(run, pass_id, force=force, package_artifact_id=package_id)

    pointers = input_pointers(run, pass_id, package_artifact_id=package_id)
    loaded = await runs.artifacts_by_ids(book_id, run_id, pointers)

    # Resolve each upstream pass's body by ITS artifact pointer, keyed by the PASS that produced it.
    # Keying by KIND would collide: pass 7 re-emits `scene_plan`.
    inputs: dict[str, Any] = {}
    missing: list[str] = []
    for dep in spec.depends_on:
        dep_entry = run.pass_state.get(dep) or {}
        dep_art_id = str(
            dep_entry.get("artifact_id") if isinstance(dep_entry, dict)
            else getattr(dep_entry, "artifact_id", "") or "",
        )
        art = loaded.get(dep_art_id)
        if art is None:
            # Not "empty" — MISSING. `assert_runnable` should already have refused, so reaching
            # here means the pointer names an artifact that is gone (or another book's). Fail
            # loudly: silently running a pass with an absent input produces a plan that looks
            # complete and is built on nothing.
            missing.append(dep)
            continue
        inputs[dep] = art.content
    if missing:
        raise ValueError(
            f"pass '{pass_id}' cannot resolve its input artifact(s): {', '.join(missing)}",
        )

    fp = fingerprint(input_artifact_ids=pointers, params=params)

    # THE ROSTER JOIN (27 PF-8b / H3). The `cast` artifact holds NAMES — the glossary `entity_id`s
    # do not exist until the human has applied the seed proposal (PF-7). So before any pass reads the
    # cast, resolve each member to the id that proposal minted.
    #
    # Without this, `grounded_decompose`'s `cast_index` is EMPTY (it keys on `entity_id`, and there
    # is none), every scene comes back with `present_entity_ids: []`, and the linker writes scene
    # nodes with no cast on them. The live 7-pass smoke showed it plainly — `present=0` on every
    # scene — while the plan looked complete in every other respect. Absent, silently.
    if "cast" in inputs:
        inputs["cast"] = {
            **inputs["cast"],
            "cast": await _resolve_cast_entity_ids(pool, book_id, run, inputs["cast"]),
        }

    retriever = None
    if pass_id == "motifs":
        from app.db.repositories.motif_retrieve import MotifRetriever

        retriever = MotifRetriever(pool)

    ctx = PassContext(
        llm=llm, user_id=user_id, book_id=book_id,
        project_id=UUID(str(input.get("project_id") or run.work_id or book_id)),
        model_source=input.get("model_source", "user_model"), model_ref=model_ref,
        package=package_body(package_art.content) if package_art else {},
        inputs=inputs,
        genre_tags=list(run.genre_tags or []),
        source_language=str(input.get("source_language") or "auto"),
        params=params, retriever=retriever,
        trace_id=input.get("trace_id"), cancel_check=cancel_check,
    )
    body = await PASS_ADAPTERS[pass_id](ctx)

    return {
        "status": "completed",
        "pass_id": pass_id,
        "output_kind": spec.output_kind,
        "artifact": body,
        # Recorded verbatim into `pass_state` by the finalize hook. The fingerprint is over the
        # SAME pointers we just resolved, and the params are stored WITH the pass so a later
        # freshness check recomputes with them (a caller that had to remember them would forget).
        "input_fingerprint": fp,
        "input_artifact_ids": pointers,
        "params": params,
    }


async def _resolve_cast_entity_ids(
    pool: asyncpg.Pool, book_id: UUID, run, cast_artifact: dict[str, Any],
) -> list[dict[str, Any]]:
    """The roster join: cast NAME → glossary `entity_id`, from the APPLIED seed proposal.

    Read from the proposal's `applied_results` rather than asking glossary directly — that is where
    the ids were MINTED, and composition reads the cast through the knowledge-gateway roster, never
    glossary (INV-KAL).

    Degrade-safe and HONEST: a member we cannot resolve keeps its name and gets NO `entity_id`. It
    is then absent from `cast_index`, so pass 6 falls back to `present_entity_names_unresolved` —
    which is exactly the field that exists to say "this character is in the scene and I could not
    tell you which glossary entity they are". Inventing an id would be worse than admitting it.
    """
    from app.db.repositories.plan_bootstrap_proposals import PlanBootstrapProposalsRepo

    members = list(cast_artifact.get("cast") or [])
    if not members:
        return members

    # Union the ids across EVERY applied proposal for this book — not just the one this pass points
    # at. A glossary entity id is a fact about the BOOK, not about the proposal that happened to mint
    # it. Re-run `cast` and the LLM adds one new character: the re-run's proposal contains only the
    # NEW one, and reading it alone would leave every character from the first batch un-resolved —
    # so the scenes would quietly lose the cast that was already correctly seeded.
    try:
        proposals = await PlanBootstrapProposalsRepo(pool).list_active_for_book(book_id)
    except Exception:  # noqa: BLE001 — advisory join; a read failure must not fail the pass
        logger.warning("roster join: could not load the seed proposals", exc_info=True)
        return members

    by_name: dict[str, str] = {}
    for proposal in proposals:
        # Only an APPLIED proposal has minted ids. A pending one is a request, not a fact.
        if proposal.status != "applied":
            continue
        for row in (proposal.applied_results or {}).values():
            if isinstance(row, dict) and row.get("name") and row.get("entity_id"):
                by_name[str(row["name"]).strip().casefold()] = str(row["entity_id"])
    if not by_name:
        # Nothing applied yet ⇒ there ARE no ids. For `cast` itself that is fine (it is a blocking
        # checkpoint the human has not passed); for anything downstream, PF-5 already refused.
        return members

    resolved = 0
    out: list[dict[str, Any]] = []
    for m in members:
        name = str(m.get("name") or "").strip()
        eid = by_name.get(name.casefold())
        if eid:
            resolved += 1
            out.append({**m, "entity_id": eid})
        else:
            out.append(dict(m))
    logger.info(
        "roster join: book=%s resolved %d/%d cast member(s) to glossary entities",
        book_id, resolved, len(members),
    )
    return out
