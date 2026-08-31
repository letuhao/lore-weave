"""T42 — the Kuzu schema bootstrap, against a REAL Kuzu database.

Mirrors `test_age_bootstrap.py`: per-engine setup fails looking like a missing graph rather
than a missing setup step, so it is pinned by tests that actually run the engine.

⚠️ These use a THROWAWAY database — a fresh `tmp_path` directory per test. Kuzu is embedded, so
"throwaway" is a directory rather than a DSN, and there is no shared instance to protect. The
one thing that DOES bite is the file lock: a handle left open makes the next `Database(path)`
fail with `Could not set lock on file`, which reads like corruption. Hence `close_kuzu`, and
hence a test for it.

They SKIP when `kuzu` is not installed rather than failing: it is an optional dependency for
one T43 candidate, and the other two adapters must keep working on a host that never heard of
it. A skip that hides a real regression is the failure mode recorded elsewhere in this repo —
so `test_kuzu_is_declared_or_the_skip_is_honest` asserts the skip means what it says.
"""
from __future__ import annotations

import pytest

from app.db.kuzu_bootstrap import (
    KUZU_NODE_TABLES,
    KUZU_REL_TABLES,
    close_kuzu,
    ensure_schema,
    open_kuzu,
    schema_statements,
)

kuzu = pytest.importorskip("kuzu", reason="kuzu is an optional T43-candidate dependency")


@pytest.fixture
def store(tmp_path):
    db, conn = open_kuzu(str(tmp_path / "kg"))
    try:
        yield conn
    finally:
        close_kuzu(db, conn)


# ── the DDL itself ────────────────────────────────────────────────────────────────────────
def test_every_declared_table_exists_after_open(store):
    """The whole point of the module: after `open_kuzu`, a write must not meet
    `Table Entity does not exist`."""
    got = {r[1] for r in _rows(store, "CALL show_tables() RETURN *")}
    want = set(KUZU_NODE_TABLES) | {n for n, _, _ in KUZU_REL_TABLES}
    assert want <= got, f"missing after bootstrap: {sorted(want - got)}"


def test_the_ddl_is_idempotent(tmp_path):
    """Run on every boot, so it has to survive being run twice. A bootstrap that only works on
    an empty directory is one nobody can call again."""
    db, conn = open_kuzu(str(tmp_path / "kg"))
    try:
        assert ensure_schema(conn) == len(schema_statements())
        assert ensure_schema(conn) == len(schema_statements())  # second pass must not raise
    finally:
        close_kuzu(db, conn)


def test_a_declared_column_accepts_a_write_and_reads_back(store):
    store.execute("CREATE (:Entity {id:'e1', user_id:'u', name:'Kai', confidence:0.5, "
                  "source_types:['book_content']})")
    row = _rows(store, "MATCH (e:Entity) RETURN e.name, e.confidence, e.source_types")[0]
    assert row[0] == "Kai" and row[1] == 0.5 and list(row[2]) == ["book_content"]


def test_an_UNDECLARED_property_is_REFUSED(store):
    """🔴 The difference from the other two adapters, pinned. Neo4j and AGE accept a property
    nobody declared; Kuzu rejects it at bind time. An adapter written against the AGE shape
    fails on its FIRST write, and this is the assertion that says so out loud rather than
    letting someone discover it in a conformance run."""
    with pytest.raises(Exception, match="(?i)property|binder"):
        store.execute("MATCH (e:Entity) SET e.surprise = 'x'")


# ── the two semantics the DOMAIN depends on ───────────────────────────────────────────────
def test_TWO_relations_between_the_SAME_pair_both_survive(store):
    """🔴 "Kai betrayed Mira" and "Kai guards Mira" are two claims about one pair, and the
    predicate is edge DATA rather than the edge TYPE. An engine that collapsed them to one
    edge would silently lose half the canon — and would do it quietly, since the write
    succeeds."""
    _pair(store)
    for rid, pred in (("r1", "betrayed"), ("r2", "guards")):
        store.execute("MATCH (a:Entity),(b:Entity) WHERE a.id='a' AND b.id='b' "
                      f"CREATE (a)-[:RELATES_TO {{id:'{rid}', predicate:'{pred}'}}]->(b)")
    assert _rows(store, "MATCH ()-[r:RELATES_TO]->() RETURN count(r)")[0][0] == 2


