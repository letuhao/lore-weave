"""Real-Postgres test for the T2-M3 segment-coverage rollup SQL.

Proves the book-chapters ⋈ chapter_segments ⋈ segment_translations join + the
dirty/translated FILTER counts against a live schema. Rolled back; skips with no PG."""
import os
import uuid

import asyncpg
import pytest

from app.routers.coverage import _SEGMENT_COVERAGE_SQL
from app.workers.segment_status import record_segment_translations

_DSN = os.environ.get(
    "TRANSLATION_TEST_PG_DSN",
    "postgresql://loreweave:loreweave_dev@localhost:5555/loreweave_translation",
)


async def _mk_ct(conn, book_id, chapter_id, lang):
    # a chapter_translations row is what ties a chapter to the book (segment-coverage
    # derives book chapters from it). A job is needed for the FK.
    job = await conn.fetchval(
        """INSERT INTO translation_jobs
             (book_id, owner_user_id, target_language, model_source, model_ref,
              system_prompt, user_prompt_tpl, chapter_ids)
           VALUES ($1,$2,$3,'user_model',$4,'sp','up',$5::uuid[]) RETURNING job_id""",
        book_id, uuid.uuid4(), lang, uuid.uuid4(), [],
    )
    await conn.execute(
        """INSERT INTO chapter_translations
             (job_id, chapter_id, book_id, owner_user_id, status, target_language, version_num)
           VALUES ($1,$2,$3,$4,'completed',$5,1)""",
        job, chapter_id, book_id, uuid.uuid4(), lang,
    )


async def _mk_segment(conn, chapter_id, idx, src_hash):
    await conn.execute(
        """INSERT INTO chapter_segments
             (chapter_id, segment_index, start_block_index, end_block_index,
              segment_text, block_hashes, token_estimate, source_content_hash)
           VALUES ($1,$2,$3,$3,'t',$4,10,$5)""",
        chapter_id, idx, idx, [src_hash], src_hash,
    )


@pytest.mark.asyncio
async def test_segment_coverage_counts_real_pg():
    try:
        conn = await asyncpg.connect(_DSN, timeout=3)
    except Exception:
        pytest.skip(f"no reachable Postgres at TRANSLATION_TEST_PG_DSN ({_DSN})")

    try:
        tx = conn.transaction()
        await tx.start()
        try:
            book_id, ch1, ch2 = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
            await _mk_ct(conn, book_id, ch1, "vi")
            await _mk_ct(conn, book_id, ch2, "vi")
            # ch1: 3 segments, translate all, then change seg 2 → 1 dirty.
            for i, h in enumerate(["a", "b", "c"]):
                await _mk_segment(conn, ch1, i, h)
            await record_segment_translations(conn, ch1, "vi", uuid.uuid4())
            await conn.execute(
                "UPDATE chapter_segments SET source_content_hash='c-new' "
                "WHERE chapter_id=$1 AND segment_index=2", ch1,
            )
            # ch2: 2 segments, never translated → all dirty.
            for i, h in enumerate(["x", "y"]):
                await _mk_segment(conn, ch2, i, h)

            rows = await conn.fetch(_SEGMENT_COVERAGE_SQL, book_id, "vi")
            by_ch = {r["chapter_id"]: r for r in rows}
            assert by_ch[ch1]["segment_total"] == 3
            assert by_ch[ch1]["translated_count"] == 3   # all have a recorded row
            assert by_ch[ch1]["dirty_count"] == 1        # only seg 2 changed
            assert by_ch[ch2]["segment_total"] == 2
            assert by_ch[ch2]["translated_count"] == 0
            assert by_ch[ch2]["dirty_count"] == 2        # never translated

            # a different language sees everything dirty/untranslated for ch1 too
            rows_en = await conn.fetch(_SEGMENT_COVERAGE_SQL, book_id, "en")
            # ch2 has no 'en' chapter_translations row → not a book chapter for 'en'
            # but ch1 does NOT either (only 'vi'); so 'en' yields no rows at all.
            assert rows_en == []
        finally:
            await tx.rollback()
    finally:
        await conn.close()
