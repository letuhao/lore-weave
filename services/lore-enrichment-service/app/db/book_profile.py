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

__all__ = [
    "BookProfile",
    "NEUTRAL_PROFILE",
    "get_book_profile",
    "upsert_book_profile",
    "validate_dimension_overrides",
]


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


def _profile_from_row(row: Any) -> BookProfile:
    """Build a :class:`BookProfile` from a DB row (tolerating asyncpg's str-jsonb)."""
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
    return _profile_from_row(row)


async def upsert_book_profile(
    pool: asyncpg.Pool,
    book_id: UUID,
    *,
    worldview: str,
    language: str,
    era_policy: str | None,
    voice: str | None,
    anachronism_markers: tuple[tuple[str, str], ...],
    dimension_overrides: dict[str, Any],
    profile_source: str,
) -> BookProfile:
    """Insert-or-update a book's profile and return the persisted model (C3).

    ``anachronism_markers`` is serialized to the stored ``[{term, reason}]`` JSONB
    shape; ``dimension_overrides`` is written as-is (validate BEFORE calling — see
    :func:`validate_dimension_overrides`). ``updated_at`` is bumped on conflict.
    The caller sets ``profile_source`` (``manual`` on author edit, ``seed``/
    ``ai_suggested`` for their flows)."""
    markers_json = json.dumps(
        [{"term": t, "reason": r} for t, r in anachronism_markers], ensure_ascii=False
    )
    overrides_json = json.dumps(dimension_overrides or {}, ensure_ascii=False)
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO enrichment_book_profile
              (book_id, worldview, language, era_policy, voice,
               anachronism_markers, dimension_overrides, profile_source, updated_at)
            VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7::jsonb, $8, now())
            ON CONFLICT (book_id) DO UPDATE SET
              worldview           = EXCLUDED.worldview,
              language            = EXCLUDED.language,
              era_policy          = EXCLUDED.era_policy,
              voice               = EXCLUDED.voice,
              anachronism_markers = EXCLUDED.anachronism_markers,
              dimension_overrides = EXCLUDED.dimension_overrides,
              profile_source      = EXCLUDED.profile_source,
              updated_at          = now()
            RETURNING book_id, worldview, language, era_policy, voice,
                      anachronism_markers, dimension_overrides, profile_source
            """,
            book_id, worldview, language, era_policy, voice,
            markers_json, overrides_json, profile_source,
        )
    return _profile_from_row(row)


_OVERRIDE_OPS = frozenset({"add", "remove", "relabel", "reweight"})


def _as_weight(value: Any, what: str) -> float:
    """Coerce a JSON number to a POSITIVE weight, rejecting bools, non-numerics,
    zero, and negatives (the LLM / author may send garbage; the structural gate must
    catch it before persist). A weight <= 0 is invalid: a negative inverts C1's
    rank_score, and ``DimensionSpec.weight`` is ``gt=0`` — so an ``add`` with weight 0
    would be silently DROPPED at resolve (constructor ValidationError) and a
    ``reweight`` to 0 would set a zero-salience dim via model_copy (which skips
    validation). Reject it loudly here (400) instead — to disable a dimension the
    author REMOVES it, never weights it 0."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{what} must be a number")
    out = float(value)
    if out <= 0:
        raise ValueError(f"{what} must be > 0 (remove a dimension to disable it)")
    return out


def validate_dimension_overrides(raw: Any) -> dict[str, Any]:
    """Structurally validate + normalize the per-kind ``dimension_overrides`` from
    an author PUT or an AI suggestion, BEFORE persist (spec §2.7, decision E).

    Shape: ``{kind: {add:[{id,label?,weight?,required?,payload_shape?}], remove:
    [id...], relabel:{id:label}, reweight:{id:weight}}}``. Rejects anything the
    runtime resolver (:func:`app.gaps.model._apply_overrides`) would silently drop
    (missing add ``id``) or that is the wrong type — turning malformed LLM output
    into a 400 instead of a quiet no-op. Returns the cleaned dict; raises
    ``ValueError`` on malformed input. Defense-in-depth: the resolver is ALSO
    crash-safe, so a stored-but-odd override never breaks generation."""
    if not isinstance(raw, dict):
        raise ValueError("dimension_overrides must be an object")
    clean: dict[str, Any] = {}
    for kind, ops in raw.items():
        if not isinstance(kind, str) or not kind.strip():
            raise ValueError("override kind must be a non-empty string")
        if not isinstance(ops, dict):
            raise ValueError(f"override for {kind!r} must be an object")
        unknown = set(ops) - _OVERRIDE_OPS
        if unknown:
            raise ValueError(f"unknown override op(s) for {kind!r}: {sorted(unknown)}")
        clean_ops: dict[str, Any] = {}

        if "add" in ops:
            adds = ops["add"]
            if not isinstance(adds, list):
                raise ValueError(f"'add' for {kind!r} must be a list")
            clean_adds: list[dict[str, Any]] = []
            for spec in adds:
                if not isinstance(spec, dict):
                    raise ValueError(f"each 'add' for {kind!r} must be an object")
                did = str(spec.get("id") or spec.get("dimension") or "").strip()
                if not did:
                    raise ValueError(f"each 'add' for {kind!r} needs an 'id'")
                item: dict[str, Any] = {"id": did, "label": str(spec.get("label") or did)}
                if "weight" in spec:
                    item["weight"] = _as_weight(spec["weight"], f"add.weight for {kind!r}")
                if "required" in spec:
                    if not isinstance(spec["required"], bool):
                        raise ValueError(f"add.required for {kind!r} must be a boolean")
                    item["required"] = spec["required"]
                if "payload_shape" in spec:
                    item["payload_shape"] = str(spec["payload_shape"])
                clean_adds.append(item)
            clean_ops["add"] = clean_adds

        if "remove" in ops:
            rem = ops["remove"]
            if not isinstance(rem, list) or not all(
                isinstance(x, str) and x.strip() for x in rem
            ):
                raise ValueError(f"'remove' for {kind!r} must be a list of dimension ids")
            clean_ops["remove"] = [x for x in rem]

        if "relabel" in ops:
            rel = ops["relabel"]
            if not isinstance(rel, dict) or not all(
                isinstance(k, str) and isinstance(v, str) for k, v in rel.items()
            ):
                raise ValueError(f"'relabel' for {kind!r} must map id → label")
            clean_ops["relabel"] = dict(rel)

        if "reweight" in ops:
            rew = ops["reweight"]
            if not isinstance(rew, dict):
                raise ValueError(f"'reweight' for {kind!r} must map id → weight")
            clean_ops["reweight"] = {
                str(k): _as_weight(v, f"reweight[{k!r}] for {kind!r}")
                for k, v in rew.items()
            }

        clean[kind] = clean_ops
    return clean
