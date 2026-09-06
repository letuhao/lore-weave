"""D-SNAPSHOT-IS-BLIND-TO-AN-IN-PLACE-EDIT-WITH-NO-UPDATED-AT
   + D-IDEMPOTENCY-PROBE-IS-BLIND-TO-NEO4J-OWNED-TOOLS.

ONE CAUSE, and both rows say so: "the same warning, two different blind spots, and neither is
the tool being quiet."

    THE INVARIANT. An axis the snapshot cannot see a MUTATION on must report itself BLIND.
    "Unchanged" for a table it can only see CREATIONS in is not a weaker answer than the truth,
    it is the OPPOSITE of it — and the probe then prints STRICTLY IDEMPOTENT.

TWO MEASURED INSTANCES, both verdicts inverted:

    divergence_spec   taxonomy went `au` -> `character_transform` on the first call and the
                      store diff was {}. Columns: id, created_by, project_id, book_id, work_id,
                      taxonomy, pov_anchor, canon_rule, created_at. No updated_at, so max()
                      over the only timestamp is the CREATION time.
    memory_forget     re-stamps `valid_until` on an EXISTING Fact. The graph axis counted nodes
                      and nothing else, so the count held and the probe said the second call
                      "touched nothing at all".

BOTH MECHANISMS ALREADY EXISTED AND WERE MERELY EMPTY, which is the first thing METHOD says to
check. The Postgres sweep folds in every timestamptz column the table HAS — divergence_spec
simply has no mutating one. The graph carries `updated_at` on all 455 Fact nodes and
`valid_until` on 25, and the axis read neither.

WHY THE BLIND LIST IS NOT "TABLES WITHOUT updated_at". That would name 16 tables, of which 8
are append-only — `entity_revisions`, `extraction_batch_outcomes`, `translation_chapter_memos`
— where a row count is entirely sufficient. A blind list that is half false positives gets
ignored, and an ignored refusal is the same as no refusal. So blindness is (no mutation
timestamp) AND (something in services/ actually UPDATEs it): 8 of 78 book-scoped tables.
"""
from __future__ import annotations

import json
import pathlib
import subprocess
import sys

import pytest

import sys as _sys, pathlib as _pathlib
_sys.path.insert(0, str(_pathlib.Path(__file__).resolve().parent))
import live_stack  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "toolloop"))
sys.path.insert(0, str(ROOT / "scripts"))

import blind_axes as ba  # noqa: E402
import store_snapshot as ss  # noqa: E402

# 🔴 THE OLD GUARD COULD NOT SKIP IN CI. `(ROOT / "infra").exists()` is true in every
# checkout (the directory is committed) and `docker ps` succeeds on every GitHub runner, so
# both proxies were TRUE where there is no stack at all. 22 red-ability proofs ran on the
# runner and failed with `could not read NEO4J_PASSWORD`, `SnapshotUnavailable`,
# `httpx.ConnectError` and `psql failed` -- every one of them saying only "no stack here".
# `live_stack.up()` probes the thing itself, via the anchor gate-wiring-gate already uses.
pytestmark = pytest.mark.skipif(not live_stack.up(), reason=live_stack.REASON)

GUARD_FACT = "zz-blind-axis-guard-fact"


def _sql(db: str, q: str) -> str:
    return subprocess.run(
        ["docker", "exec", "-i", "infra-postgres-1", "psql", "-U", "loreweave", "-d", db,
         "-At", "-c", q], capture_output=True, text=True).stdout.strip()


# ── the Postgres half ────────────────────────────────────────────────────────────────────

def test_the_measured_table_really_has_no_mutation_timestamp():
    """ANTI-VACUITY, and the fact the row was written from. If divergence_spec grows an
    updated_at, this whole file's premise changes and it must be re-derived, not quietly
    kept."""
    cols = _sql("loreweave_composition",
                "SELECT string_agg(column_name, ',' ORDER BY column_name) "
                "FROM information_schema.columns WHERE table_name='divergence_spec' "
                "AND data_type LIKE 'timestamp%';")
    assert cols == "created_at", f"divergence_spec's timestamps are now {cols!r}"


def test_the_blind_list_holds_the_measured_table():
    assert "loreweave_composition.divergence_spec" in ba.blind_axes()


def test_an_APPEND_ONLY_table_is_NOT_called_blind():
    """PRECISION — the half that keeps the list worth reading. These have no updated_at either,
    and a row count sees everything that ever happens to them."""
    known = ba.blind_axes()
    for t in ("loreweave_glossary.entity_revisions",
              "loreweave_translation.extraction_batch_outcomes",
              "loreweave_book.user_favorites"):
        assert t not in known, f"{t} is append-only; calling it blind makes the list noise"


