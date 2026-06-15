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
    record_segment_translations,
)

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
