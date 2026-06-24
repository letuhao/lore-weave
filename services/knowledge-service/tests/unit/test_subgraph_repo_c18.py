"""C18 (G5) — repo-layer tests for get_project_subgraph.

These exercise the Cypher-binding contract WITHOUT a live Neo4j by
feeding a fake session that captures the cypher + params and returns a
canned record. The invariants under test (the adversary focus):

  - BOTH `$user_id` AND `$project_id` are bound on every call — no
    cross-user / cross-project bleed.
  - the node cap is enforced IN the query: the cypher LIMITs a node
    collection that is ORDERed deterministically (anchor_score,
    mention_count, id) BEFORE any edge traversal — not post-filtered.
  - limit/hops are clamped to the hard ceilings even for a direct repo
    caller (defence in depth past the route's Query(le=...)).
  - the project-wide vs ego-expansion (center) path selection.
  - result mapping: node_props → SubgraphNode, edge_props → SubgraphEdge
    (source=subject_id, target=object_id), with cap-hit detection.

The live proof that a real Cypher against the real graph returns capped
nodes+edges is the VERIFY-phase smoke (project 019eb683).
"""

from __future__ import annotations

import pytest

from app.db.neo4j_repos.relations import (
    SUBGRAPH_MAX_HOPS,
    SUBGRAPH_MAX_NODE_CAP,
    get_project_subgraph,
)

_USER = "u-1"
_PROJECT = "p-1"


class _FakeResult:
    def __init__(self, record):
        self._record = record

    async def single(self):
        return self._record


class _FakeSession:
    """Captures the last cypher + params; returns a canned record.

    Records ALL cypher strings + params seen (the ego path issues
    several queries: center lookup, per-hop steps, final assemble).
    """

    def __init__(self, record):
        self._record = record
        self.last_cypher: str | None = None
        self.last_params: dict | None = None
        self.cyphers: list[str] = []
        self.params: list[dict] = []

    async def run(self, cypher, /, **params):
        self.last_cypher = cypher
        self.last_params = params
        self.cyphers.append(cypher)
        self.params.append(params)
        return _FakeResult(self._record)


class _ScriptedSession:
    """Returns scripted records keyed by a substring of the cypher, so
    the multi-query ego path can be driven deterministically."""

    def __init__(self, routes):
        # routes: list of (substring, record) checked in order
        self._routes = routes
        self.cyphers: list[str] = []
        self.params: list[dict] = []

    async def run(self, cypher, /, **params):
        self.cyphers.append(cypher)
        self.params.append(params)
        for sub, rec in self._routes:
            if sub in cypher:
                return _FakeResult(rec)
        return _FakeResult(None)


def _record(node_props, edge_props):
    return {"node_props": node_props, "edge_props": edge_props}


# ── partition: both keys bound ───────────────────────────────────────


@pytest.mark.asyncio
async def test_binds_both_user_and_project():
    session = _FakeSession(_record([], []))
    await get_project_subgraph(
        session, user_id=_USER, project_id=_PROJECT,
    )
    assert session.last_params["user_id"] == _USER
    assert session.last_params["project_id"] == _PROJECT
    # the cypher itself references both partition keys
    assert "$user_id" in session.last_cypher
    assert "$project_id" in session.last_cypher
    # every Entity match in the project-wide path is scoped to both keys
    assert "n.user_id = user_id" in session.last_cypher
    assert "n.project_id = project_id" in session.last_cypher


# ── cap IN the query, deterministic order ────────────────────────────


@pytest.mark.asyncio
async def test_cap_is_in_query_with_deterministic_order():
    session = _FakeSession(_record([], []))
    await get_project_subgraph(
        session, user_id=_USER, project_id=_PROJECT, limit=50,
    )
    cypher = session.last_cypher
    # LIMIT on the seed-node collection (the cap) precedes the edge
    # OPTIONAL MATCH — i.e. nodes are capped BEFORE traversal, not after.
    limit_pos = cypher.index("LIMIT $limit")
    edge_pos = cypher.index("OPTIONAL MATCH")
    assert limit_pos < edge_pos, "node cap must precede edge traversal"
    # deterministic order: anchor_score DESC, mention_count DESC, id ASC
    assert "anchor_score" in cypher
    assert "mention_count" in cypher
    assert "ORDER BY" in cypher
    assert ".id ASC" in cypher
    assert session.last_params["limit"] == 50


