"""D-SEED-ASSERT-CANNOT-ADDRESS-THE-GRAPH.

A scenario's `seed_assert` ran `psql` against a named Postgres database. Facts, entities and
events live in NEO4J, so an assertion over them could not be written at all — hit 2026-08-26
writing scenarios-c-factsearch.json, where the harness refused the batch with:

    db_query failed (neo4j): psql: error: ... database "neo4j" does not exist

THE REFUSAL WAS CORRECT AND WAS NEVER THE DEFECT. A scenario whose assertion cannot execute
measures nothing, and declining to start is the right call. The defect was that a whole class of
seeded state could not be preflighted, so a graph-seeded scenario ran with no guard that its
seed had landed — and a seed is a claim about the world.

`db: "neo4j"` now routes to cypher-shell inside `oracle.db_query`, which is the ONE place both
seed-assert paths go through: `preflight_seed_asserts` (every query once, before the batch
spends a turn) and `assert_seeded` (per-run, against the real fixture). Dispatching at each call
site would have been two chances to diverge.
"""
from __future__ import annotations

import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "toolloop"))

from scripts.eval.tool_liveness import oracle  # noqa: E402

pytestmark = pytest.mark.skipif(
    not (ROOT / "infra").exists(), reason="needs the local stack"
)


def test_the_graph_is_addressable_at_all():
    """The defect verbatim: `db='neo4j'` used to reach psql and die."""
    rows = oracle.db_query("neo4j", "MATCH (f:Fact) RETURN count(f);")
    assert rows and rows[0], "a scalar Cypher query returned nothing"
    assert rows[0][0].isdigit(), f"expected a scalar count, got {rows[0]!r}"


def test_it_returns_the_SAME_SHAPE_as_a_postgres_scalar():
    """This is what makes it a drop-in. `assert_seeded` compares `rows[0][0]` against `expect`
    as a string — the open question recorded on the row was whether a Cypher scalar needs a
    different comparison rule. It does not."""
    pg = oracle.db_query("loreweave_knowledge", "SELECT count(*) FROM kg_triage_items;")
    gr = oracle.db_query("neo4j", "MATCH (f:Fact) RETURN count(f);")
    assert isinstance(pg[0][0], str) and isinstance(gr[0][0], str)
    assert len(pg[0]) == len(gr[0]) == 1


def test_postgres_is_UNTOUCHED():
    """PRECISION. The dispatch must not swallow an ordinary database name — every existing
    seed_assert in the corpus goes through this same function."""
    rows = oracle.db_query("loreweave_knowledge", "SELECT 1;")
    assert rows == [["1"]], rows


def test_a_bad_cypher_query_RAISES_rather_than_reporting_zero():
    """The whole value of a seed assertion is refusing to start. A graph reader that swallowed a
    syntax error and returned [] would make every assertion over it read as 'expected 1, store
    says ""' — a wrong diagnosis pointing at the fixture instead of at the query."""
    with pytest.raises(RuntimeError) as e:
        oracle.db_query("neo4j", "MATCH (f:Fact RETURN count(f);")
    assert "cypher_query failed" in str(e.value)


def test_an_unreachable_graph_is_not_silently_clean():
    """A missing password must not read as an empty graph — that would turn 'the graph is down'
    into 'your seed did not land', which is the same class of lie the snapshot's own comment
    warns about ('a snapshot whose silence is read as nothing happened')."""
    import unittest.mock as mock

    with mock.patch.object(oracle, "_neo4j_password", return_value=""):
        with pytest.raises(RuntimeError) as e:
            oracle.cypher_query("MATCH (f:Fact) RETURN count(f);")
    assert "unreachable" in str(e.value).lower()


def test_there_is_only_ONE_graph_reader():
    """The row's own instruction was to reuse the existing helper 'rather than adding a second
    way to reach the graph'. store_snapshot._neo4j had its own inline cypher-shell call; it now
    calls oracle.cypher_query. If a second `cypher-shell` subprocess appears anywhere in the
    harness, this fails."""
    # SCOPED TO THE HARNESS, and the first version of this bar was not. It asserted that nothing
    # under scripts/ shells out to the graph except oracle, which was never true and is not this
    # defect's subject: scripts/seed_fengshen_demo.py is a one-off DEMO SEEDER, outside the
    # measurement path entirely. Narrowed rather than deleted, and the exclusion is named here
    # instead of being silently absent.
    #
    # memory_forget_idempotency_probe.py IS in the harness and did have its own reader — with
    # the password HARDCODED — so it was unified rather than excused.
    harness = [ROOT / "scripts" / "toolloop", ROOT / "scripts" / "eval"]
    hits = []
    for base in harness:
        for p in base.rglob("*.py"):
            if p.name.startswith("test_"):
                continue
            # Strip comments first. The comment explaining THIS fix names cypher-shell, and a
            # scan that cannot tell a comment from a call would forbid documenting the defect
            # it guards — the third time today that distinction has mattered.
            code = "\n".join(
                ln for ln in p.read_text(encoding="utf-8", errors="ignore").splitlines()
                if not ln.lstrip().startswith("#")
            )
            if "cypher-shell" in code:
                hits.append(p.relative_to(ROOT).as_posix())
    assert hits == ["scripts/eval/tool_liveness/oracle.py"], (
        f"more than one place in the HARNESS shells out to the graph: {hits}"
    )


def test_no_harness_file_hardcodes_the_graph_password():
    """Found while narrowing the bar above: the idempotency probe carried the password in the
    tree. The reader now asks the container that owns the connection."""
    for base in (ROOT / "scripts" / "toolloop", ROOT / "scripts" / "eval"):
        for p in base.rglob("*.py"):
            if p.name.startswith("test_"):
                continue
            src = p.read_text(encoding="utf-8", errors="ignore")
            assert "loreweave_dev_neo4j" not in src, f"{p} hardcodes the graph password"


def test_the_snapshot_still_reads_the_graph_through_it():
    """store_snapshot runs on EVERY batch; unifying the reader must not have cost it its graph
    counts, which are the only view the Postgres sweep cannot provide."""
    import store_snapshot as ss

    snap = ss.snapshot(book_id=None, project_id=None)
    assert "neo4j.Fact.total" in snap, snap
    assert snap["neo4j.Fact.total"]["rows"] >= 0
