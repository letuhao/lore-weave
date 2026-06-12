"""LLM re-arch Phase 3 M5 — video-gen terminal-event consumer.

Consumes ``loreweave:events:llm_job_terminal`` (the durable terminal-event
stream the provider-registry relay XADDs on every job's terminal transition)
under its OWN group ``video-gen-resume``. For each terminal event it looks up
the matching ``video_gen_jobs`` row by ``provider_job_id``; a miss → some other
service's job (LLM/judge/translation share the stream) → ack + ignore. On a
match it fetches the gateway result, downloads the video → MinIO, and CAS-marks
the row done (bill once on the winning transition).

Mirrors learning-service's ``LLMJudgeConsumer`` for the correctness-critical
Redis bits (blocking XREADGROUP needs ``socket_timeout=None``; BUSYGROUP-safe
group; drain pending on startup; ack on success; bounded retry then ack) + the
stuck-job sweeper. Unlike M1 there is no multi-batch resume — a video job is a
single terminal, so completion is one-shot + idempotent via the repo CAS.
"""

from __future__ import annotations

import asyncio
import logging
import platform
from uuid import UUID

import redis.asyncio as aioredis

from loreweave_llm import Client
from loreweave_llm.models import VideoGenResult

from app.config import settings
from app.db.repository import VideoGenJobsRepo
from app.routers.generate import download_and_store, record_usage

log = logging.getLogger("video-gen.worker.consumer")

STREAM = "loreweave:events:llm_job_terminal"
GROUP_NAME = "video-gen-resume"
MAX_RETRIES = 3
BLOCK_MS = 5000


class VideoGenTerminalConsumer:
    """Redis-Streams consumer; run() as a background task from the worker
    entrypoint. ``sdk`` is the long-lived internal-auth loreweave_llm Client used
    for get_job (per-call user_id comes from the terminal event's
    owner_user_id / the row's user_id)."""

    def __init__(
        self, redis_url: str, pool, sdk: Client, *, consumer_name: str | None = None,
    ) -> None:
        self._redis_url = redis_url
        self._pool = pool
        self._sdk = sdk
        self._consumer_name = consumer_name or f"video-gen-{platform.node()}"
        self._redis: aioredis.Redis | None = None
        self._running = False

    async def _ensure_redis(self) -> aioredis.Redis:
        if self._redis is None:
            self._redis = aioredis.from_url(
                self._redis_url, decode_responses=True, socket_timeout=None,
            )
        return self._redis

    async def _ensure_group(self) -> None:
        r = await self._ensure_redis()
        try:
            # id="$" — new events only. A job in flight at first deploy used the
            # inline path (no row); after creation the group persists + redelivers
            # a crash-window event. The sweeper backstops a missed terminal.
            await r.xgroup_create(STREAM, GROUP_NAME, id="$", mkstream=True)
            log.info("created consumer group %s on %s", GROUP_NAME, STREAM)
        except aioredis.ResponseError as e:
            if "BUSYGROUP" not in str(e):
                raise

    async def run(self) -> None:
        self._running = True
        log.info("video-gen terminal consumer starting (consumer=%s)", self._consumer_name)
        r: aioredis.Redis | None = None
        while self._running:
            try:
                await self._ensure_group()
                r = await self._ensure_redis()
                await self._drain(r, "0")  # unacked from a prior run
                break
            except asyncio.CancelledError:
                await self.close()
                return
            except Exception:
                log.warning("video-gen consumer: Redis not ready, retry in 5s", exc_info=True)
                self._redis = None
                await asyncio.sleep(5)
        if not self._running or r is None:
            await self.close()
            return

        while self._running:
            try:
                results = await r.xreadgroup(
                    GROUP_NAME, self._consumer_name, {STREAM: ">"},
                    count=10, block=BLOCK_MS,
                )
                for _stream, messages in results or []:
                    for msg_id, fields in messages:
                        await self._handle(r, msg_id, fields)
            except asyncio.CancelledError:
                break
            except aioredis.TimeoutError:
                continue  # idle long-poll
            except aioredis.ConnectionError:
                log.warning("redis connection lost; reconnecting in 5s")
                self._redis = None
                await asyncio.sleep(5)
                r = await self._ensure_redis()
            except Exception:
                log.exception("video-gen consumer loop error; retrying in 2s")
                await asyncio.sleep(2)
        await self.close()

    async def _drain(self, r: aioredis.Redis, start_id: str) -> None:
        try:
            results = await r.xreadgroup(
                GROUP_NAME, self._consumer_name, {STREAM: start_id}, count=100,
            )
            for _stream, messages in results or []:
                for msg_id, fields in messages:
                    await self._handle(r, msg_id, fields)
        except Exception:
            log.exception("error draining pending video-gen events")

    async def _handle(self, r: aioredis.Redis, msg_id: str, fields: dict) -> None:
        job_id = fields.get("job_id")
        owner_user_id = fields.get("owner_user_id") or None
        operation = fields.get("operation") or None
        if not job_id:
            await r.xack(STREAM, GROUP_NAME, msg_id)
            return
        try:
            handled = await complete_job(
                self._pool, self._sdk,
                provider_job_id=job_id, owner_user_id=owner_user_id, operation=operation,
            )
            # handled is informational; either way this event is dealt with.
            _ = handled
            await r.xack(STREAM, GROUP_NAME, msg_id)
        except Exception as exc:
            retry_key = f"videogen:resume:retry:{msg_id}"
            count = int(await r.incr(retry_key))
            await r.expire(retry_key, 3600)
            if count >= MAX_RETRIES:
                log.error("video-gen event %s (job=%s) failed %d× — acking to stop "
                          "redelivery: %s", msg_id, job_id, count, exc)
                await r.xack(STREAM, GROUP_NAME, msg_id)
                await r.delete(retry_key)
            else:
                log.warning("video-gen event %s (job=%s) failed (%d/%d): %s",
                            msg_id, job_id, count, MAX_RETRIES, exc)
                # leave unacked → redelivered

    async def run_sweeper(self, *, interval_s: int, timeout_s: int, batch: int) -> None:
        """Long-running periodic stuck-job sweeper. interval_s <= 0 ⇒ disabled.

        Re-drives rows stuck active past the timeout (a lost terminal event /
        consumer crash — a Redis stream gives no post-ACK redelivery). Replays the
        SAME idempotent ``complete_job`` the event path uses, keyed off the row's
        own provider_job_id."""
        if interval_s <= 0:
            log.info("video-gen sweeper disabled (interval<=0)")
            return
        log.info("video-gen sweeper started (interval=%ds timeout=%ds batch=%d)",
                 interval_s, timeout_s, batch)
        while True:
            try:
                n = await sweep_once(self._pool, self._sdk, timeout_s=timeout_s, batch=batch)
                if n:
                    log.info("video-gen sweep: re-drove %d stuck job(s)", n)
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 — one bad tick mustn't kill the loop
                log.exception("video-gen sweeper tick failed")
            await asyncio.sleep(interval_s)

    async def stop(self) -> None:
        self._running = False

    async def close(self) -> None:
        if self._redis is not None:
            await self._redis.aclose()
            self._redis = None


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
