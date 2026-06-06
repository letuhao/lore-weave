"""L2 glossary fallback selector.

Given a project and a user message, returns the ranked list of
glossary entities that should be injected into the memory block.

## Why extract candidates client-side

K2b's `select-for-context` endpoint runs four tiers: pinned, exact,
fts, recent. The FTS tier uses Postgres's `plainto_tsquery('simple',
query)` which AND-combines every token in the query:

    "Tell me about Kai"  →  tell & me & about & kai

For an entity whose search_vector contains only `kai` (because that's
its cached_name), this query fails: not all four tokens appear. The
user asking a natural-language question gets zero FTS hits and falls
through to the recent-edited tier — a clear quality loss, masked only
by pinned entities.

The fix is to extract proper-noun candidates from the message
client-side (K4.3) and issue one K2b call per candidate. K2b's exact
tier then reliably hits because each query IS a name. Results are
deduped by entity_id and merged in first-occurrence order so earlier
candidates' tier-0/tier-1 hits take priority.

Calls run in parallel via asyncio.gather — N candidates × 50ms each
stays within our 300ms Gate-3 latency budget.

## Edge cases handled

  - project.book_id is None         → empty list
  - glossary-service is down         → empty list (client degraded)
  - no proper nouns in message       → one K2b call with empty query
                                        (tier-0 pinned + tier-3 recent)
  - candidate count > MAX_CANDIDATES → first MAX_CANDIDATES used
  - duplicate candidates             → case-insensitive dedupe

The Mode builder just iterates whatever we return.
"""

import asyncio
import logging
import re
from uuid import UUID

from app.clients.embedding_client import EmbeddingClient
from app.clients.glossary_client import GlossaryClient, GlossaryEntityForContext
from app.context.query_embedding import embed_query_cached
from app.context.formatters.stopwords import (
    ARTICLE_STOPPHRASES,
    CJK_PARTICLES,
    STOPPHRASES_LOWER,
)
from app.db.models import Project
from app.db.neo4j import neo4j_session
from app.db.neo4j_helpers import CypherSession
from app.db.neo4j_repos.entities import find_entities_by_vector

logger = logging.getLogger(__name__)

__all__ = [
    "extract_candidates",
    "select_glossary_for_context",
    "select_glossary_semantic",
]


# ── candidate extraction ───────────────────────────────────────────────────

# Matches English capitalized phrases: `Kai`, `Master Lin`, `The Dragon Lord`.
# Limited to 1-3 word sequences to avoid false-positive sentence starts.
_ENGLISH_CAPITALIZED = re.compile(
    r"\b[A-Z][a-z]+(?:[\s\-][A-Z][a-z]+){0,2}\b"
)

# Matches runs of 2+ CJK characters. The run is then re-split inside
# _push_cjk on CJK_PARTICLES (shared in app.context.formatters.stopwords).
# Python's `re` doesn't support character-class intersection, which is
# why we split in two passes.
_CJK_RUN = re.compile(r"[\u4e00-\u9fff]{2,}")

# Secondary splitter used inside _push_cjk to break long CJK runs at particles.
_CJK_SPLIT = re.compile(f"[{CJK_PARTICLES}]+")

# Matches double-quoted and single-quoted strings.
_QUOTED = re.compile(r"\"([^\"]+)\"|'([^']+)'")

MAX_CANDIDATES = 5


