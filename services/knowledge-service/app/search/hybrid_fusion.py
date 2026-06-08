"""Raw-search Phase 2 — hybrid fusion (pure, no I/O).

Reciprocal Rank Fusion (RRF) fuses the lexical leg (book-service, trigram)
and the semantic leg (Neo4j passage vectors, cosine). RRF is RANK-based, so
the two legs' incomparable score scales fuse fairly (spec §3.4, ADJ-3).
"""

from __future__ import annotations

from typing import Any

RRF_K = 60
PER_CHAPTER_CAP = 3
# E5: "block" granularity (exhaustive mining) lifts the per-chapter cap so
# every matching block can surface; "chapter" granularity uses cap=1 (best
# block per chapter). A large finite cap (vs None) keeps the function total.
BLOCK_CHAPTER_CAP = 10_000

Hit = dict[str, Any]


def _hit_key(hit: Hit) -> tuple:
    """Stable identity for a hit. `surface` distinguishes the legs
    (lexical=draft / semantic=canon in v1), and position is the chunk
    (semantic) or block (lexical) index within the chapter.

    chunkIndex is preferred because it is UNIQUE per passage; blockIndex is
    NOT (P3-C: several chunks of one oversized paragraph share a block_index).
    Keying on blockIndex would collide distinct semantic passages and drop
    them in fusion (review-impl MED-1). Lexical hits carry only blockIndex."""
    loc = hit.get("location") or {}
    pos = loc.get("chunkIndex")
    if pos is None:
        pos = loc.get("blockIndex")
    return (hit.get("chapterId"), hit.get("surface"), pos)


def rrf_fuse(ranked_lists: list[list[Hit]], *, k: int = RRF_K) -> list[Hit]:
    """Fuse already-ranked per-leg lists into one ranked list.

    Each leg MUST be in descending relevance order. A hit's fused score is
    Σ 1/(k + rank) across the legs it appears in; the hit's `score` field is
    replaced with this RRF score. Order is preserved deterministically
    (insertion order breaks ties).
    """
    scores: dict[tuple, float] = {}
    chosen: dict[tuple, Hit] = {}
    order: list[tuple] = []
    for leg in ranked_lists:
        for rank, hit in enumerate(leg):
            key = _hit_key(hit)
            scores[key] = scores.get(key, 0.0) + 1.0 / (k + rank + 1)
            if key not in chosen:
                chosen[key] = hit
                order.append(key)
    fused = [{**chosen[key], "score": round(scores[key], 6)} for key in order]
    fused.sort(key=lambda h: h["score"], reverse=True)
    return fused


def cap_per_chapter(hits: list[Hit], *, cap: int = PER_CHAPTER_CAP) -> list[Hit]:
    """Keep at most `cap` hits per chapterId (post-fusion order preserved)
    so one chapter can't flood the top of the results."""
    seen: dict[Any, int] = {}
    out: list[Hit] = []
    for hit in hits:
        cid = hit.get("chapterId")
        n = seen.get(cid, 0)
        if n >= cap:
            continue
        seen[cid] = n + 1
        out.append(hit)
    return out


def apply_relevance_floor(hits: list[Hit], min_relevance: float) -> list[Hit]:
    """E5 — drop hits whose native `relevance` (0–1: lexical similarity /
    semantic cosine) is below `min_relevance`. This is the score-floor that
    suppresses junk: a negative-control query (e.g. an absent term) returns
    only low-cosine nearest-neighbours, which the floor removes.

    A hit MISSING `relevance` passes through (treated as 1.0) so a leg that
    doesn't yet emit the field is never silently nuked. `min_relevance <= 0`
    is a no-op (floor disabled)."""
    if min_relevance <= 0.0:
        return hits
    return [h for h in hits if float(h.get("relevance", 1.0)) >= min_relevance]
