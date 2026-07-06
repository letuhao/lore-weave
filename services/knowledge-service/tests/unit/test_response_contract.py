"""L1/L2 reference-first contract guard for the knowledge SET-returning MCP tools
(Context Budget Law §6b).

The kit proves `apply_response_contract` generically (loreweave_mcp test_kit). This
pins the knowledge-SPECIFIC contracts: for every refactored SET tool the ref-field
set must DROP the heavy body at detail="summary" and KEEP the reference fields, and
`detail` must default to "full" (versioned-default migration — no behavior change
for legacy/federated callers). If someone re-admits a heavy field to a ref set, or
flips a default, one of these goes red.
"""

from __future__ import annotations

import pytest
from loreweave_mcp import apply_response_contract

from app.tools.definitions import (
    MemorySearchArgs,
    MemoryTimelineArgs,
    StorySearchArgs,
)
from app.tools.executor import (
    MEMORY_SEARCH_REF_FIELDS,
    MEMORY_TIMELINE_REF_FIELDS,
    STORY_SEARCH_REF_FIELDS,
    _one_line,
)
from app.tools.graph_schema_tools import (
    GRAPH_EDGE_REF_FIELDS,
    GRAPH_NODE_REF_FIELDS,
    SUBGRAPH_EDGE_REF_FIELDS,
    SUBGRAPH_NODE_REF_FIELDS,
    TIMELINE_INSTANCE_REF_FIELDS,
    TRIAGE_GROUP_REF_FIELDS,
    KgEntityEdgeTimelineArgs,
    KgGraphQueryArgs,
    KgMultiQueryArgs,
    KgTriageListArgs,
    KgWorldQueryArgs,
)


# ── versioned-default migration (spec §6b rule #1) ────────────────────
# Every refactored SET tool's `detail` MUST default to "full" so an existing
# caller (chat-service OpenAI path / a federated agent) is byte-unchanged until it
# opts into "summary".
@pytest.mark.parametrize(
    "model",
    [
        StorySearchArgs, MemorySearchArgs, MemoryTimelineArgs,
        KgGraphQueryArgs, KgWorldQueryArgs, KgMultiQueryArgs,
        KgEntityEdgeTimelineArgs, KgTriageListArgs,
    ],
)
def test_detail_defaults_to_full(model):
    field = model.model_fields["detail"]
    assert field.default == "full", f"{model.__name__}.detail must default to 'full'"


# ── story_search — drop the full passage snippet at summary ───────────
def _story_hit(**over) -> dict:
    base = dict(
        chapterId="ch-1", chapterTitle="Chapter One", sortOrder=1, surface="canon",
        matchType="semantic", sourceLang="en", score=0.91, relevance=0.91,
        snippet="x" * 800, highlights=[], location={"chunkIndex": 3},
    )
    base.update(over)
    return base


class TestStorySearchRefFields:
    def test_heavy_snippet_dropped_at_summary(self):
        out, meta = apply_response_contract(
            [_story_hit()], ref_fields=STORY_SEARCH_REF_FIELDS, detail="summary"
        )
        assert "snippet" not in out[0]
        assert "highlights" not in out[0]
        assert meta["detail"] == "summary"

    def test_chapter_ref_kept_at_summary(self):
        out, _ = apply_response_contract(
            [_story_hit()], ref_fields=STORY_SEARCH_REF_FIELDS, detail="summary"
        )
        for required in ("chapterId", "chapterTitle", "sortOrder", "score", "location"):
            assert required in out[0], f"summary ref must keep {required}"

    def test_full_keeps_snippet(self):
        out, _ = apply_response_contract(
            [_story_hit()], ref_fields=STORY_SEARCH_REF_FIELDS, detail="full"
        )
        assert out[0]["snippet"]

    def test_summary_is_materially_smaller(self):
        rows = [_story_hit() for _ in range(12)]
        summ, _ = apply_response_contract(rows, ref_fields=STORY_SEARCH_REF_FIELDS, detail="summary")
        full, _ = apply_response_contract(rows, ref_fields=STORY_SEARCH_REF_FIELDS, detail="full")
        assert len(str(summ)) < len(str(full)) * 0.4

    def test_ref_fields_never_include_the_passage_body(self):
        assert "snippet" not in STORY_SEARCH_REF_FIELDS
        assert "highlights" not in STORY_SEARCH_REF_FIELDS


