"""T2-M2.2: dirty-only re-translate — the worker overlay + the retranslate-dirty endpoint.

Overlay tests are pure (monkeypatched translate + seed). The endpoint tests use
fake_pool and patch the job-create core to capture the scoped payload."""
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from tests.conftest import FakeRecord


# ── worker overlay: _partial_retranslate_blocks ───────────────────────────────

def _seg_status_row(idx, start, end, dirty, stale=False):
    # compute_segment_status reads these columns; dirty = no translated_hash.
    return FakeRecord({
        "segment_index": idx, "start_block_index": start, "end_block_index": end,
        "token_estimate": 50, "current_hash": "cur",
        "translated_hash": None if dirty else "cur",
        "translated_at": None if dirty else datetime(2026, 6, 15, tzinfo=timezone.utc),
        "is_glossary_stale": stale,
    })


@pytest.mark.asyncio
async def test_partial_overlay_replaces_only_dirty(monkeypatch):
    from app.workers import chapter_worker
    seed = [{"b": 0}, {"b": 1}, {"b": 2}, {"b": 3}]
    blocks = [{"s": 0}, {"s": 1}, {"s": 2}, {"s": 3}]

    async def fake_seed(pool, sid, cid):
        return list(seed)
    monkeypatch.setattr(chapter_worker, "_load_seed_blocks", fake_seed)

    async def fake_translate(*, blocks, **k):
        tb = [{"t": b["s"]} for b in blocks]
        texts = {i: f"T{b['s']}" for i, b in enumerate(blocks)}
        return (tb, 10, 5, len(tb), len(tb), texts)

    merged, in_tok, out_tok, t_count, t_able, texts = await chapter_worker._partial_retranslate_blocks(
        pool=None, llm_client=None, chapter_translation_id=uuid4(), chapter_id=uuid4(),
        blocks=blocks, block_filter=[3, 1, 1], seed_version_id=uuid4(),  # dup + unsorted
        source_lang="zh", msg={"chapter_id": str(uuid4())}, context_window=8192,
        translate_blocks_fn=fake_translate,
    )
    assert merged[0] == {"b": 0}  # copied from seed
    assert merged[2] == {"b": 2}  # copied from seed
    assert merged[1] == {"t": 1}  # re-translated source block 1
    assert merged[3] == {"t": 3}  # re-translated source block 3
    assert texts == {1: "T1", 3: "T3"}  # remapped to source positions
    assert (in_tok, out_tok) == (10, 5)


@pytest.mark.asyncio
async def test_partial_seed_mismatch_falls_back_to_full(monkeypatch):
    from app.workers import chapter_worker

    async def fake_seed(pool, sid, cid):
        return [{"b": 0}]  # len 1 != 3 → misaligned
    monkeypatch.setattr(chapter_worker, "_load_seed_blocks", fake_seed)

    seen = {}

    async def fake_translate(*, blocks, **k):
        seen["n"] = len(blocks)
        return ([{"t": i} for i in range(len(blocks))], 1, 1, len(blocks), len(blocks), {})

    await chapter_worker._partial_retranslate_blocks(
        pool=None, llm_client=None, chapter_translation_id=uuid4(), chapter_id=uuid4(),
        blocks=[{"s": 0}, {"s": 1}, {"s": 2}], block_filter=[1], seed_version_id=uuid4(),
        source_lang="zh", msg={"chapter_id": str(uuid4())}, context_window=8192,
        translate_blocks_fn=fake_translate,
    )
    assert seen["n"] == 3  # translated the WHOLE chapter, not just the 1 dirty block


@pytest.mark.asyncio
async def test_partial_empty_filter_no_llm_spend(monkeypatch):
    from app.workers import chapter_worker

    async def fake_seed(pool, sid, cid):
        return [{"b": 0}, {"b": 1}]
    monkeypatch.setattr(chapter_worker, "_load_seed_blocks", fake_seed)

    called = {"t": 0}

    async def fake_translate(**k):
        called["t"] += 1
        return ([], 0, 0, 0, 0, {})

    merged, *_ = await chapter_worker._partial_retranslate_blocks(
        pool=None, llm_client=None, chapter_translation_id=uuid4(), chapter_id=uuid4(),
        blocks=[{"s": 0}, {"s": 1}], block_filter=[5, 9], seed_version_id=uuid4(),  # all OOR
        source_lang="zh", msg={"chapter_id": str(uuid4())}, context_window=8192,
        translate_blocks_fn=fake_translate,
    )
    assert merged == [{"b": 0}, {"b": 1}]  # seed unchanged
    assert called["t"] == 0  # never called the LLM


# ── full-chapter memo from merged body (review-impl LOW-4) ────────────────────

def test_block_plain_text_extracts_nested_and_ignores_nontext():
    from app.workers.chapter_worker import _block_plain_text
    node = {"type": "paragraph", "content": [
        {"type": "text", "text": "Hello"},
        {"type": "hardBreak"},
        {"type": "text", "text": "World"},
    ]}
    assert _block_plain_text(node) == "Hello\nWorld"
    assert _block_plain_text({"type": "image", "attrs": {"src": "x"}}) == ""
    assert _block_plain_text("not-a-dict") == ""


