"""W8 — motif mining worker entrypoint (Wave-2, P3).

``run_mine_motifs`` is the worker handler behind the Tier-W ``composition_motif_mine``
tool: the confirm effect (``routers/actions.py:_execute_motif_mine``) enqueues a
``mine_motifs`` job; the consumer dispatches HERE. The FROZEN input envelope (stamped
by the confirm effect) is::

    input = {
        "worker_op": "mine_motifs",
        "scope":       "book" | "corpus",
        "book_id":     str | None,     # required when scope == "book"
        "min_support": int | None,     # min occurrences before a beat-pattern is a draft
        "promote_to":  "user" | None,  # where accepted drafts land (default user-tier draft)
        "language":    str | None,     # motif language axis (P1)
    }

and ``user_id`` comes off the job row. The result dict is written to
``generation_job.result`` for the GET /jobs/{id} poll.

The compute (W8): cross-service ``motif_beat`` extraction in knowledge-service →
PrefixSpan over ``event_order``-ordered beat sequences → LLM abstraction → binary
judge → ``status='draft'`` motif rows (``source='mined'``, ``judge_score``,
``mining_support``), embedded NULL (W3 lazily back-fills). All provider calls route
through provider-registry (provider-gateway invariant); no hardcoded model names.

W2-F0 FREEZE: this module is the SOLE worker-owned entrypoint for mining — W8 fills
the body. The worker-dispatch seam (``constants.py`` + ``job_consumer.py``) is frozen
and MUST NOT be re-edited by W8; only this file's body changes.
"""

from __future__ import annotations

from typing import Any

import asyncpg

from app.clients.llm_client import LLMClient

__all__ = ["run_mine_motifs"]


async def run_mine_motifs(
    pool: asyncpg.Pool, llm: LLMClient, knowledge, *, user_id: str, input: dict[str, Any]
) -> dict[str, Any]:
    """Mine recurring motif beat-patterns from the user's own corpus/book → draft
    motifs. See module docstring for the frozen input envelope. Raises ``ValueError``
    (a terminal business error — the job is marked failed cleanly, never an infra
    redeliver loop) until W8 lands the compute."""
    raise ValueError(
        "mine_motifs worker handler not yet implemented "
        "(Wave-2 W8 — tracked D-MOTIF-W8-MINE-IMPL)"
    )