# ── memory_search — drop the full text, keep the 1-line snippet ───────
def _mem_item(**over) -> dict:
    base = dict(
        snippet=_one_line("y" * 800), text="y" * 500, source_type="chapter", score=0.7,
    )
    base.update(over)
    return base


class TestMemorySearchRefFields:
    def test_full_text_dropped_snippet_kept_at_summary(self):
        out, _ = apply_response_contract(
            [_mem_item()], ref_fields=MEMORY_SEARCH_REF_FIELDS, detail="summary"
        )
        assert "text" not in out[0]
        assert out[0]["snippet"] and out[0]["source_type"] and out[0]["score"]

    def test_full_keeps_text(self):
        out, _ = apply_response_contract(
            [_mem_item()], ref_fields=MEMORY_SEARCH_REF_FIELDS, detail="full"
        )
        assert out[0]["text"]

    def test_snippet_preview_is_one_line_and_bounded(self):
        preview = _one_line("a b\nc  d\t e" * 100)
        assert "\n" not in preview and "\t" not in preview
        assert len(preview) <= 161  # _PREVIEW_CHARS + the ellipsis

    def test_summary_is_smaller(self):
        rows = [_mem_item() for _ in range(20)]
        summ, _ = apply_response_contract(rows, ref_fields=MEMORY_SEARCH_REF_FIELDS, detail="summary")
        full, _ = apply_response_contract(rows, ref_fields=MEMORY_SEARCH_REF_FIELDS, detail="full")
        assert len(str(summ)) < len(str(full))

    def test_ref_fields_never_include_full_text(self):
        assert "text" not in MEMORY_SEARCH_REF_FIELDS


# ── memory_timeline — drop the per-event summary body at summary ──────
def _event(**over) -> dict:
    base = dict(
        title="A battle", summary="z" * 500, event_date="1850-03",
        participants=["Kai", "Mira"],
    )
    base.update(over)
    return base


class TestMemoryTimelineRefFields:
    def test_summary_body_dropped_at_summary(self):
        out, _ = apply_response_contract(
            [_event()], ref_fields=MEMORY_TIMELINE_REF_FIELDS, detail="summary"
        )
        assert "summary" not in out[0]
        for required in ("title", "event_date", "participants"):
            assert required in out[0]

    def test_full_keeps_summary(self):
        out, _ = apply_response_contract(
            [_event()], ref_fields=MEMORY_TIMELINE_REF_FIELDS, detail="full"
        )
        assert out[0]["summary"]

    def test_ref_fields_never_include_summary(self):
        assert "summary" not in MEMORY_TIMELINE_REF_FIELDS


# ── kg_graph_query — compact node/edge refs at summary ────────────────
def _gnode(**over) -> dict:
    base = dict(
        id="e1", kind="character", name="Kai", glossary_entity_id="g1",
        kind_label="Character", name_label="凯",
    )
    base.update(over)
    return base


def _gedge(**over) -> dict:
    base = dict(
        edge_type="ALLY_OF", source_id="e1", target_id="e2", valid_from=1,
        valid_to=None, schema_version=4, edge_type_label="ally of",
    )
    base.update(over)
    return base


class TestGraphQueryRefFields:
    def test_node_labels_and_glossary_dropped_at_summary(self):
        out, _ = apply_response_contract([_gnode()], ref_fields=GRAPH_NODE_REF_FIELDS, detail="summary")
        assert set(out[0]) == {"id", "kind", "name"}
        assert "glossary_entity_id" not in out[0] and "name_label" not in out[0]

    def test_edge_schema_version_and_label_dropped_at_summary(self):
        out, _ = apply_response_contract([_gedge()], ref_fields=GRAPH_EDGE_REF_FIELDS, detail="summary")
        assert "schema_version" not in out[0] and "edge_type_label" not in out[0]
        for required in ("edge_type", "source_id", "target_id"):
            assert required in out[0]

    def test_full_keeps_labels(self):
        out, _ = apply_response_contract([_gnode()], ref_fields=GRAPH_NODE_REF_FIELDS, detail="full")
        assert out[0]["name_label"] and out[0]["glossary_entity_id"]

    def test_ref_fields_exclude_heavy(self):
        assert "name_label" not in GRAPH_NODE_REF_FIELDS
        assert "schema_version" not in GRAPH_EDGE_REF_FIELDS


