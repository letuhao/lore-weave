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


#: The value a scenario puts in a seed_assert's `db` to address the GRAPH instead of a
#: Postgres database. Chosen to match what `store_snapshot` already calls that store.
GRAPH_DB = "neo4j"


def _neo4j_password() -> str:
    """Read the graph password from the service that owns the connection.

    Deliberately not a new env var or a config constant: the credential already exists in the
    running container, and a second place to configure it is a second place for it to be wrong.
    """
    out = subprocess.run(
        ["docker", "exec", "infra-knowledge-service-1", "printenv", "NEO4J_PASSWORD"],
        capture_output=True, text=True, timeout=60,
    )
    return out.stdout.strip()


def cypher_query(cypher: str) -> list[list[str]]:
    """Run a read-only Cypher query against the graph; same row/cell shape as `db_query`.

    🔴 D-SEED-ASSERT-CANNOT-ADDRESS-THE-GRAPH. A scenario's `seed_assert` ran `psql` against a
    named Postgres database, and facts, entities and events live in NEO4J — so an assertion over
    them could not be written at all. Hit 2026-08-26 writing scenarios-c-factsearch.json: the
    harness refused the batch with `db_query failed (neo4j): psql: ... database "neo4j" does not
    exist`.

    THE REFUSAL WAS CORRECT and was never the defect — a scenario whose assertion cannot execute
    measures nothing, and declining to start is the right call. The defect was that a whole class
    of seeded state could not be preflighted, so a graph-seeded scenario ran with no guard that
    its seed had landed.

    The output shape is what makes this a drop-in: cypher-shell `--format plain` prints a header
    line then the rows, exactly like psql's `-tA`, so a scalar comparison needs no new rule —
    which was the open question recorded on the row.
    """
    pw = _neo4j_password()
    if not pw:
        raise RuntimeError(
            "cypher_query: could not read NEO4J_PASSWORD from infra-knowledge-service-1 — the "
            "graph is unreachable, so a seed assertion over it cannot be checked (and must not "
            "be reported as passing)")
    out = subprocess.run(
        ["docker", "exec", "-i", "infra-neo4j-1", "cypher-shell", "-u", "neo4j", "-p", pw,
         "--format", "plain", cypher],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60,
    )
    if out.returncode != 0:
        # 🔴 STRIP THE JVM NOISE OR THE MESSAGE NAMES THE WRONG THING. cypher-shell prints four
        # lines of "WARNING: A restricted method in java.lang.System has been called" to stderr
        # on every invocation, and a bare [:400] truncation shows ONLY those — so a syntax error
        # in the caller's Cypher arrives as a Java module warning, pointing the reader at the
        # JVM instead of at their query. Measured the first time this path was exercised.
        noise = ("WARNING:", "warning:")
        real = [ln for ln in out.stderr.splitlines()
                if ln.strip() and not ln.lstrip().startswith(noise)]
        raise RuntimeError(f"cypher_query failed: {' '.join(real).strip()[:400] or out.stderr.strip()[:200]}")
    lines = [ln.strip() for ln in out.stdout.splitlines()
             if ln.strip() and not ln.startswith("WARNING")]
    # plain format prints the column header first; a scalar query yields header + one value.
    return [[c.strip().strip('"')] for c in lines[1:]] if len(lines) >= 2 else []


def db_query(dbname: str, sql: str) -> list[list[str]]:
    """Run a read-only query and return rows as lists of string cells.

    `dbname="neo4j"` addresses the GRAPH and `sql` is Cypher — routed here rather than at each
    call site so that BOTH seed-assert paths get it from one place: `preflight_seed_asserts`
    (which checks every query once before the batch spends a turn) and `assert_seeded` (which
    runs it per-run against the real fixture). Two dispatches would be two chances to diverge.
    """
    if dbname == GRAPH_DB:
        return cypher_query(sql)
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
