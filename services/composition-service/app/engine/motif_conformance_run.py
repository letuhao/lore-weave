"""W5 (Wave-2 wiring) — conformance-run worker entrypoint (§14.4, P4 arc altitude).

``run_conformance_run`` is the worker handler behind the Tier-W
``composition_conformance_run`` tool: the confirm effect
(``routers/actions.py:_execute_conformance_run``) enqueues a ``conformance_run`` job;
the consumer dispatches HERE. The FROZEN input envelope (stamped by the confirm
effect) is::

    input = {
        "worker_op":  "conformance_run",
        "book_id":    str,                  # the Work's book (resolved at confirm)
        "scope":      "chapter" | "arc",
        "chapter_id": str | None,           # required when scope == "chapter"
    }

with ``user_id`` + ``project_id`` off the job row. The result is written to
``generation_job.result`` for the poll.

The compute (W5 Wave-2 — distinct from W5 Wave-1's already-shipped binary scene judge
``engine/motif_conformance.py`` + the trace READ in ``routers/conformance.py``): the
COST-GATED extract-diff. For ``scope='arc'`` it runs the generate→extract flywheel over
the arc's chapters and diffs realized structure vs the ``arc_template`` (thread
progression, pacing, legal succession, promise ledger — §14.4.3). It REUSES the
existing ``engine/motif_conformance.py`` judge functions; this module is only the
worker orchestration. Advisory, never a hard gate (§14.6). All LLM calls route through
provider-registry.

This graduates only after ``D-MOTIF-CONFORMANCE-GOLD-SET`` (calibration) — until then
conformance ships uncalibrated-advisory. W2-F0 FREEZE: SOLE worker-owned entrypoint
for conformance-run — the conformance-wiring WS fills the body; the dispatch seam is
frozen.
"""

from __future__ import annotations

from typing import Any

import asyncpg

from app.clients.llm_client import LLMClient

__all__ = ["run_conformance_run"]


async def run_conformance_run(
    pool: asyncpg.Pool, llm: LLMClient, knowledge, *, user_id: str, project_id: str,
    input: dict[str, Any],
) -> dict[str, Any]:
    """Run the cost-gated chapter/arc conformance extract-diff. See module docstring
    for the frozen input envelope. Raises ``ValueError`` (terminal business error —
    clean job-failed, no redeliver loop) until the conformance-wiring WS lands the
    compute."""
    raise ValueError(
        "conformance_run worker handler not yet implemented "
        "(Wave-2 W5 — tracked D-MOTIF-CONFORMANCE-ENGINE-WIRING)"
    )
