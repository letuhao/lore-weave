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
from typing import Any
from uuid import UUID

import asyncpg

from app.clients.llm_client import LLMClient
from app.config import settings

__all__ = [
    "UnsupportedOperationError",
    "SUPPORTED_OPERATIONS",
    "run_decompose",
    "run_stitch",
    "run_generate",
]

logger = logging.getLogger("composition.worker.operations")


class UnsupportedOperationError(RuntimeError):
    """The job's operation has no worker handler (a config/enqueue bug — the
    endpoint should only enqueue operations the worker can run)."""


#: worker-op identifiers the worker can run (the sweeper re-drive whitelist). For
#: decompose/stitch this equals the job's ``operation`` column; for generate the
#: ``operation`` is the user's free-form prose op ("draft_scene", …), so the
#: canonical worker-op is carried in ``input['worker_op']`` and matched there too.
SUPPORTED_OPERATIONS = ("decompose_preview", "stitch_chapter", "generate")


async def run_decompose(llm: LLMClient, *, user_id: str, input: dict[str, Any]) -> dict[str, Any]:
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
    )
    return dataclasses.asdict(result)


async def run_stitch(
    pool: asyncpg.Pool, llm: LLMClient, knowledge, *, input: dict[str, Any]
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
    from app.engine.stitch import stitch_chapter
    from app.packer.profile import from_settings

    user_id = input["user_id"]
    project_id = input["project_id"]
    chapter_id = input["chapter_id"]
    jobs_repo = GenerationJobsRepo(pool)
    works = WorksRepo(pool)

    work = await works.get(UUID(user_id), UUID(project_id))
    profile = from_settings(work.settings if work else None)
    drafts = await jobs_repo.chapter_scene_drafts(
        UUID(user_id), UUID(project_id), UUID(chapter_id)
    )
    if not drafts:
        raise ValueError("no completed scene drafts to stitch")

    max_out = input["max_out"]
    reasoning_effort = input.get("reasoning_effort")  # already None when passthrough

    stitched, stitch_finish = await stitch_chapter(
        llm, user_id=user_id, model_source=input["model_source"], model_ref=input["model_ref"],
        scene_drafts=drafts, chapter_intent=input["chapter_intent"], profile=profile,
        max_tokens=max_out, max_input_chars=settings.stitch_max_input_chars,
        reasoning_effort=reasoning_effort,
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
            reasoning_effort=reasoning_effort,
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
    pool: asyncpg.Pool, llm: LLMClient, knowledge, *, input: dict[str, Any]
) -> dict[str, Any]:
    """Run the AUTO per-scene draft (diverge→converge→canon-reflect) from the
    persisted, fully-resolved input. Mirrors the inline ``generate`` auto path
    (engine.py): the endpoint already ran ``pack()`` (bearer retrieval) and stored
    the packed prompt + scene signals in ``input``, so this needs only the
    internal-auth LLM + knowledge (canon-reflect). The result is stored on the job
    (NO book persistence — a per-scene auto draft isn't a chapter artifact; the FE
    accepts it into the editor). The cowrite STREAM path stays inline (a worker
    can't stream)."""
    from app.db.repositories.narrative_thread import NarrativeThreadRepo
    from app.db.repositories.works import WorksRepo
    from app.engine.adaptive_k import adaptive_k
    from app.engine.canon_reflect import run_canon_reflect
    from app.engine.narrative_thread import detect_and_update_threads
    from app.engine.select import select_draft
    from app.packer.profile import from_settings

    user_id = input["user_id"]
    project_id = input["project_id"]
    work = await WorksRepo(pool).get(UUID(user_id), UUID(project_id))
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
            reasoning_effort=effort_arg,
        )
        canon = {"violations": [v.model_dump() for v in reflect.violations],
                 "resolved": reflect.resolved, "iterations": reflect.iterations,
                 "status": reflect.status}
        revise_finish = reflect.revise_finish_reason
    except Exception:  # noqa: BLE001 — canon reflect must NEVER fail the generate (F1).
        logger.warning("generate canon reflect failed (advisory) — keeping winner", exc_info=True)

    # FD-1 narrative_thread S2: best-effort promise-ledger producer (gated per-work).
    if sdict.get("narrative_thread_enabled"):
        try:
            opened_at = input.get("outline_node_id")
            await detect_and_update_threads(
                llm, NarrativeThreadRepo(pool),
                user_id=UUID(user_id), project_id=UUID(project_id),
                scene_text=final_text,
                opened_at_node=UUID(opened_at) if opened_at else None,
                drafter_source=model_source, drafter_ref=model_ref,
                source_language=profile.source_language,
                max_open=settings.narrative_thread_max_open_per_scene,
            )
        except Exception:  # noqa: BLE001 — advisory; must not fail the generate
            logger.warning("narrative_thread S2 producer failed (advisory)", exc_info=True)

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
    }
