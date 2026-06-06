"""BookProfile — per-book worldview/language threading (§2.6 de-bias).

Lore-enrichment paid 3 XL cycles for this: a generation pipeline silently
inherits the demo book's universe (language/era/genre) unless worldview is an
explicit per-book object threaded everywhere. The fix is a `BookProfile` with a
**NEUTRAL default** that a missing/empty settings row resolves to (never raises),
carried into every prompt builder + judge (M6).

Lives in `composition_work.settings` (a JSONB dict). NEUTRAL =
`source_language='auto'` + no voice + generic structure. The packer reads it at
pack time; M6 threads it into the draft + judge prompts (where the actual
language bias lives — assembly blocks here stay structural).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class BookProfile:
    source_language: str = "auto"   # 'auto' = let the model infer (NEUTRAL)
    voice: str = ""
    structure_pref: str = "generic"
    tone: str = ""
    density: str = ""


NEUTRAL = BookProfile()


def from_settings(settings: dict[str, Any] | None) -> BookProfile:
    """Parse a `composition_work.settings` dict into a BookProfile. A missing
    row / empty dict / missing key all fall back to NEUTRAL fields — never
    raises. Empty-string and None values normalise to the NEUTRAL default so a
    blank setting can't force English/a genre."""
    if not settings:
        return NEUTRAL
    return BookProfile(
        source_language=(settings.get("source_language") or "auto"),
        voice=(settings.get("voice") or ""),
        structure_pref=(settings.get("structure_pref") or "generic"),
        tone=(settings.get("tone") or ""),
        density=(settings.get("density") or ""),
    )


def resolve_source_language(profile: BookProfile, fallback_language: str | None) -> BookProfile:
    """Resolve `source_language='auto'` to a concrete language when the caller
    can supply one (e.g. the book's chapter `original_language`). A non-'auto'
    explicit setting is never overridden; an unavailable fallback keeps 'auto'
    (NEUTRAL stays safe — the draft prompt then lets the model infer)."""
    if profile.source_language != "auto":
        return profile
    if not fallback_language or fallback_language == "auto":
        return profile
    return BookProfile(
        source_language=fallback_language, voice=profile.voice,
        structure_pref=profile.structure_pref, tone=profile.tone, density=profile.density,
    )
