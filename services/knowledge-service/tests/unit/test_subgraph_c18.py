"""C18 (G5) — unit tests for GET /v1/knowledge/projects/{id}/subgraph.

The project subgraph endpoint generalises the existing per-entity 1-hop
read into a project-wide n-hop, node-capped view for the C19 graph
canvas. It returns `{nodes, edges}` for the `(user_id, project_id)`
partition.

LOCKED (G5 / C18):
  - read-only: raw nodes + edges, NO server-side layout.
  - the node cap is enforced IN the Cypher (deterministic order) — the
    route NEVER returns more than the cap; same query → same nodes.
  - partition scoping: the Cypher binds BOTH user_id AND project_id; a
    project the caller doesn't own / a different project yields no
    foreign nodes.
  - `hops` / `limit` / `center` params shape the result.

Neo4j is mocked here; the live proof is the VERIFY-phase smoke against
the built graph (project 019eb683 — 万古神帝).
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from fastapi.testclient import TestClient

from app.db.neo4j_repos.relations import (
    SUBGRAPH_MAX_HOPS,
    SUBGRAPH_MAX_NODE_CAP,
    Subgraph,
    SubgraphEdge,
    SubgraphNode,
)

_TEST_USER = uuid4()
_PROJECT_ID = uuid4()


def _node(i: int) -> SubgraphNode:
    return SubgraphNode(
        id=f"e{i}",
        name=f"entity-{i}",
        kind="character",
        anchor_score=1.0 - i * 0.01,
        mention_count=100 - i,
        glossary_entity_id=None,
    )


def _edge(src: str, tgt: str) -> SubgraphEdge:
    return SubgraphEdge(
        id=f"{src}-{tgt}",
        source=src,
        target=tgt,
        predicate="ally_of",
        confidence=0.9,
    )


@asynccontextmanager
async def _noop_session():
    yield MagicMock()


def _make_client():
    from app.main import app
    from app.middleware.jwt_auth import get_current_user

    app.dependency_overrides[get_current_user] = lambda: _TEST_USER
    return TestClient(app, raise_server_exceptions=False)


def _teardown():
    from app.main import app

    app.dependency_overrides.clear()


# ── (1) route exists + returns {nodes, edges} ────────────────────────


def test_subgraph_returns_nodes_and_edges():
    sg = Subgraph(
        nodes=[_node(0), _node(1)],
        edges=[_edge("e0", "e1")],
        node_cap_hit=False,
    )
    try:
        with patch(
            "app.routers.public.entities.get_project_subgraph",
            new_callable=AsyncMock,
            return_value=sg,
        ), patch(
            "app.routers.public.entities.neo4j_session",
            new=lambda: _noop_session(),
        ):
            client = _make_client()
            resp = client.get(f"/v1/knowledge/projects/{_PROJECT_ID}/subgraph")
        assert resp.status_code == 200, resp.json()
        body = resp.json()
        assert [n["id"] for n in body["nodes"]] == ["e0", "e1"]
        assert body["edges"][0]["source"] == "e0"
        assert body["edges"][0]["target"] == "e1"
        assert body["node_cap_hit"] is False
    finally:
        _teardown()


# ── (2) node count NEVER exceeds the cap ─────────────────────────────


def test_node_count_never_exceeds_cap():
    """The route caps `limit` at SUBGRAPH_MAX_NODE_CAP via Query(le=...):
    a request above the ceiling is rejected (422) so the repo is never
    asked for an unbounded set."""
    try:
        with patch(
            "app.routers.public.entities.get_project_subgraph",
            new_callable=AsyncMock,
        ) as mock_sg:
            client = _make_client()
            resp = client.get(
                f"/v1/knowledge/projects/{_PROJECT_ID}/subgraph"
                f"?limit={SUBGRAPH_MAX_NODE_CAP + 1}"
            )
        assert resp.status_code == 422
        assert mock_sg.await_count == 0
    finally:
        _teardown()


def test_limit_within_cap_passes_through():
    sg = Subgraph(nodes=[_node(i) for i in range(10)], edges=[], node_cap_hit=True)
    try:
        with patch(
            "app.routers.public.entities.get_project_subgraph",
            new_callable=AsyncMock,
            return_value=sg,
        ) as mock_sg, patch(
            "app.routers.public.entities.neo4j_session",
            new=lambda: _noop_session(),
        ):
            client = _make_client()
            resp = client.get(
                f"/v1/knowledge/projects/{_PROJECT_ID}/subgraph?limit=10"
            )
        assert resp.status_code == 200, resp.json()
        kwargs = mock_sg.await_args.kwargs
        assert kwargs["limit"] == 10
        assert len(resp.json()["nodes"]) == 10
        # cap-hit surfaced so the FE can offer load-more
        assert resp.json()["node_cap_hit"] is True
    finally:
        _teardown()


# ── (3) partition scoping: both user_id + project_id threaded ────────


def test_partition_scoping_threads_user_and_project():
    """The route threads the JWT user_id AND the path project_id straight
    into the repo call — no user_id body field (no spoofing), and the
    project is the route's, not a foreign one."""
    sg = Subgraph(nodes=[], edges=[], node_cap_hit=False)
    try:
        with patch(
            "app.routers.public.entities.get_project_subgraph",
            new_callable=AsyncMock,
            return_value=sg,
        ) as mock_sg, patch(
            "app.routers.public.entities.neo4j_session",
            new=lambda: _noop_session(),
        ):
            client = _make_client()
            resp = client.get(f"/v1/knowledge/projects/{_PROJECT_ID}/subgraph")
        assert resp.status_code == 200, resp.json()
        kwargs = mock_sg.await_args.kwargs
        assert kwargs["user_id"] == str(_TEST_USER)
        assert kwargs["project_id"] == str(_PROJECT_ID)
    finally:
        _teardown()


