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
    """A single glossary entity for translation context."""
    zh_names: list[str]
    target_names: list[str]
    kind: str

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
    # Source→target map for auto-correct post-processing
    correction_map: dict[str, str] = field(default_factory=dict)


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
    for raw in raw_entries:
        zh_names = raw.get("zh", [])
        target_names = raw.get(target_language, [])
        kind = raw.get("kind", "")
        if not zh_names:
            continue
        entries.append(GlossaryEntry(zh_names=zh_names, target_names=target_names, kind=kind))

    if not entries:
        return GlossaryContext()

    # Score by occurrence in chapter text × name length
    scored: list[tuple[int, GlossaryEntry]] = []
    for entry in entries:
        score = 0
        for name in entry.zh_names:
            count = chapter_text.count(name)
            score += count * len(name)
        # Include score-0 entries only if they have a target translation
        # (Tier 0 pinned entities — worth including even if not in this chunk)
        if score > 0 or entry.target_names:
            scored.append((score, entry))

    # Sort: highest score first (most relevant to this chapter)
    scored.sort(key=lambda x: -x[0])

    # Build JSONL lines within token budget
    lines: list[str] = []
    token_estimate = 0
    selected: list[GlossaryEntry] = []
    correction_map: dict[str, str] = {}

    for score, entry in scored:
        line = entry.to_jsonl(target_language)
        # Rough estimate: ~4 chars per token for this metadata text
        line_tokens = len(line) // 4 + 1
        if token_estimate + line_tokens > max_tokens:
            break

        lines.append(line)
        token_estimate += line_tokens
        selected.append(entry)

        # Build correction map: source name → target name
        if entry.target_names:
            primary_target = entry.target_names[0]
            for zh_name in entry.zh_names:
                correction_map[zh_name] = primary_target

    if not lines:
        return GlossaryContext()

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
