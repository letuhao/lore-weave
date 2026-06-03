"""Per-book enrichment PROFILE — the de-bias source of record (C1 / slice 0a).

The :class:`BookProfile` is the per-book worldview the prompt builders, the
dimension resolver, and the anachronism check read at runtime to DE-BIAS
enrichment away from the hardcoded 封神演义 / 商周 / 中文 / 地点 universe.

An UNSET book resolves to :data:`NEUTRAL_PROFILE` (language ``auto``, NO era
constraint → anachronism OFF, no dimension overrides) — so a book with no
profile behaves like a generic worldbuilder, never like a Shang-Zhou xianxia
book. The Fengshen demo book is SEEDED with the old constants so its output is
byte-identical to today (no regression).

This module is read-only persistence (mirrors the eval_runs repo JSONB
convention: write ``$N::jsonb`` with ``json.dumps``, read tolerating either a
str or an already-parsed value). No write API here — authoring lands in C3.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:  # annotation-only — keeps this module import-light (no asyncpg
    # at runtime) so the pure BookProfile/NEUTRAL_PROFILE can be imported by the
    # strategy base + prompt builders without pulling the DB driver.
    import asyncpg

__all__ = ["BookProfile", "NEUTRAL_PROFILE", "get_book_profile"]


class BookProfile(BaseModel):
    """A book's worldview profile (frozen). Read by the prompt builders, the
    dimension resolver, and the anachronism check.

    ``anachronism_markers`` is a tuple of ``(term, reason)`` pairs — empty means
    the anachronism check is OFF (no denylist). ``era_policy`` is free text for
    the prompt's era clause; ``None`` omits the clause AND (with empty markers)
    turns the check off. ``dimension_overrides`` is the per-kind dynamic-dimension
    layer (``{kind: {"add": [...], "remove": [...], "relabel": {...}, "reweight":
    {...}}}``) — opaque here, interpreted by ``resolve_dimensions`` (T6).
    """

    model_config = ConfigDict(frozen=True)

    book_id: UUID | None = None
    worldview: str = ""
    language: str = "auto"
    era_policy: str | None = None
    voice: str | None = None
    anachronism_markers: tuple[tuple[str, str], ...] = ()
    dimension_overrides: dict[str, Any] = Field(default_factory=dict)
    profile_source: str = "manual"

    @property
    def anachronism_enabled(self) -> bool:
        """True iff the anachronism check has a denylist to enforce. An empty
        marker set → the check is OFF (never auto-flag a non-Fengshen book)."""
        return len(self.anachronism_markers) > 0


#: The fallback for any book with no row. NEUTRAL = generic worldbuilder,
#: language auto, anachronism OFF, no dimension overrides. Used everywhere a
#: ``book_id`` is absent so the no-profile path behaves identically to a fresh
#: non-Fengshen book (NOT like the old hardcoded 封神 default).
NEUTRAL_PROFILE = BookProfile()


def _parse_markers(raw: Any) -> tuple[tuple[str, str], ...]:
    """Parse the JSONB ``anachronism_markers`` (``[{term, reason}, ...]``) into a
    tuple of ``(term, reason)`` pairs. NULL / malformed → empty (check OFF)."""
    if isinstance(raw, str):
        raw = json.loads(raw) if raw.strip() else None
    if not isinstance(raw, list):
        return ()
    out: list[tuple[str, str]] = []
    for item in raw:
        if isinstance(item, dict) and item.get("term"):
            out.append((str(item["term"]), str(item.get("reason", ""))))
        elif isinstance(item, (list, tuple)) and len(item) >= 1 and item[0]:
            out.append((str(item[0]), str(item[1]) if len(item) > 1 else ""))
    return tuple(out)


def _parse_overrides(raw: Any) -> dict[str, Any]:
    """Parse the JSONB ``dimension_overrides`` into a dict. NULL / malformed → {}."""
    if isinstance(raw, str):
        raw = json.loads(raw) if raw.strip() else None
    return raw if isinstance(raw, dict) else {}


async def get_book_profile(pool: asyncpg.Pool, book_id: UUID | None) -> BookProfile:
    """Resolve a book's enrichment profile, or :data:`NEUTRAL_PROFILE` when unset.

    A ``None`` book_id (a job that never supplied one) → the neutral default. A
    book_id with no row → the neutral default carrying that ``book_id`` (so the
    caller still knows which book it is). Never raises on a missing row.
    """
    if book_id is None:
        return NEUTRAL_PROFILE
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT book_id, worldview, language, era_policy, voice,
                   anachronism_markers, dimension_overrides, profile_source
            FROM enrichment_book_profile
            WHERE book_id = $1
            """,
            book_id,
        )
    if row is None:
        return NEUTRAL_PROFILE.model_copy(update={"book_id": book_id})
    return BookProfile(
        book_id=row["book_id"],
        worldview=row["worldview"] or "",
        language=row["language"] or "auto",
        era_policy=row["era_policy"],
        voice=row["voice"],
        anachronism_markers=_parse_markers(row["anachronism_markers"]),
        dimension_overrides=_parse_overrides(row["dimension_overrides"]),
        profile_source=row["profile_source"] or "manual",
    )