@pytest.mark.asyncio
async def test_project_wide_edge_stage_binds_project_on_both_endpoints():
    """Adversary F2 — the edge stage must re-assert project_id on BOTH
    endpoints, not rely on seed-id confinement alone (defence in depth
    matching the 1-hop sibling)."""
    session = _FakeSession(_record([], []))
    await get_project_subgraph(
        session, user_id=_USER, project_id=_PROJECT,
    )
    cypher = session.last_cypher
    assert "a.project_id = $project_id" in cypher
    assert "b.project_id = $project_id" in cypher


@pytest.mark.asyncio
async def test_limit_clamped_to_ceiling():
    session = _FakeSession(_record([], []))
    await get_project_subgraph(
        session, user_id=_USER, project_id=_PROJECT,
        limit=SUBGRAPH_MAX_NODE_CAP + 999,
    )
    assert session.last_params["limit"] == SUBGRAPH_MAX_NODE_CAP


@pytest.mark.asyncio
async def test_hops_clamped_bounds_bfs_iterations():
    """Adversary F1 — hops is clamped to the ceiling AND each hop is a
    SEPARATE bounded query (frontier BFS), never one unbounded
    variable-length path enumeration. With a non-empty frontier the BFS
    must not issue more than SUBGRAPH_MAX_HOPS hop-step queries."""
    center_rec = {"id": "c1"}
    # every hop returns one fresh neighbour so the frontier never empties
    hop_rec = {"next_ids": ["n-extra"]}
    session = _ScriptedSession([
        ("RETURN c.id AS id", center_rec),
        ("RETURN collect(nbr.id) AS next_ids", hop_rec),
        ("RETURN node_props", _record([{"id": "c1", "name": "c", "kind": "k"}], [])),
    ])
    await get_project_subgraph(
        session, user_id=_USER, project_id=_PROJECT,
        center="c1", hops=SUBGRAPH_MAX_HOPS + 5,
    )
    hop_queries = [c for c in session.cyphers if "next_ids" in c]
    # clamped: at most SUBGRAPH_MAX_HOPS hop-step queries, never *1..N
    assert len(hop_queries) <= SUBGRAPH_MAX_HOPS
    assert all("RELATES_TO*" not in c for c in session.cyphers), \
        "ego path must not use unbounded variable-length expansion"


# ── ego: hub-safety, partition, active-edge consistency ──────────────


@pytest.mark.asyncio
async def test_ego_hop_step_is_bounded_and_partition_scoped():
    """The per-hop step caps its neighbour set (LIMIT $limit) and binds
    BOTH partition keys on the neighbour — so a hub's fan-out cannot
    explode the frontier and no foreign node is admitted (F1 + F2)."""
    center_rec = {"id": "c1"}
    session = _ScriptedSession([
        ("RETURN c.id AS id", center_rec),
        ("RETURN collect(nbr.id) AS next_ids", {"next_ids": []}),
        ("RETURN node_props", _record([], [])),
    ])
    await get_project_subgraph(
        session, user_id=_USER, project_id=_PROJECT, center="c1", hops=2,
    )
    hop_cypher = next(c for c in session.cyphers if "next_ids" in c)
    assert "LIMIT $limit" in hop_cypher, "hop step must cap its frontier"
    assert "nbr.user_id = $user_id" in hop_cypher
    assert "nbr.project_id = $project_id" in hop_cypher
    # active-edge consistency (F3): the SAME confidence/pending filter the
    # returned-edge stage uses must gate reachability (no orphan nodes).
    assert "coalesce(r.confidence, 0.0) >= $min_confidence" in hop_cypher
    assert "r.valid_until IS NULL" in hop_cypher


@pytest.mark.asyncio
async def test_ego_assemble_binds_project_on_both_endpoints():
    """Adversary F2 — the ego edge stage also re-asserts project_id on
    both endpoints."""
    center_rec = {"id": "c1"}
    session = _ScriptedSession([
        ("RETURN c.id AS id", center_rec),
        ("RETURN collect(nbr.id) AS next_ids", {"next_ids": []}),
        ("RETURN node_props", _record([{"id": "c1", "name": "c", "kind": "k"}], [])),
    ])
    await get_project_subgraph(
        session, user_id=_USER, project_id=_PROJECT, center="c1", hops=1,
    )
    assemble = next(c for c in session.cyphers if "node_props" in c and "OPTIONAL MATCH" in c)
    assert "a.project_id = $project_id" in assemble
    assert "b.project_id = $project_id" in assemble


