"""Saga driver — stateless reconcile loop (S1).

Every tick, for each ACTIVE campaign:
  1. load the per-chapter projection (the single source of truth — decision J);
  2. ask `gating.next_dispatches` what to run (mode-aware);
  3. mark attempt-exhausted stages terminally failed;
  4. issue ONE batched downstream job per stage (the existing APIs are batch-
     oriented: translation takes a chapter_ids list, knowledge starts a job over
     a scope) and mark each claimed row `dispatched`;
  5. flip the campaign to `completed` when every in-scope stage is settled;
  6. honour `cancelling` (stop dispatching, let in-flight drain, → `cancelled`).

Stateless by construction: nothing is held in memory between ticks — a restart
re-derives everything from `campaign_chapters`, so the loop is crash-resumable
(decision D). Per-chapter completion arrives asynchronously via the projection
consumer (`knowledge.chapter_extracted`, `chapter.translated`).

Reliability hardening (rate-limit governor, circuit-breaker, budget pause, paced
fairness, stuck-`dispatched` timeout reconcile) is **S3** — S1's only pacing is
the gate's bounded in-flight window.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from uuid import UUID, uuid4

import asyncpg

from .. import repositories as repo
from ..clients.dispatch_clients import (
    DispatchError,
    KnowledgeDispatchClient,
    TranslationDispatchClient,
)
from . import gating

logger = logging.getLogger(__name__)


@dataclass
class DispatchClients:
    translation: TranslationDispatchClient
    knowledge: KnowledgeDispatchClient


async def process_campaign(
    pool: asyncpg.Pool,
    clients: DispatchClients,
    campaign: asyncpg.Record,
    *,
    max_attempts: int,
    max_inflight: int,
) -> None:
    """Drive one campaign one tick. Swallows per-campaign errors at the loop
    boundary (a single sick campaign must not stall the others)."""
    campaign_id: UUID = campaign["campaign_id"]
    status: str = campaign["status"]
    stages: list[str] = list(campaign["stages"])

    states = await repo.load_chapter_states(pool, campaign_id)

    # ── cancellation (S3c-2): ACTIVELY cancel in-flight jobs, then finalize ──
    # Propagate cancel to the downstream jobs (best-effort), terminalize the
    # still-dispatched stages (cancelled jobs won't emit completion events, so
    # waiting for a passive drain would hang forever), then finalize. A genuine
    # completion that raced in before cancel already flipped its row to `done`.
    if status == "cancelling":
        await _propagate_cancel(pool, clients, campaign)
        await repo.mark_dispatched_stages_cancelled(pool, campaign_id)
        await repo.set_campaign_status(
            pool, campaign_id, "cancelled", set_finished=True
        )
        logger.info("campaign %s cancelled (propagated + finalized)", campaign_id)
        return

    # ── completion ──────────────────────────────────────────────────────────
    if gating.is_complete(chapters=states, stages=stages, max_attempts=max_attempts):
        await repo.set_campaign_status(
            pool, campaign_id, "completed", set_finished=True
        )
        logger.info("campaign %s completed", campaign_id)
        return

    # Enforce the per-campaign in-flight ceiling ACROSS ticks (not just per tick):
    # the fan-out budget this tick is the ceiling minus what's already dispatched.
    # Prevents a 4000-chapter campaign from dumping everything over a few ticks
    # (S3 replaces this with the real per-provider governor + paced fairness).
    inflight = await repo.count_inflight(pool, campaign_id)
    budget = max(0, max_inflight - inflight) if max_inflight >= 0 else -1
    if budget == 0:
        return  # at ceiling — wait for in-flight to drain (events advance them)

    result = gating.next_dispatches(
        gating_mode=campaign["gating_mode"],
        chapters=states,
        stages=stages,
        max_attempts=max_attempts,
        max_inflight=budget,
    )

    # Attempt-exhausted stages → terminal failed (no more dispatch).
    for f in result.exhausted:
        await repo.mark_stage_failed(
            pool, campaign_id, f.chapter_id, f.stage, "attempts exhausted"
        )

    knowledge_ch = [d.chapter_id for d in result.dispatches if d.stage == "knowledge"]
    translation_ch = [d.chapter_id for d in result.dispatches if d.stage == "translation"]

    user_id = str(campaign["owner_user_id"])
    book_id = str(campaign["book_id"])

    # CLAIM-FIRST ordering (double-spend guard): flip the rows to `dispatched`
    # BEFORE the HTTP job-create, then release to `failed` if the call errors. A
    # crash between claim and dispatch leaves a chapter STUCK (re-driven by the S3
    # stuck-timeout reconcile) rather than re-dispatched next tick = double-spent.
    # The per-row `pending|failed → dispatched` guard in mark_stage_dispatched
    # also makes a concurrent reconcile a no-op for an already-claimed row.

    # ── knowledge: one extraction job covering the campaign's project ───────
    if knowledge_ch:
        project_id = campaign["knowledge_project_id"]
        if project_id is None:
            for cid in knowledge_ch:
                await repo.mark_stage_failed(
                    pool, campaign_id, cid, "knowledge",
                    "no knowledge_project_id configured",
                )
        else:
            for cid in knowledge_ch:
                await repo.mark_stage_dispatched(pool, campaign_id, cid, "knowledge")
            try:
                kn_job_id = await clients.knowledge.dispatch_extraction(
                    project_id=str(project_id),
                    user_id=user_id,
                    scope="chapters",
                    chapter_from=campaign["chapter_from"],
                    chapter_to=campaign["chapter_to"],
                    model_source=campaign["knowledge_model_source"],
                    model_ref=(
                        str(campaign["knowledge_model_ref"])
                        if campaign["knowledge_model_ref"] else None
                    ),
                    campaign_id=str(campaign_id),  # S4a: cost attribution
                )
                if kn_job_id:  # S3c-2: record for cancel propagation
                    await repo.set_dispatched_job_id(
                        pool, campaign_id, knowledge_ch, "knowledge", kn_job_id
                    )
            except DispatchError as exc:
                logger.warning("campaign %s knowledge dispatch failed: %s", campaign_id, exc)
                for cid in knowledge_ch:
                    await repo.mark_stage_failed(
                        pool, campaign_id, cid, "knowledge", str(exc)
                    )

    # ── translation: one job over the eligible chapter batch ────────────────
    if translation_ch:
        for cid in translation_ch:
            await repo.mark_stage_dispatched(pool, campaign_id, cid, "translation")
        try:
            tr_job_id = await clients.translation.dispatch_job(
                user_id=user_id,
                book_id=book_id,
                chapter_ids=translation_ch,
                target_language=campaign["target_language"],
                model_source=campaign["translation_model_source"],
                model_ref=(
                    str(campaign["translation_model_ref"])
                    if campaign["translation_model_ref"] else None
                ),
                campaign_id=str(campaign_id),  # S4a: cost attribution
                verifier_model_source=campaign["verifier_model_source"],  # S5b
                verifier_model_ref=(
                    str(campaign["verifier_model_ref"])
                    if campaign["verifier_model_ref"] else None
                ),
                eval_judge_model_source=campaign["eval_judge_model_source"],  # S5b-eval
                eval_judge_model_ref=(
                    str(campaign["eval_judge_model_ref"])
                    if campaign["eval_judge_model_ref"] else None
                ),
            )
            if tr_job_id:  # S3c-2: record for cancel propagation
                await repo.set_dispatched_job_id(
                    pool, campaign_id, translation_ch, "translation", tr_job_id
                )
        except DispatchError as exc:
            logger.warning("campaign %s translation dispatch failed: %s", campaign_id, exc)
            for cid in translation_ch:
                await repo.mark_stage_failed(
                    pool, campaign_id, cid, "translation", str(exc)
                )


async def _propagate_cancel(
    pool: asyncpg.Pool, clients: DispatchClients, campaign: asyncpg.Record,
) -> None:
    """S3c-2: cancel the campaign's in-flight downstream jobs. Best-effort — a
    cancel failure must not block finalization (the worker settles on its own;
    we terminalize the projection regardless). Translation is cancelled per
    distinct in-flight job_id; knowledge by the project's active extraction."""
    campaign_id: UUID = campaign["campaign_id"]
    user_id = str(campaign["owner_user_id"])

    for jid in await repo.inflight_translation_job_ids(pool, campaign_id):
        try:
            await clients.translation.cancel_job(user_id=user_id, job_id=str(jid))
        except DispatchError as exc:
            logger.warning("campaign %s translation cancel %s failed: %s", campaign_id, jid, exc)

    project_id = campaign["knowledge_project_id"]
    if project_id is not None and await repo.has_inflight_knowledge(pool, campaign_id):
        try:
            await clients.knowledge.cancel_extraction(user_id=user_id, project_id=str(project_id))
        except DispatchError as exc:
            logger.warning("campaign %s knowledge cancel failed: %s", campaign_id, exc)