# ── seed load is chapter-scoped (review-impl HIGH-1) ──────────────────────────

@pytest.mark.asyncio
async def test_load_seed_blocks_is_chapter_scoped():
    from app.workers import chapter_worker
    captured = {}

    class _Conn:
        async def fetchrow(self, sql, *args):
            captured["sql"] = sql
            captured["args"] = args
            return {"translated_body_json": [{"b": 0}]}

    class _Pool:
        def acquire(self):
            class _CM:
                async def __aenter__(s):
                    return _Conn()
                async def __aexit__(s, *e):
                    return False
            return _CM()

    sid, cid = uuid4(), uuid4()
    out = await chapter_worker._load_seed_blocks(_Pool(), str(sid), str(cid))
    assert out == [{"b": 0}]
    # the query MUST constrain by chapter_id (a foreign-chapter seed → no row)
    assert "chapter_id=$2" in captured["sql"]
    assert captured["args"] == (sid, cid)


# ── endpoint: POST /chapters/{id}/retranslate-dirty ───────────────────────────

def _capture_job_create(monkeypatch):
    """Patch the job-create core; capture the CreateJobPayload, return a valid job."""
    from app.routers import jobs
    from app.models import TranslationJob
    holder = {}

    async def fake_create(db, book_id, payload, user_id, **k):
        holder["payload"] = payload
        holder["book_id"] = book_id
        return TranslationJob(
            job_id=uuid4(), book_id=book_id, owner_user_id=uuid4(), status="pending",
            target_language=payload.target_language or "vi", model_source="user_model",
            model_ref=uuid4(), system_prompt="", user_prompt_tpl="",
            chapter_ids=payload.chapter_ids, total_chapters=1, completed_chapters=0,
            failed_chapters=0, error_message=None, started_at=None, finished_at=None,
            created_at=datetime(2026, 6, 15, tzinfo=timezone.utc),
        )
    monkeypatch.setattr(jobs, "_resolve_and_create_job", fake_create)
    return holder


def test_retranslate_dirty_scopes_to_dirty_blocks(client, fake_pool, monkeypatch):
    holder = _capture_job_create(monkeypatch)
    book_id, seed_id = uuid4(), uuid4()
    # book_for_chapter (1st fetchval) → book; seed lookup (2nd fetchval) → seed.
    fake_pool.fetchval.side_effect = [book_id, seed_id]
    # compute_segment_status: seg0 clean, seg1 dirty (blocks 3..5), seg2 dirty (block 6).
    fake_pool.fetch.return_value = [
        _seg_status_row(0, 0, 2, dirty=False),
        _seg_status_row(1, 3, 5, dirty=True),
        _seg_status_row(2, 6, 6, dirty=True),
    ]
    resp = client.post(
        f"/v1/translation/chapters/{uuid4()}/retranslate-dirty",
        json={"target_language": "vi"},
    )
    assert resp.status_code == 201
    p = holder["payload"]
    assert p.block_index_filter == [3, 4, 5, 6]  # union of the dirty segment ranges
    assert str(p.seed_version_id) == str(seed_id)
    assert p.force_retranslate is True
    assert [str(c) for c in p.chapter_ids] and len(p.chapter_ids) == 1


def test_retranslate_dirty_includes_glossary_stale_segments(client, fake_pool, monkeypatch):
    holder = _capture_job_create(monkeypatch)
    book_id, seed_id = uuid4(), uuid4()
    fake_pool.fetchval.side_effect = [book_id, seed_id]
    # seg 0 clean, seg 1 source-dirty (blocks 3..4), seg 2 glossary-stale only (block 6)
    fake_pool.fetch.return_value = [
        _seg_status_row(0, 0, 2, dirty=False),
        _seg_status_row(1, 3, 4, dirty=True),
        _seg_status_row(2, 6, 6, dirty=False, stale=True),
    ]
    resp = client.post(
        f"/v1/translation/chapters/{uuid4()}/retranslate-dirty",
        json={"target_language": "vi"},
    )
    assert resp.status_code == 201
    # needs = dirty ∪ stale → blocks of seg 1 AND seg 2
    assert holder["payload"].block_index_filter == [3, 4, 6]


def test_retranslate_dirty_409_when_nothing_dirty(client, fake_pool, monkeypatch):
    _capture_job_create(monkeypatch)
    fake_pool.fetchval.side_effect = [uuid4()]  # book_for_chapter
    fake_pool.fetch.return_value = [_seg_status_row(0, 0, 2, dirty=False)]
    resp = client.post(
        f"/v1/translation/chapters/{uuid4()}/retranslate-dirty",
        json={"target_language": "vi"},
    )
    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "TRANSL_NO_DIRTY_SEGMENTS"


def test_retranslate_dirty_409_when_no_seed_version(client, fake_pool, monkeypatch):
    _capture_job_create(monkeypatch)
    fake_pool.fetchval.side_effect = [uuid4(), None]  # book ok, no llm seed
    fake_pool.fetch.return_value = [_seg_status_row(1, 3, 5, dirty=True)]
    resp = client.post(
        f"/v1/translation/chapters/{uuid4()}/retranslate-dirty",
        json={"target_language": "vi"},
    )
    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "TRANSL_NO_SEED_VERSION"
