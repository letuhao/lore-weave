"""
Glossary client for Translation Pipeline V2.

Fetches scoped glossary from glossary-service and builds a compact
context block for LLM prompt injection.

Design reference: TRANSLATION_PIPELINE_V2.md §4 (Tiered Glossary Injection)

Key principles:
- Glossary is fetched ONCE per chapter, injected into EVERY batch (stability)
- Graceful degradation: if glossary-service is down, translate without glossary
- Token budget cap: glossary block never exceeds max_tokens
- Auto-correct: post-process output to fix untranslated source terms
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

import httpx

from ..config import settings

log = logging.getLogger(__name__)

_GLOSSARY_FETCH_TIMEOUT = 5.0  # seconds


@dataclass
class GlossaryEntry:
    """A single glossary entity for translation context.

    ``confidence`` is the target translation's trust tier (``verified`` |
    ``machine`` | ``draft``) from glossary-service. ``None`` means the field was
    absent — a glossary build predating D-TRANSL-M1D — and is treated as legacy
    *trusted* (hard-checked) for backward compatibility. Both rolling-deploy
    orders are therefore safe with no ordering constraint: glossary-old +
    translation-new ⇒ key absent ⇒ legacy hard-check (old behavior); glossary-new
    + translation-old ⇒ the old client ignores the extra field entirely.
    """
    zh_names: list[str]
    target_names: list[str]
    kind: str
    confidence: str | None = None
    # M6b: the glossary entity anchor. Lets the worker record which entities a
    # chapter's translation used so a later entity change flags only the affected
    # chapters. None for a legacy glossary build predating the endpoint change.
    entity_id: str | None = None

    def to_jsonl(self, target_lang: str) -> str:
        """Format as compact JSONL line for prompt injection."""
        obj = {"zh": self.zh_names, "kind": self.kind}
        if self.target_names:
            obj[target_lang] = self.target_names
        return json.dumps(obj, ensure_ascii=False)


@dataclass
class GlossaryContext:
    """Complete glossary context for one chapter's translation."""
    entries: list[GlossaryEntry] = field(default_factory=list)
    prompt_block: str = ""
    token_estimate: int = 0
    # Source→target map for auto-correct post-processing + prompt (ALL tiers).
    correction_map: dict[str, str] = field(default_factory=dict)
    # M6b full-propagate: entity_ids of entries that scored > 0 — the glossary
    # entities this chapter's text actually references, recorded so a later
    # change to one of them flags only the chapters that used it.
    used_entity_ids: set[str] = field(default_factory=set)
    # D-TRANSL-M1D trust ladder: the canon-only subset of ``correction_map`` the
    # V3 verifier hard-enforces (HIGH wrong_name → re-translate). Excludes
    # ``machine``/``draft`` translations so an unverified term never forces churn.
    verified_map: dict[str, str] = field(default_factory=dict)


@dataclass
class ContextEntity:
    """A tiered glossary entity from select-for-context (M4b).

    Carries the ``entity_id`` (the anchor the knowledge layer keys on) plus the
    authored bio (name/kind/short_description) used for pronoun/honorific cues.
    """
    entity_id: str
    name: str
    aliases: list[str]
    short_description: str
    kind: str
    tier: str


async def fetch_translation_glossary(
    book_id: str,
    target_language: str,
    chapter_id: str | None = None,
    max_entries: int = 50,
) -> list[dict]:
    """Fetch scoped glossary entries from glossary-service.

    Calls: GET /internal/books/{book_id}/translation-glossary

    Returns raw dicts from the API, or empty list on any failure.
    """
    params = {"target_language": target_language, "max_entries": str(max_entries)}
    if chapter_id:
        params["chapter_id"] = chapter_id

    try:
        async with httpx.AsyncClient(timeout=_GLOSSARY_FETCH_TIMEOUT) as client:
            resp = await client.get(
                f"{settings.glossary_service_internal_url}"
                f"/internal/books/{book_id}/translation-glossary",
                params=params,
                headers={"X-Internal-Token": settings.internal_service_token},
            )
            if resp.status_code != 200:
                log.warning(
                    "glossary fetch returned %d for book=%s — translating without glossary",
                    resp.status_code, book_id,
                )
                return []
            return resp.json()
    except Exception as exc:
        log.warning(
            "glossary fetch failed for book=%s: %s — translating without glossary",
            book_id, exc,
        )
        return []


