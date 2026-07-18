"""Worker-op constants (leaf module — no app imports, breaks the router/repo ↔
worker import cycle).

``SUPPORTED_OPERATIONS`` is the set of operations the batch worker can run from a
job's persisted ``input`` (the sweeper re-drive whitelist). It is ALSO the
retryability predicate (D-JOBS-P4-RETRY-COMPOSITION): a failed job is
server-reconstructable iff it is worker-drivable — its ``input`` carries the full
bearer-resolved context the worker re-runs from. The inline/streamed cowrite path
packs its prompt live and never persists it, so it is NOT in this set and NOT
retryable server-side (the FE's own re-generate is that surface).

Every worker-bound job carries the canonical worker-op in ``input['worker_op']``
(the server stamps it on the worker path — generate/selection-edit/chapter-generate
AND decompose/stitch). For DISPATCH the worker tolerates a missing ``worker_op`` and
falls back to the ``operation`` column (``worker_op_of``); for RETRYABILITY the
predicate is STRICT — ``input['worker_op']`` only. That strictness is load-bearing:
the inline/streamed path and a few inline fallbacks reuse the same ``operation``
values ("stitch_chapter", or a user-supplied free-form "generate") with only PARTIAL
``input`` (no packed prompt / no resolved context), so an ``operation``-based
predicate would falsely mark them retryable and a retry would re-fail instantly when
the worker reads a missing ``input`` key (/review-impl MED-1).
"""

from __future__ import annotations

from typing import Any

__all__ = ["SUPPORTED_OPERATIONS", "worker_op_of", "is_worker_drivable"]

#: worker-op identifiers the worker can run (== the retryable set).
#: The three Wave-2 motif ops (mine_motifs/analyze_reference/conformance_run) are
#: enqueued TODAY by the Tier-W confirm effects (routers/actions.py) — they are in
#: this set so the dispatch RECOGNIZES them (not ``UnsupportedOperationError``) and
#: they are server-retryable; the compute is owned by the Wave-2 workstreams behind
#: their own engine modules (W8 motif_mine / W9 motif_deconstruct / W5 conformance).
SUPPORTED_OPERATIONS: frozenset[str] = frozenset(
    {"decompose_preview", "plan_pipeline", "stitch_chapter", "generate", "chapter_generate",
     "selection_edit", "mine_motifs", "analyze_reference", "conformance_run", "self_heal_propose",
     "quality_report", "promise_coverage", "plan_forge_propose", "plan_forge_refine",
     # 27 V2-C2 — ONE op runs ANY of the seven compiler passes; which one is `input['pass_id']`.
     # Seven ops would have meant seven dispatch branches drifting apart from one registry.
     "plan_pass"}
)


def worker_op_of(operation: str, input: dict[str, Any] | None) -> str:
    """The canonical worker-op id for DISPATCH: ``input['worker_op']`` when present,
    else the ``operation`` column (tolerant — used by the worker + the retry core's
    guarded-vs-plain routing). For the strict retryability test use
    ``is_worker_drivable`` instead."""
    return (input or {}).get("worker_op") or operation


def is_worker_drivable(operation: str, input: dict[str, Any] | None) -> bool:
    """STRICT retryability predicate: True iff this job was dispatched to the batch
    worker with a full, persisted ``input`` — i.e. the server stamped a recognized
    ``input['worker_op']``. Deliberately does NOT fall back to the ``operation``
    column: an inline/streamed job (or a user-supplied free-form ``operation`` that
    happens to collide with a worker-op name) carries only partial input and is NOT
    server-reconstructable (/review-impl MED-1)."""
    return (input or {}).get("worker_op") in SUPPORTED_OPERATIONS
