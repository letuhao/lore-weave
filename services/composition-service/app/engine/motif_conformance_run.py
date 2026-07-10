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

import logging
from typing import Any

import asyncpg

from app.clients.llm_client import LLMClient

logger = logging.getLogger(__name__)

__all__ = ["run_conformance_run"]


async def run_conformance_run(
    pool: asyncpg.Pool, llm: LLMClient, knowledge, *, user_id: str, project_id: str,
    input: dict[str, Any], job_id: str | None = None,
) -> dict[str, Any]:
    """Run the cost-gated arc conformance extract-diff (D-W10-ARC-CONFORMANCE-DEEP-JOB).

    For ``scope='arc'`` this is the production home of the DEEP overlay: the synchronous
    ``GET …/conformance?scope=arc&deep&model_ref`` fires ~tag-threads+tag-motifs+causal-edges
    over the whole book — a storm that times out on a GET — so the FE proposes this Tier-W job
    and polls the result. It REUSES the shared ``compute_arc_report`` (the same compute the GET
    runs) with ``deep=True``. ``scope='chapter'`` stays a terminal ``ValueError`` — the cheap
    synchronous GET trace already serves chapter conformance; the per-scene extract-diff is a
    separate unbuilt slice (D-MOTIF-CONFORMANCE-ENGINE-WIRING).

    Raises ``ValueError`` (terminal business error — clean job-failed, no redeliver) on an
    unsupported scope or an unresolvable work/arc. All LLM calls route through provider-registry
    via the passed ``model_ref``/``model_source``."""
    from uuid import UUID

    from app.db.repositories.motif_repo import MotifRepo
    from app.db.repositories.structure import StructureRepo
    from app.db.repositories.works import WorksRepo
    from app.engine.arc_conformance_orchestrate import compute_arc_report
    from app.routers.conformance import ConformanceTraceReader

    scope = input.get("scope")
    if scope != "arc":
        raise ValueError(
            f"conformance_run worker supports scope='arc' only (got {scope!r}); "
            "chapter conformance is the synchronous GET trace "
            "(tracked D-MOTIF-CONFORMANCE-ENGINE-WIRING)"
        )

    # 23-A4/BA4: the arc scope is measured against the DURABLE spec (structure_node), not the
    # template it came from. `arc_id` = structure_node.id; the deep report reads the realized
    # bindings via the first-class motif_application.structure_node_id column (by_structure=True).
    arc_id = input.get("arc_id")
    if not arc_id:
        raise ValueError("conformance_run arc scope requires arc_id (a structure_node id)")

    uid, pid = UUID(user_id), UUID(project_id)
    work = await WorksRepo(pool).get(pid)
    if work is None:
        raise ValueError("conformance_run: work not found")
    node = await StructureRepo(pool).get(UUID(arc_id))
    if node is None or node.book_id != work.book_id:
        raise ValueError("conformance_run: arc not found / not in this book")

    report = await compute_arc_report(
        reader=ConformanceTraceReader(pool), mrepo=MotifRepo(pool), knowledge=knowledge,
        user_id=uid, project_id=pid, book_id=work.book_id, arc=node, by_structure=True,
        deep=True, model_ref=input.get("model_ref"), model_source=input.get("model_source"),
        llm=llm,  # the job runs the deepest signal — the entailment judge (the GET does not)
    )

    # IX-8 — persist the durable, input-pinned snapshot through the ONE seam the sync
    # GET also uses (deep=True here; provenance = this job). BEST-EFFORT: the report is
    # already the job result the poll returns, so a snapshot-write failure is logged,
    # never fails the job (OQ-1 philosophy).
    try:
        from app.clients.book_client import get_book_client
        from app.engine.arc_conformance_orchestrate import persist_conformance_state

        await persist_conformance_state(
            pool=pool, book_client=get_book_client(), book_id=work.book_id, arc=node,
            report=report, deep=True, generation_job_id=job_id)
    except Exception:  # noqa: BLE001 — best-effort snapshot (IX-8); logged, never fatal
        logger.warning(
            "arc_conformance_state persist failed for arc %s", arc_id, exc_info=True)
    return report
