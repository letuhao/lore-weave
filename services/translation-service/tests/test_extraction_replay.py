"""CACHE/M6 slice 3 — replay a cached extraction parse to glossary at $0 LLM.

Round-trips against real Postgres (skip when none reachable); the book-service chapter
fetch + the glossary writeback are patched so the test exercises the reconstruction +
gating logic, not the network."""
import hashlib
import json
import os
import uuid

import asyncpg
import pytest

from app.migrate import DDL
from app.workers import extraction_replay as R

_DSN = os.environ.get(
    "TRANSLATION_TEST_PG_DSN",
    "postgresql://loreweave:loreweave_dev@localhost:5555/loreweave_translation",
)

_TEXT = "In the hall, Alice met Bob. Alice smiled."
_HASH = hashlib.sha256(_TEXT.encode("utf-8")).hexdigest()
_PROFILE = {"character": {"name": "replace"}}
_PROFILE_HASH = hashlib.sha256(
    json.dumps(_PROFILE, sort_keys=True, ensure_ascii=False).encode("utf-8")
).hexdigest()


class _ConnPool:
    def __init__(self, conn):
        self._conn = conn

    def acquire(self):
        conn = self._conn

        class _CM:
            async def __aenter__(self):
                return conn

            async def __aexit__(self, *a):
                return False

        return _CM()


def _chapter(text=_TEXT):
    return {"text_content": text, "sort_order": 5, "original_language": "en", "title": "Ch5"}


async def _seed_job(conn, *, job_id, owner, book, profile=_PROFILE):
    await conn.execute(
        """INSERT INTO extraction_jobs (job_id, book_id, owner_user_id, model_ref,
                                        extraction_profile, chapter_ids)
           VALUES ($1,$2,$3,$4,$5,$6)""",
        job_id, book, owner, uuid.uuid4(), json.dumps(profile), [],
    )


async def _seed_cache_window(conn, *, owner, book, chap, job_id, window_idx, entities,
                             content_hash=_HASH, profile_hash=_PROFILE_HASH,
                             kinds=("character",), effort_band="none"):
    await conn.execute(
        """INSERT INTO extraction_raw_outputs
           (owner_user_id, book_id, chapter_id, chapter_content_hash, chapter_chunk_idx,
            batch_idx, kinds_requested, profile_hash, effort_band, parsed_entities,
            parse_status, job_id)
           VALUES ($1,$2,$3,$4,$5,0,$6,$7,$8,$9,'ok',$10)""",
        owner, book, chap, content_hash, window_idx, list(kinds), profile_hash,
        effort_band, json.dumps(entities), job_id,
    )


def _ent(name):
    return {"name": name, "kind_code": "character", "evidence": name}


async def _fixture(conn):
    """Two windows that both surface 'Alice' (→ merges to one) plus 'Bob' in window 0."""
    owner, book, chap, job = (uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), uuid.uuid4())
    await _seed_job(conn, job_id=job, owner=owner, book=book)
    await _seed_cache_window(conn, owner=owner, book=book, chap=chap, job_id=job,
                             window_idx=0, entities=[_ent("Alice"), _ent("Bob")])
    await _seed_cache_window(conn, owner=owner, book=book, chap=chap, job_id=job,
                             window_idx=1, entities=[_ent("Alice")])
    return owner, book, chap, job


@pytest.fixture
def patched_io(monkeypatch):
    """Patch the chapter fetch + glossary writeback; record the writeback call."""
    calls = {}

    async def fake_fetch(book_id, chapter_id):
        return calls.get("chapter", _chapter())

    async def fake_post(**kw):
        calls["writeback"] = kw
        return {"created": 2, "updated": 0, "skipped": 0}

    monkeypatch.setattr(R, "_fetch_chapter", fake_fetch)
    monkeypatch.setattr(R, "post_extracted_entities", fake_post)
    return calls


async def _with_pg(fn):
    try:
        conn = await asyncpg.connect(_DSN, timeout=3)
    except Exception:
        pytest.skip(f"no reachable Postgres at TRANSLATION_TEST_PG_DSN ({_DSN})")
    try:
        await conn.execute(DDL)
        tx = conn.transaction()
        await tx.start()
        try:
            await fn(conn, _ConnPool(conn))
        finally:
            await tx.rollback()
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_replay_preview_does_not_write(patched_io):
    async def body(conn, pool):
        owner, book, chap, _ = await _fixture(conn)
        res = await R.replay_chapter_from_cache(
            pool, caller_user_id=str(owner), book_id=str(book),
            chapter_id=str(chap), confirm=False)
        assert res["status"] == "preview"
        # Alice (×2 windows → merged) + Bob = 2 entities.
        assert res["would_write"] == 2
        assert res["generation"]["batch_rows"] == 2
        assert "writeback" not in patched_io  # dry-run made NO glossary call
    await _with_pg(body)


@pytest.mark.asyncio
async def test_replay_confirm_writes_merged_entities(patched_io):
    async def body(conn, pool):
        owner, book, chap, _ = await _fixture(conn)
        res = await R.replay_chapter_from_cache(
            pool, caller_user_id=str(owner), book_id=str(book),
            chapter_id=str(chap), confirm=True)
        assert res["status"] == "replayed"
        assert res["created"] == 2 and res["source_language"] == "en"
        wb = patched_io["writeback"]
        # Faithful writeback: caller-attributed, exact profile as attribute-actions, the
        # whole-chapter idempotency key + content hash present, entities merged to 2.
        assert wb["owner_user_id"] == str(owner)
        assert wb["attribute_actions"] == _PROFILE
        assert wb["content_hash"] == _HASH and wb["writeback_key"]
        names = sorted(e["name"] for e in wb["entities"])
        assert names == ["Alice", "Bob"]
        alice = next(e for e in wb["entities"] if e["name"] == "Alice")
        assert len(alice["chapter_links"]) == 1  # de-duped across the 2 windows
    await _with_pg(body)


@pytest.mark.asyncio
async def test_replay_no_cache_on_content_drift(patched_io):
    async def body(conn, pool):
        owner, book, chap, _ = await _fixture(conn)
        patched_io["chapter"] = _chapter("COMPLETELY different text now.")
        res = await R.replay_chapter_from_cache(
            pool, caller_user_id=str(owner), book_id=str(book),
            chapter_id=str(chap), confirm=True)
        assert res["status"] == "no_cache"  # current text hashes to a generation we don't have
        assert "writeback" not in patched_io
    await _with_pg(body)


@pytest.mark.asyncio
async def test_replay_profile_unavailable_when_job_gone(patched_io):
    async def body(conn, pool):
        owner, book, chap = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        # cache rows reference a job_id that has no extraction_jobs row.
        await _seed_cache_window(conn, owner=owner, book=book, chap=chap,
                                 job_id=uuid.uuid4(), window_idx=0, entities=[_ent("Alice")])
        res = await R.replay_chapter_from_cache(
            pool, caller_user_id=str(owner), book_id=str(book),
            chapter_id=str(chap), confirm=True)
        assert res["status"] == "profile_unavailable"
        assert "writeback" not in patched_io
    await _with_pg(body)


@pytest.mark.asyncio
async def test_replay_tenant_isolation(patched_io):
    async def body(conn, pool):
        owner, book, chap, _ = await _fixture(conn)
        other = uuid.uuid4()  # a DIFFERENT tenant with no cache rows of their own (INV-9)
        res = await R.replay_chapter_from_cache(
            pool, caller_user_id=str(other), book_id=str(book),
            chapter_id=str(chap), confirm=True)
        assert res["status"] == "no_cache"
        assert "writeback" not in patched_io
    await _with_pg(body)
