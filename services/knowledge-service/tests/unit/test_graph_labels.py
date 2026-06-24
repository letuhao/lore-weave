"""KG-ML M5 (C7) — pure label-decoration + resolution unit tests.

These prove the localization core without a live Neo4j or glossary:
  * ``OntologyKinds.kind_labels`` builds a code→label map for a language,
    primary-subtag folded, untranslated kinds omitted;
  * ``localize_graph_slice`` sets kind_label / name_label / edge_type_label,
    leaving None where there's no localized override (the source-fallback);
  * ``localize_edge_timeline`` localizes the predicate + per-instance target;
  * ``clean_lang_param`` validates / trims the inbound ?language= hint.
"""

from __future__ import annotations

from app.clients.glossary_ontology_client import OntologyKind, OntologyKinds
from app.labels.graph_labels import localize_edge_timeline, localize_graph_slice
from app.labels.reader_lang import clean_lang_param, primary_subtag
from app.routers.public.graph_views import (
    EdgeTimeline,
    GraphEdge,
    GraphNode,
    GraphSlice,
    TimelineInstance,
)


# ── OntologyKinds.kind_labels ──────────────────────────────────────────────
def test_kind_labels_resolves_language_and_folds_subtag():
    kinds = OntologyKinds(
        kinds=[
            OntologyKind(code="character", name="Character", name_i18n={"vi": "Nhân vật"}),
            OntologyKind(code="location", name="Location", name_i18n={"vi": "Địa điểm"}),
            OntologyKind(code="item", name="Item", name_i18n={}),  # no label
        ]
    )
    assert kinds.kind_labels("vi") == {"character": "Nhân vật", "location": "Địa điểm"}
    # primary subtag folding: vi-VN resolves the vi label
    assert kinds.kind_labels("vi-VN")["character"] == "Nhân vật"
    # an untranslated kind is omitted (caller falls back to canonical)
    assert "item" not in kinds.kind_labels("vi")


def test_kind_labels_blank_language_is_empty():
    kinds = OntologyKinds(kinds=[OntologyKind(code="character", name_i18n={"vi": "Nhân vật"})])
    assert kinds.kind_labels("") == {}
    assert kinds.kind_labels(None) == {}
    # a language with no curated label yields an empty map (English fallback path)
    assert kinds.kind_labels("en") == {}


# ── localize_graph_slice ───────────────────────────────────────────────────
def _slice() -> GraphSlice:
    return GraphSlice(
        nodes=[
            GraphNode(id="a", kind="character", name="火魔", glossary_entity_id="g1"),
            GraphNode(id="b", kind="location", name="天剑峰", glossary_entity_id="g2"),
            GraphNode(id="c", kind="character", name="Nameless", glossary_entity_id=None),
        ],
        edges=[
            GraphEdge(edge_type="ALLY_OF", source_id="a", target_id="b"),
            GraphEdge(edge_type="obscure_custom_pred", source_id="a", target_id="c"),
        ],
    )


def test_localize_graph_slice_sets_all_three_label_kinds():
    sl = _slice()
    localize_graph_slice(
        sl,
        kind_labels={"character": "Nhân vật", "location": "Địa điểm"},
        entity_names={"g1": "Hỏa Ma"},  # only g1 translated
        language="vi",
    )
    by_id = {n.id: n for n in sl.nodes}
    assert by_id["a"].kind_label == "Nhân vật"
    assert by_id["a"].name_label == "Hỏa Ma"
    assert by_id["b"].kind_label == "Địa điểm"
    # g2 untranslated → name_label stays None (source-fallback to canonical name)
    assert by_id["b"].name_label is None
    # node c has no glossary anchor → no name_label, but kind still localizes
    assert by_id["c"].kind_label == "Nhân vật"
    assert by_id["c"].name_label is None
    # curated predicate localizes; open-vocab predicate humanizes (never raw code)
    by_pred = {e.edge_type: e for e in sl.edges}
    assert by_pred["ALLY_OF"].edge_type_label == "đồng minh của"
    assert by_pred["obscure_custom_pred"].edge_type_label == "obscure custom pred"


def test_localize_graph_slice_blank_language_is_noop():
    sl = _slice()
    localize_graph_slice(sl, kind_labels={"character": "X"}, entity_names={"g1": "Y"}, language="")
    assert all(n.kind_label is None and n.name_label is None for n in sl.nodes)
    assert all(e.edge_type_label is None for e in sl.edges)


# ── localize_edge_timeline ─────────────────────────────────────────────────
def test_localize_edge_timeline_predicate_and_targets():
    tl = EdgeTimeline(
        entity_id="kai",
        edge_type="PURSUES",
        instances=[
            TimelineInstance(target_id="revenge", target_label="Revenge", target_glossary_entity_id="g9"),
            TimelineInstance(target_id="seek_dao", target_label="Seek Dao", target_glossary_entity_id=None),
        ],
    )
    localize_edge_timeline(tl, entity_names={"revenge": "Báo thù"}, language="vi")
    assert tl.edge_type_label == "theo đuổi"
    by_id = {i.target_id: i for i in tl.instances}
    assert by_id["revenge"].target_label_localized == "Báo thù"
    assert by_id["seek_dao"].target_label_localized is None  # untranslated → fallback


# ── clean_lang_param ───────────────────────────────────────────────────────
def test_clean_lang_param():
    assert clean_lang_param("vi") == "vi"
    assert clean_lang_param("  zh-Hant  ") == "zh-Hant"
    assert clean_lang_param("") is None
    assert clean_lang_param(None) is None
    assert clean_lang_param("not a tag!") is None  # malformed → None (resolver falls through)
    assert clean_lang_param("toolonglang") is None  # > 3-char primary subtag


def test_primary_subtag_folds_to_same_axis():
    # All KG label types key by primary subtag — folding keeps entity-name
    # translations (stored under 'vi') reachable for a 'vi-VN' reader.
    assert primary_subtag("vi") == "vi"
    assert primary_subtag("vi-VN") == "vi"
    assert primary_subtag("zh-Hant") == "zh"
    assert primary_subtag("EN_US") == "en"
    assert primary_subtag("") is None
    assert primary_subtag(None) is None
