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


async def purge_stale_raw_outputs(
    pool,
    *,
    keep: int = 3,
    owner_user_id: str | None = None,
    book_id: str | None = None,
    chapter_id: str | None = None,
    store=None,
) -> int:
    """Retention (CACHE/M6, architecture §8.1): keep the latest `keep` content-hash
    GENERATIONS per chapter and purge older ones. As a chapter is edited, each new
    `chapter_content_hash` mints a fresh generation (a set of rows, one per window×batch);
    older generations will never be hit again (a cache lookup is content-addressed on the
    CURRENT text), so they are dead weight. This keeps cache growth bounded by edit-history
    depth, not edit COUNT.

    A "generation" is one `chapter_content_hash` for a chapter; its recency is the MAX
    `created_at` across its rows. The retention unit is **(owner, book, chapter)** — every
    `effort_band`/`profile_hash` variant of a KEPT content_hash survives (they share the
    kept hash); every variant of a PURGED content_hash goes. So this is literally "keep the
    latest K versions of the chapter's text", regardless of how many effort/profile combos
    were cached against each version. The CURRENT text is always the most-recently-written
    generation ⇒ rank 1 ⇒ never purged.

    `DENSE_RANK` (not `ROW_NUMBER`) so generations that tie on recency share a rank — a
    conservative keep (never purges a generation tied with a kept one). Optional filters
    scope the sweep to one tenant / book / chapter (a targeted compaction); unfiltered =
    the global retention job. Returns the number of rows deleted. Tenancy (INV-9): the
    partition is always keyed by `owner_user_id`, so one tenant's generations never count
    against another's keep-window. Best-effort — a failure logs and returns 0 (retention is
    an optimization; a transient failure must never surface as a job error).

    When a `store` is given (D-RAWCACHE-MINIO-OFFLOAD), any purged row whose `raw_response`
    was cold-archived has its object deleted too, so a purge never orphans a blob. Blob
    deletes are best-effort (a leaked object is harmless), and run AFTER the DB commit."""
    if keep < 1:
        keep = 1
    filters = ["TRUE"]
    params: list = [keep]
    if owner_user_id is not None:
        params.append(owner_user_id)
        filters.append(f"owner_user_id = ${len(params)}")
    if book_id is not None:
        params.append(book_id)
        filters.append(f"book_id = ${len(params)}")
    if chapter_id is not None:
        params.append(chapter_id)
        filters.append(f"chapter_id = ${len(params)}")
    where = " AND ".join(filters)
    # $1 is the keep window; the optional scope predicates ($2..) appear in BOTH the
    # generation CTE and the DELETE's USING-join so the same scoped subset is ranked
    # and purged. The predicate text is built from FIXED column names (never user input),
    # so the f-string is injection-safe; all VALUES are bound params.
    sql = f"""
        WITH gens AS (
            SELECT owner_user_id, book_id, chapter_id, chapter_content_hash,
                   MAX(created_at) AS max_created
            FROM extraction_raw_outputs
            WHERE {where}
            GROUP BY owner_user_id, book_id, chapter_id, chapter_content_hash
        ),
        ranked AS (
            SELECT owner_user_id, book_id, chapter_id, chapter_content_hash,
                   DENSE_RANK() OVER (
                       PARTITION BY owner_user_id, book_id, chapter_id
                       ORDER BY max_created DESC
                   ) AS gen_rank
            FROM gens
        )
        DELETE FROM extraction_raw_outputs ro
        USING ranked r
        WHERE ro.owner_user_id = r.owner_user_id
          AND ro.book_id = r.book_id
          AND ro.chapter_id = r.chapter_id
          AND ro.chapter_content_hash = r.chapter_content_hash
          AND r.gen_rank > $1
        RETURNING ro.raw_response_uri
    """
    try:
        async with pool.acquire() as db:
            rows = await db.fetch(sql, *params)
        deleted = len(rows)
        if deleted:
            log.info("extraction_cache: retention purged %d stale raw-output row(s) "
                     "(keep=%d, owner=%s book=%s chapter=%s)",
                     deleted, keep, owner_user_id, book_id, chapter_id)
        # Best-effort blob cleanup AFTER the DB commit, so a purged row never orphans its
        # cold-archived body. A delete failure is logged inside the store (harmless leak).
        if store is not None:
            for r in rows:
                uri = r["raw_response_uri"]
                if uri:
                    await store.delete(uri)
        return deleted
    except Exception as exc:  # noqa: BLE001 — retention is best-effort
        log.warning("extraction_cache: retention purge failed (%s)", exc)
        return 0


