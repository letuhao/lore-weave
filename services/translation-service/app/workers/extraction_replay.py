"""Replay a chapter's CACHED extraction parse into glossary at $0 LLM (CACHE/M6 slice 3,
architecture §8.1).

The EXECUTE ledger (`extraction_raw_outputs`) records "the LLM produced this parse" per
batch. Replay re-drives the glossary WRITEBACK from that cached parse WITHOUT calling an LLM
— the recovery path when the original writeback failed (glossary was down), the glossary
entities were cleared, or a re-materialization is wanted, all without re-spending tokens.

Faithful-by-construction safety: replay re-fetches the chapter and only proceeds when the
CURRENT text still hashes to the cached generation's `chapter_content_hash` AND the source
job's `extraction_profile` still hashes to the cached `profile_hash`. With both matching, the
cached parse is exactly reproducible against live state — its evidence offsets (re-stamped
here against the current text), chapter links, and attribute-actions are all valid. A drift in
either → no faithful replay (the caller runs a fresh extraction instead).

Gating (the endpoint enforces it): grant — the caller must hold EDIT on the book; tenancy
(INV-9) — replay reads ONLY the caller's own cache rows (`owner_user_id = caller`) and writes
attributed to the caller, so it never reuses another tenant's cache. confirm — a write is only
performed when `confirm=True`; otherwise a dry-run PREVIEW (no glossary call) is returned.
"""
from __future__ import annotations

import hashlib
import json
import logging

import httpx

from ..config import settings
from .extraction_preprocessor import prepare_chapter_text
from .extraction_provenance import stamp_entity_provenance
from .glossary_client import post_extracted_entities

log = logging.getLogger(__name__)

_CHAPTER_TIMEOUT = httpx.Timeout(connect=10, read=30, write=30, pool=5)


async def _fetch_chapter(book_id: str, chapter_id: str) -> dict | None:
    """GET the chapter from book-service (text + sort_order + original_language). None on
    any non-200 / transport failure."""
    try:
        async with httpx.AsyncClient(timeout=_CHAPTER_TIMEOUT) as client:
            r = await client.get(
                f"{settings.book_service_internal_url}"
                f"/internal/books/{book_id}/chapters/{chapter_id}",
                headers={"X-Internal-Token": settings.internal_service_token},
            )
        if r.status_code != 200:
            log.warning("replay: book-service returned %d for chapter %s", r.status_code, chapter_id)
            return None
        return r.json()
    except Exception as exc:  # noqa: BLE001
        log.warning("replay: chapter fetch failed for %s (%s)", chapter_id, exc)
        return None


