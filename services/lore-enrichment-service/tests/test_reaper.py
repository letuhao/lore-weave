"""Worker reaper (D-COMPOSE-S3-UPLOAD-REAPER + D-COMPOSE-CONTEXT-CORPUS-SCOPE).

Fake pool + monkeypatched MinIO (mirrors test_uploads_api.py's mock-heavy unit
style). Asserts: stale 'processing' uploads are failed (and the no-op guard);
orphan objects are deleted ONLY when old + parseable + row-less (in-flight objects
spared); ephemeral corpora are reaped by TTL (and the ttl<=0 no-op); reap_once is
best-effort (one failing sweep doesn't abort the others)."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from app.storage.minio_client import StoredObject
from app.worker import reaper as reaper_mod
from app.worker.reaper import (
    reap_once,
    sweep_ephemeral_corpora,
    sweep_orphan_objects,
    sweep_stale_uploads,
    upload_id_from_key,
)


class _FakeConn:
    def __init__(self, *, exec_tag="UPDATE 0", fetch_rows=None):
        self._exec_tag = exec_tag
        self._fetch_rows = fetch_rows if fetch_rows is not None else []
        self.calls: list[tuple] = []

    async def execute(self, sql, *args):
        self.calls.append(("execute", sql, args))
        return self._exec_tag

    async def fetch(self, sql, *args):
        self.calls.append(("fetch", sql, args))
        return self._fetch_rows


class _Acquire:
    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, *exc):
        return False


class _FakePool:
    def __init__(self, *, exec_tag="UPDATE 0", fetch_rows=None):
        self.conn = _FakeConn(exec_tag=exec_tag, fetch_rows=fetch_rows)

    def acquire(self):
        return _Acquire(self.conn)


# ── upload_id_from_key ───────────────────────────────────────────────────────
def test_upload_id_from_key_valid():
    uid = uuid4()
    assert upload_id_from_key(f"{uuid4()}/{uuid4()}/{uid}.pdf") == uid
    assert upload_id_from_key(f"{uuid4()}/{uuid4()}/{uid}") == uid  # no extension


def test_upload_id_from_key_unparseable():
    assert upload_id_from_key("a/b/not-a-uuid.txt") is None
    assert upload_id_from_key("") is None


# ── sweep_stale_uploads ──────────────────────────────────────────────────────
def test_sweep_stale_uploads_fails_old_rows():
    pool = _FakePool(exec_tag="UPDATE 4")
    n = asyncio.run(sweep_stale_uploads(pool, max_age_s=1800))
    assert n == 4
    sql = pool.conn.calls[0][1]
    assert "status='failed'" in sql and "status='processing'" in sql


def test_sweep_stale_uploads_disabled_is_noop():
    pool = _FakePool(exec_tag="UPDATE 9")
    assert asyncio.run(sweep_stale_uploads(pool, max_age_s=0)) == 0
    assert pool.conn.calls == []  # no SQL ran


# ── sweep_orphan_objects ─────────────────────────────────────────────────────
def test_sweep_orphan_objects_deletes_only_old_rowless(monkeypatch):
    now = datetime(2026, 6, 4, tzinfo=timezone.utc)
    old = now - timedelta(hours=3)
    fresh = now - timedelta(seconds=30)
    has_row = uuid4()
    orphan = uuid4()
    fresh_orphan = uuid4()
    objs = [
        StoredObject(key=f"u/b/{has_row}.pdf", last_modified=old),      # old but HAS a row → keep
        StoredObject(key=f"u/b/{orphan}.txt", last_modified=old),       # old + no row → DELETE
        StoredObject(key=f"u/b/{fresh_orphan}.txt", last_modified=fresh),  # no row but FRESH → keep
        StoredObject(key="u/b/garbage.txt", last_modified=old),         # unparseable → keep
    ]

    async def _list():
        return objs

    deleted: list[str] = []

    async def _del(key):
        deleted.append(key)

    monkeypatch.setattr(reaper_mod, "list_objects", _list)
    monkeypatch.setattr(reaper_mod, "delete_object", _del)
    # The DB says only has_row exists among the OLD candidates.
    pool = _FakePool(fetch_rows=[{"upload_id": has_row}])

    n = asyncio.run(sweep_orphan_objects(pool, grace_s=3600, now=now))
    assert n == 1
    assert deleted == [f"u/b/{orphan}.txt"]


def test_sweep_orphan_objects_empty_bucket(monkeypatch):
    async def _list():
        return []

    monkeypatch.setattr(reaper_mod, "list_objects", _list)
    assert asyncio.run(sweep_orphan_objects(_FakePool(), grace_s=3600)) == 0


# ── sweep_ephemeral_corpora (through the real SourceCorpusStore + fake pool) ──
def test_sweep_ephemeral_corpora_reaps_by_ttl():
    pool = _FakePool(fetch_rows=[{"corpus_id": uuid4()}, {"corpus_id": uuid4()}])
    n = asyncio.run(sweep_ephemeral_corpora(pool, ttl_s=30 * 24 * 3600))
    assert n == 2
    sql = pool.conn.calls[0][1]
    assert "compose_ephemeral" in sql and "DELETE FROM source_corpus" in sql


def test_sweep_ephemeral_corpora_disabled_is_noop():
    pool = _FakePool(fetch_rows=[{"corpus_id": uuid4()}])
    assert asyncio.run(sweep_ephemeral_corpora(pool, ttl_s=0)) == 0
    assert pool.conn.calls == []  # ttl<=0 → no SQL


# ── reap_once best-effort ────────────────────────────────────────────────────
def test_reap_once_is_best_effort(monkeypatch):
    async def _ok(*a, **k):
        return 2

    async def _boom(*a, **k):
        raise RuntimeError("sweep down")

    monkeypatch.setattr(reaper_mod, "sweep_stale_uploads", _ok)
    monkeypatch.setattr(reaper_mod, "sweep_orphan_objects", _boom)
    monkeypatch.setattr(reaper_mod, "sweep_ephemeral_corpora", _ok)

    out = asyncio.run(reap_once(_FakePool()))
    assert out == {"stale_uploads": 2, "orphan_objects": -1, "ephemeral_corpora": 2}