def build_glossary_context(
    raw_entries: list[dict],
    chapter_text: str,
    target_language: str,
    max_tokens: int = 1500,
) -> GlossaryContext:
    """Build scoped glossary context block for LLM prompt injection.

    Strategy (from V2 design §4):
    1. Parse raw entries into GlossaryEntry objects
    2. Score by occurrence count in chapter text × name length
    3. Format as JSONL within token budget
    4. Build correction_map for auto-correct post-processing

    Args:
        raw_entries: Dicts from glossary-service API.
        chapter_text: Full chapter text (for occurrence scoring).
        target_language: Target language code (e.g. "vi").
        max_tokens: Max tokens for glossary block.

    Returns:
        GlossaryContext with prompt_block and correction_map.
    """
    if not raw_entries:
        return GlossaryContext()

    # Parse entries
    entries: list[GlossaryEntry] = []
    _MISSING = object()
    for raw in raw_entries:
        zh_names = raw.get("zh", [])
        target_names = raw.get(target_language, [])
        kind = raw.get("kind", "")
        if not zh_names:
            continue
        # Distinguish an ABSENT confidence key (legacy glossary → None → trusted)
        # from a present-but-blank one ("" → demoted, not verified).
        raw_conf = raw.get("confidence", _MISSING)
        confidence = None if raw_conf is _MISSING else raw_conf
        entity_id = raw.get("entity_id") or None
        entries.append(GlossaryEntry(
            zh_names=zh_names, target_names=target_names, kind=kind,
            confidence=confidence, entity_id=entity_id,
        ))

    if not entries:
        return GlossaryContext()

    # Score by occurrence in chapter text × name length
    scored: list[tuple[int, GlossaryEntry]] = []
    # M6b: entities whose names appear in this chapter (score > 0) are the ones
    # the translation drew on — the staleness propagation unit. Pinned score-0
    # entities (not in this chapter's text) are NOT "used".
    used_entity_ids: set[str] = set()
    for entry in entries:
        score = 0
        for name in entry.zh_names:
            count = chapter_text.count(name)
            score += count * len(name)
        if score > 0 and entry.entity_id:
            used_entity_ids.add(entry.entity_id)
        # Include score-0 entries only if they have a target translation
        # (Tier 0 pinned entities — worth including even if not in this chunk)
        if score > 0 or entry.target_names:
            scored.append((score, entry))

    # Sort: highest score first (most relevant to this chapter)
    scored.sort(key=lambda x: -x[0])

    # Build JSONL lines within token budget
    lines: list[str] = []
    # D-T2-01: use the CJK-aware estimator from chunk_splitter instead
    # of the raw len/4. Glossary JSONL lines are mostly ASCII metadata
    # with CJK names embedded — the old heuristic under-budgeted CJK-
    # heavy glossaries and overran the target token ceiling.
    from app.workers.chunk_splitter import estimate_tokens as _estimate_tokens

    token_estimate = 0
    selected: list[GlossaryEntry] = []
    correction_map: dict[str, str] = {}
    verified_map: dict[str, str] = {}

    for score, entry in scored:
        line = entry.to_jsonl(target_language)
        line_tokens = _estimate_tokens(line) + 1
        if token_estimate + line_tokens > max_tokens:
            break

        lines.append(line)
        token_estimate += line_tokens
        selected.append(entry)

        # Build correction map: source name → target name. The full map drives V2
        # auto-correct + the prompt block (unchanged). The verified subset is what
        # the V3 verifier hard-enforces — trust ladder: an absent confidence key is
        # legacy-trusted; a present 'verified' is canon; machine/draft are demoted.
        if entry.target_names:
            primary_target = entry.target_names[0]
            is_verified = entry.confidence is None or entry.confidence == "verified"
            for zh_name in entry.zh_names:
                correction_map[zh_name] = primary_target
                if is_verified:
                    verified_map[zh_name] = primary_target

    if not lines:
        return GlossaryContext(used_entity_ids=used_entity_ids)

    prompt_block = (
        "GLOSSARY — Use these EXACT translations for character/place/term names:\n"
        + "\n".join(lines)
    )

    log.info(
        "glossary_context: %d entries, ~%d tokens, %d correction rules",
        len(selected), token_estimate, len(correction_map),
    )

    return GlossaryContext(
        entries=selected,
        prompt_block=prompt_block,
        token_estimate=token_estimate,
        correction_map=correction_map,
        verified_map=verified_map,
        used_entity_ids=used_entity_ids,
    )