async def replay_chapter_from_cache(
    pool,
    *,
    caller_user_id: str,
    book_id: str,
    chapter_id: str,
    confirm: bool = False,
    use_authored_strategy: bool = False,
) -> dict:
    """Re-apply a chapter's cached parse to glossary at $0 LLM (caller-owns-cache, INV-9).

    Returns a dict whose ``status`` is one of:
      - ``"no_cache"``   — no cached parse for the chapter's CURRENT text (run extraction).
      - ``"profile_unavailable"`` — the source job's profile is gone / drifted, so the
        attribute-actions can't be faithfully reconstructed (run extraction).
      - ``"empty"``      — the cached parse held no entities (nothing to write).
      - ``"preview"``    — dry-run (``confirm=False``): what WOULD be written; no glossary call.
      - ``"replayed"``   — entities re-applied via the idempotent whole-chapter writeback.
      - ``"writeback_failed"`` — reconstruction succeeded but the glossary write failed (retry).
    """
    chapter = await _fetch_chapter(book_id, chapter_id)
    if chapter is None:
        return {"status": "no_cache", "reason": "chapter_unavailable"}
    chapter_text = prepare_chapter_text(chapter)
    if not chapter_text.strip():
        return {"status": "empty", "reason": "chapter_has_no_text"}
    content_hash = hashlib.sha256(chapter_text.encode("utf-8")).hexdigest()
    source_language = chapter.get("original_language") or "zh"
    chapter_index = int(chapter.get("sort_order") or 0)
    chapter_title = chapter.get("title") or ""

    async with pool.acquire() as db:
        # Pick the latest cached GENERATION for the CURRENT text (caller's own cache only).
        head = await db.fetchrow(
            """SELECT effort_band, profile_hash, job_id
               FROM extraction_raw_outputs
               WHERE owner_user_id=$1 AND book_id=$2 AND chapter_id=$3 AND chapter_content_hash=$4
               ORDER BY created_at DESC LIMIT 1""",
            caller_user_id, book_id, chapter_id, content_hash,
        )
        if head is None:
            return {"status": "no_cache", "reason": "no_parse_for_current_text"}
        effort_band, profile_hash, job_id = head["effort_band"], head["profile_hash"], head["job_id"]

        # Gather every batch row of that (content, effort, profile) generation, ordered.
        rows = await db.fetch(
            """SELECT chapter_chunk_idx, batch_idx, parsed_entities, kinds_requested
               FROM extraction_raw_outputs
               WHERE owner_user_id=$1 AND book_id=$2 AND chapter_id=$3 AND chapter_content_hash=$4
                 AND effort_band=$5 AND profile_hash=$6
               ORDER BY chapter_chunk_idx, batch_idx""",
            caller_user_id, book_id, chapter_id, content_hash, effort_band, profile_hash,
        )

        # Recover the EXACT attribute-actions from the source job (the SSOT for what produced
        # these rows); verify its hash still matches the cached profile_hash. The job row is
        # the only faithful source of the kind→attr→action map (the cache stores only its
        # hash), so a missing/drifted job means we can't reconstruct it → refuse.
        extraction_profile = None
        if job_id is not None:
            prof_raw = await db.fetchval(
                "SELECT extraction_profile FROM extraction_jobs WHERE job_id=$1", job_id)
            if prof_raw is not None:
                extraction_profile = json.loads(prof_raw) if isinstance(prof_raw, str) else prof_raw

    if extraction_profile is None:
        return {"status": "profile_unavailable", "reason": "source_job_gone"}
    recomputed = hashlib.sha256(
        json.dumps(extraction_profile, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    if recomputed != profile_hash:
        return {"status": "profile_unavailable", "reason": "profile_drifted"}

    # Reassemble entities across windows/batches, re-attach this chapter's link (the link is
    # per-run, never cached — §8.1), and merge duplicates surfaced in multiple windows.
    assembled: list[dict] = []
    all_kinds: set[str] = set()
    for row in rows:
        raw = row["parsed_entities"]
        ents = json.loads(raw) if isinstance(raw, str) else (raw or [])
        for k in (row["kinds_requested"] or []):
            all_kinds.add(k)
        for ent in ents:
            ent["chapter_links"] = [{
                "chapter_id": chapter_id,
                "chapter_title": chapter_title,
                "chapter_index": chapter_index,
                "relevance": ent.get("relevance", "appears"),
            }]
            assembled.append(ent)
    # Reuse the worker's exact merge (single source of truth — a future change to the
    # window-merge key must not silently diverge between live extraction and replay). Lazy
    # import keeps the router's import graph light + dodges any import-order coupling.
    from .extraction_worker import _merge_window_entities
    entities = _merge_window_entities(assembled)
    if not entities:
        return {"status": "empty", "reason": "cached_parse_had_no_entities"}

    # Re-stamp VALIDATED evidence provenance against the CURRENT text — sound because the
    # content_hash matched, so the offsets index exactly the text that will back the writeback.
    stamp_entity_provenance(entities, chapter_text)

    # Same whole-chapter idempotency key the worker computes (book, chapter, content, kinds,
    # profile) — so a replay of an already-applied clean chapter dedups at the writeback log.
    # HEAL mode (use_authored_strategy, D-EXTRACT-ATTR-MERGE-DEFAULTS M3) adds a "heal"
    # discriminator: a chapter already written under the OLD frozen `fill` actions has a
    # writeback_key the faithful replay would dedup against — so healing must key distinctly to
    # actually re-merge under the authored append/overwrite strategies. Re-running heal is still
    # idempotent (this distinct key dedups the 2nd heal; the append merge dedups per-item anyway).
    key_parts = [book_id, chapter_id, content_hash, ",".join(sorted(all_kinds)), profile_hash]
    if use_authored_strategy:
        key_parts.append("heal")
    writeback_key = hashlib.sha256("|".join(key_parts).encode("utf-8")).hexdigest()

    generation = {
        "content_hash": content_hash,
        "effort_band": effort_band,
        "profile_hash": profile_hash,
        "batch_rows": len(rows),
        "entity_count": len(entities),
    }

    mode = "heal" if use_authored_strategy else "faithful"
    if not confirm:
        # Dry-run: surface what a confirmed replay WOULD write; make NO glossary call.
        return {"status": "preview", "mode": mode, "generation": generation,
                "would_write": len(entities), "source_language": source_language}

    # HEAL mode sends EMPTY attribute_actions so the glossary resolver defers every attribute to
    # its authored merge_strategy (append/overwrite/fill) instead of the source job's frozen
    # actions — that's what unfreezes attributes extracted under the old `fill` default.
    upsert = await post_extracted_entities(
        book_id=book_id,
        source_language=source_language,
        attribute_actions={} if use_authored_strategy else extraction_profile,
        entities=entities,
        chapter_id=chapter_id,
        content_hash=content_hash,
        writeback_key=writeback_key,
        owner_user_id=caller_user_id,
    )
    if upsert is None:
        # The cache WAS found + reconstructed; only the glossary write failed. A distinct
        # status (not "no_cache") so a retry/cron knows the write was attempted, not absent.
        return {"status": "writeback_failed", "mode": mode, "generation": generation}
    return {"status": "replayed", "mode": mode, "generation": generation,
            "created": upsert.get("created", 0), "updated": upsert.get("updated", 0),
            "skipped": upsert.get("skipped", 0), "source_language": source_language}


async def rerun_merge_book(
    pool,
    *,
    caller_user_id: str,
    book_id: str,
    confirm: bool = False,
    chapter_ids: list[str] | None = None,
) -> dict:
    """Heal a whole book (D-EXTRACT-ATTR-MERGE-DEFAULTS M3): re-merge every chapter that has a
    faithful cached parse under the attributes' AUTHORED merge_strategy — unfreezing attributes
    that were extracted under the old `fill` default — at $0 LLM. Reuses replay_chapter_from_cache
    (use_authored_strategy=True) per chapter, so faithful-by-construction + tenancy/INV-9 hold.

    `confirm=False` is a dry-run (per-chapter preview counts, no glossary write). `chapter_ids`
    optionally narrows the heal to a subset (else every chapter with a cached parse for this
    book+owner). The response is BOUNDED: aggregate status counts + total would-write/created,
    plus a capped sample of non-replayed chapters for diagnostics (a 4000-chapter book must not
    return 4000 detail rows)."""
    if chapter_ids is None:
        async with pool.acquire() as db:
            rows = await db.fetch(
                """SELECT DISTINCT chapter_id FROM extraction_raw_outputs
                   WHERE owner_user_id=$1 AND book_id=$2""",
                caller_user_id, book_id,
            )
        chapter_ids = [str(r["chapter_id"]) for r in rows]

    status_counts: dict[str, int] = {}
    total_writes = 0
    problems: list[dict] = []
    PROBLEM_CAP = 50
    for cid in chapter_ids:
        r = await replay_chapter_from_cache(
            pool, caller_user_id=caller_user_id, book_id=book_id,
            chapter_id=cid, confirm=confirm, use_authored_strategy=True,
        )
        st = r.get("status", "unknown")
        status_counts[st] = status_counts.get(st, 0) + 1
        # created+updated on a confirm heal (entities usually already exist → the heal
        # APPENDS/OVERWRITES, so updated is where the action is); would_write on a dry-run.
        total_writes += int(r.get("created", 0)) + int(r.get("updated", 0)) + int(r.get("would_write", 0))
        if st not in ("replayed", "preview", "empty") and len(problems) < PROBLEM_CAP:
            problems.append({"chapter_id": cid, "status": st, "reason": r.get("reason")})
    return {
        "book_id": book_id,
        "confirm": confirm,
        "mode": "heal",
        "chapters_scanned": len(chapter_ids),
        "status_counts": status_counts,
        "total_writes": total_writes,
        "problem_sample": problems,
    }
