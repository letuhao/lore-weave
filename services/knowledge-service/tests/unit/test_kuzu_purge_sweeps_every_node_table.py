"""T17 A31 — Kuzu's purge must sweep EVERY node table, derived from its own schema.

Kuzu is schema-full: a label is a TABLE, so there is no label-less `MATCH (n)` and the purge
has to name each one. Neo4j and AGE express the same operation as one property-scoped sweep
across the whole graph, so neither of them can go wrong this way and the
adapter-parameterised conformance suite cannot see it either — it creates entities, and an
adapter that swept only `Entity` would pass every rule in it.

The tempting constant is `PROJECT_GRAPH_LABELS`, which is four of these five. It governs what
a **re-extraction rebuild** may clear and deliberately excludes `Passage`; a project DELETE is
the other case entirely, because the owning row is already gone. Using the rebuild's list here
strands `EntityStatus` behind a purge that reports success — invisible, because the count it
returns would still be non-zero.
"""

from __future__ import annotations

import pytest

from app.adapters.kuzu_graph_store import KuzuGraphStore
from app.db.kuzu_bootstrap import KUZU_NODE_TABLES
from app.domain.graph_labels import PROJECT_GRAPH_LABELS


class _RecordingResult:
    def __init__(self, rows):
        self._rows = list(rows)

    def get_column_names(self):
        return ["c"]

    def has_next(self):
        return bool(self._rows)

    def get_next(self):
        return self._rows.pop(0)


class _RecordingConn:
    """Answers every count with 1 so the DELETE branch is always taken and recorded."""

    def __init__(self) -> None:
        self.queries: list[str] = []

    def execute(self, query, parameters=None):
        self.queries.append(query)
        return _RecordingResult([[1]] if "count(n)" in query else [])


@pytest.mark.asyncio
async def test_the_purge_sweeps_EVERY_node_table_kuzu_declares():
    conn = _RecordingConn()
    out = await KuzuGraphStore(conn).purge_project(project_id="p1")

    swept = {
        q.split("(n:", 1)[1].split(")", 1)[0]
        for q in conn.queries
        if "DETACH DELETE" in q
    }
    assert swept == set(KUZU_NODE_TABLES), (
        f"the purge swept {sorted(swept)} but Kuzu declares {sorted(KUZU_NODE_TABLES)} — a "
        f"table left out keeps its rows while the purge reports success"
    )
    assert out["nodes_deleted"] == len(KUZU_NODE_TABLES)


def test_the_REBUILD_list_is_not_the_PURGE_list___and_this_pins_the_difference():
    """The control that makes the test above mean something.

    If the two tuples were equal, sweeping `PROJECT_GRAPH_LABELS` would satisfy the assertion
    and the docstring's warning would be about nothing. They are not equal, and the difference
    is exactly the row that would strand.
    """
    missing = set(KUZU_NODE_TABLES) - set(PROJECT_GRAPH_LABELS)
    assert missing == {"EntityStatus"}, (
        f"the gap between the rebuild list and the schema changed to {missing} — re-read "
        f"which of the two a project DELETE should use before updating this number"
    )


@pytest.mark.asyncio
async def test_a_table_with_NOTHING_to_delete_is_not_swept():
    """The purge counts first and deletes only when it found something, so an empty table
    costs one count and no write. Without this, an adapter that issued a DETACH DELETE per
    table unconditionally would pass the test above while reporting `nodes_deleted` it never
    deleted."""

    class _EmptyConn(_RecordingConn):
        def execute(self, query, parameters=None):
            self.queries.append(query)
            return _RecordingResult([[0]] if "count(n)" in query else [])

    conn = _EmptyConn()
    out = await KuzuGraphStore(conn).purge_project(project_id="p1")
    assert out["nodes_deleted"] == 0
    assert not [q for q in conn.queries if "DETACH DELETE" in q]
