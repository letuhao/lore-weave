"""TOOLV2 LOOP #251 — one tool, two response shapes, depending on how the read went.

kg_multi_query is correct on everything it advertises. Measured live:

    two owned projects        -> partitions_read 2, unreadable 0, 180 nodes / 262 edges
    Neo4j truth, same two     -> 151 + 29 = 180
    one owned + one not       -> partitions_read 1, unreadable 1, only the owned partition's
                                 nodes present (checked via each node's source_project_id)
    unify="by_name"           -> adds unification_clusters / bridge_edges / disagreements /
                                 unify_method / unify_capped, node+edge counts unchanged

A note on how nearly this became a false report: my first two probes both came back
"read 1, unreadable 1" on project ids I believed I owned. The tool was right — only ONE of the
three ids I had picked exists in `knowledge_projects` at all. The other two appear on Neo4j
entities carrying my user_id but have no project row, so they are orphaned graph partitions, not
projects of mine. Checking the table before filing is what turned a defect into a confirmation.

What IS wrong is the shape. The all-unreadable path is a deliberate early return ("empty-but-
honest", EC-B2) and returns good information — but it omitted `meta` and `node_cap_hit`, which
every other outcome of the same tool includes. Measured keys:

    read >= 1  -> [edges, meta, node_cap_hit, nodes, partitions_read, partitions_unreadable]
    read == 0  -> [edges, nodes, note, partitions_read, partitions_unreadable]

The tool's own `detail` parameter tells the caller "Result `meta` reports total/returned/
truncated". So `result["meta"]["truncated"]` raises KeyError precisely when every requested
partition was unreadable — the case a defensive caller is most likely to be probing for.

Zeros are the honest answer for an empty union. An absent key is not.
"""

from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "app" / "tools" / "graph_schema_tools.py"


def _empty_branch() -> str:
    body = SRC.read_text(encoding="utf-8").replace("\r\n", "\n")
    start = body.index("none of the requested projects are readable by you")
    return body[start: body.index("async with neo4j_session()", start)]


def _world_empty_branch() -> str:
    body = SRC.read_text(encoding="utf-8").replace(chr(13), "")
    start = body.index("this world has no KG partitions you can read")
    return body[start: body.index("async with neo4j_session()", start)]


def test_BOTH_empty_returns_carry_meta():
    """#307 CORRECTION — #251 fixed kg_multi_query's empty return and left kg_world_query's,
    in the SAME FILE, with the same shape. Measured: a real (empty) world returned meta None.

    Asserting over BOTH branches by name, because fixing the handler under test and leaving its
    twin is the failure this loop has now repeated five times."""
    for label, branch in (("multi_query", _empty_branch()), ("world_query", _world_empty_branch())):
        assert '"meta": {' in branch, f"{label}: the empty return dropped meta again"
        assert '"node_cap_hit": False' in branch, f"{label}: node_cap_hit missing"
        assert '"truncated": False' in branch, f"{label}: an empty result is complete, not cut short"
        assert '"detail": args.detail' in branch, f"{label}: detail must be echoed, not hardcoded"


def test_the_empty_union_still_carries_meta():
    branch = _empty_branch()
    assert '"meta": {' in branch, (
        "the all-unreadable early return dropped `meta` again — the same tool now answers with "
        "two different shapes depending on the outcome"
    )
    for field in ("nodes_total", "nodes_returned", "edges_total", "edges_returned", "truncated"):
        assert f'"{field}"' in branch, f"meta is missing {field}, which the detail contract names"


def test_the_empty_meta_reports_zeros_and_not_truncated():
    """An empty union is complete, not cut short. Reporting truncated=True (or omitting it and
    letting a caller default to None-is-falsy by luck) would say the opposite."""
    branch = _empty_branch()
    assert '"truncated": False' in branch
    assert '"nodes_total": 0' in branch
    assert '"node_cap_hit": False' in branch, (
        "the populated path always sets node_cap_hit; leaving it off here means a caller "
        "reading it gets None on one path and a bool on the other"
    )


def test_the_detail_is_echoed_rather_than_hardcoded():
    """meta.detail on the populated path comes from the caller's argument. Hardcoding
    'summary' here would misreport what was asked for."""
    assert '"detail": args.detail' in _empty_branch()


def test_the_honest_note_survives():
    """The note is the useful half of this branch and predates the fix — it must not be lost
    while adding the missing keys."""
    branch = _empty_branch()
    assert '"note": note + "."' in branch
    assert "not owned or don't exist" in branch


def test_the_branch_still_returns_empty_collections():
    """The whole point is that an unreadable id is reported, never silently turned into someone
    else's data."""
    branch = _empty_branch()
    assert '"nodes": []' in branch
    assert '"edges": []' in branch
    assert '"partitions_read": 0' in branch