def extract_candidates(message: str, *, max_candidates: int = MAX_CANDIDATES) -> list[str]:
    """Return a deduped list of proper-noun candidates from `message`.

    The returned list preserves first-occurrence order so the most
    specific / leftmost mentions take priority. Case-insensitive
    dedupe. Each candidate is trimmed of surrounding whitespace.
    """
    if not message:
        return []

    out: list[str] = []
    seen_lower: set[str] = set()

    def _push_one(s: str) -> None:
        """Append `s` to the candidate list if it isn't a duplicate or
        a bare stopphrase. Common dedup tail used by both _push paths.
        """
        if not s:
            return
        key = s.lower()
        if key in STOPPHRASES_LOWER:
            return
        if key in seen_lower:
            return
        seen_lower.add(key)
        out.append(s)

    def _push(raw: str, *, trusted: bool = False) -> None:
        """Push a candidate.

        - `trusted=True` (quoted strings): no stripping at all. The user
          explicitly wrapped the phrase, "The Wanderer" stays intact.
        - `trusted=False` (regex matches): handles three cases:
            1. Leading word is a verb/pronoun stopphrase ("Is Mary-Anne")
               → strip aggressively, push only the stripped form.
            2. Leading word is an article ("The Wanderer")
               → push BOTH "The Wanderer" AND "Wanderer". Articles can
               legitimately prefix titles (K4-I6); we let K2b decide.
            3. No leading stopphrase → push as-is.
        """
        s = raw.strip()
        if not s:
            return
        if trusted:
            _push_one(s)
            return

        tokens = s.split()
        if not tokens:
            return

        first_lower = tokens[0].lower()
        if first_lower in ARTICLE_STOPPHRASES and len(tokens) >= 2:
            # Multi-token phrase starting with article — keep both forms.
            _push_one(s)
            _push_one(" ".join(tokens[1:]))
            return

        # Default: strip leading verb/pronoun stopphrases.
        while tokens and tokens[0].lower() in STOPPHRASES_LOWER:
            tokens = tokens[1:]
        if not tokens:
            return
        _push_one(" ".join(tokens))

    def _push_cjk(raw: str) -> None:
        """Push a CJK run, splitting on common stopword particles first.

        `告诉我关于李雲的故事` → split on `的` → `告诉我关于李雲`, `故事`.
        Still imperfect without a segmenter, but better than pushing the
        whole sentence as one candidate.
        """
        for segment in _CJK_SPLIT.split(raw):
            segment = segment.strip()
            if len(segment) >= 2:
                _push(segment)
                if len(out) >= max_candidates:
                    return

    # 1) Quoted strings first — strongest signal of a name. Trusted
    #    (no stopphrase stripping) because the user explicitly wrapped
    #    the phrase: "The Wanderer" stays intact.
    for match in _QUOTED.finditer(message):
        _push(match.group(1) or match.group(2) or "", trusted=True)
        if len(out) >= max_candidates:
            return out

    # 2) English capitalized phrases. For `Master Lin` we also push `Lin`
    #    (the last token) so a brute exact-match on the bare name wins.
    for match in _ENGLISH_CAPITALIZED.finditer(message):
        phrase = match.group(0)
        _push(phrase)
        if len(out) >= max_candidates:
            return out
        if " " in phrase or "-" in phrase:
            tail = re.split(r"[\s\-]+", phrase)[-1]
            _push(tail)
            if len(out) >= max_candidates:
                return out

    # 3) CJK character runs (2+ chars), split on particles.
    for match in _CJK_RUN.finditer(message):
        _push_cjk(match.group(0))
        if len(out) >= max_candidates:
            return out

    return out


# ── selector ───────────────────────────────────────────────────────────────


