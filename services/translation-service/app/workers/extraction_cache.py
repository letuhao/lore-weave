"""Raw-output extraction cache — the EXECUTE ledger (CACHE/M6, architecture §8.1, §2.1).

Records "the LLM produced this parse" per batch so a re-extraction of an UNCHANGED chapter
skips the LLM (don't re-spend tokens). This module is the INTERFACE seam: the physical store
is `extraction_raw_outputs` in translation-service today, but every access goes through
`get_cached_batch`/`put_batch` keyed by `RawCacheKey`, so the deferred re-home to
knowledge-service (`D-EXTRACTION-REHOME-KNOWLEDGE`) is a later impl swap, not a caller change.

Tenancy (INV-9): `owner_user_id` is in the key AND every lookup — cross-tenant cache reuse is
forbidden; `chapter_content_hash` is a WITHIN-tenant idempotency key. The cache is a
best-effort LLM-skip optimization: a read/write failure falls back to a normal LLM call
(never fails extraction), and concurrent misses dedup via `ON CONFLICT DO NOTHING`.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class RawCacheKey:
    """The tenant-scoped EXECUTE-ledger key for one batch's LLM output. `profile_hash` is part
    of the key (§8.1): a changed extraction profile re-maps `batch_idx` to different kinds/attrs,
    so it MUST miss the cache (re-extract) rather than reuse the old profile's parse.

    NOTE (D-CACHE-MODEL-KEY): per design §8.1 the MODEL is deliberately NOT in the key — the
    cache is content-addressed (content+profile+effort determines WHAT to extract). A
    consequence: switching the extraction model and re-running the same chapter reuses the prior
    model's parse (cache hit). If a per-deployment "re-extract on model upgrade" is wanted, add
    `model_ref` to the key OR thread a force-refresh flag — tracked, the model IS stored on the
    row so a buster can compare it."""

    owner_user_id: str
    book_id: str
    chapter_id: str
    content_hash: str
    batch_idx: int
    profile_hash: str = ""
    effort_band: str = "none"
    chunk_idx: int = 0


def effort_band_for(thinking_enabled: bool, reasoning_effort: str | None = None) -> str:
    """Coarse effort band that participates in the cache key — different effort yields a
    different output, so it must NOT collide in the cache. Prefers an explicit graded effort
    (when the worker threads one — D-RE-WORKER-GRADED-EFFORT); else maps the legacy
    thinking_enabled bool (True→medium, False→none)."""
    if reasoning_effort:
        return reasoning_effort
    return "medium" if thinking_enabled else "none"


async def get_cached_batch(pool, key: RawCacheKey) -> dict | None:
    """Return the cached parse for this batch key, or None on miss / any error.

    On hit returns ``{"parsed_entities": list, "finish_reason": str|None,
    "input_tokens": int, "output_tokens": int, "parse_status": str}``. Best-effort: a query
    failure logs + returns None so the caller falls back to a live LLM call."""
    try:
        async with pool.acquire() as db:
            row = await db.fetchrow(
                """SELECT parsed_entities, finish_reason, input_tokens, output_tokens, parse_status
                   FROM extraction_raw_outputs
                   WHERE owner_user_id=$1 AND book_id=$2 AND chapter_id=$3
                     AND chapter_chunk_idx=$4 AND chapter_content_hash=$5
                     AND effort_band=$6 AND batch_idx=$7 AND profile_hash=$8""",
                key.owner_user_id, key.book_id, key.chapter_id, key.chunk_idx,
                key.content_hash, key.effort_band, key.batch_idx, key.profile_hash,
            )
        if row is None:
            return None
        raw = row["parsed_entities"]
        entities = json.loads(raw) if isinstance(raw, str) else (raw or [])
        return {
            "parsed_entities": entities,
            "finish_reason": row["finish_reason"],
            "input_tokens": row["input_tokens"] or 0,
            "output_tokens": row["output_tokens"] or 0,
            "parse_status": row["parse_status"],
        }
    except Exception as exc:  # noqa: BLE001 — cache is best-effort; fall back to a live call
        log.warning("extraction_cache: get failed for chapter %s batch %d (%s) — live call",
                    key.chapter_id, key.batch_idx, exc)
        return None


async def put_batch(
    pool,
    key: RawCacheKey,
    *,
    job_id: str | None,
    kinds_requested: list[str],
    model_source: str,
    model_ref: str | None,
    reasoning_effort: str,
    input_tokens: int,
    output_tokens: int,
    finish_reason: str | None,
    raw_response: str,
    parsed_entities: list,
    parse_status: str = "ok",
) -> None:
    """Idempotently record a batch's LLM output (EXECUTE ledger). `ON CONFLICT DO NOTHING`
    makes a concurrent-miss race / replay a no-op. Best-effort — a write failure logs and is
    swallowed (the entities already flow to writeback; only the LLM-skip optimization is lost)."""
    mref = None
    if model_ref:
        try:
            from uuid import UUID
            mref = UUID(model_ref)
        except (ValueError, TypeError):
            mref = None
    try:
        async with pool.acquire() as db:
            await db.execute(
                """INSERT INTO extraction_raw_outputs
                   (job_id, owner_user_id, book_id, chapter_id, chapter_content_hash,
                    chapter_chunk_idx, batch_idx, kinds_requested, profile_hash, model_source,
                    model_ref, reasoning_effort, effort_band, input_tokens, output_tokens,
                    finish_reason, raw_response, parsed_entities, parse_status)
                   VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19)
                   ON CONFLICT (owner_user_id, book_id, chapter_id, chapter_chunk_idx,
                                chapter_content_hash, effort_band, batch_idx, profile_hash) DO NOTHING""",
                job_id, key.owner_user_id, key.book_id, key.chapter_id, key.content_hash,
                key.chunk_idx, key.batch_idx, kinds_requested, key.profile_hash, model_source,
                mref, reasoning_effort, key.effort_band, input_tokens, output_tokens,
                finish_reason, raw_response, json.dumps(parsed_entities, ensure_ascii=False),
                parse_status,
            )
    except Exception as exc:  # noqa: BLE001 — cache write is best-effort
        log.warning("extraction_cache: put failed for chapter %s batch %d (%s)",
                    key.chapter_id, key.batch_idx, exc)
