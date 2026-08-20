"""TOOLV2 LOOP #249 — "idempotent" read as "no-op", and it costs a 412.

kg_create_node does everything its description promises: the same name+kind returns the same
entity_id, a different kind makes a different node, and a kind outside the closed set is refused
with an error naming the value sent. Neo4j confirmed exactly one node per (name, kind).

But "Idempotent: the same name+kind returns the existing node" reads as a free call, and the same
description tells an agent to make it defensively ("Use this BEFORE kg_propose_edge when a
relationship's endpoint isn't in the graph yet"). It is not free. `_handle_kg_create_node`
delegates to the shared `merge_entity`, whose ON MATCH branch is unconditional:

    e.version = coalesce(e.version, 1) + 1,
    e.updated_at = datetime()

Measured live on one node, three calls: version 1 → 2 → 3.

`version` is not decorative. PATCH /v1/knowledge/entities/{id} requires If-Match (428 without it)
and 412s on mismatch. With a control, on the same entity and the same request body:

    read ETag W/"4"  ->  PATCH immediately                        -> 200
    read ETag W/"5"  ->  kg_create_node (same name+kind) -> PATCH -> 412

One "idempotent" call between the read and the write is the whole difference. An agent following
this tool's own advice can invalidate a human's in-flight edit.

The bump itself is NOT obviously wrong: merge_entity is shared with extraction, where folding new
evidence into a node genuinely is an update, and the frontend already accounts for the effect (a
kg_create_node must invalidate the cast/arc caches "else the next human rename 412s against an
unseen version"). What was missing is any of that reaching the caller. Whether the manual path
should skip the bump when nothing changed is DQ-22 — it touches extraction's semantics and is not
mine to decide.
"""

from pathlib import Path

APP = Path(__file__).resolve().parents[2] / "app"


def _read(rel: str) -> str:
    return APP.joinpath(rel).read_text(encoding="utf-8").replace("\r\n", "\n")


def test_create_node_does_not_call_itself_idempotent_without_qualification():
    """Both copies of the description — the live MCP registration and the OpenAI-schema list."""
    for rel in ("mcp/server.py", "tools/graph_schema_tools.py"):
        body = _read(rel)
        assert "Idempotent: the same name+kind returns the existing" not in body, (
            f"{rel}: the unqualified claim is back; measured, a re-run bumps version and 412s "
            "a concurrent PATCH"
        )
        assert "Idempotent in RESULT" in body, f"{rel}: the qualifier is missing"
        assert "it is a WRITE, not a no-op" in body, f"{rel}"


def test_the_description_names_the_consequence_not_just_the_mechanism():
    """'bumps the version' means nothing to a caller who does not know version gates PATCH. The
    412 is the part they can act on."""
    for rel in ("mcp/server.py", "tools/graph_schema_tools.py"):
        body = _read(rel)
        assert "will 412" in body, rel
        assert "Do not call it defensively" in body, (
            f"{rel}: the description recommends a defensive call BEFORE kg_propose_edge; it must "
            "also say when not to, or the advice and the hazard cancel out"
        )


def test_the_superseding_tool_carries_the_same_warning():
    """kg_add_nodes' own wording ('re-running adds no duplicates') was already precise — it never
    claimed a no-op — but it is the tool that replaces kg_create_node, so a caller migrating to it
    must not lose the warning."""
    body = _read("mcp/server.py")
    start = body.index('name="kg_add_nodes"')
    desc = body[start: body.index("meta=", start)]
    assert "adds no duplicates" in desc, "the accurate half must survive"
    assert "will 412" in desc


def test_the_merge_really_bumps_version_unconditionally():
    """If ON MATCH ever becomes conditional, the warning becomes the false statement and these
    guards would pin a new lie. Anchor to the Cypher."""
    body = _read("db/neo4j_repos/entities.py")
    start = body.index("_MERGE_ENTITY_CYPHER = ")
    cypher = body[start: body.index("ON MATCH SET", start) + 2000]
    assert "e.version = coalesce(e.version, 1) + 1" in cypher, (
        "merge_entity no longer bumps version unconditionally — re-check whether "
        "kg_create_node still invalidates a concurrent If-Match before trusting the warning"
    )