def _estimate_entity_tokens(e: GlossaryEntityForContext) -> int:
    """Rough token estimate for an entity's rendered context form
    (name + aliases + short_description). CJK ≈ 1 token/char, latin ≈ 1/4;
    over-estimate is safe — mirrors the writeback metering heuristic."""
    text = " ".join(
        s for s in (
            e.cached_name or "",
            " ".join(e.cached_aliases or []),
            e.short_description or "",
        ) if s
    )
    if not text:
        return 1
    cjk = sum(1 for ch in text if "一" <= ch <= "鿿")
    other = len(text) - cjk
    return cjk + max(1, other // 4)


async def select_glossary_semantic(
    *,
    session: CypherSession,
    embedding_client: EmbeddingClient,
    glossary_client: GlossaryClient,
    user_id: UUID,
    project_id: UUID,
    book_id: UUID,
    embedding_model: str | None,
    embedding_dimension: int | None,
    query: str,
    max_entities: int = 20,
    max_tokens: int = 800,
) -> list[GlossaryEntityForContext]:
    """mui #4 — semantic glossary selection (architecture B).

    Embed the query, vector-search `:Entity` nodes (knowledge owns the
    embeddings), keep only glossary-anchored hits, enrich them via glossary's
    `entities/by-ids`, and rank by `weighted_score`. Best-effort: returns []
    on missing embedding config or any failure (the caller falls back to FTS).
    Only `glossary_entity_id`-anchored entities are returned, so orphan KG
    nodes never leak into glossary context (AC6).
    """
    if not query.strip() or not embedding_model or not embedding_dimension:
        return []

    try:
        vector = await embed_query_cached(
            embedding_client,
            user_id=user_id,
            project_id=str(project_id),
            embedding_model=embedding_model,
            message=query,
        )
    except Exception:
        logger.warning("semantic glossary: embed failed (non-fatal)", exc_info=True)
        return []
    if not vector:
        return []

    try:
        hits = await find_entities_by_vector(
            session,
            user_id=str(user_id),
            project_id=str(project_id),
            query_vector=vector,
            dim=embedding_dimension,
            embedding_model=embedding_model,
            limit=max_entities,
        )
    except Exception:
        logger.warning(
            "semantic glossary: vector search failed (non-fatal)", exc_info=True
        )
        return []

    # weighted_score = raw_score * anchor_score (two-layer). Sort defensively
    # in case the index query order isn't relied upon, then keep the first
    # occurrence of each glossary-anchored id.
    hits.sort(key=lambda h: h.weighted_score, reverse=True)
    ranked_ids: list[str] = []
    score_by_id: dict[str, float] = {}
    for h in hits:
        gid = h.entity.glossary_entity_id
        if not gid or gid in score_by_id:
            continue
        score_by_id[gid] = h.weighted_score
        ranked_ids.append(gid)
    if not ranked_ids:
        return []

    rows = await glossary_client.fetch_entities_by_ids(
        book_id=book_id, entity_ids=ranked_ids
    )
    by_id = {r.entity_id: r for r in rows}
    out: list[GlossaryEntityForContext] = []
    for gid in ranked_ids:  # preserve vector rank order
        r = by_id.get(gid)
        if r is None:
            continue
        r.tier = "semantic"
        r.rank_score = score_by_id[gid]
        out.append(r)

    # mui #4 MED-1 — respect max_tokens (parity with FTS select-for-context,
    # which trims its response to the token budget). Without this the semantic
    # block could overrun the caller's glossary budget. Always keep at least
    # the top-ranked entity; stop before the budget would go negative.
    trimmed: list[GlossaryEntityForContext] = []
    budget = max_tokens
    for r in out[:max_entities]:
        cost = _estimate_entity_tokens(r)
        if trimmed and cost > budget:
            break
        budget -= cost
        trimmed.append(r)
    return trimmed


async def _pinned_entities(
    client: GlossaryClient, user_id: UUID, book_id: UUID, max_tokens: int
) -> list[GlossaryEntityForContext]:
    """Fetch just the pinned tier (empty-query select-for-context returns
    pinned + recent; keep only pinned). Best-effort — [] on failure."""
    rows = await client.select_for_context(
        user_id=user_id, book_id=book_id, query="",
        max_entities=10, max_tokens=max_tokens,
    )
    return [r for r in rows if r.tier == "pinned"]


async def _semantic_with_pinned(
    client: GlossaryClient,
    embedding_client: EmbeddingClient,
    *,
    user_id: UUID,
    project: Project,
    message: str,
    max_entities: int,
    max_tokens: int,
) -> list[GlossaryEntityForContext]:
    """mui #4 K-2: vector-ranked entities + pinned merged ahead. Returns []
    if semantic yielded nothing (caller falls back to FTS)."""
    async with neo4j_session() as session:
        semantic = await select_glossary_semantic(
            session=session,
            embedding_client=embedding_client,
            glossary_client=client,
            user_id=user_id,
            project_id=project.project_id,
            book_id=project.book_id,
            embedding_model=project.embedding_model,
            embedding_dimension=project.embedding_dimension,
            query=message,
            max_entities=max_entities,
            max_tokens=max_tokens,
        )
    if not semantic:
        return []
    # Pinned is an authoring signal vectors can't represent — merge it ahead
    # of the semantic hits, deduped by entity_id (AC3).
    pinned = await _pinned_entities(client, user_id, project.book_id, max_tokens)
    seen: set[str] = set()
    out: list[GlossaryEntityForContext] = []
    for e in [*pinned, *semantic]:
        if e.entity_id in seen:
            continue
        seen.add(e.entity_id)
        out.append(e)
    return out[:max_entities]


async def select_glossary_for_context(
    client: GlossaryClient,
    *,
    user_id: UUID,
    project: Project,
    message: str,
    max_entities: int = 20,
    max_tokens: int = 800,
    embedding_client: EmbeddingClient | None = None,
) -> list[GlossaryEntityForContext]:
    if project.book_id is None:
        return []

    # mui #4 — semantic-first when embeddings are available (Mode 3 passes
    # embedding_client; Mode 2/static has none → FTS as before). On empty or
    # any failure, select_glossary_semantic returns [] and we fall through to
    # the FTS candidate path below — graceful degradation (AC2/AC5).
    if embedding_client is not None and project.embedding_model:
        semantic = await _semantic_with_pinned(
            client, embedding_client,
            user_id=user_id, project=project, message=message,
            max_entities=max_entities, max_tokens=max_tokens,
        )
        if semantic:
            return semantic

    candidates = extract_candidates(message)

    if not candidates:
        # No proper nouns → single call with empty query. K2b's tier 0
        # still returns pinned entities and tier 3 fills in recents when
        # nothing else matched. Single round trip, no parallelism.
        return await client.select_for_context(
            user_id=user_id,
            book_id=project.book_id,
            query="",
            max_entities=max_entities,
            max_tokens=max_tokens,
        )

    # K4-I2: divide the entity budget across candidates with a small
    # safety cushion. Without this, every parallel K2b call asked for
    # the FULL max_entities, fetching up to N×max_entities rows that
    # we'd then dedupe and truncate to max_entities — wasted bandwidth
    # and wasted Postgres work. The +2 cushion absorbs duplicates from
    # K2b's pinned tier (which runs unconditionally on every query).
    per_call_limit = max(5, (max_entities // len(candidates)) + 2)
    tasks = [
        client.select_for_context(
            user_id=user_id,
            book_id=project.book_id,
            query=candidate,
            max_entities=per_call_limit,
            max_tokens=max_tokens,
        )
        for candidate in candidates
    ]
    results = await asyncio.gather(*tasks)

    # Merge preserving first-occurrence order across candidates.
    seen: set[str] = set()
    merged: list[GlossaryEntityForContext] = []
    for result_list in results:
        for entity in result_list:
            if entity.entity_id in seen:
                continue
            seen.add(entity.entity_id)
            merged.append(entity)
            if len(merged) >= max_entities:
                return merged
    return merged
