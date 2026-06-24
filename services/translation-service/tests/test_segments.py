"""T2-M1: the internal segments-rebuild route + ensure_chapter_segments idempotency.

Mock-style (fake_pool), mirroring test_versions.py. ensure_chapter_segments runs under
the route; book-service blocks are stubbed via monkeypatch on app.book_client."""
import json
from uuid import uuid4

from tests.conftest import FakeRecord
from app.workers.segmentation import segment_blocks, segment_source_hash

TOKEN = {"X-Internal-Token": "test_internal_token"}


def _blk(i, text, h):
    return {"block_index": i, "block_type": "paragraph", "text_content": text, "content_hash": h}


def _seg_inserts(fake_pool):
    return [c for c in fake_pool.execute.call_args_list if "INSERT INTO chapter_segments" in c.args[0]]


def _url(chapter_id):
    return f"/internal/translation/chapters/{chapter_id}/segments/rebuild"


def test_rebuild_inserts_segments_when_absent(client, fake_pool, monkeypatch):
    async def fake_blocks(_b, _c):
        return [_blk(0, "a", "h0"), _blk(1, "b", "h1")]
    monkeypatch.setattr("app.book_client.get_chapter_blocks", fake_blocks)
    fake_pool.fetch.return_value = []  # no existing segments

    resp = client.post(_url(uuid4()), json={"book_id": str(uuid4())}, headers=TOKEN)
    assert resp.status_code == 200
    body = resp.json()
    assert body["changed"] is True
    assert body["segments"] == 1
    assert len(_seg_inserts(fake_pool)) == 1
    # the get-or-rebuild is serialized by an advisory lock (concurrent-rebuild guard)
    assert any("pg_advisory_xact_lock" in c.args[0] for c in fake_pool.execute.call_args_list)


def test_rebuild_skips_when_source_unchanged(client, fake_pool, monkeypatch):
    blocks = [_blk(0, "a", "h0")]
    seg = segment_blocks(blocks, 2000)[0]

    async def fake_blocks(_b, _c):
        return blocks
    monkeypatch.setattr("app.book_client.get_chapter_blocks", fake_blocks)
    fake_pool.fetch.return_value = [
        FakeRecord({"segment_index": 0, "source_content_hash": segment_source_hash(seg)}),
    ]

    resp = client.post(_url(uuid4()), json={"book_id": str(uuid4())}, headers=TOKEN)
    assert resp.status_code == 200
    assert resp.json()["changed"] is False
    assert _seg_inserts(fake_pool) == []  # no rewrite when unchanged


def test_rebuild_replaces_on_change(client, fake_pool, monkeypatch):
    async def fake_blocks(_b, _c):
        return [_blk(0, "new text", "h0-CHANGED"), _blk(1, "b", "h1")]
    monkeypatch.setattr("app.book_client.get_chapter_blocks", fake_blocks)
    # existing has a stale hash → mismatch → delete+insert
    fake_pool.fetch.return_value = [FakeRecord({"segment_index": 0, "source_content_hash": "STALE"})]

    resp = client.post(_url(uuid4()), json={"book_id": str(uuid4())}, headers=TOKEN)
    assert resp.status_code == 200
    assert resp.json()["changed"] is True
    deletes = [c for c in fake_pool.execute.call_args_list if "DELETE FROM chapter_segments" in c.args[0]]
    assert len(deletes) == 1
    assert len(_seg_inserts(fake_pool)) == 1


def test_rebuild_requires_internal_token(client):
    resp = client.post(_url(uuid4()), json={"book_id": str(uuid4())})  # no token
    assert resp.status_code == 401