def test_foreign_project_returns_empty_no_foreign_nodes():
    """A project the caller doesn't own resolves to an empty subgraph at
    the repo (partition-scoped Cypher), not someone else's nodes. The
    route surfaces the empty result as 200 {nodes:[], edges:[]}."""
    other_project = uuid4()
    sg = Subgraph(nodes=[], edges=[], node_cap_hit=False)
    try:
        with patch(
            "app.routers.public.entities.get_project_subgraph",
            new_callable=AsyncMock,
            return_value=sg,
        ) as mock_sg, patch(
            "app.routers.public.entities.neo4j_session",
            new=lambda: _noop_session(),
        ):
            client = _make_client()
            resp = client.get(
                f"/v1/knowledge/projects/{other_project}/subgraph"
            )
        assert resp.status_code == 200, resp.json()
        assert resp.json()["nodes"] == []
        assert resp.json()["edges"] == []
        # the foreign project id was bound — the repo (not the route)
        # enforces the empty result via the partition filter.
        assert mock_sg.await_args.kwargs["project_id"] == str(other_project)
    finally:
        _teardown()


# ── (4) hops / limit / center params shape the result ────────────────


def test_hops_limit_center_params_passed_through():
    sg = Subgraph(nodes=[_node(0)], edges=[], node_cap_hit=False)
    try:
        with patch(
            "app.routers.public.entities.get_project_subgraph",
            new_callable=AsyncMock,
            return_value=sg,
        ) as mock_sg, patch(
            "app.routers.public.entities.neo4j_session",
            new=lambda: _noop_session(),
        ):
            client = _make_client()
            resp = client.get(
                f"/v1/knowledge/projects/{_PROJECT_ID}/subgraph"
                "?hops=2&limit=50&center=e42"
            )
        assert resp.status_code == 200, resp.json()
        kwargs = mock_sg.await_args.kwargs
        assert kwargs["hops"] == 2
        assert kwargs["limit"] == 50
        assert kwargs["center"] == "e42"
    finally:
        _teardown()


def test_default_params():
    sg = Subgraph(nodes=[], edges=[], node_cap_hit=False)
    try:
        with patch(
            "app.routers.public.entities.get_project_subgraph",
            new_callable=AsyncMock,
            return_value=sg,
        ) as mock_sg, patch(
            "app.routers.public.entities.neo4j_session",
            new=lambda: _noop_session(),
        ):
            client = _make_client()
            resp = client.get(f"/v1/knowledge/projects/{_PROJECT_ID}/subgraph")
        assert resp.status_code == 200
        kwargs = mock_sg.await_args.kwargs
        assert kwargs["hops"] == 1
        assert kwargs["limit"] == 200
        assert kwargs["center"] is None
    finally:
        _teardown()


def test_hops_above_max_rejected():
    try:
        with patch(
            "app.routers.public.entities.get_project_subgraph",
            new_callable=AsyncMock,
        ) as mock_sg:
            client = _make_client()
            resp = client.get(
                f"/v1/knowledge/projects/{_PROJECT_ID}/subgraph"
                f"?hops={SUBGRAPH_MAX_HOPS + 1}"
            )
        assert resp.status_code == 422
        assert mock_sg.await_count == 0
    finally:
        _teardown()