async def offload_raw_responses(
    pool,
    store,
    *,
    older_than_days: int = 7,
    limit: int = 500,
    owner_user_id: str | None = None,
    book_id: str | None = None,
) -> dict:
    """Cold-archive the bulky `raw_response` of rows older than `older_than_days` to object
    storage, then NULL the DB column (D-RAWCACHE-MINIO-OFFLOAD). raw_response is a verbatim
    debug/provenance artifact never needed for replay (which uses `parsed_entities`), so
    offloading it is transparent to the cache while shrinking the hot table.

    Per-row best-effort: a row is archived in its OWN step — write the blob, then a GUARDED
    UPDATE (`WHERE id=$ AND raw_response_uri IS NULL`) that flips the row to offloaded only if
    nothing else claimed it meanwhile. A write/update failure skips that row (its body stays
    in the DB; a later sweep retries) and never aborts the batch. The object key is
    tenant-prefixed (INV-9): ``raw/{owner}/{id}``. Returns
    ``{"offloaded": n, "bytes": total, "scanned": m}``. No-op (offloaded=0) when `store` is
    None (MinIO unconfigured)."""
    if store is None:
        return {"offloaded": 0, "bytes": 0, "scanned": 0, "disabled": True}
    if limit < 1:
        limit = 1
    filters = ["raw_response <> ''", "raw_response_uri IS NULL",
               "created_at < now() - make_interval(days => $1)"]
    params: list = [int(older_than_days)]
    if owner_user_id is not None:
        params.append(owner_user_id)
        filters.append(f"owner_user_id = ${len(params)}")
    if book_id is not None:
        params.append(book_id)
        filters.append(f"book_id = ${len(params)}")
    params.append(limit)
    where = " AND ".join(filters)
    # Column names are fixed literals (never user input) → injection-safe; values are bound.
    select_sql = (f"SELECT id, owner_user_id, raw_response FROM extraction_raw_outputs "
                  f"WHERE {where} ORDER BY created_at LIMIT ${len(params)}")
    try:
        async with pool.acquire() as db:
            rows = await db.fetch(select_sql, *params)
    except Exception as exc:  # noqa: BLE001 — offload is an optional maintenance sweep
        log.warning("extraction_cache: offload scan failed (%s)", exc)
        return {"offloaded": 0, "bytes": 0, "scanned": 0}

    offloaded = 0
    total_bytes = 0
    for row in rows:
        body = row["raw_response"] or ""
        if not body:
            continue
        data = body.encode("utf-8")
        key = f"raw/{row['owner_user_id']}/{row['id']}"
        try:
            uri = await store.put(key, data)
        except Exception as exc:  # noqa: BLE001 — leave the row's body in the DB; retry later
            log.warning("extraction_cache: offload put failed for row %s (%s)", row["id"], exc)
            continue
        try:
            async with pool.acquire() as db:
                # Guard on raw_response_uri IS NULL so a concurrent sweep can't double-flip.
                res = await db.execute(
                    "UPDATE extraction_raw_outputs SET raw_response='', raw_response_uri=$2 "
                    "WHERE id=$1 AND raw_response_uri IS NULL", row["id"], uri)
            if res.split()[-1] == "0":
                # Another sweep already marked this row. The object key is DETERMINISTIC
                # (raw/{owner}/{id}), so the blob we just wrote is byte-identical to and
                # AT THE SAME KEY AS the one the winning sweep's pointer references — we must
                # NOT delete it (that would orphan the live pointer = data loss). Just skip.
                continue
        except Exception as exc:  # noqa: BLE001
            # The blob is written at the row's deterministic key; leave it (the next sweep
            # re-marks this still-NULL row and re-uploads the same key). Deleting here risks
            # removing a blob a concurrent winner already pointed at.
            log.warning("extraction_cache: offload mark failed for row %s (%s)", row["id"], exc)
            continue
        offloaded += 1
        total_bytes += len(data)
    if offloaded:
        log.info("extraction_cache: offloaded %d raw-output bod(ies) (%d bytes) to object store",
                 offloaded, total_bytes)
    return {"offloaded": offloaded, "bytes": total_bytes, "scanned": len(rows)}


async def fetch_raw_response(pool, store, row_id: str) -> str | None:
    """Read a row's verbatim raw_response, transparently fetching from cold storage if it was
    offloaded (D-RAWCACHE-MINIO-OFFLOAD). Returns the inline body if present, else the archived
    object's text, else None (row gone / object missing / store unavailable). For debug/audit
    only — replay never calls this."""
    try:
        async with pool.acquire() as db:
            row = await db.fetchrow(
                "SELECT raw_response, raw_response_uri FROM extraction_raw_outputs WHERE id=$1",
                row_id)
    except Exception as exc:  # noqa: BLE001
        log.warning("extraction_cache: fetch_raw_response lookup failed for %s (%s)", row_id, exc)
        return None
    if row is None:
        return None
    if row["raw_response"]:
        return row["raw_response"]
    uri = row["raw_response_uri"]
    if not uri or store is None:
        return None
    data = await store.get(uri)
    return data.decode("utf-8") if data is not None else None
