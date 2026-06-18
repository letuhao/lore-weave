"""Real-Postgres cycle for T2-M2.1 segment status: record → dirty → re-record.

Proves the `record_segment_translations` / `compute_segment_status` SQL behaves
against a live schema (the mock test asserts shape only). Runs inside a rolled-back
transaction; skips when no Postgres is reachable (point at one with
TRANSLATION_TEST_PG_DSN)."""
import os
import uuid

import asyncpg
import pytest

from app.workers.segment_status import (
    compute_segment_status,
    record_segment_glossary_usage,
    record_segment_translations,
)
from app.events.glossary_consumer import handle_glossary_event, GLOSSARY_CHANGE_EVENT

_DSN = os.environ.get(
    "TRANSLATION_TEST_PG_DSN",
    "postgresql://loreweave:loreweave_dev@localhost:5555/loreweave_translation",
)


async def _mk_segment(conn, chapter_id, idx, src_hash, *, start=None, end=None):
    start = idx if start is None else start
    end = idx if end is None else end
    await conn.execute(
        """INSERT INTO chapter_segments
             (chapter_id, segment_index, start_block_index, end_block_index,
              segment_text, block_hashes, token_estimate, source_content_hash)
           VALUES ($1,$2,$3,$4,'t',$5,10,$6)""",
        chapter_id, idx, start, end, [src_hash], src_hash,
    )


@pytest.mark.asyncio
async def test_segment_status_record_dirty_cycle_real_pg():
    try:
        conn = await asyncpg.connect(_DSN, timeout=3)
    except Exception:
        pytest.skip(f"no reachable Postgres at TRANSLATION_TEST_PG_DSN ({_DSN})")

    try:
        tx = conn.transaction()
        await tx.start()
        try:
            chapter_id, ct_id = uuid.uuid4(), uuid.uuid4()
            await _mk_segment(conn, chapter_id, 0, "h0")
            await _mk_segment(conn, chapter_id, 1, "h1")

            # Before any translation: both segments dirty + untranslated.
            st = await compute_segment_status(conn, chapter_id, "vi")
            assert [s["dirty"] for s in st] == [True, True]
            assert [s["translated"] for s in st] == [False, False]

            # Record a full-chapter translation → both clean.
            n = await record_segment_translations(conn, chapter_id, "vi", ct_id)
            assert n == 2
            st = await compute_segment_status(conn, chapter_id, "vi")
            assert [s["dirty"] for s in st] == [False, False]
            assert all(s["translated"] for s in st)

            # A different language is independent → still dirty there.
            st_en = await compute_segment_status(conn, chapter_id, "en")
            assert [s["dirty"] for s in st_en] == [True, True]

            # Source edit on segment 1 (its block hash changes) → segment 1 dirty again.
            await conn.execute(
                "UPDATE chapter_segments SET source_content_hash='h1-new', block_hashes=$2 "
                "WHERE chapter_id=$1 AND segment_index=1",
                chapter_id, ["h1-new"],
            )
            st = await compute_segment_status(conn, chapter_id, "vi")
            assert [s["dirty"] for s in st] == [False, True]

            # Re-record (idempotent upsert) → clean again.
            await record_segment_translations(conn, chapter_id, "vi", ct_id)
            st = await compute_segment_status(conn, chapter_id, "vi")
            assert [s["dirty"] for s in st] == [False, False]
        finally:
            await tx.rollback()
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_segment_glossary_staleness_cycle_real_pg():
    """T2-M3.2: per-segment glossary staleness — usage → entity_updated flags only
    the segments that use the changed entity → status shows stale → re-record clears it."""
    try:
        conn = await asyncpg.connect(_DSN, timeout=3)
    except Exception:
        pytest.skip(f"no reachable Postgres at TRANSLATION_TEST_PG_DSN ({_DSN})")

    try:
        tx = conn.transaction()
        await tx.start()
        try:
            book_id, chapter_id, ct_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
            entity_a, entity_b = uuid.uuid4(), uuid.uuid4()
            # a chapter_translations row ties the chapter to the book (consumer scopes by book)
            job = await conn.fetchval(
                """INSERT INTO translation_jobs
                     (book_id, owner_user_id, target_language, model_source, model_ref,
                      system_prompt, user_prompt_tpl, chapter_ids)
                   VALUES ($1,$2,'vi','user_model',$3,'sp','up',$4::uuid[]) RETURNING job_id""",
                book_id, uuid.uuid4(), uuid.uuid4(), [],
            )
            await conn.execute(
                """INSERT INTO chapter_translations
                     (job_id, chapter_id, book_id, owner_user_id, status, target_language, version_num)
                   VALUES ($1,$2,$3,$4,'completed','vi',1)""",
                job, chapter_id, book_id, uuid.uuid4(),
            )
            await _mk_segment(conn, chapter_id, 0, "h0")
            await _mk_segment(conn, chapter_id, 1, "h1")
            await record_segment_translations(conn, chapter_id, "vi", ct_id)
            # seg 0 uses entity A; seg 1 uses entity B.
            await record_segment_glossary_usage(conn, chapter_id, [(0, str(entity_a)), (1, str(entity_b))])

            # entity A changes → only seg 0 flagged stale.
            await handle_glossary_event(conn, GLOSSARY_CHANGE_EVENT, {
                "book_id": str(book_id), "glossary_entity_id": str(entity_a), "target_language": "vi",
            })
            st = await compute_segment_status(conn, chapter_id, "vi")
            assert [s["stale"] for s in st] == [True, False]
            assert [s["needs"] for s in st] == [True, False]  # source unchanged → needs == stale
            assert [s["dirty"] for s in st] == [False, False]

            # re-record (a re-translation) clears the segment stale flag.
            await record_segment_translations(conn, chapter_id, "vi", ct_id)
            st = await compute_segment_status(conn, chapter_id, "vi")
            assert [s["stale"] for s in st] == [False, False]
        finally:
            await tx.rollback()
    finally:
        await conn.close()
