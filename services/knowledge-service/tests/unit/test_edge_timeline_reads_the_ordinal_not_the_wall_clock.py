"""TOOLV2 LOOP #250 — the timeline tool returned a timeline with no time in it.

`kg_entity_edge_timeline` promises "the ordered temporal chain of one relationship type for a
single entity … Returns the full arc, including closed (superseded) instances."

Measured live on 紂王 / "commands":

    tool response   -> total 14, returned 14, valid_from non-null: 0, valid_to non-null: 0
    Neo4j, same pair-> 14 edges, 14 with valid_from_ordinal, 13 CLOSED (valid_to_ordinal set)

Every row came back. Every row came back looking identical — undated and open. A caller could not
tell the thirteen superseded instances from the one that is still true, which is the only question
a "drive arc" is asked.

The cause is a field-name mismatch in `build_timeline`, which read the bare properties:

    valid_from=_coerce_ordinal(rel.get("valid_from")),   # a wall-clock datetime
    valid_to=_coerce_ordinal(rel.get("valid_to")),       # not a property at all

F3's ordinal model (neo4j_repos/temporal.py) puts the narrative interval in
`valid_from_ordinal` / `valid_to_ordinal` (null ⇒ open), with `valid_to_ordinal_eff` as the
INT64_MAX-sentinel mirror for index-served range queries. `_coerce_ordinal` deliberately returns
None for anything non-int — a guard written against legacy `valid_until` datetimes — so feeding it
a datetime nulled the value silently.

Graph-wide, this never worked once:

    1142 RELATES_TO edges | 1142 have valid_from | 0 of those are int-like
                          |  866 have valid_from_ordinal | 222 are closed

A 100% failure rate with a green suite, because nothing asserted the field was populated. The
ORDER BY had the same mismatch (`coalesce(r.valid_from, 2147483647)`), so the chain was ordered by
when the extractor happened to write each edge rather than by narrative position — and against
INT32_MAX where the documented null-sink for this scale is INT64_MAX.

The Pydantic model was never in doubt about the intent: `valid_from: int | None`. An int is an
ordinal. It was being handed a datetime.

`build_timeline` and `_TIMELINE_CYPHER` are shared by the MCP tool and the HTTP route, so the fix
lands on both surfaces at once.
"""

from pathlib import Path

# T17 SPLIT THIS FILE IN TWO. The row BUILDER still lives in the public router; the timeline
# CYPHER moved to the repo module. One SRC could only ever check one of them, and pointing
# it at either alone makes the other assertion pass vacuously against the wrong text.
SRC = Path(__file__).resolve().parents[2] / "app" / "routers" / "public" / "graph_views.py"
REPO_SRC = Path(__file__).resolve().parents[2] / "app" / "db" / "graph_repos" / "graph_views.py"


def _repo_body() -> str:
    """The timeline CYPHER, which T17 moved out of the router."""
    return REPO_SRC.read_text(encoding="utf-8").replace('\r\n', '\n')


def _body() -> str:
    return SRC.read_text(encoding="utf-8").replace("\r\n", "\n")


def test_the_builder_reads_the_ordinal_properties():
    body = _body()
    assert 'valid_from=_coerce_ordinal(rel.get("valid_from_ordinal"))' in body, (
        "the builder reads the bare valid_from again — a datetime, which _coerce_ordinal "
        "nulls on every edge in the graph"
    )
    assert 'valid_to=_coerce_ordinal(rel.get("valid_to_ordinal"))' in body


def test_the_builder_does_not_read_the_bare_temporal_properties():
    """Named separately from the positive assertion: a future edit could add the ordinal read
    while leaving a bare fallback that silently wins."""
    body = _body()
    start = body.index("def build_timeline(")
    fn = body[start: body.index("\nasync def ", start)]
    assert 'rel.get("valid_from")' not in fn, "the wall-clock datetime is back in the builder"
    assert 'rel.get("valid_to")' not in fn, (
        "valid_to is not a property on these edges at all — 0 of 1142 carry it; the closed "
        "interval is valid_to_ordinal"
    )


def test_the_chain_is_ordered_by_narrative_position_not_extraction_time():
    body = _repo_body()          # T17 — the Cypher moved; the builder did not
    assert "ORDER BY coalesce(r.valid_from_ordinal, 9223372036854775807) ASC" in body, (
        "the timeline orders by wall-clock valid_from again — that is the order the extractor "
        "wrote the edges in, not the order they happen in the story"
    )
    assert "coalesce(r.valid_from, 2147483647)" not in body, (
        "2147483647 is INT32_MAX; temporal.py documents INT64_MAX as the null-sink for this "
        "scale, and mixing the two lets the sentinels drift apart"
    )


def test_the_coercion_docstring_no_longer_states_a_false_premise():
    """It claimed `valid_from`/`valid_to` are ints. Measured: 0 of 1142 are. The docstring is
    what made the mismatch look correct to anyone reading the call site."""
    body = _body()
    start = body.index("def _coerce_ordinal(")
    doc = body[start: body.index('"""', body.index('"""', start) + 3) + 3]
    assert "`valid_from`/`valid_to` are chapter ordinals stored as ints" not in doc
    assert "valid_from_ordinal`/`valid_to_ordinal` are chapter ordinals" in doc
    assert "never the bare ones" in doc, (
        "the docstring must warn the next caller off the exact mistake, or it recurs"
    )


def test_the_model_still_types_these_as_ordinals():
    """If the contract ever becomes a datetime, the fix above is wrong rather than right."""
    body = _body()
    start = body.index("class TimelineInstance(BaseModel):")
    model = body[start: body.index("class EdgeTimeline", start)]
    assert "valid_from: int | None" in model
    assert "valid_to: int | None" in model
