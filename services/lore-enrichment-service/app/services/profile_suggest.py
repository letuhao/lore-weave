"""AI-suggest a book's enrichment profile (C3 / slice 0d, T6).

ONE LLM call proposes the de-bias :class:`BookProfile` fields (worldview /
language / era_policy / voice) **plus** per-kind ``dimension_overrides`` (spec
§2.7, decision E) from the book's metadata + sample-chapter excerpts + an
optional knowledge-graph summary. The seam is an injected ``async (prompt) -> str``
(the endpoint binds it to ``make_complete_fn`` + a :class:`StrategyContext` so the
model resolves by ``model_ref`` — NO hardcoded model name).

The result is a DRAFT only — it is NOT persisted here. The author reviews + edits
it (incl. the suggested dimensions in the override editor) then PUTs it, at which
point ``profile_source`` becomes ``manual``. Suggested overrides are salvaged
per-kind: a malformed kind is dropped (never raises), so one bad suggestion never
sinks the whole draft. A response with no JSON at all → :class:`ProfileSuggestError`
(the endpoint maps it to a 502 — the model produced nothing usable).
"""

from __future__ import annotations

import json
import re
from typing import Any, Awaitable, Callable

from pydantic import BaseModel, ConfigDict, Field

from app.clients.book import BookProjection
from app.db.book_profile import validate_dimension_overrides
from app.gaps.model import kind_label_for

__all__ = [
    "SuggestedProfile",
    "ProfileSuggestError",
    "DEFAULT_SUGGEST_KINDS",
    "build_suggest_prompt",
    "suggest_profile",
]

#: A pre-bound completion seam: ``async (prompt) -> generated_text``.
CompleteText = Callable[[str], Awaitable[str]]

#: The built-in entity kinds we ask the model to propose dimension overrides for
#: (those with a static dimension table; an unmodeled kind falls back to GENERIC).
DEFAULT_SUGGEST_KINDS: tuple[str, ...] = (
    "character", "location", "item", "faction", "event",
)

#: Cap the per-chapter excerpt fed to the model so the prompt stays bounded
#: regardless of chapter length (suggest is a cheap, single call).
_SAMPLE_CHARS = 1500
#: Cap the knowledge-graph summary blob (``build_context`` returns a whole
#: context string) so a large graph can't bloat the suggest prompt unbounded.
_KG_CHARS = 2000


class ProfileSuggestError(RuntimeError):
    """The model produced no usable profile (no JSON object in the response)."""


class SuggestedProfile(BaseModel):
    """The AI-suggested profile draft (not persisted; the author edits + PUTs)."""

    model_config = ConfigDict(frozen=True)

    worldview: str = ""
    language: str = "auto"
    era_policy: str | None = None
    voice: str | None = None
    dimension_overrides: dict[str, Any] = Field(default_factory=dict)
    profile_source: str = "ai_suggested"


def build_suggest_prompt(
    *,
    book: BookProjection,
    sample_texts: list[str],
    kg_summary: str,
    kinds: tuple[str, ...] = DEFAULT_SUGGEST_KINDS,
) -> str:
    """Assemble the single-call suggest prompt from the book digest.

    The KG block is included only when a summary is present (best-effort — an
    empty/down graph degrades to book-only). The dimension-override shape +
    localized kind labels are described so the model returns the exact JSON the
    server validates."""
    lang = book.original_language or "auto"
    label_hints = ", ".join(f"{k} ({kind_label_for(k, lang)})" for k in kinds)
    parts: list[str] = [
        "You are a worldbuilding analyst. Read the book digest below and propose a "
        "concise enrichment PROFILE describing its world, so an enrichment engine can "
        "generate faithful off-page canon in the book's own genre, era, and language.",
        "",
        "## Book",
        f"Title: {book.title or '(untitled)'}",
        f"Original language: {lang}",
    ]
    if book.genre_tags:
        parts.append(f"Genre tags: {', '.join(book.genre_tags)}")
    if book.description:
        parts.append(f"Description: {book.description}")
    if book.summary_excerpt:
        parts.append(f"Summary: {book.summary_excerpt}")
    if sample_texts:
        parts.append("")
        parts.append("## Sample chapter excerpts")
        for i, text in enumerate(sample_texts, 1):
            excerpt = (text or "").strip()[:_SAMPLE_CHARS]
            if excerpt:
                parts.append(f"--- excerpt {i} ---\n{excerpt}")
    if kg_summary.strip():
        parts.append("")
        parts.append("## Knowledge graph summary")
        parts.append(kg_summary.strip()[:_KG_CHARS])
    parts += [
        "",
        "## Output",
        "Return ONE JSON object ONLY (no prose, no code fence) with these keys:",
        '  "worldview": a one-sentence setting description (genre + era + place),',
        '  "language": the BCP-style output language code (e.g. "zh","en","vi") or "auto",',
        '  "era_policy": a short era/anachronism constraint, or null if none applies,',
        '  "voice": an optional tone/voice hint, or null,',
        '  "dimension_overrides": an object keyed by entity kind '
        f"(one of: {label_hints}); each value may have "
        '"add":[{"id","label","weight","required"}], "remove":[id], '
        '"relabel":{id:label}, "reweight":{id:weight}. Propose genre-appropriate '
        "dimensions (e.g. a cyberpunk character: implants, faction_ties, street_cred). "
        "Use {} if the defaults suffice.",
        "Respond in valid JSON only.",
    ]
    return "\n".join(parts)


