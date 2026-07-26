"""Effect oracle — independently verify a tool's claimed effect actually persisted.

This is what catches the "silent success" bug class: a tool that returns
`{"ok": true}` and writes NOTHING must FAIL the eval. Per CD3's anti-oracle rule,
the read-back goes through a DIFFERENT path than the write — here, the domain's
Postgres DB read DIRECTLY (via the postgres container), never the domain's own read
tool, so a shared bug can't make both agree.

Read tools (tier R) don't mutate; their G4 asserts the result is consistent with
the seeded fixture (handled in the probe's own `oracle` callable, not here).
"""
from __future__ import annotations

import subprocess

from . import config


def db_query(dbname: str, sql: str) -> list[list[str]]:
    """Run a read-only SQL query in the postgres container; return rows as lists of
    string cells. Uses `-tAF|` (tuples-only, unaligned, pipe-separated)."""
    cmd = [
        "docker", "exec", config.PG_CONTAINER,
        "psql", "-U", config.PG_USER, "-d", dbname,
        "-tAF", "|", "-c", sql,
    ]
    out = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if out.returncode != 0:
        raise RuntimeError(f"db_query failed ({dbname}): {out.stderr.strip()[:400]}")
    rows = []
    for line in out.stdout.splitlines():
        line = line.rstrip("\n")
        if line == "":
            continue
        rows.append(line.split("|"))
    return rows


def scalar(dbname: str, sql: str) -> str | None:
    rows = db_query(dbname, sql)
    if rows and rows[0]:
        return rows[0][0]
    return None


def count(dbname: str, sql_where_table: str) -> int:
    """count(*) helper: pass the FROM/WHERE tail, e.g. "books WHERE id='...'"."""
    v = scalar(dbname, f"SELECT count(*) FROM {sql_where_table}")
    return int(v) if v is not None else 0


# ── Convenience oracles for the P0 probe set ──────────────────────────────────
def _q(v: str) -> str:
    return v.replace("'", "''")


def book_row(book_id: str) -> dict | None:
    db = config.DOMAIN_DB["book"]
    rows = db_query(db, f"SELECT title, description FROM books WHERE id='{_q(book_id)}'")
    if not rows:
        return None
    return {"title": rows[0][0], "description": rows[0][1] if len(rows[0]) > 1 else None}


def chapter_row(chapter_id: str) -> dict | None:
    db = config.DOMAIN_DB["book"]
    rows = db_query(
        db,
        "SELECT title, lifecycle_state, published_revision_id, trashed_at "
        f"FROM chapters WHERE id='{_q(chapter_id)}'",
    )
    if not rows:
        return None
    r = rows[0] + [""] * (4 - len(rows[0]))
    return {"title": r[0], "lifecycle_state": r[1],
            "published_revision_id": r[2] or None, "trashed_at": r[3] or None}


def glossary_entity_count(book_id: str, alive: bool | None = None) -> int:
    db = config.DOMAIN_DB["glossary"]
    where = f"glossary_entities WHERE book_id='{_q(book_id)}'"
    if alive is not None:
        where += f" AND alive={'true' if alive else 'false'}"
    return count(db, where)


def glossary_entity_alive(entity_id: str) -> bool | None:
    db = config.DOMAIN_DB["glossary"]
    v = scalar(db, f"SELECT alive FROM glossary_entities WHERE entity_id='{_q(entity_id)}'")
    if v is None:
        return None
    return v.strip().lower() in ("t", "true")


def glossary_entity_names(book_id: str) -> list[str]:
    db = config.DOMAIN_DB["glossary"]
    rows = db_query(
        db, f"SELECT cached_name FROM glossary_entities WHERE book_id='{_q(book_id)}' AND alive=true")
    return [r[0] for r in rows if r and r[0]]


def book_kind_exists(book_id: str, code: str) -> bool:
    db = config.DOMAIN_DB["glossary"]
    return count(db, f"book_kinds WHERE book_id='{_q(book_id)}' AND code='{_q(code)}'") > 0
