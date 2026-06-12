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
]

logger = logging.getLogger("composition.worker.operations")


class UnsupportedOperationError(RuntimeError):
    """The job's operation has no worker handler (a config/enqueue bug — the
    endpoint should only enqueue operations the worker can run)."""


#: operations the worker can currently run (gates the endpoint's 202 path too).
SUPPORTED_OPERATIONS = ("decompose_preview", "stitch_chapter")


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