def test_MERGE_on_the_predicate_is_idempotent(store):
    """`upsert_relation` is specified idempotent. If MERGE keyed on the predicate created a
    second edge, every re-extraction would multiply the graph."""
    _pair(store)
    for _ in range(2):
        store.execute("MATCH (a:Entity),(b:Entity) WHERE a.id='a' AND b.id='b' "
                      "MERGE (a)-[r:RELATES_TO {predicate:'betrayed'}]->(b) "
                      "ON MATCH SET r.confidence = 0.9 ON CREATE SET r.confidence = 0.5")
    rows = _rows(store, "MATCH ()-[r:RELATES_TO]->() RETURN count(r), max(r.confidence)")
    assert rows[0][0] == 1, "MERGE created a duplicate edge"
    assert rows[0][1] == 0.9, "ON MATCH did not run on the second pass"


def test_EVIDENCED_BY_spans_its_three_FROM_labels_in_one_table(store):
    """The AGE adapter parameterises `target_label`, so the edge leaves Entity, Event OR Fact.
    Kuzu needs those endpoint pairs declared up front; this asserts one un-labelled MATCH
    still sees them all, which is what the adapter's queries assume."""
    store.execute("CREATE (:Entity {id:'e', user_id:'u'})")
    store.execute("CREATE (:Fact {id:'f', user_id:'u'})")
    store.execute("CREATE (:ExtractionSource {id:'s', user_id:'u'})")
    for label in ("Entity", "Fact"):
        store.execute(f"MATCH (t:{label}),(s:ExtractionSource) "
                      "CREATE (t)-[:EVIDENCED_BY {job_id:'j'}]->(s)")
    assert _rows(store, "MATCH ()-[r:EVIDENCED_BY]->() RETURN count(r)")[0][0] == 2


# ── the lock, which is the deployment constraint T43 must weigh ───────────────────────────
def test_a_SECOND_handle_on_the_same_path_is_refused(tmp_path):
    """⚠️ Kuzu is EMBEDDED: one process may hold the database. This is not a defect to fix —
    it is the fact that decides whether Kuzu can be the engine at all, and it belongs in the
    suite so the bake-off cannot forget it. `knowledge-service` runs a bare uvicorn with no
    `--workers` today; nothing pins that, and `--workers 4` breaks Kuzu and nothing else."""
    path = str(tmp_path / "kg")
    db, conn = open_kuzu(path)
    try:
        with pytest.raises(Exception, match="(?i)lock|io"):
            kuzu.Database(path)
    finally:
        close_kuzu(db, conn)


def test_close_RELEASES_the_lock_so_the_path_can_be_reopened(tmp_path):
    """The other half, and the reason `close_kuzu` exists rather than leaving it to GC: a
    leaked handle makes the next open fail in a way that reads like corruption."""
    path = str(tmp_path / "kg")
    db, conn = open_kuzu(path)
    close_kuzu(db, conn)
    db2, conn2 = open_kuzu(path)          # must not raise
    try:
        assert _rows(conn2, "MATCH (e:Entity) RETURN count(e)")[0][0] == 0
    finally:
        close_kuzu(db2, conn2)


# ── helpers ───────────────────────────────────────────────────────────────────────────────
def _rows(conn, q: str) -> list[list]:
    res = conn.execute(q)
    out = []
    while res.has_next():
        out.append(res.get_next())
    return out


def _pair(conn) -> None:
    conn.execute("CREATE (:Entity {id:'a', user_id:'u', name:'Kai'})")
    conn.execute("CREATE (:Entity {id:'b', user_id:'u', name:'Mira'})")
