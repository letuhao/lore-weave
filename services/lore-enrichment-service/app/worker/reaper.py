"""Background reaper (D-COMPOSE-S3-UPLOAD-REAPER + D-COMPOSE-CONTEXT-CORPUS-SCOPE).

A periodic sweep that runs on the ``lore-enrichment-worker`` (alongside the resume
consumer + heartbeat) to garbage-collect the mode-F / mode-C debris that the
request path can leave behind:

  1. **Stale uploads** — an ``enrichment_upload`` row stuck in ``processing`` past a
     service restart (its background extraction task died) is flipped to ``failed``
     so the files branch stops 409-ing on it forever (the author re-uploads).
  2. **Orphan objects** — a MinIO object whose row INSERT never landed (the INSERT
     failed AFTER the object was stored) is deleted, but only once it is older than
     a grace window so an in-flight upload (row INSERT mid-request) is never raced.
  3. **Ephemeral corpora** — compose pastes (mode C) and file ingests (mode F) are
     tagged ``provenance_json.compose_ephemeral`` at ingest; here they are reaped by
     TTL so a project's grounding corpora don't accumulate forever. The curated
     ``/sources`` reference library is untagged and never touched.

Every sweep is BEST-EFFORT and independent: one failing sweep logs + is skipped,
the others still run, and the loop survives to the next interval (this is advisory
cleanup — it must never crash the worker or touch canon, H0).
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID

import asyncpg

from app.config import settings
from app.retrieval.store import SourceCorpusStore
from app.storage.minio_client import delete_object, list_objects

logger = logging.getLogger("lore_enrichment.reaper")

__all__ = [
    "upload_id_from_key",
    "sweep_stale_uploads",
    "sweep_orphan_objects",
    "sweep_ephemeral_corpora",
    "reap_once",
    "reaper_loop",
]


def upload_id_from_key(key: str) -> UUID | None:
    """Parse the upload_id out of a storage key ``{user}/{book}/{upload_id}{ext}``.

    Returns None for a key that doesn't match the shape (a stray object the reaper
    leaves alone rather than guessing). The id is the final path segment's stem
    (strip a single trailing extension)."""
    seg = key.rsplit("/", 1)[-1]
    stem = seg.rsplit(".", 1)[0] if "." in seg else seg
    try:
        return UUID(stem)
    except (ValueError, AttributeError):
        return None


def _count_from_tag(tag: str | None) -> int:
    """asyncpg command tag → affected-row count (e.g. 'UPDATE 3' → 3)."""
    if not tag:
        return 0
    try:
        return int(tag.rsplit(" ", 1)[-1])
    except (ValueError, IndexError):
        return 0


async def sweep_stale_uploads(pool: asyncpg.Pool, *, max_age_s: float) -> int:
    """Fail uploads stuck in ``processing`` older than ``max_age_s`` (their extract
    task died, e.g. a restart). Returns the number failed. No-op when ``max_age_s
    <= 0``."""
    if max_age_s <= 0:
        return 0
    async with pool.acquire() as conn:
        tag = await conn.execute(
            """
            UPDATE enrichment_upload
            SET status='failed',
                error_message='extraction stalled (no result before reaper deadline — re-upload)',
                updated_at=now()
            WHERE status='processing'
              AND created_at < now() - ($1 * interval '1 second')
            """,
            max_age_s,
        )
    n = _count_from_tag(tag)
    if n:
        logger.info("reaper: failed %d stale 'processing' upload(s)", n)
    return n


async def sweep_orphan_objects(pool: asyncpg.Pool, *, grace_s: float, now: datetime | None = None) -> int:
    """Delete MinIO objects whose ``enrichment_upload`` row never landed (INSERT
    failed after the object was stored), older than ``grace_s`` (so an in-flight
    upload is never raced). Returns the number deleted. Best-effort per object.

    ASSUMPTION (review-impl #2): this service's DB OWNS the bucket 1:1 — an object
    with no row in *this* ``enrichment_upload`` is an orphan. That holds in any real
    deployment (one stack → one DB → one bucket). It would NOT hold if a single MinIO
    bucket were shared across stacks backed by SEPARATE Postgres DBs (then this would
    delete the other stack's objects); don't point two distinct lore-enrichment DBs at
    one bucket. The ``grace_s`` window further bounds blast radius to old objects."""
    objects = await list_objects()
    if not objects:
        return 0
    cutoff = (now or datetime.now(timezone.utc)) - timedelta(seconds=grace_s)
    # Candidate orphans: parseable keys older than the grace window.
    candidates: dict[UUID, str] = {}
    for obj in objects:
        if obj.last_modified >= cutoff:
            continue  # too fresh — could be an in-flight upload
        uid = upload_id_from_key(obj.key)
        if uid is not None:
            candidates[uid] = obj.key
    if not candidates:
        return 0
    # Which of those upload_ids actually have a row? Anything missing is an orphan.
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT upload_id FROM enrichment_upload WHERE upload_id = ANY($1::uuid[])",
            list(candidates.keys()),
        )
    have = {r["upload_id"] for r in rows}
    deleted = 0
    for uid, key in candidates.items():
        if uid in have:
            continue
        try:
            await delete_object(key)
            deleted += 1
        except Exception:  # noqa: BLE001 — best-effort; a storage hiccup retries next sweep
            logger.warning("reaper: failed to delete orphan object %s", key, exc_info=True)
    if deleted:
        logger.info("reaper: deleted %d orphan upload object(s)", deleted)
    return deleted


async def sweep_ephemeral_corpora(pool: asyncpg.Pool, *, ttl_s: float) -> int:
    """Reap compose-ephemeral grounding corpora older than ``ttl_s`` (mode-C pastes
    + mode-F file ingests). Returns the number deleted. No-op when ``ttl_s <= 0``."""
    deleted = await SourceCorpusStore(pool).reap_ephemeral_corpora(ttl_seconds=ttl_s)
    if deleted:
        logger.info("reaper: reaped %d ephemeral compose corpus/corpora", len(deleted))
    return len(deleted)


async def reap_once(pool: asyncpg.Pool) -> dict[str, int]:
    """Run all three sweeps once (best-effort each). Returns a counts dict for
    logging/observability. A sweep that raises is logged + recorded as -1 (the
    others still run)."""
    out: dict[str, int] = {}

    async def _run(name: str, coro) -> None:
        try:
            out[name] = await coro
        except Exception:  # noqa: BLE001 — one sweep must never abort the others
            logger.warning("reaper: sweep %s failed", name, exc_info=True)
            out[name] = -1

    await _run("stale_uploads", sweep_stale_uploads(pool, max_age_s=settings.upload_stale_processing_s))
    await _run("orphan_objects", sweep_orphan_objects(pool, grace_s=settings.upload_orphan_grace_s))
    await _run("ephemeral_corpora", sweep_ephemeral_corpora(pool, ttl_s=settings.context_corpus_ttl_s))
    return out


async def reaper_loop(
    pool: asyncpg.Pool,
    *,
    interval_s: float | None = None,
    iterations: int | None = None,
) -> None:
    """Run :func:`reap_once` every ``interval_s`` (default from settings). Runs
    forever unless ``iterations`` is given (tests). Cancel-safe — the caller cancels
    it on shutdown. A failing cycle is already swallowed per-sweep, so the loop
    itself never dies on a transient DB/MinIO blip."""
    period = interval_s if interval_s is not None else settings.reaper_interval_s
    n = 0
    while True:
        await reap_once(pool)
        n += 1
        if iterations is not None and n >= iterations:
            return
        await asyncio.sleep(period)
