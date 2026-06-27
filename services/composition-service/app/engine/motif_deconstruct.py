"""W9 — import/deconstruct worker entrypoint (Wave-2, P4, the 拆文 mode).

``run_analyze_reference`` is the worker handler behind the Tier-W
``composition_arc_import_analyze`` tool: the confirm effect
(``routers/actions.py:_execute_arc_import``) re-checks import_source ownership, then
enqueues an ``analyze_reference`` job; the consumer dispatches HERE. The FROZEN input
envelope (stamped by the confirm effect) is::

    input = {
        "worker_op":        "analyze_reference",
        "import_source_id": str,          # the per-user import_source row (ownership re-checked at confirm)
        "use_web":          bool | None,  # augment with web-search arc boundaries for known works
        "arc_hint":         str | None,   # optional author hint to anchor segmentation
    }

and ``user_id`` comes off the job row. The result is written to
``generation_job.result`` for the poll.

The compute (W9): ride the P1/P2/P3 map-reduce extraction rails (§12.4) — chunk the
imported text → ``motif_beat`` map extract per chunk → arc-reduce (semantic
segmentation, web-anchored for known works) → a proposed ``arc_template``
(``source='imported'``, ``status='draft'``) + member motifs (``imported_derived=true``,
B-3 taint). The deconstruct MUST abstract proper nouns / verbatim phrasing into role
slots + generic beats (§12.6 copyright guardrail); ``examples[]`` on an imported-derived
motif is author-written/synthetic, never copied source prose. All LLM/embed calls
route through provider-registry; no hardcoded model names.

W2-F0 FREEZE: SOLE worker-owned entrypoint for import — W9 fills the body. The
worker-dispatch seam is frozen; only this file's body changes.
"""

from __future__ import annotations

from typing import Any

import asyncpg

from app.clients.llm_client import LLMClient

__all__ = ["run_analyze_reference"]


async def run_analyze_reference(
    pool: asyncpg.Pool, llm: LLMClient, *, user_id: str, input: dict[str, Any]
) -> dict[str, Any]:
    """Deconstruct an imported reference work into an abstract arc_template + member
    motifs. See module docstring for the frozen input envelope. Raises ``ValueError``
    (terminal business error — clean job-failed, no redeliver loop) until W9 lands
    the compute."""
    raise ValueError(
        "analyze_reference worker handler not yet implemented "
        "(Wave-2 W9 — tracked D-MOTIF-W9-IMPORT-IMPL)"
    )
