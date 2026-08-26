"""A node the store accepted must be visible to the read whose job is to show the graph.

    kg_add_nodes  -> {"entity_id": "...", "note": "node ready — pass entity_id as a
                      subject/object endpoint to kg_propose_edge"}
    kg_graph_query -> {"nodes": [], "edges": [], "meta": {"nodes_total": 0, ...}}

🔴 STRUCTURALLY INVISIBLE, NOT MERELY MISSING. `_GRAPH_READ_CYPHER` is
`MATCH (subj:Entity)-[r:RELATES_TO]->(obj:Entity)` — it projects nodes FROM EDGES, and
`build_graph_slice`'s own docstring said so: "a node only appears if it is the endpoint of at
least one surviving edge". Every node this fixture can create is edgeless, because placing an
edge needs an approved card. So the write succeeds, the store holds it, and the read reports a
project with nothing in it.

REPRODUCED 2026-08-26 on a throwaway project: kg_add_nodes returned an entity_id, Neo4j held the
node with 0 edges, kg_graph_query answered nodes: [] / nodes_total: 0, and `memory_recall_entity`
found it — BY EXACT NAME. So a reader existed and only for a caller who already knew the answer.

🔴 AND THE OBVIOUS FIX WAS REFUTED BY MEASUREMENT. "Also return isolated nodes" would re-run this
repo's own 146K-token `composition_list_outline` incident. Measured on this instance:

    5,351 entities / 455 projects · 4,887 (91%) isolated · 440 projects with NO edges at all
    isolated per project:  p50 2 · p90 7 · p99 41 · max 3,172

Cheap for virtually every project, ruinous for two. Hence: capped rows, and a TOTAL counted
separately so a capped read still states the whole set's size (K25).
"""
from __future__ import annotations

import inspect

import pytest

from app.routers.public.graph_views import build_graph_slice

USER, PROJ = "u-1", "p-1"


def _n(nid: str, kind: str = "character", name: str | None = None) -> dict:
    return {"id": nid, "kind": kind, "name": name or nid.upper(), "user_id": USER,
            "project_id": PROJ}


def _edge(a: str, b: str, predicate: str = "knows") -> dict:
    return {"rel": {"predicate": predicate, "user_id": USER}, "subj": _n(a), "obj": _n(b)}


def _slice(records, isolated=None, view=None):
    return build_graph_slice(records, view=view, as_of_chapter=None,
                             deprecated_edge_codes=[], view_code=None, isolated=isolated)


class TestTheNodeTheStoreAcceptedIsVisible:
    def test_an_edgeless_node_appears(self):
        s = _slice([], isolated=[_n("solo")])
        assert [n.id for n in s.nodes] == ["solo"]
        assert s.edges == []

    def test_the_edgeless_case_is_the_WHOLE_project_not_an_edge_case(self):
        """440 of 455 projects on this instance have no edges at all, so 'no edges' is the
        ordinary state of a project and not a corner."""
        s = _slice([], isolated=[_n("a"), _n("b"), _n("c")])
        assert len(s.nodes) == 3 and s.edges == []

    def test_a_connected_node_is_not_DUPLICATED(self):
        """The isolated query and the edge walk can disagree — a node connected between the two
        reads would arrive twice, and a graph with the same node listed twice is worse than one
        missing it."""
        s = _slice([_edge("a", "b")], isolated=[_n("a"), _n("z")])
        assert sorted(n.id for n in s.nodes) == ["a", "b", "z"]

    def test_the_edge_endpoint_WINS_over_the_isolated_copy(self):
        """`setdefault`, not assignment: whatever the edge walk placed is the authoritative row."""
        src = inspect.getsource(build_graph_slice)
        seg = src.split("for props in isolated", 1)[1]
        assert "nodes.setdefault(" in seg and "nodes[" not in seg


class TestTheLensStillApplies:
    def test_an_isolated_node_outside_the_view_is_EXCLUDED(self):
        """A lens that excludes a kind must exclude it however the node was reached. Letting
        isolated nodes bypass the facet would make the view lie in the other direction."""
        from datetime import datetime, timezone
        from uuid import uuid4

        from app.db.ontology_models import GraphView

        now = datetime.now(timezone.utc)
        view = GraphView(view_id=uuid4(), project_id=PROJ, user_id=uuid4(), code="people",
                         name="People", description="", edge_type_codes=[],
                         node_kind_codes=["character"], created_at=now, updated_at=now)
        s = _slice([], isolated=[_n("hero", "character"), _n("keep", "location")], view=view)
        assert [n.id for n in s.nodes] == ["hero"]


