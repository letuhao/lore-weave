"""P3 — Deterministic Python tree-merge (spec D1 + H2 chunked strategy).

Bottom-up merge: scene KGs -> ChapterKG (in memory, small).
Part/Book aggregation reads ChapterKG / PartKG SUMMARIES from Postgres
(not raw entities) to keep memory bounded — see H2 fix.

This module is pure-Python + dependency-free w.r.t. Neo4j: it consumes
Pydantic candidates and produces ChapterKG / PartKG / BookKG dataclasses
that hierarchy_writer + pass2_writer write to Neo4j in a single Tx
(per D2a).

Tarjan union-find: O(N α(N)) ~ linear; tested against the per-scene
entity counts typical of a chapter (~50-100 entities).

Cross-chapter dedup at merge time is OUT OF SCOPE (D-P3-WHOLE-BOOK-MERGE-
FOR-COREF). Global canonical_id_map at pass2_writer handles cross-
chapter via existing K11 merge logic.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Iterable

logger = logging.getLogger(__name__)

__all__ = [
    "SceneKG",
    "ChapterKG",
    "tree_merge_chapter",
    "alias_union_find",
]


# ── Dataclasses (Python in-process; do NOT import Pydantic to keep cheap) ──


@dataclass
class _EntityShape:
    """Minimal entity shape used by tree_merge. Mirrors
    loreweave_extraction.LLMEntityCandidate but as plain dataclass
    for fast Python ops + serialization."""
    name: str
    canonical_id: str
    canonical_name: str
    kind: str
    aliases: list[str] = field(default_factory=list)
    confidence: float = 0.0


@dataclass
class _RelationShape:
    subject_canonical_id: str
    predicate: str
    object_canonical_id: str
    polarity: str = "asserts"  # asserts | negates


@dataclass
class _EventShape:
    name_norm: str
    time_cue: str | None = None
    participants: list[str] = field(default_factory=list)


@dataclass
class _FactShape:
    subject_canonical_id: str
    attribute: str
    value: str


@dataclass
class SceneKG:
    """Input shape: one scene's extracted candidates."""
    scene_id: str
    scene_path: str  # "book/part-1/chapter-3/scene-2"
    entities: list[_EntityShape] = field(default_factory=list)
    relations: list[_RelationShape] = field(default_factory=list)
    events: list[_EventShape] = field(default_factory=list)
    facts: list[_FactShape] = field(default_factory=list)


@dataclass
class ChapterKG:
    """Output shape: merged candidates for a chapter, ready to write."""
    chapter_id: str
    chapter_path: str  # "book/part-1/chapter-3"
    scenes: list[SceneKG]
    entities: list[_EntityShape]
    relations: list[_RelationShape]
    events: list[_EventShape]
    facts: list[_FactShape]
    canonical_id_map: dict[str, str]  # alias canonical_id -> merged canonical_id


# ── Tarjan union-find (path compression + union by rank) ────────────────────


class _UnionFind:
    """Simple union-find with path compression. Supports `find` + `union`."""

    def __init__(self) -> None:
        self._parent: dict[str, str] = {}
        self._rank: dict[str, int] = {}

    def make(self, x: str) -> None:
        if x not in self._parent:
            self._parent[x] = x
            self._rank[x] = 0

    def find(self, x: str) -> str:
        self.make(x)
        # Path compression.
        root = x
        while self._parent[root] != root:
            root = self._parent[root]
        # Compress.
        current = x
        while self._parent[current] != root:
            nxt = self._parent[current]
            self._parent[current] = root
            current = nxt
        return root

    def union(self, x: str, y: str) -> None:
        rx, ry = self.find(x), self.find(y)
        if rx == ry:
            return
        # Union by rank.
        if self._rank[rx] < self._rank[ry]:
            rx, ry = ry, rx
        self._parent[ry] = rx
        if self._rank[rx] == self._rank[ry]:
            self._rank[rx] += 1


def alias_union_find(entities: Iterable[_EntityShape]) -> dict[str, str]:
    """Build canonical_id_map: any entity sharing >=2 aliases is unioned.

    Returns: dict mapping every entity's canonical_id -> its merged-root
    canonical_id. Entities with no alias overlap map to themselves.

    Algorithm:
      - For each pair of entities (e1, e2): if |aliases(e1) ∩ aliases(e2)| >= 2,
        union them.
      - Result: every entity's canonical_id maps to its UF root.
    """
    uf = _UnionFind()
    entities_list = list(entities)
    for e in entities_list:
        uf.make(e.canonical_id)

    # O(N²) pairwise check — acceptable for per-chapter (N ~ 50-100).
    # If chapter grows large, switch to inverted-index (alias -> entity list).
    for i, e1 in enumerate(entities_list):
        if not e1.aliases:
            continue
        e1_aliases = set(e1.aliases)
        for e2 in entities_list[i + 1 :]:
            if not e2.aliases:
                continue
            shared = e1_aliases & set(e2.aliases)
            if len(shared) >= 2:
                uf.union(e1.canonical_id, e2.canonical_id)

    return {e.canonical_id: uf.find(e.canonical_id) for e in entities_list}


