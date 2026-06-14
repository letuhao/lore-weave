"""T2-M1: persist a chapter's source-side segments idempotently.

`ensure_chapter_segments` fetches the chapter's blocks, runs the pure segmenter, and
upserts `chapter_segments` rows — skipping the rewrite when the source is unchanged
(per-segment source_content_hash match), so the full backfill is re-runnable/resumable.
"""
import logging

import asyncpg

from .. import book_client
from .segmentation import DEFAULT_MAX_TOKENS, segment_blocks, segment_source_hash

log = logging.getLogger(__name__)


async def ensure_chapter_segments(
    pool: asyncpg.Pool,
    book_id,
    chapter_id,
    *,
    fetch_blocks=None,
    max_tokens: int = DEFAULT_MAX_TOKENS,
) -> dict:
    """Re-segment a chapter from its current blocks; replace the rows only if changed.

    `fetch_blocks` is an injectable async fn(book_id, chapter_id) -> list[dict] (the
    book-service client by default) — keeps the function unit-testable.
    """
    fetch = fetch_blocks or book_client.get_chapter_blocks
    blocks = await fetch(book_id, chapter_id)
    segments = segment_blocks(blocks, max_tokens)
    new_map = {s.segment_index: segment_source_hash(s) for s in segments}

    async with pool.acquire() as conn:
        async with conn.transaction():
            # Serialize concurrent rebuilds of the same chapter (backfill loop vs a
            # future draft-edit trigger) so the DELETE-all + re-INSERT can't collide on
            # UNIQUE(chapter_id, segment_index). Mirrors the T1 get-or-create lock.
            await conn.execute("SELECT pg_advisory_xact_lock(hashtext($1)::bigint)", str(chapter_id))
            existing = await conn.fetch(
                "SELECT segment_index, source_content_hash FROM chapter_segments WHERE chapter_id=$1",
                chapter_id,
            )
            existing_map = {r["segment_index"]: r["source_content_hash"] for r in existing}
            # Unchanged source (and not the empty→empty bootstrap) → skip the rewrite.
            if existing_map and existing_map == new_map:
                return {"chapter_id": str(chapter_id), "segments": len(segments), "changed": False}

            await conn.execute("DELETE FROM chapter_segments WHERE chapter_id=$1", chapter_id)
            for s in segments:
                await conn.execute(
                    """
                    INSERT INTO chapter_segments
                      (chapter_id, segment_index, start_block_index, end_block_index,
                       segment_text, block_hashes, token_estimate, source_content_hash)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                    """,
                    chapter_id, s.segment_index, s.start_block_index, s.end_block_index,
                    s.segment_text, s.block_hashes, s.token_estimate, segment_source_hash(s),
                )
    return {"chapter_id": str(chapter_id), "segments": len(segments), "changed": True}
