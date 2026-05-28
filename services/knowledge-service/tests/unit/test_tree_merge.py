"""P3 — tests for tree_merge.py (D1 + H2 chunked per-chapter)."""

from __future__ import annotations

import time

import pytest

from app.extraction.tree_merge import (
    ChapterKG,
    SceneKG,
    _EntityShape,
    _EventShape,
    _FactShape,
    _RelationShape,
    alias_union_find,
    tree_merge_chapter,
)


def _entity(cid: str, name: str, aliases: list[str] | None = None,
            confidence: float = 0.8) -> _EntityShape:
    return _EntityShape(
        name=name,
        canonical_id=cid,
        canonical_name=name.lower(),
        kind="person",
        aliases=aliases or [],
        confidence=confidence,
    )


def _scene(scene_id: str, entities=None, relations=None, events=None, facts=None) -> SceneKG:
    return SceneKG(
        scene_id=scene_id,
        scene_path=f"book/part-1/chapter-1/{scene_id}",
        entities=entities or [],
        relations=relations or [],
        events=events or [],
        facts=facts or [],
    )


# ── Tarjan union-find ──────────────────────────────────────────────────────


def test_alias_uf_two_entities_no_overlap_no_union():
    e1 = _entity("e1", "Alice", aliases=["Ali"])
    e2 = _entity("e2", "Bob", aliases=["Bobby"])
    cmap = alias_union_find([e1, e2])
    assert cmap["e1"] == "e1"
    assert cmap["e2"] == "e2"


def test_alias_uf_two_entities_with_2_shared_aliases_unioned():
    """Spec D1 Tarjan UF: >=2 shared aliases -> same canonical group."""
    e1 = _entity("e1", "Alice", aliases=["Al", "Ali", "Alice the Great"])
    e2 = _entity("e2", "AliceClone", aliases=["Al", "Ali", "Another"])
    cmap = alias_union_find([e1, e2])
    # Both map to the same root (which one wins is UF-impl-dependent; just check equality).
    assert cmap["e1"] == cmap["e2"]


def test_alias_uf_only_1_shared_alias_no_union():
    """Edge: exactly 1 shared alias is NOT enough (spec threshold = 2)."""
    e1 = _entity("e1", "Alice", aliases=["Al", "Ali"])
    e2 = _entity("e2", "Alfred", aliases=["Al", "Fred"])
    cmap = alias_union_find([e1, e2])
    assert cmap["e1"] != cmap["e2"]


def test_alias_uf_transitive_3_way_chain():
    """A↔B, B↔C share -> A and C also unioned."""
    e1 = _entity("e1", "A", aliases=["x", "y"])
    e2 = _entity("e2", "B", aliases=["x", "y", "z", "w"])  # shares 2 with A AND 2 with C
    e3 = _entity("e3", "C", aliases=["z", "w"])
    cmap = alias_union_find([e1, e2, e3])
    assert cmap["e1"] == cmap["e2"] == cmap["e3"]


# ── Per-chapter merge ──────────────────────────────────────────────────────


def test_merge_empty_scene_list_returns_empty_chapter_kg():
    result = tree_merge_chapter("ch-1", "book/part-1/chapter-1", [])
    assert isinstance(result, ChapterKG)
    assert result.entities == []
    assert result.relations == []
    assert result.canonical_id_map == {}


def test_merge_single_scene_passes_through_entities():
    s1 = _scene("s1", entities=[_entity("e1", "Alice")])
    out = tree_merge_chapter("ch-1", "book/part-1/chapter-1", [s1])
    assert len(out.entities) == 1
    assert out.entities[0].canonical_id == "e1"


def test_merge_two_scenes_dedups_same_canonical_id():
    """Same canonical_id across 2 scenes -> 1 merged entity."""
    s1 = _scene("s1", entities=[_entity("e1", "Alice", confidence=0.7)])
    s2 = _scene("s2", entities=[_entity("e1", "Alice", confidence=0.9)])
    out = tree_merge_chapter("ch-1", "book/part-1/chapter-1", [s1, s2])
    assert len(out.entities) == 1
    # Higher-confidence wins for canonical form.
    assert out.entities[0].confidence == 0.9