# ── Per-chapter merge ──────────────────────────────────────────────────────


def _merge_entity_pair(a: _EntityShape, b: _EntityShape) -> _EntityShape:
    """Pick the higher-confidence entity as the canonical form; union aliases."""
    if b.confidence > a.confidence:
        primary, secondary = b, a
    else:
        primary, secondary = a, b
    merged_aliases = sorted(set(primary.aliases) | set(secondary.aliases))
    return _EntityShape(
        name=primary.name,
        canonical_id=primary.canonical_id,
        canonical_name=primary.canonical_name,
        kind=primary.kind,
        aliases=merged_aliases,
        confidence=max(primary.confidence, secondary.confidence),
    )


def tree_merge_chapter(
    chapter_id: str, chapter_path: str, scene_kgs: list[SceneKG],
) -> ChapterKG:
    """Merge per-scene KGs into a single ChapterKG.

    Idempotent: same input -> same output (preserves canonical_id_map
    deterministic ordering).

    H2 fix: this operates on ONE chapter at a time. Caller is responsible
    for invoking per-chapter (chunked) instead of loading the whole book
    in memory.
    """
    if not scene_kgs:
        return ChapterKG(
            chapter_id=chapter_id,
            chapter_path=chapter_path,
            scenes=[],
            entities=[],
            relations=[],
            events=[],
            facts=[],
            canonical_id_map={},
        )

    # 1. Collect all entities + build alias UF.
    all_entities: list[_EntityShape] = []
    for sk in scene_kgs:
        all_entities.extend(sk.entities)
    canonical_map = alias_union_find(all_entities)

    # 2. Re-key entities by canonical_id_map; merge duplicates by canonical_id.
    merged_entities_by_cid: dict[str, _EntityShape] = {}
    for e in all_entities:
        cid = canonical_map.get(e.canonical_id, e.canonical_id)
        # Re-write the entity to use the merged canonical_id.
        e_rekeyed = _EntityShape(
            name=e.name,
            canonical_id=cid,
            canonical_name=e.canonical_name,
            kind=e.kind,
            aliases=e.aliases,
            confidence=e.confidence,
        )
        if cid in merged_entities_by_cid:
            merged_entities_by_cid[cid] = _merge_entity_pair(
                merged_entities_by_cid[cid], e_rekeyed
            )
        else:
            merged_entities_by_cid[cid] = e_rekeyed

    # 3. Re-key relations using canonical_id_map; dedup by composite key.
    seen_relations: set[tuple[str, str, str, str]] = set()
    merged_relations: list[_RelationShape] = []
    for sk in scene_kgs:
        for r in sk.relations:
            subj = canonical_map.get(r.subject_canonical_id, r.subject_canonical_id)
            obj = canonical_map.get(r.object_canonical_id, r.object_canonical_id)
            key = (subj, r.predicate, obj, r.polarity)
            if key in seen_relations:
                continue
            seen_relations.add(key)
            merged_relations.append(_RelationShape(
                subject_canonical_id=subj,
                predicate=r.predicate,
                object_canonical_id=obj,
                polarity=r.polarity,
            ))

    # 4. Events: dedup by (name_norm, time_cue).
    seen_events: set[tuple[str, str | None]] = set()
    merged_events: list[_EventShape] = []
    for sk in scene_kgs:
        for ev in sk.events:
            key = (ev.name_norm, ev.time_cue)
            if key in seen_events:
                continue
            seen_events.add(key)
            merged_events.append(ev)

    # 5. Facts: dedup by (subject_canonical_id, attribute, value).
    seen_facts: set[tuple[str, str, str]] = set()
    merged_facts: list[_FactShape] = []
    for sk in scene_kgs:
        for f in sk.facts:
            subj = canonical_map.get(f.subject_canonical_id, f.subject_canonical_id)
            key = (subj, f.attribute, f.value)
            if key in seen_facts:
                continue
            seen_facts.add(key)
            merged_facts.append(_FactShape(
                subject_canonical_id=subj,
                attribute=f.attribute,
                value=f.value,
            ))

    # Deterministic ordering: entities by canonical_id; relations by key tuple.
    sorted_entities = sorted(merged_entities_by_cid.values(), key=lambda e: e.canonical_id)
    sorted_relations = sorted(
        merged_relations,
        key=lambda r: (r.subject_canonical_id, r.predicate, r.object_canonical_id, r.polarity),
    )
    sorted_events = sorted(
        merged_events, key=lambda e: (e.name_norm, e.time_cue or ""),
    )
    sorted_facts = sorted(
        merged_facts, key=lambda f: (f.subject_canonical_id, f.attribute, f.value),
    )

    return ChapterKG(
        chapter_id=chapter_id,
        chapter_path=chapter_path,
        scenes=scene_kgs,
        entities=sorted_entities,
        relations=sorted_relations,
        events=sorted_events,
        facts=sorted_facts,
        canonical_id_map=canonical_map,
    )