async def reconcile_once(
    pool: asyncpg.Pool,
    clients: DispatchClients,
    *,
    driver_id: str,
    max_attempts: int,
    max_inflight: int,
    lease_seconds: int = 60,
    claim_limit: int = 100,
) -> None:
    """One pass over the active campaigns THIS driver claims (HA, S3c). The lease
    (`lease_seconds`) must exceed how long a tick spends per campaign so a peer
    replica doesn't re-claim a campaign mid-process; the owner renews its own
    leases each tick via `driver_id`. `paused` campaigns are not claimed → new
    dispatch stops while in-flight work drains."""
    campaigns = await repo.claim_active_campaigns(
        pool, driver_id=driver_id, lease_seconds=lease_seconds, limit=claim_limit,
    )
    for c in campaigns:
        try:
            await process_campaign(
                pool, clients, c,
                max_attempts=max_attempts, max_inflight=max_inflight,
            )
        except Exception:
            logger.exception("driver: error processing campaign %s", c["campaign_id"])


class SagaDriver:
    """Background reconcile loop; run() as a lifespan task."""

    def __init__(
        self,
        pool: asyncpg.Pool,
        clients: DispatchClients,
        *,
        tick_seconds: float,
        max_attempts: int,
        max_inflight: int,
    ) -> None:
        self._pool = pool
        self._clients = clients
        self._tick = tick_seconds
        self._max_attempts = max_attempts
        self._max_inflight = max_inflight
        # Unique per process → owns its leases (renew own, exclude peers). HA-safe.
        self._driver_id = uuid4().hex
        # Lease must outlast a tick so a campaign mid-process isn't re-claimed by
        # a peer; the owner renews it every tick.
        self._lease_seconds = max(int(tick_seconds * 6), 30)
        self._running = False

    async def run(self) -> None:
        self._running = True
        logger.info("saga driver started (tick=%ss, id=%s)", self._tick, self._driver_id)
        while self._running:
            try:
                await reconcile_once(
                    self._pool, self._clients,
                    driver_id=self._driver_id,
                    max_attempts=self._max_attempts,
                    max_inflight=self._max_inflight,
                    lease_seconds=self._lease_seconds,
                )
            except asyncio.CancelledError:
                logger.info("saga driver cancelled")
                break
            except Exception:
                logger.exception("saga driver tick error")
            await asyncio.sleep(self._tick)

    async def stop(self) -> None:
        self._running = False
