"""LLM re-arch Phase 3 M5 — video-gen terminal-event consumer.

Consumes ``loreweave:events:llm_job_terminal`` (the durable terminal-event
stream the provider-registry relay XADDs on every job's terminal transition)
under its OWN group ``video-gen-resume``. For each terminal event it looks up
the matching ``video_gen_jobs`` row by ``provider_job_id``; a miss → some other
service's job (LLM/judge/translation share the stream) → ack + ignore. On a
match it fetches the gateway result, downloads the video → MinIO, and CAS-marks
the row done (bill once on the winning transition).

Unified Job Control Plane P1 — the transport (BUSYGROUP-safe group, startup PEL
drain, ``socket_timeout=None`` blocking loop, redis-py-8 idle ``TimeoutError``,
operation pre-filter, bounded retry → poison-ack, sweeper scaffold) now lives in
the shared ``loreweave_jobs.BaseTerminalConsumer``; this module supplies only the
business fold (``complete_job``) + sweeper SQL (``sweep_once``). Unlike M1 there
is no multi-batch resume — a video job is a single terminal, so completion is
one-shot + idempotent via the repo CAS.
"""

from __future__ import annotations

import logging
from uuid import UUID

from loreweave_jobs import BaseTerminalConsumer
from loreweave_llm import Client
from loreweave_llm.models import VideoGenResult

from app.config import settings
from app.db.repository import VideoGenJobsRepo
from app.routers.generate import download_and_store, record_usage

log = logging.getLogger("video-gen.worker.consumer")


class VideoGenTerminalConsumer(BaseTerminalConsumer):
    """video-gen terminal-event consumer on the shared transport scaffold. The
    business fold is the module-level ``complete_job``; the sweeper is ``sweep_once``.
    ``sdk`` is the long-lived internal-auth loreweave_llm Client used for get_job
    (per-call user_id comes from the terminal event's owner_user_id / the row's
    user_id)."""

    group = "video-gen-resume"
    operation = "video_gen"  # drop a foreign op sharing the stream without a DB hit
    consumer_name_prefix = "video-gen"
    retry_prefix = "videogen:resume:retry"

    def __init__(
        self, redis_url: str, pool, sdk: Client, *, consumer_name: str | None = None,
    ) -> None:
        super().__init__(redis_url, consumer_name=consumer_name)
        self._pool = pool
        self._sdk = sdk

    async def handle(self, fields: dict) -> None:
        job_id = fields.get("job_id")
        if not job_id:
            return  # no job id → ack-ignore (the base acks on a normal return)
        owner_user_id = fields.get("owner_user_id") or None
        # The base already applied the operation pre-filter; complete_job stays
        # idempotent for at-least-once redelivery + the sweeper race.
        await complete_job(
            self._pool, self._sdk,
            provider_job_id=job_id, owner_user_id=owner_user_id,
            operation=fields.get("operation"),
        )

    async def sweep_once(self, *, timeout_s: int, batch: int) -> int:
        return await sweep_once(self._pool, self._sdk, timeout_s=timeout_s, batch=batch)


async def complete_job(
    pool, sdk: Client, *, provider_job_id: str, owner_user_id: str | None,
    operation: str | None = None,
) -> str:
    """Fold ONE terminal video-gen job: look up our row, fetch the gateway
    result, download → MinIO, CAS the row done (bill once). Idempotent for
    at-least-once redelivery + the sweeper race.

    ``operation`` is the terminal event's operation field (None from the
    sweeper, which already starts from our own rows): a cheap pre-filter so a
    chat/judge/translation terminal — which all share this stream — is dropped
    WITHOUT a DB round-trip. A missing/None operation falls through to the
    authoritative provider_job_id lookup (back-compat with older events).

    Returns a short outcome tag ('not_ours' | 'already_terminal' | 'completed' |
    'failed' | 'cancelled' | 'no_url'). Raises only on a transient infra fault
    (the caller leaves the event un-acked → redelivered)."""
    if operation is not None and operation != "video_gen":
        return "not_ours"  # another operation on the shared stream — no DB hit
    try:
        pjid = UUID(provider_job_id)
    except (ValueError, TypeError):
        return "not_ours"

    repo = VideoGenJobsRepo(pool)
    row = await repo.get_by_provider_job_id(pjid)
    if row is None:
        return "not_ours"  # another service's job on the shared stream
    if row.status in ("completed", "failed", "cancelled"):
        return "already_terminal"  # idempotent — a redelivery / sweep race

    await repo.mark_running(row.id)
    job = await sdk.get_job(provider_job_id, user_id=owner_user_id or str(row.user_id))

    if job.status == "completed":
        if job.result is None:
            await repo.fail(row.id, status="failed",
                            error={"code": "empty_result", "message": "completed but no result"})
            return "failed"
        result = VideoGenResult.model_validate(job.result)
        if not result.data or not result.data[0].url:
            await repo.fail(row.id, status="failed",
                            error={"code": "no_url", "message": "gateway returned no video URL"})
            return "no_url"
        local_url, size_bytes, content_type = await download_and_store(
            str(row.user_id), result.data[0].url,
        )
        won = await repo.complete(
            row.id, video_url=local_url, size_bytes=size_bytes, content_type=content_type,
        )
        if won:
            req = row.request_json or {}
            await record_usage(
                str(row.user_id), None,
                req.get("model_source", "user_model"), req.get("model_ref", ""),
                len(req.get("prompt", "")),
            )
        return "completed"

    if job.status == "cancelled":
        await repo.fail(row.id, status="cancelled",
                        error={"code": "cancelled", "message": "job cancelled"})
        return "cancelled"

    # failed
    err = (
        {"code": job.error.code, "message": job.error.message}
        if job.error is not None
        else {"code": "failed", "message": "job failed without error body"}
    )
    await repo.fail(row.id, status="failed", error=err)
    return "failed"


async def sweep_once(pool, sdk: Client, *, timeout_s: int, batch: int) -> int:
    """Re-drive rows stuck active past the idle timeout (submit→persist gap, a
    lost terminal event, or a consumer crash). Replays the idempotent
    ``complete_job``; a row whose gateway job isn't terminal yet is left alone
    (slow ≠ stuck). Returns the number re-driven."""
    repo = VideoGenJobsRepo(pool)
    rows = await repo.list_stuck(timeout_secs=timeout_s, batch=batch)
    redriven = 0
    for row in rows:
        if row.provider_job_id is None:
            continue
        try:
            job = await sdk.get_job(str(row.provider_job_id), user_id=str(row.user_id))
        except Exception:  # noqa: BLE001 — transient get_job fault: next row/tick
            continue
        if not job.is_terminal():
            continue  # slow, not stuck
        try:
            await complete_job(
                pool, sdk,
                provider_job_id=str(row.provider_job_id), owner_user_id=str(row.user_id),
            )
            redriven += 1
            log.warning("video-gen sweep: re-drove stranded job id=%s via %s",
                        row.id, row.provider_job_id)
        except Exception:  # noqa: BLE001 — one bad row mustn't stop the sweep
            log.exception("video-gen sweep: re-drive failed id=%s", row.id)
    return redriven
