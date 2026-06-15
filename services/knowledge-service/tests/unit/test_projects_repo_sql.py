"""C5 (ARCH-1) — no-DB coverage of ProjectsRepo.list's dynamic SQL.

The integration repo tests need a real Postgres (KNOWLEDGE_DB_URL) and skip
locally, so the dynamic ``$N`` placeholder numbering in list() — which composes
the optional cursor params and the new C5 book_id filter — had no CI coverage
without a DB. This drives the REAL repo against a recording connection and
asserts the exact query string + params for all 4 combinations, locking the
placeholder math into the always-run unit suite.
"""
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.db.repositories.projects import ProjectsRepo


class _RecordingConn:
    def __init__(self) -> None:
        self.query: str | None = None
        self.params: tuple = ()

    async def fetch(self, query, *params):
        self.query = query
        self.params = params
        return []  # no rows — we only care about the generated SQL/params


class _RecordingPool:
    def __init__(self) -> None:
        self.conn = _RecordingConn()

    def acquire(self):
        conn = self.conn

        class _Cm:
            async def __aenter__(self):
                return conn

            async def __aexit__(self, *a):
                return False

        return _Cm()


def _norm(q: str) -> str:
    return " ".join(q.split())


@pytest.mark.asyncio
async def test_list_sql_no_cursor_no_book():
    pool = _RecordingPool()
    repo = ProjectsRepo(pool)
    user = uuid4()
    await repo.list(user, limit=50)
    q = _norm(pool.conn.query)
    # only user_id + fetch_limit → LIMIT is $2
    assert "WHERE user_id = $1 AND NOT is_archived" in q
    assert "book_id =" not in q
    # Default order unchanged (back-compat).
    assert "ORDER BY created_at DESC, project_id DESC" in q
    assert q.endswith("LIMIT $2")
    assert pool.conn.params == (user, 51)


@pytest.mark.asyncio
async def test_list_sql_book_no_cursor():
    pool = _RecordingPool()
    repo = ProjectsRepo(pool)
    user, book = uuid4(), uuid4()
    await repo.list(user, limit=10, book_id=book)
    q = _norm(pool.conn.query)
    # user_id $1, book_id $2, fetch_limit $3
    assert "AND book_id = $2" in q
    assert q.endswith("LIMIT $3")
    assert pool.conn.params == (user, book, 11)


@pytest.mark.asyncio
async def test_list_sql_cursor_no_book():
    pool = _RecordingPool()
    repo = ProjectsRepo(pool)
    user, cid = uuid4(), uuid4()
    cts = datetime.now(timezone.utc)
    await repo.list(user, limit=5, cursor_sort_value=cts, cursor_project_id=cid)
    q = _norm(pool.conn.query)
    # user_id $1, cursor $2/$3, fetch_limit $4
    assert "(created_at, project_id) < ($2, $3)" in q
    assert "book_id =" not in q
    assert q.endswith("LIMIT $4")
    assert pool.conn.params == (user, cts, cid, 6)


@pytest.mark.asyncio
async def test_list_sql_cursor_and_book():
    pool = _RecordingPool()
    repo = ProjectsRepo(pool)
    user, cid, book = uuid4(), uuid4(), uuid4()
    cts = datetime.now(timezone.utc)
    await repo.list(
        user, limit=5, cursor_sort_value=cts, cursor_project_id=cid, book_id=book,
    )
    q = _norm(pool.conn.query)
    # user_id $1, cursor $2/$3, book_id $4, fetch_limit $5 — the combo no
    # other test (or the live smoke) exercised.
    assert "(created_at, project_id) < ($2, $3)" in q
    assert "AND book_id = $4" in q
    assert q.endswith("LIMIT $5")
    assert pool.conn.params == (user, cts, cid, book, 6)


@pytest.mark.asyncio
async def test_list_sql_book_filter_is_user_scoped():
    """The book predicate is ANDed with the unconditional user scope — it can
    only narrow, never widen past the owner."""
    pool = _RecordingPool()
    repo = ProjectsRepo(pool)
    user, book = uuid4(), uuid4()
    await repo.list(user, book_id=book)
    q = _norm(pool.conn.query)
    assert q.index("user_id = $1") < q.index("book_id =")


# ── C7-followup (KN-7) — server-side search / sort / status ───────────


@pytest.mark.asyncio
async def test_list_sql_search_adds_escaped_ilike():
    pool = _RecordingPool()
    repo = ProjectsRepo(pool)
    user = uuid4()
    await repo.list(user, limit=50, search="万古")
    q = _norm(pool.conn.query)
    # user_id $1, search $2, fetch_limit $3
    assert "name ILIKE $2 ESCAPE" in q
    assert pool.conn.params == (user, "%万古%", 51)


@pytest.mark.asyncio
async def test_list_sql_search_escapes_wildcards():
    """A literal % / _ in the search must not widen the match — they're
    backslash-escaped so ILIKE treats them as literals."""
    pool = _RecordingPool()
    repo = ProjectsRepo(pool)
    user = uuid4()
    await repo.list(user, search="50%_off")
    # The bound param is the wrapped, escaped pattern.
    assert pool.conn.params[1] == "%50\\%\\_off%"


@pytest.mark.asyncio
async def test_list_sql_sort_by_name_asc():
    pool = _RecordingPool()
    repo = ProjectsRepo(pool)
    user = uuid4()
    await repo.list(user, sort_by="name", sort_dir="asc")
    q = _norm(pool.conn.query)
    assert "ORDER BY name ASC, project_id ASC" in q


@pytest.mark.asyncio
async def test_list_sql_sort_by_status_maps_to_extraction_status():
    pool = _RecordingPool()
    repo = ProjectsRepo(pool)
    user = uuid4()
    await repo.list(user, sort_by="status", sort_dir="desc")
    q = _norm(pool.conn.query)
    assert "ORDER BY extraction_status DESC, project_id DESC" in q


@pytest.mark.asyncio
async def test_list_sql_cursor_seek_op_flips_for_asc():
    """Ascending sort seeks with `>` so the cursor advances forward."""
    pool = _RecordingPool()
    repo = ProjectsRepo(pool)
    user, cid = uuid4(), uuid4()
    await repo.list(
        user, sort_by="name", sort_dir="asc",
        cursor_sort_value="Zephyr", cursor_project_id=cid,
    )
    q = _norm(pool.conn.query)
    assert "(name, project_id) > ($2, $3)" in q


@pytest.mark.asyncio
async def test_list_sql_status_archived_forces_is_archived():
    pool = _RecordingPool()
    repo = ProjectsRepo(pool)
    user = uuid4()
    await repo.list(user, status="archived")
    q = _norm(pool.conn.query)
    assert "AND is_archived" in q
    assert "extraction_status =" not in q


@pytest.mark.asyncio
async def test_list_sql_status_value_filters_extraction_status_non_archived():
    pool = _RecordingPool()
    repo = ProjectsRepo(pool)
    user = uuid4()
    await repo.list(user, status="ready")
    q = _norm(pool.conn.query)
    # user_id $1, status $2, fetch_limit $3
    assert "AND NOT is_archived AND extraction_status = $2" in q
    assert pool.conn.params == (user, "ready", 51)