# ── kg_world_query / kg_multi_query — compact subgraph refs ───────────
def _snode(**over) -> dict:
    base = dict(
        id="e1", name="Kai", kind="character", anchor_score=0.9, mention_count=12,
        glossary_entity_id="g1", source_project_id="p1",
    )
    base.update(over)
    return base


def _sedge(**over) -> dict:
    base = dict(id="r1", source="e1", target="e2", predicate="ALLY_OF", confidence=0.8)
    base.update(over)
    return base


class TestSubgraphRefFields:
    def test_node_scores_dropped_source_kept_at_summary(self):
        out, _ = apply_response_contract([_snode()], ref_fields=SUBGRAPH_NODE_REF_FIELDS, detail="summary")
        assert "anchor_score" not in out[0] and "mention_count" not in out[0]
        assert out[0]["source_project_id"] == "p1"  # the cross-book tag survives

    def test_edge_confidence_dropped_at_summary(self):
        out, _ = apply_response_contract([_sedge()], ref_fields=SUBGRAPH_EDGE_REF_FIELDS, detail="summary")
        assert "confidence" not in out[0]
        for required in ("id", "source", "target", "predicate"):
            assert required in out[0]

    def test_full_keeps_scores(self):
        out, _ = apply_response_contract([_snode()], ref_fields=SUBGRAPH_NODE_REF_FIELDS, detail="full")
        assert out[0]["anchor_score"] == 0.9

    def test_ref_fields_exclude_heavy(self):
        assert "anchor_score" not in SUBGRAPH_NODE_REF_FIELDS
        assert "confidence" not in SUBGRAPH_EDGE_REF_FIELDS


# ── kg_entity_edge_timeline — compact instance refs ───────────────────
def _instance(**over) -> dict:
    base = dict(
        target_id="e2", target_label="Mira", valid_from=1, valid_to=5,
        evidence_chapter_id="ch-9", schema_version=4,
        target_glossary_entity_id="g2", target_label_localized="米拉",
    )
    base.update(over)
    return base


class TestTimelineInstanceRefFields:
    def test_evidence_and_localized_dropped_at_summary(self):
        out, _ = apply_response_contract([_instance()], ref_fields=TIMELINE_INSTANCE_REF_FIELDS, detail="summary")
        assert "evidence_chapter_id" not in out[0] and "schema_version" not in out[0]
        assert "target_label_localized" not in out[0]
        for required in ("target_id", "target_label", "valid_from", "valid_to"):
            assert required in out[0]

    def test_full_keeps_evidence(self):
        out, _ = apply_response_contract([_instance()], ref_fields=TIMELINE_INSTANCE_REF_FIELDS, detail="full")
        assert out[0]["evidence_chapter_id"]

    def test_ref_fields_exclude_heavy(self):
        assert "evidence_chapter_id" not in TIMELINE_INSTANCE_REF_FIELDS


# ── kg_triage_list — drop the sample_payload blob at summary ──────────
def _group(**over) -> dict:
    base = dict(
        signature="edge:WORSHIPS:god", item_type="unmatched_edge", count=7,
        status="pending", sample_payload={"a": "x" * 400, "b": [1, 2, 3]},
        suggested_actions=["map", "add_to_schema"],
    )
    base.update(over)
    return base


class TestTriageGroupRefFields:
    def test_sample_payload_and_actions_dropped_at_summary(self):
        out, _ = apply_response_contract([_group()], ref_fields=TRIAGE_GROUP_REF_FIELDS, detail="summary")
        assert "sample_payload" not in out[0] and "suggested_actions" not in out[0]
        for required in ("signature", "item_type", "count", "status"):
            assert required in out[0]

    def test_full_keeps_sample_payload(self):
        out, _ = apply_response_contract([_group()], ref_fields=TRIAGE_GROUP_REF_FIELDS, detail="full")
        assert out[0]["sample_payload"] and out[0]["suggested_actions"]

    def test_summary_is_smaller(self):
        rows = [_group() for _ in range(10)]
        summ, _ = apply_response_contract(rows, ref_fields=TRIAGE_GROUP_REF_FIELDS, detail="summary")
        full, _ = apply_response_contract(rows, ref_fields=TRIAGE_GROUP_REF_FIELDS, detail="full")
        assert len(str(summ)) < len(str(full)) * 0.6

    def test_ref_fields_exclude_payload(self):
        assert "sample_payload" not in TRIAGE_GROUP_REF_FIELDS