@pytest.mark.asyncio
async def test_ego_missing_center_yields_empty():
    """A center that doesn't resolve (missing / cross-partition) yields
    an empty subgraph — no hop queries, no existence leak."""
    session = _ScriptedSession([
        ("RETURN c.id AS id", None),  # center not found
    ])
    sg = await get_project_subgraph(
        session, user_id=_USER, project_id=_PROJECT, center="nope", hops=2,
    )
    assert sg.nodes == []
    assert sg.edges == []
    assert not any("next_ids" in c for c in session.cyphers)


@pytest.mark.asyncio
async def test_no_center_selects_project_wide_path():
    session = _FakeSession(_record([], []))
    await get_project_subgraph(
        session, user_id=_USER, project_id=_PROJECT,
    )
    # project-wide cypher has no variable-length path
    assert "RELATES_TO*" not in session.last_cypher
    assert "center" not in (session.last_params or {})


# ── result mapping + cap-hit ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_maps_nodes_and_edges():
    node_props = [
        {"id": "e0", "name": "张若尘", "kind": "character",
         "anchor_score": 1.0, "mention_count": 420, "glossary_entity_id": "g0"},
        {"id": "e1", "name": "林妃", "kind": "character",
         "anchor_score": 0.5, "mention_count": 88},
    ]
    edge_props = [
        {"id": "r0", "subject_id": "e0", "object_id": "e1",
         "predicate": "ally_of", "confidence": 0.9},
    ]
    session = _FakeSession(_record(node_props, edge_props))
    sg = await get_project_subgraph(
        session, user_id=_USER, project_id=_PROJECT,
    )
    assert [n.id for n in sg.nodes] == ["e0", "e1"]
    assert sg.nodes[0].glossary_entity_id == "g0"
    assert sg.nodes[1].mention_count == 88
    assert len(sg.edges) == 1
    assert sg.edges[0].source == "e0"
    assert sg.edges[0].target == "e1"
    assert sg.edges[0].predicate == "ally_of"


@pytest.mark.asyncio
async def test_drops_malformed_edges():
    """An edge row missing subject_id/object_id is dropped (no dangling
    pointer), not surfaced as a broken edge."""
    node_props = [{"id": "e0", "name": "a", "kind": "character"}]
    edge_props = [
        {"id": "r0", "subject_id": "e0"},  # missing object_id → dropped
        {"id": "r1", "subject_id": "e0", "object_id": "e0",
         "predicate": "self", "confidence": 1.0},
    ]
    session = _FakeSession(_record(node_props, edge_props))
    sg = await get_project_subgraph(
        session, user_id=_USER, project_id=_PROJECT,
    )
    assert [e.id for e in sg.edges] == ["r1"]


@pytest.mark.asyncio
async def test_cap_hit_detection():
    node_props = [
        {"id": f"e{i}", "name": str(i), "kind": "character"} for i in range(10)
    ]
    session = _FakeSession(_record(node_props, []))
    sg = await get_project_subgraph(
        session, user_id=_USER, project_id=_PROJECT, limit=10,
    )
    # got exactly the cap → cap-hit true (there may be more)
    assert sg.node_cap_hit is True

    session2 = _FakeSession(_record(node_props, []))
    sg2 = await get_project_subgraph(
        session2, user_id=_USER, project_id=_PROJECT, limit=50,
    )
    # got fewer than the cap → whole partition fit, cap not hit
    assert sg2.node_cap_hit is False


@pytest.mark.asyncio
async def test_empty_record_yields_empty_subgraph():
    session = _FakeSession(None)
    sg = await get_project_subgraph(
        session, user_id=_USER, project_id=_PROJECT,
    )
    assert sg.nodes == []
    assert sg.edges == []
    assert sg.node_cap_hit is False


# ── input validation ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_rejects_empty_project():
    session = _FakeSession(_record([], []))
    with pytest.raises(ValueError):
        await get_project_subgraph(session, user_id=_USER, project_id="")


@pytest.mark.asyncio
async def test_rejects_nonpositive_limit():
    session = _FakeSession(_record([], []))
    with pytest.raises(ValueError):
        await get_project_subgraph(
            session, user_id=_USER, project_id=_PROJECT, limit=0,
        )
