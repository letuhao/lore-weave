"""Raw-search Phase 2 — hybrid fusion (pure, no I/O).

Reciprocal Rank Fusion (RRF) fuses the lexical leg (book-service, trigram)
and the semantic leg (Neo4j passage vectors, cosine). RRF is RANK-based, so
the two legs' incomparable score scales fuse fairly (spec §3.4, ADJ-3).
"""

from __future__ import annotations

from typing import Any

RRF_K = 60
PER_CHAPTER_CAP = 3

Hit = dict[str, Any]


def _hit_key(hit: Hit) -> tuple:
    """Stable identity for a hit. `surface` distinguishes the legs
    (lexical=draft / semantic=canon in v1), and position is the block
    (lexical) or chunk (semantic) index within the chapter."""
    loc = hit.get("location") or {}
    pos = loc.get("blockIndex")
    if pos is None:
        pos = loc.get("chunkIndex")
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