def _extract_json_object(text: str) -> dict[str, Any]:
    """Extract + parse the outermost balanced ``{...}`` from the model output
    (tolerating a ```code fence``` and surrounding chatter). Raises
    :class:`ProfileSuggestError` when there is no parseable object."""
    stripped = (text or "").strip()
    # drop a leading/trailing code fence if present
    stripped = re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", stripped)
    stripped = re.sub(r"\s*```$", "", stripped).strip()
    start = stripped.find("{")
    if start == -1:
        raise ProfileSuggestError("no JSON object in suggest response")
    depth = 0
    in_str = False
    escape = False
    for i in range(start, len(stripped)):
        ch = stripped[i]
        if escape:
            escape = False
            continue
        if ch == "\\":
            escape = True
            continue
        if ch == '"':
            in_str = not in_str
            continue
        if in_str:
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    data = json.loads(stripped[start : i + 1])
                except json.JSONDecodeError as exc:
                    raise ProfileSuggestError(f"unparseable suggest JSON: {exc}")
                if not isinstance(data, dict):
                    raise ProfileSuggestError("suggest JSON is not an object")
                return data
    raise ProfileSuggestError("unbalanced JSON object in suggest response")


def _salvage_overrides(raw: Any) -> dict[str, Any]:
    """Validate the suggested overrides PER KIND, dropping any malformed kind
    (never raises — a single bad suggestion must not sink the whole draft). The
    surviving kinds are the cleaned/normalized shape the author can edit + PUT."""
    if not isinstance(raw, dict):
        return {}
    out: dict[str, Any] = {}
    for kind, ops in raw.items():
        try:
            out.update(validate_dimension_overrides({kind: ops}))
        except ValueError:
            continue
    return out


async def suggest_profile(
    *,
    book: BookProjection,
    sample_texts: list[str],
    kg_summary: str,
    complete: CompleteText,
    kinds: tuple[str, ...] = DEFAULT_SUGGEST_KINDS,
) -> SuggestedProfile:
    """Run the one-call AI-suggest and parse a :class:`SuggestedProfile` draft.

    ``complete`` is the bound LLM seam; a transport/upstream failure propagates
    (the endpoint maps it to 502). The model output is parsed leniently (fence +
    prose tolerant); overrides are salvaged per-kind. ``language`` defaults to
    ``auto`` when absent. Does NOT persist."""
    prompt = build_suggest_prompt(
        book=book, sample_texts=sample_texts, kg_summary=kg_summary, kinds=kinds
    )
    raw_text = await complete(prompt)
    data = _extract_json_object(raw_text)
    era = data.get("era_policy")
    voice = data.get("voice")
    return SuggestedProfile(
        worldview=str(data.get("worldview") or ""),
        language=str(data.get("language") or "auto"),
        era_policy=str(era) if isinstance(era, str) and era.strip() else None,
        voice=str(voice) if isinstance(voice, str) and voice.strip() else None,
        dimension_overrides=_salvage_overrides(data.get("dimension_overrides")),
        profile_source="ai_suggested",
    )
