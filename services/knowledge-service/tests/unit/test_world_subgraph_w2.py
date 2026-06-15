"""G4 (W2) — get_world_subgraph union logic (no Neo4j).

Drives the REAL rollup function against a monkeypatched get_project_subgraph
that returns canned per-project Subgraphs, locking the merge / source-tag /
global re-cap / edge-survivor / dedup behaviour into the always-run unit suite.
The live cross-service round-trip (membership → projects → union over Neo4j) is
the W2 live-smoke.
"""
import pytest

from app.db.neo4j_repos import relations
from app.db.neo4j_repos.relations import (
    Subgraph,
    SubgraphEdge,
    SubgraphNode,
    get_world_subgraph,
)


def _node(nid: str, anchor: float = 0.0, mentions: int = 0) -> SubgraphNode:
    return SubgraphNode(
        id=nid, name=nid, kind="person", anchor_score=anchor, mention_count=mentions
    )


def _edge(eid: str, src: str, tgt: str) -> SubgraphEdge:
    return SubgraphEdge(id=eid, source=src, target=tgt, predicate="knows", confidence=0.9)


def _patch(monkeypatch, canned: dict[str, Subgraph]):
    async def fake(session, *, user_id, project_id, limit, min_confidence=0.8):
        return canned.get(project_id, Subgraph())

    monkeypatch.setattr(relations, "get_project_subgraph", fake)


@pytest.mark.asyncio
async def test_unions_and_tags_source_project(monkeypatch):
    _patch(monkeypatch, {
        "projA": Subgraph(nodes=[_node("a1", 0.9), _node("a2", 0.5)],
                          edges=[_edge("e1", "a1", "a2")]),
        "projB": Subgraph(nodes=[_node("b1", 0.8)], edges=[]),
    })
    sg = await get_world_subgraph(
        None, user_id="u", project_ids=["projA", "projB"], limit=200
    )
    # union of all nodes, ordered by anchor DESC globally
    assert [n.id for n in sg.nodes] == ["a1", "b1", "a2"]
    # each node tagged with its source member project
    assert {n.id: n.source_project_id for n in sg.nodes} == {
        "a1": "projA", "a2": "projA", "b1": "projB",
    }
    assert {e.id for e in sg.edges} == {"e1"}
    assert sg.node_cap_hit is False


@pytest.mark.asyncio
async def test_union_recap_trims_and_flags(monkeypatch):
    _patch(monkeypatch, {
        "projA": Subgraph(nodes=[_node("a1", 0.9), _node("a2", 0.4)], edges=[]),
        "projB": Subgraph(nodes=[_node("b1", 0.7)], edges=[]),
    })
    sg = await get_world_subgraph(
        None, user_id="u", project_ids=["projA", "projB"], limit=2
    )
    # top-2 by global anchor order; a2 crowded out
    assert [n.id for n in sg.nodes] == ["a1", "b1"]
    assert sg.node_cap_hit is True


@pytest.mark.asyncio
async def test_member_cap_propagates(monkeypatch):
    _patch(monkeypatch, {
        "projA": Subgraph(nodes=[_node("a1")], edges=[], node_cap_hit=True),
    })
    sg = await get_world_subgraph(None, user_id="u", project_ids=["projA"], limit=200)
    # a member's own subgraph hit its cap → flagged even though the union fit
    assert sg.node_cap_hit is True


@pytest.mark.asyncio
async def test_edges_into_capped_out_nodes_are_dropped(monkeypatch):
    _patch(monkeypatch, {
        "projA": Subgraph(nodes=[_node("a1", 0.9), _node("a2", 0.1)],
                          edges=[_edge("e1", "a1", "a2")]),
    })
    sg = await get_world_subgraph(None, user_id="u", project_ids=["projA"], limit=1)
    assert [n.id for n in sg.nodes] == ["a1"]
    # e1's endpoint a2 was capped out → no dangling edge
    assert sg.edges == []


@pytest.mark.asyncio
async def test_dedups_colliding_ids_first_writer_wins(monkeypatch):
    _patch(monkeypatch, {
        "projA": Subgraph(nodes=[_node("x", 0.9)], edges=[]),
        "projB": Subgraph(nodes=[_node("x", 0.5)], edges=[]),
    })
    sg = await get_world_subgraph(
        None, user_id="u", project_ids=["projA", "projB"], limit=200
    )
    assert len(sg.nodes) == 1
    # projA queried first → its node wins, tagged projA
    assert sg.nodes[0].source_project_id == "projA"


@pytest.mark.asyncio
async def test_empty_world_makes_no_project_queries(monkeypatch):
    called: list[str] = []

    async def fake(session, *, user_id, project_id, limit, min_confidence=0.8):
        called.append(project_id)
        return Subgraph()

    monkeypatch.setattr(relations, "get_project_subgraph", fake)
    sg = await get_world_subgraph(None, user_id="u", project_ids=[], limit=200)
    assert sg.nodes == [] and sg.edges == [] and sg.node_cap_hit is False
    assert called == []


@pytest.mark.asyncio
async def test_skips_empty_project_id(monkeypatch):
    called: list[str] = []

    async def fake(session, *, user_id, project_id, limit, min_confidence=0.8):
        called.append(project_id)
        return Subgraph(nodes=[_node("p")], edges=[])

    monkeypatch.setattr(relations, "get_project_subgraph", fake)
    await get_world_subgraph(None, user_id="u", project_ids=["", "p1"], limit=200)
    assert called == ["p1"]
