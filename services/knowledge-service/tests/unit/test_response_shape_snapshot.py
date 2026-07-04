"""§13b — MCP response-shape contract SNAPSHOT (knowledge slice).

The per-tool guards in `test_response_contract.py` assert a heavy body is absent
at `detail=summary`; they don't pin the EXACT ref set, so a silent re-bloat keeps
them green while the grounding hot-path payload grows again. This snapshot pins
the committed ref set for every refactored knowledge SET tool (story/memory search,
timeline, graph/subgraph, triage) so drift in EITHER direction turns a test red.

Regenerate an intentional change with
`WRITE_MCP_SHAPES=1 pytest tests/unit/test_response_shape_snapshot.py`.
"""
from __future__ import annotations

from loreweave_mcp import assert_or_write_shape_snapshot

from app.tools.executor import (
    MEMORY_SEARCH_REF_FIELDS,
    MEMORY_TIMELINE_REF_FIELDS,
    STORY_SEARCH_REF_FIELDS,
)
from app.tools.graph_schema_tools import (
    GRAPH_EDGE_REF_FIELDS,
    GRAPH_NODE_REF_FIELDS,
    SUBGRAPH_EDGE_REF_FIELDS,
    SUBGRAPH_NODE_REF_FIELDS,
    TIMELINE_INSTANCE_REF_FIELDS,
    TRIAGE_GROUP_REF_FIELDS,
)


def test_response_shapes_match_committed_snapshot():
    assert_or_write_shape_snapshot(
        "knowledge",
        {
            "STORY_SEARCH_REF_FIELDS": STORY_SEARCH_REF_FIELDS,
            "MEMORY_SEARCH_REF_FIELDS": MEMORY_SEARCH_REF_FIELDS,
            "MEMORY_TIMELINE_REF_FIELDS": MEMORY_TIMELINE_REF_FIELDS,
            "GRAPH_NODE_REF_FIELDS": GRAPH_NODE_REF_FIELDS,
            "GRAPH_EDGE_REF_FIELDS": GRAPH_EDGE_REF_FIELDS,
            "SUBGRAPH_NODE_REF_FIELDS": SUBGRAPH_NODE_REF_FIELDS,
            "SUBGRAPH_EDGE_REF_FIELDS": SUBGRAPH_EDGE_REF_FIELDS,
            "TIMELINE_INSTANCE_REF_FIELDS": TIMELINE_INSTANCE_REF_FIELDS,
            "TRIAGE_GROUP_REF_FIELDS": TRIAGE_GROUP_REF_FIELDS,
        },
        test_file=__file__,
    )
