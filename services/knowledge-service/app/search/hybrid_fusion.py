"""Raw-search Phase 2 — hybrid fusion (pure, no I/O).

Reciprocal Rank Fusion (RRF) fuses the lexical leg (book-service, trigram)
and the semantic leg (Neo4j passage vectors, cosine). RRF is RANK-based, so
the two legs' incomparable score scales fuse fairly (spec §3.4, ADJ-3).
"""

from __future__ import annotations

import re
from typing import Any

RRF_K = 60
# KG-ML M4 (D5/DD6) — default language-preference boost. ≈ a rank-0 RRF
# contribution at k=60 (1/(60+1) ≈ 0.0164): a language match adds roughly the
# weight of appearing first in one leg — enough to lift a reader-language hit
# above an equally-fused off-language one, without overpowering a hit that wins
# both legs. Env-tunable (settings.lang_pref_weight); tune against the eval set.
DEFAULT_LANG_PREF_WEIGHT = 0.0164
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


def normalize_lang(value: Any) -> str:
    """ISO-639-1 primary subtag, lowercased (BCP-47 region/script stripped:
    "zh-Hant"→"zh", "en_US"→"en"). "" for empty/None/"unknown". Mirrors
    `passage_ingester.resolve_source_lang`'s normalization so both sides of the
    M4 `reader_pref == source_lang` comparison agree on the primary subtag."""
    s = str(value or "").strip().lower()
    if not s or s == "unknown":
        return ""
    return re.split(r"[-_]", s, maxsplit=1)[0]


def apply_language_preference(
    hits: list[Hit], pref_lang: str | None, *, w_lang: float = DEFAULT_LANG_PREF_WEIGHT,
) -> list[Hit]:
    """KG-ML M4 (D5/DD6) — soft language-preference re-ranking.

    Applied POST-RRF / PRE-rerank. For each hit, a match on the reader's
    preferred language adds `w_lang` to the fused score; hits then re-sort by
    ``(boosted_score, lang_match, fused_score)`` — a deterministic order where
    language is a soft tiebreaker, never a hard filter (robust to partial
    translation; an off-language hit with no on-language alternative still
    surfaces). A ``"mixed"`` passage matches ANY preference (it contains the
    reader's language). The original fused RRF score is preserved on
    ``fusedScore`` so a later rerank / floor can still reason about it.

    No-op when `pref_lang` is empty/None (the wiki in-process path and any
    caller that doesn't resolve a reader language) — order is unchanged.
    """
    pref = normalize_lang(pref_lang)
    if not pref:
        return hits
    for h in hits:
        hl = normalize_lang(h.get("sourceLang"))
        match = bool(hl) and (hl == pref or hl == "mixed")
        fused = float(h.get("score") or 0.0)
        h["fusedScore"] = fused
        h["langMatch"] = match
        h["score"] = round(fused + (w_lang if match else 0.0), 6)
    hits.sort(
        key=lambda h: (
            float(h.get("score") or 0.0),
            1 if h.get("langMatch") else 0,
            float(h.get("fusedScore") or 0.0),
        ),
        reverse=True,
    )
    return hits


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
