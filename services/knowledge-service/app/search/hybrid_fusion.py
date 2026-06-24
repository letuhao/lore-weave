"""Raw-search Phase 2 — hybrid fusion (pure, no I/O).

Reciprocal Rank Fusion (RRF) fuses the lexical leg (book-service, trigram)
and the semantic leg (Neo4j passage vectors, cosine). RRF is RANK-based, so
the two legs' incomparable score scales fuse fairly (spec §3.4, ADJ-3).
"""

from __future__ import annotations

import re
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
    them in fusion (review-impl MED-1). Lexical hits carry only blockIndex.

    KG-ML M4 (/review-impl HIGH) — `sourceLang` is part of the key so a chapter's
    dual-indexed translation (vi) and its source (zh/en) passages do NOT collide:
    they share `chapterId` + `surface` (canon) + `chunkIndex` (the M2 node id keeps
    `source_id` clean), so without language in the key RRF would drop one language
    before the language-preference pass ever runs — silently denying a reader the
    very language they asked for. Mirrors `passage_canonical_id`, which already
    includes `source_lang` (DD1). Missing/None sourceLang groups together (pre-M4
    back-compat: single-language corpora behave exactly as before)."""
    loc = hit.get("location") or {}
    pos = loc.get("chunkIndex")
    if pos is None:
        pos = loc.get("blockIndex")
    return (hit.get("chapterId"), hit.get("surface"), pos, hit.get("sourceLang"))


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


def apply_language_preference(hits: list[Hit], pref_lang: str | None) -> list[Hit]:
    """KG-ML M4 (D5) — soft language-preference re-ordering.

    Applied as the FINAL ordering pass (post-rerank, post-floor, pre-cap) so it
    is the last word on order REGARDLESS of whether the cross-encoder rerank ran.
    It must therefore be SCALE-INDEPENDENT: a pre-rerank additive boost is
    discarded because rerank re-sorts the whole pool by its 0–1 relevance (and
    `w_lang` is meaningless on that scale) — the /review-impl HIGH this replaces.

    Mechanism: a STABLE partition — hits whose `sourceLang` matches the reader's
    preference move to the front, preserving the upstream (rerank-relevance or
    RRF) order WITHIN the matched and unmatched groups. Soft, never a hard
    filter: an off-language hit always still surfaces (just after matched ones),
    so partial translation degrades gracefully (no vi ⇒ the zh/en order is
    unchanged). Combined with the relevance floor upstream, the partition only
    re-orders survivors, never resurrects junk. A ``"mixed"`` passage matches ANY
    preference (it contains the reader's language). Sets ``langMatch`` for
    observability.

    No-op when `pref_lang` is empty/None (the wiki in-process path and any
    caller that doesn't resolve a reader language) — order is unchanged.
    Idempotent: re-running with the same pref preserves order.
    """
    pref = normalize_lang(pref_lang)
    if not pref:
        return hits
    for h in hits:
        hl = normalize_lang(h.get("sourceLang"))
        h["langMatch"] = bool(hl) and (hl == pref or hl == "mixed")
    # Stable sort: matched (key 0) before unmatched (key 1); Python's stable sort
    # preserves the incoming order within each group — so the upstream relevance
    # ranking is retained, just partitioned by language.
    hits.sort(key=lambda h: 0 if h.get("langMatch") else 1)
    return hits


def language_coverage(langs: list[Any], pref_lang: str | None) -> dict | None:
    """KG-ML M7 (C12) — coverage summary for a reader-language preference.

    Given the per-hit source languages of a result set + the reader's preference,
    report how much of what they're seeing is actually in their language, so the
    consumer can surface an HONEST coverage note (a vi reader on a partially-
    translated book should know "3 of 8 results are in Vietnamese"). Returns
    ``None`` when no preference is set (no note to show). ``in_language`` counts
    `mixed` passages (they contain the reader's language). ``note`` is None when
    coverage is full (nothing to flag) or there are no results."""
    pref = normalize_lang(pref_lang)
    if not pref:
        return None
    norm = [normalize_lang(x) for x in langs]
    total = len(norm)
    in_lang = sum(1 for x in norm if x and (x == pref or x == "mixed"))
    if total == 0 or in_lang == total:
        note = None
    elif in_lang == 0:
        note = f"No results in your language ({pref}); showing source-language results."
    else:
        note = (
            f"{in_lang} of {total} results are in your language ({pref}); "
            "the rest are shown in the source language."
        )
    return {
        "reader_lang": pref,
        "total": total,
        "in_language": in_lang,
        "partial": in_lang < total,
        "note": note,
    }


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