# ── GEP-BE-11: Extraction pipeline client functions ──────────────────────────


async def fetch_extraction_profile(book_id: str) -> dict | None:
    """Fetch the extraction profile (kinds + attributes) for a book.

    Calls: GET /internal/books/{book_id}/extraction-profile

    Returns the response dict with 'kinds' array, or None on failure.
    """
    try:
        async with httpx.AsyncClient(timeout=_GLOSSARY_FETCH_TIMEOUT) as client:
            resp = await client.get(
                f"{settings.glossary_service_internal_url}"
                f"/internal/books/{book_id}/extraction-profile",
                headers={"X-Internal-Token": settings.internal_service_token},
            )
            if resp.status_code != 200:
                log.warning(
                    "extraction profile fetch returned %d for book=%s",
                    resp.status_code, book_id,
                )
                return None
            return resp.json()
    except Exception as exc:
        log.warning("extraction profile fetch failed for book=%s: %s", book_id, exc)
        return None


async def fetch_known_entities(
    book_id: str,
    alive: bool = True,
    min_frequency: int = 2,
    before_chapter_index: int | None = None,
    recency_window: int = 100,
    limit: int = 50,
) -> list[dict]:
    """Fetch filtered known entities for extraction prompt context.

    Calls: GET /internal/books/{book_id}/known-entities

    Returns list of entity dicts (name, kind_code, aliases, frequency),
    or empty list on failure.
    """
    params: dict[str, str] = {
        "alive": str(alive).lower(),
        "min_frequency": str(min_frequency),
        "recency_window": str(recency_window),
        "limit": str(limit),
    }
    if before_chapter_index is not None:
        params["before_chapter_index"] = str(before_chapter_index)

    try:
        async with httpx.AsyncClient(timeout=_GLOSSARY_FETCH_TIMEOUT) as client:
            resp = await client.get(
                f"{settings.glossary_service_internal_url}"
                f"/internal/books/{book_id}/known-entities",
                params=params,
                headers={"X-Internal-Token": settings.internal_service_token},
            )
            if resp.status_code != 200:
                log.warning(
                    "known entities fetch returned %d for book=%s",
                    resp.status_code, book_id,
                )
                return []
            return resp.json()
    except Exception as exc:
        log.warning("known entities fetch failed for book=%s: %s", book_id, exc)
        return []


async def fetch_context_entities(
    book_id: str,
    user_id: str,
    query: str,
    max_entities: int = 20,
    max_tokens: int = 1000,
) -> list[ContextEntity]:
    """Fetch tiered context entities (pinned→exact→fts→recent) for a chapter.

    Calls: POST /internal/books/{book_id}/select-for-context

    Returns parsed ``ContextEntity`` objects (with entity_id + bio), or an empty
    list on any failure. The entity_id anchors the knowledge layer (M4b relations);
    the bio drives pronoun/honorific cues. ``query`` is the chapter source text —
    it drives the exact/FTS tiers (capped to keep the payload reasonable).
    """
    if not book_id:
        return []
    try:
        async with httpx.AsyncClient(timeout=_GLOSSARY_FETCH_TIMEOUT) as client:
            resp = await client.post(
                f"{settings.glossary_service_internal_url}"
                f"/internal/books/{book_id}/select-for-context",
                json={
                    "user_id": user_id,
                    "query": (query or "")[:4000],
                    "max_entities": max_entities,
                    "max_tokens": max_tokens,
                    "exclude_ids": [],
                },
                headers={"X-Internal-Token": settings.internal_service_token},
            )
            if resp.status_code != 200:
                log.warning(
                    "select-for-context returned %d for book=%s — no entity context",
                    resp.status_code, book_id,
                )
                return []
            payload = resp.json()
    except Exception as exc:
        log.warning("select-for-context fetch failed for book=%s: %s", book_id, exc)
        return []

    out: list[ContextEntity] = []
    for e in payload.get("entities", []):
        if not isinstance(e, dict):
            continue
        eid = e.get("entity_id")
        if not eid:
            continue
        raw_aliases = e.get("cached_aliases")
        aliases = [str(a) for a in raw_aliases] if isinstance(raw_aliases, list) else []
        out.append(ContextEntity(
            entity_id=str(eid),
            name=(e.get("cached_name") or ""),
            aliases=aliases,
            short_description=(e.get("short_description") or ""),
            kind=str(e.get("kind_code", "")),
            tier=str(e.get("tier", "")),
        ))
    return out


