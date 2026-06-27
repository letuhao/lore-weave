"""W9 — ImportSourceRepo unit tests (no DB) via a recording fake pool.

Proves the per-user tenancy discipline (§12.6): create SERVER-STAMPS the owner (never an
arg), every read/write filters on owner_user_id = caller, a foreign id returns None/False
(IDOR-safe — the router maps to the uniform H13 404), and there is NO visibility/public
path. House style mirrors tests/unit/test_arc_template_repo.py's _FakePool/_FakeConn.
"""

from __future__ import annotations

import uuid

import pytest

from app.db.models import ImportSource
from app.db.repositories.import_source_repo import ImportSourceRepo

USER = uuid.uuid4()
OTHER = uuid.uuid4()


def _row(**kw) -> dict:
    return {
        "id": kw.get("id", uuid.uuid4()),
        "owner_user_id": kw.get("owner_user_id", USER),
        "project_id": kw.get("project_id", None),
        "title": kw.get("title", "Admired Work"),
        "content": kw.get("content", "chapter one ..."),
        "created_at": None,
    }


class _FakeConn:
    def __init__(self, *, rows=None, status="DELETE 1"):
        self._rows = rows or []
        self._status = status
        self.calls: list[tuple[str, tuple]] = []

    async def fetchrow(self, sql, *args):
        self.calls.append((sql, args))
        return self._rows[0] if self._rows else None

    async def fetch(self, sql, *args):
        self.calls.append((sql, args))
        return self._rows

    async def execute(self, sql, *args):
        self.calls.append((sql, args))
        return self._status


class _FakeAcquire:
    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, *exc):
        return False


class _FakePool:
    def __init__(self, conn):
        self.conn = conn

    def acquire(self):
        return _FakeAcquire(self.conn)


def _repo(conn):
    return ImportSourceRepo(_FakePool(conn))


# ── create: owner server-stamped, no visibility column ────────────────────────────────
async def test_create_stamps_owner_first_and_maps_row():
    conn = _FakeConn(rows=[_row(owner_user_id=USER)])
    src = await _repo(conn).create(USER, content="raw text", title="X")
    sql, params = conn.calls[0]
    assert "INSERT INTO import_source" in sql
    # owner_user_id is the FIRST bound param (server-stamped = caller, never an arg).
    assert params[0] == USER
    # NO visibility column written (un-shareable by construction — §12.6).
    assert "visibility" not in sql
    assert isinstance(src, ImportSource)
    assert src.owner_user_id == USER


async def test_create_passes_project_and_content():
    pid = uuid.uuid4()
    conn = _FakeConn(rows=[_row(project_id=pid, content="body")])
    await _repo(conn).create(USER, content="body", title="T", project_id=pid)
    _, params = conn.calls[0]
    assert params[0] == USER and params[1] == pid
    assert params[3] == "body"


# ── get_for_owner: owner-only, no read predicate that admits foreign rows ──────────────
async def test_get_for_owner_filters_owner_eq_caller():
    sid = uuid.uuid4()
    conn = _FakeConn(rows=[_row()])
    await _repo(conn).get_for_owner(USER, sid)
    sql, params = conn.calls[0]
    assert "owner_user_id = $2" in sql
    assert params == (sid, USER)
    # there is NO 'visibility = public' / 'owner IS NULL' admission (private-only).
    assert "visibility" not in sql
    assert "IS NULL" not in sql


async def test_get_for_owner_foreign_returns_none():
    # the owner-filter excludes a foreign row → fetchrow returns None (no oracle).
    conn = _FakeConn(rows=[])
    assert await _repo(conn).get_for_owner(USER, uuid.uuid4()) is None


# ── list_for_owner: never another user's rows ─────────────────────────────────────────
async def test_list_for_owner_filters_caller_and_orders_newest():
    conn = _FakeConn(rows=[_row(), _row()])
    rows = await _repo(conn).list_for_owner(USER)
    sql, params = conn.calls[0]
    assert "owner_user_id = $1" in sql
    assert params[0] == USER
    assert "ORDER BY created_at DESC" in sql
    assert len(rows) == 2


async def test_list_for_owner_optional_project_scope():
    pid = uuid.uuid4()
    conn = _FakeConn(rows=[])
    await _repo(conn).list_for_owner(USER, project_id=pid)
    sql, params = conn.calls[0]
    assert "project_id = $2" in sql
    assert params[1] == pid


# ── delete_for_owner: owner-only, status-string → bool ────────────────────────────────
async def test_delete_for_owner_true_on_deleted_row():
    conn = _FakeConn(status="DELETE 1")
    ok = await _repo(conn).delete_for_owner(USER, uuid.uuid4())
    sql, params = conn.calls[0]
    assert "DELETE FROM import_source" in sql and "owner_user_id = $2" in sql
    assert params[1] == USER
    assert ok is True


async def test_delete_for_owner_false_on_foreign_or_missing():
    # a foreign/missing id deletes nothing → "DELETE 0" → False (router → H13).
    conn = _FakeConn(status="DELETE 0")
    assert await _repo(conn).delete_for_owner(USER, uuid.uuid4()) is False
