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
from typing import Any

from app.clients.llm_client import LLMClient

__all__ = ["UnsupportedOperationError", "SUPPORTED_OPERATIONS", "run_decompose"]


class UnsupportedOperationError(RuntimeError):
    """The job's operation has no worker handler (a config/enqueue bug — the
    endpoint should only enqueue operations the worker can run)."""


#: operations the worker can currently run (gates the endpoint's 202 path too).
SUPPORTED_OPERATIONS = ("decompose_preview",)


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