def test_merge_unions_aliases_when_2_overlap():
    """Two entities with 2+ shared aliases merge to ONE entity."""
    e1 = _entity("e1", "Alice", aliases=["Al", "Ali"])
    e2 = _entity("e2", "AliceClone", aliases=["Al", "Ali"])
    s = _scene("s1", entities=[e1, e2])
    out = tree_merge_chapter("ch-1", "book/part-1/chapter-1", [s])
    assert len(out.entities) == 1
    # canonical_id_map maps both originals to the same root.
    assert out.canonical_id_map["e1"] == out.canonical_id_map["e2"]


def test_relation_dedup_by_composite_key_after_uf_remap():
    """Relations sharing (subj, pred, obj, polarity) AFTER UF remap dedup."""
    e1 = _entity("e1", "Alice", aliases=["a1", "a2"])
    e2 = _entity("e2", "AliceClone", aliases=["a1", "a2"])  # unioned with e1
    e3 = _entity("e3", "Bob")
    # Both relations target e1/e2 (will be unioned) -> dedup
    r1 = _RelationShape(subject_canonical_id="e1", predicate="loves", object_canonical_id="e3")
    r2 = _RelationShape(subject_canonical_id="e2", predicate="loves", object_canonical_id="e3")
    s1 = _scene("s1", entities=[e1, e2, e3], relations=[r1])
    s2 = _scene("s2", entities=[e1, e2, e3], relations=[r2])
    out = tree_merge_chapter("ch-1", "book/part-1/chapter-1", [s1, s2])
    # After UF, both r1 and r2 have subj = the union root -> dedup to 1 relation.
    assert len(out.relations) == 1


def test_event_dedup_by_name_norm_and_time_cue():
    ev1 = _EventShape(name_norm="battle of helm's deep", time_cue="dawn")
    ev2 = _EventShape(name_norm="battle of helm's deep", time_cue="dawn")  # dup
    ev3 = _EventShape(name_norm="battle of helm's deep", time_cue=None)    # diff time_cue
    s1 = _scene("s1", events=[ev1, ev2])
    s2 = _scene("s2", events=[ev3])
    out = tree_merge_chapter("ch-1", "book/part-1/chapter-1", [s1, s2])
    assert len(out.events) == 2  # ev1==ev2 dedup; ev3 distinct


def test_fact_dedup_by_subject_attribute_value():
    f1 = _FactShape(subject_canonical_id="e1", attribute="hometown", value="Hobbiton")
    f2 = _FactShape(subject_canonical_id="e1", attribute="hometown", value="Hobbiton")  # dup
    f3 = _FactShape(subject_canonical_id="e1", attribute="hometown", value="Buckland")  # diff
    s1 = _scene("s1", facts=[f1, f2])
    s2 = _scene("s2", facts=[f3])
    out = tree_merge_chapter("ch-1", "book/part-1/chapter-1", [s1, s2])
    assert len(out.facts) == 2


def test_50_scene_chapter_merge_completes_under_2s():
    """Perf sanity for the largest realistic per-chapter merge.
    R1 risk mitigation: chunked per-chapter merge must stay fast.
    """
    scenes = []
    for s_idx in range(50):
        entities = [_entity(f"e-{s_idx}-{i}", f"Entity{s_idx}{i}",
                            aliases=[f"alias-{s_idx}-{i}-a"]) for i in range(20)]
        relations = [_RelationShape(
            subject_canonical_id=f"e-{s_idx}-0",
            predicate="related_to",
            object_canonical_id=f"e-{s_idx}-{i}",
        ) for i in range(1, 5)]
        scenes.append(_scene(f"s-{s_idx}", entities=entities, relations=relations))

    t0 = time.perf_counter()
    out = tree_merge_chapter("ch-perf", "book/part-1/chapter-perf", scenes)
    elapsed = time.perf_counter() - t0

    assert elapsed < 2.0, f"merge took {elapsed:.2f}s — too slow"
    # 50 scenes × 20 entities, no alias overlap → all 1000 distinct.
    assert len(out.entities) == 1000


def test_legacy_chapter_no_scenes_returns_empty_chapter_kg():
    """D8 fallback path — orchestrator wraps legacy chapter in 1 virtual scene
    upstream; tree_merge sees that scene as input. Here we test the
    truly-empty case (no scenes at all) returns clean empty KG."""
    out = tree_merge_chapter("ch-legacy", "legacy/chapter-1", [])
    assert len(out.entities) == 0
    assert len(out.relations) == 0
    assert len(out.events) == 0
    assert len(out.facts) == 0
