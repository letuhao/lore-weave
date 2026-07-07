"""M-recall — CJK/VI-aware entity-anchor resolution via Aho-Corasick.

**Why this exists.** The intent classifier (`app.context.intent.classifier`)
extracts anchor entities by splitting on whitespace/punctuation. That works for
Latin scripts but FAILS on scriptio-continua (Chinese/Japanese have no spaces):
for "九王子修炼什么武功？" it emits the whole clause as one "entity", so
`select_l2_facts` resolves nothing and returns **0 facts** — even when the answer
("九王子 —practices→ 龙象般若掌") is a single 1-hop relation in the graph.
Measured on 万古神帝: 3/12 goldens missed purely on this.

**The fix.** We already KNOW every entity's name — so this is *dictionary
matching*, not segmentation. Build a per-project Aho-Corasick automaton over the
entity names + aliases and find which appear in the message. Language-agnostic
(zh/ja/ko/vi in one path — jieba would only cover zh), exact (no segmentation
errors), and sub-millisecond via the C extension even at scale.

The resolved anchor names are UNIONed into `intent.entities` for the L2 facts +
M1a bridge path. Gated to non-Latin messages (Latin scripts already segment on
whitespace; running it there risks over-matching short entity names like "Will"
inside "I will"). Kill-switch `context_dict_anchor_enabled`.
"""

from __future__ import annotations

import logging
import time

try:
    import ahocorasick  # pyahocorasick (prebuilt manylinux wheel; see requirements.txt)

    _AHOCORASICK_OK = True
except Exception:  # dep missing in a stripped env — degrade to no dict-anchoring
    ahocorasick = None  # type: ignore[assignment]
    _AHOCORASICK_OK = False
    logging.getLogger(__name__).warning(
        "pyahocorasick unavailable — CJK/VI dictionary-anchor recall disabled "
        "(select_l2_facts falls back to classifier-only anchors)."
    )

from app.db.neo4j import neo4j_session
from app.db.neo4j_repos.entities import list_project_entity_names

logger = logging.getLogger(__name__)

__all__ = [
    "has_non_ascii_letter",
    "resolve_anchors",
    "get_anchor_index",
    "clear_anchor_cache",
]


def has_non_ascii_letter(text: str) -> bool:
    """True when the message carries a non-ASCII LETTER — the signal that a
    whitespace-blind classifier can't be trusted to anchor (CJK, or Vietnamese
    with its diacritics). Pure-ASCII English returns False (classifier is fine)."""
    return any(ord(c) > 127 and c.isalpha() for c in text)


# ── per-project automaton cache ─────────────────────────────────────────────
# The entity dictionary changes only when extraction runs, so a short TTL is
# plenty: at most `ttl` seconds of staleness (a newly-extracted entity becomes
# anchorable within the window). Keyed by (user_id, project_id). Value is the
# built automaton or None (project has no entities yet — cached so we don't
# re-query every turn). `time.monotonic` so a wall-clock change can't wedge it.
_CACHE: dict[tuple[str, str], tuple[float, object | None]] = {}


def clear_anchor_cache() -> None:
    """Test seam — drop the cache so a fresh dictionary is loaded."""
    _CACHE.clear()


async def get_anchor_index(
    user_id: str,
    project_id: str,
    *,
    ttl_s: float = 300.0,
    min_len: int = 2,
) -> object | None:
    """Return a cached Aho-Corasick automaton over the project's entity names +
    aliases (value = the canonical display name `find_entities_by_name` resolves),
    or None when pyahocorasick is unavailable / the project has no entities.

    Loads via one owner+project-scoped Neo4j read on a cache miss; degrade-safe
    (any load failure → None, so grounding proceeds classifier-only)."""
    if not _AHOCORASICK_OK:
        return None
    key = (user_id, project_id)
    now = time.monotonic()
    cached = _CACHE.get(key)
    if cached is not None and (now - cached[0]) < ttl_s:
        return cached[1]

    try:
        async with neo4j_session() as session:
            rows = await list_project_entity_names(
                session, user_id=user_id, project_id=project_id
            )
    except Exception:
        logger.warning(
            "anchor index load failed user_id=%s project_id=%s — no dict-anchoring",
            user_id, project_id, exc_info=True,
        )
        _CACHE[key] = (now, None)  # cache the miss briefly to avoid hammering
        return None

    automaton = ahocorasick.Automaton()
    n = 0
    for name, aliases in rows:
        # Every surface form (name + aliases) is a pattern; the emitted value is
        # the canonical display name so anchors dedup + resolve consistently.
        for surface in (name, *aliases):
            if surface and len(surface) >= min_len:
                # Store (canonical_name, surface_len): iter() returns only the
                # VALUE, so we carry the surface length to compute the match span
                # correctly when an ALIAS differs in length from its canonical name.
                automaton.add_word(surface, (name, len(surface)))
                n += 1
    if n == 0:
        _CACHE[key] = (now, None)
        return None
    automaton.make_automaton()
    _CACHE[key] = (now, automaton)
    logger.info(
        "anchor index built user_id=%s project_id=%s entities=%d patterns=%d",
        user_id, project_id, len(rows), n,
    )
    return automaton


def resolve_anchors(
    automaton: object | None,
    message: str,
    *,
    max_anchors: int = 12,
    min_len: int = 2,
) -> list[str]:
    """Distinct canonical entity names whose surface form appears in `message`.

    Longest-match tiling (leftmost-longest): a shorter name nested inside a longer
    match ("王子" inside "九王子") is dropped, but the same short name standing
    alone elsewhere is kept. Order-preserving dedup, capped at `max_anchors`.
    Empty on no automaton / no match (degrade to classifier-only)."""
    if automaton is None or not message:
        return []
    spans: list[tuple[int, int, str]] = []
    for end_idx, (name, surf_len) in automaton.iter(message):  # type: ignore[attr-defined]
        # surf_len is the matched SURFACE length (name may be a longer/shorter
        # canonical for an alias), so the span is measured from the surface.
        start = end_idx - surf_len + 1
        if surf_len >= min_len:
            spans.append((start, end_idx, name))
    if not spans:
        return []
    # start asc, then longer first so the longest match at a position wins.
    spans.sort(key=lambda s: (s[0], -(s[1] - s[0])))
    picked: list[str] = []
    seen: set[str] = set()
    covered_end = -1
    for start, end, name in spans:
        if start > covered_end:  # non-overlapping with the last kept span
            if name not in seen:
                picked.append(name)
                seen.add(name)
                if len(picked) >= max_anchors:
                    break
            covered_end = end
    return picked