class TestTheCOUNTStopsLyingAboutTheProject:
    def test_nodes_total_is_the_partitions_size_not_the_slices(self):
        """`nodes_total` was len(nodes-in-the-slice), so an EMPTY slice reported an empty
        PROJECT. That is the false zero the whole row is about — the number, not the rows."""
        from app.tools.graph_schema_tools import _project_graph

        out = _project_graph({"nodes": [], "edges": []}, "summary",
                             node_ref=("id",), edge_ref=("edge_type",), nodes_total=3172)
        assert out["meta"]["nodes_total"] == 3172
        assert out["meta"]["nodes_returned"] == 0

    def test_without_a_counted_total_the_old_behaviour_is_UNCHANGED(self):
        """The other three graph handlers (world/multi/view) do not count, and must keep working
        exactly as before rather than silently gaining a wrong number."""
        from app.tools.graph_schema_tools import _project_graph

        out = _project_graph({"nodes": [{"id": "a"}], "edges": []}, "summary",
                             node_ref=("id",), edge_ref=("edge_type",))
        assert out["meta"]["nodes_total"] == 1

    def test_a_capped_isolated_read_sets_TRUNCATED(self):
        src = inspect.getsource(_kg_graph_query_handler())
        assert "iso_truncated = len(iso_records) > args.limit" in src
        assert "truncated=edges_truncated or iso_truncated" in src, (
            "a capped isolated read that does not flag truncation reads as the whole set")


class TestTheRESTCallerIsNotDraggedAlong:
    def test_isolated_DEFAULTS_to_none(self):
        """Two consumers, genuinely different needs: the FE draws a picture and the agent answers
        a question. A drawing of 3,172 unconnected dots is not useful; an agent told a populated
        project has 0 nodes has been told something false. The router passes nothing."""
        sig = inspect.signature(build_graph_slice)
        assert sig.parameters["isolated"].default is None
        s = _slice([_edge("a", "b")])
        assert sorted(n.id for n in s.nodes) == ["a", "b"]

    def test_the_MCP_handler_is_the_one_that_passes_them(self):
        src = inspect.getsource(_kg_graph_query_handler())
        assert "isolated=iso_records" in src
        assert "_ISOLATED_NODES_CYPHER" in src


class TestTheIsolatedQueryIsScopedTheSameWayTheEdgeQueryIs:
    def test_it_binds_the_tenant_and_skips_archived(self):
        """Same partition predicates as `_GRAPH_READ_CYPHER`. A read that widened the tenancy to
        reach more nodes would be a much worse defect than the one it fixes."""
        from app.routers.public.graph_views import _ISOLATED_NODES_CYPHER, _NODE_TOTAL_CYPHER

        for cy in (_ISOLATED_NODES_CYPHER, _NODE_TOTAL_CYPHER):
            assert "e.user_id = $user_id" in cy
            assert "e.project_id = $project_id" in cy
            assert "e.archived_at IS NULL" in cy

    def test_isolated_means_no_ACTIVE_edge(self):
        """A node whose only edge was superseded IS isolated now — `valid_until IS NULL` is the
        same liveness predicate the edge read uses, so the two cannot disagree about a node."""
        from app.routers.public.graph_views import _ISOLATED_NODES_CYPHER

        assert "NOT EXISTS" in _ISOLATED_NODES_CYPHER
        assert "r.valid_until IS NULL" in _ISOLATED_NODES_CYPHER


class TestTheScalarCountDoesNotGoThroughTheRecordDrainer:
    """🔴 A GREEN SUITE SHIPPED A CRASH, AND THIS IS THE GUARD FOR IT.

    `_records` drains a result as `{k: dict(rec[k])}` — it assumes every returned value is a
    MAPPING, because every other caller returns node or relationship properties. A scalar
    `count(e) AS total` makes it raise `'int' object is not iterable`.

    Every unit test in this area monkeypatches `_records`, so no test touches the real driver
    shape and all 4,261 of them stayed green. The LIVE probe caught it on the first call:
    `kg_graph_query error: 'int' object is not iterable`. See the repo's own standing lesson that
    mock-only coverage hides exactly this class.
    """

    def test_records_really_does_assume_a_mapping(self):
        """Pinning the PREMISE, not just the fix — if `_records` ever learned to handle scalars,
        the rule below would be cargo-cult and should be revisited rather than obeyed."""
        import asyncio

        from app.routers.public.graph_views import _records

        class _Rec:
            def keys(self):
                return ["total"]

            def __getitem__(self, k):
                return 7

        class _Result:
            def __aiter__(self):
                async def gen():
                    yield _Rec()
                return gen()

        with pytest.raises(TypeError):
            asyncio.run(_records(_Result()))

    def test_the_count_uses_single_not_records(self):
        src = inspect.getsource(_kg_graph_query_handler())
        seg = src.split("_NODE_TOTAL_CYPHER", 1)[1]
        assert "await total_result.single()" in seg
        assert "_records(total_result)" not in seg, (
            "the scalar count is being drained by the mapping-only helper again")


def _kg_graph_query_handler():
    from app.tools.graph_schema_tools import _handle_kg_graph_query

    return _handle_kg_graph_query