def test_the_derivation_still_discriminates():
    """🔴 THE LIST IS DERIVED, SO THE DERIVATION IS WHAT HAS TO BE GUARDED. A predicate that
    returned everything, or nothing, would produce a file that looks identical to a reader."""
    d = ba.derive()
    assert d["considered"] >= 70, f"only {d['considered']} book-scoped tables seen"
    assert 1 <= d["count"] < d["considered"] // 4, (
        f"{d['count']} of {d['considered']} blind — that is not a discrimination"
    )
    assert set(d["axes"]) == ba.blind_axes(), (
        "contracts/data-bar-blind-axes.json is stale — re-run "
        "`python scripts/toolloop/blind_axes.py`"
    )


def test_the_update_check_is_real():
    """The second half of the predicate, on a table each way."""
    assert ba.is_updated_in_place("divergence_spec")
    assert not ba.is_updated_in_place("zz_no_such_table_anywhere")


def test_blind_in_scope_reads_the_snapshot_keys():
    """Keys carry a scope suffix (`.run`, `.owner`), so the axis is the first two segments."""
    assert ba.blind_in_scope({"loreweave_composition.divergence_spec": {"rows": 2}}) == [
        "loreweave_composition.divergence_spec"]
    assert ba.blind_in_scope({"loreweave_composition.scene_link.run": {"rows": 1}}) == [
        "loreweave_composition.scene_link"]
    assert ba.blind_in_scope({"loreweave_book.chapters": {"rows": 9}}) == []


# ── the graph half ───────────────────────────────────────────────────────────────────────

@pytest.fixture
def guard_fact():
    from eval.tool_liveness import oracle
    oracle.cypher_query(f"MATCH (f:Fact {{id: '{GUARD_FACT}'}}) DETACH DELETE f;")
    yield oracle
    oracle.cypher_query(f"MATCH (f:Fact {{id: '{GUARD_FACT}'}}) DETACH DELETE f;")


def test_the_graph_axis_SEES_an_in_place_edit(guard_fact):
    """THE DEFECT ITSELF, on a node this test creates and removes. `memory_forget` moves
    `valid_until` on an existing fact: the node count does not move, so a count-only axis
    reports silence. This is the discrimination the old axis could not make."""
    oracle = guard_fact
    oracle.cypher_query(
        f"CREATE (f:Fact {{id: '{GUARD_FACT}', content: 'zz', "
        f"updated_at: '2020-01-01T00:00:00Z'}});")
    before = ss._neo4j(None)
    oracle.cypher_query(
        f"MATCH (f:Fact {{id: '{GUARD_FACT}'}}) SET f.valid_until = '2026-08-27T00:00:00Z';")
    after = ss._neo4j(None)
    assert before["neo4j.Fact.total"]["rows"] == after["neo4j.Fact.total"]["rows"], (
        "the node count moved — this is not the in-place case the defect is about"
    )
    assert ss.diff(before, after), "the graph axis still cannot see an in-place invalidation"
    assert after["neo4j.Fact.invalidated"]["rows"] == before["neo4j.Fact.invalidated"]["rows"] + 1


def test_the_graph_axis_carries_a_real_timestamp():
    """It was `latest: '-'` on every key, which is what made it count-only."""
    snap = ss._neo4j(None)
    assert snap["neo4j.Fact.total"]["latest"] not in ("-", "", None), snap
    assert snap["neo4j.Fact.total"]["latest"].startswith("20")


def test_an_unchanged_graph_stays_silent():
    """PRECISION. A timestamp that moves on its own would make every run report a graph write."""
    assert not ss.diff(ss._neo4j(None), ss._neo4j(None))


# ── the refusal, which is what both rows asked for ───────────────────────────────────────

def test_the_probe_REFUSES_a_verdict_when_a_blind_axis_is_in_scope():
    """`fix_direction`, verbatim from the Neo4j row: "a named refusal beats a confident wrong
    answer, which is the rule the whole gate is built on"."""
    src = (ROOT / "scripts" / "toolloop" / "idempotency_probe.py").read_text(encoding="utf-8")
    at = src.index('out["first_had_effect"] = bool(')
    seg = src[at:at + 1600]
    assert "blind_in_scope(mid)" in seg, "the probe never asks which axes are blind"
    assert "CANNOT SEE IT" in seg, "there is no refusal, only a verdict"
    assert 'if blind and not out["diff_second"]' in seg, (
        "the refusal is not conditioned on an EMPTY diff — a measured duplication is still real "
        "when an unrelated blind table happens to be in scope, and overwriting that verdict "
        "would trade one wrong answer for another"
    )


def test_the_refusal_is_scoped_to_mid_not_before():
    """`snapshot()` omits a zero-row table, so a blind table the FIRST call populated is only in
    scope from `mid` — which is exactly when its edits go dark."""
    src = (ROOT / "scripts" / "toolloop" / "idempotency_probe.py").read_text(encoding="utf-8")
    assert "blind_in_scope(mid)" in src and "blind_in_scope(before)" not in src


def test_the_contract_is_derived_not_typed():
    c = json.loads(ba.CONTRACT.read_text(encoding="utf-8"))
    assert c["_derived_by"] == "python scripts/toolloop/blind_axes.py"
    assert c["count"] == len(c["axes"])