async def post_extracted_entities(
    book_id: str,
    source_language: str,
    attribute_actions: dict[str, dict[str, str]],
    entities: list[dict],
) -> dict | None:
    """Post extracted entities to glossary-service for upsert.

    Calls: POST /internal/books/{book_id}/extract-entities

    Returns the response dict with created/updated/skipped counts,
    or None on failure.
    """
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{settings.glossary_service_internal_url}"
                f"/internal/books/{book_id}/extract-entities",
                json={
                    "source_language": source_language,
                    "attribute_actions": attribute_actions,
                    "entities": entities,
                },
                headers={"X-Internal-Token": settings.internal_service_token},
            )
            if resp.status_code != 200:
                log.error(
                    "entity upsert failed: status=%d body=%s",
                    resp.status_code, resp.text[:200],
                )
                return None
            return resp.json()
    except Exception as exc:
        log.error("entity upsert request failed: %s", exc)
        return None


def auto_correct_glossary(
    translated_text: str,
    correction_map: dict[str, str],
) -> tuple[str, int]:
    """Post-process translated text to fix untranslated source terms.

    Scans output for ZH source names that should have been translated.
    Replaces with the glossary target name.

    Args:
        translated_text: The LLM output text.
        correction_map: {source_zh: target_translation} from GlossaryContext.

    Returns:
        (corrected_text, correction_count)
    """
    if not correction_map:
        return translated_text, 0

    corrections = 0
    result = translated_text
    for source_zh, target in correction_map.items():
        if source_zh in result:
            count = result.count(source_zh)
            result = result.replace(source_zh, target)
            corrections += count
            log.info(
                "glossary_auto_correct: replaced '%s' → '%s' (%d occurrences)",
                source_zh, target, count,
            )

    return result, corrections


# ── M4d-2b: 2-pass cold-start target writeback ───────────────────────────────


def _sanitize_name(s: str, max_len: int = 120) -> str:
    """Light cross-service sanitize for a name/translation going into glossary:
    strip control chars, collapse whitespace, length-cap."""
    if not s:
        return ""
    s = "".join(ch if (ch >= " " and ch != "\x7f") else " " for ch in s)
    s = " ".join(s.split())
    return s[:max_len].rstrip()


async def writeback_name_pairs(book_id: str, source_language: str,
                               target_language: str, pairs) -> dict | None:
    """Seed M4d-2a source→target NamePairs as draft glossary entities WITH the
    target translation (name attr at ``confidence='machine'``). Best-effort; reuses
    mui#1's AI-suggested draft inbox + ai-rejected tombstone.

    ``pairs`` is a sequence of NamePair-like objects (duck-typed on
    ``.source``/``.target``/``.kind``) — taken structurally to avoid importing from
    ``app.workers.v3`` (which would cycle back through this module). Returns the
    upsert response dict, or None (no URL / no pairs / any failure). Never raises.
    """
    if not settings.glossary_service_internal_url:
        return None
    entities: list[dict] = []
    for p in pairs:
        source = _sanitize_name(getattr(p, "source", "") or "")
        target = _sanitize_name(getattr(p, "target", "") or "")
        if not source or not target:
            continue
        entities.append({
            "kind_code": getattr(p, "kind", "") or "other",
            "name": source,
            "attributes": {},
            "translation": {"language_code": target_language, "value": target},
        })
    if not entities:
        return None
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{settings.glossary_service_internal_url}"
                f"/internal/books/{book_id}/extract-entities",
                json={
                    "source_language": source_language,
                    "attribute_actions": {},
                    "entities": entities,
                    "default_tags": ["ai-suggested"],
                    "park_unknown_kinds": False,
                },
                headers={"X-Internal-Token": settings.internal_service_token},
            )
            if resp.status_code != 200:
                log.warning("name-pair writeback returned %d for book=%s",
                            resp.status_code, book_id)
                return None
            return resp.json()
    except Exception as exc:
        log.warning("name-pair writeback failed for book=%s: %s", book_id, exc)
        return None
