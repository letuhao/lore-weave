"""Gap MODEL — typed, pure-data spec for lore-enrichment (RAID C6 + de-bias C1).

De-bias (C1, KB3): **kind and dimension are DYNAMIC** — author/profile-extensible.
The closed `EntityKind`/`Dimension` enums are kept as *constants* that key the
built-in static tables, but they are NOT validation gates: `entity_kind` and
dimension ids are free `str` on `Gap`/`DimensionSpec`, an unknown kind falls back
to the GENERIC table (never `KeyError`/skip), and a profile may add/relabel
dimensions. Display labels are localized by language (`label_for`); the dimension
*identity* is the stable `id`, never the localized label.

  * ``EntityKind``   — built-in kind constants (str-enum). NOT a gate.
  * ``Dimension``    — built-in LOCATION dimension ids (str-enum, kept for the
    locked Fengshen golden tests). NOT a gate.
  * ``DimensionSpec``— per-dimension metadata: stable ``dimension`` id (str),
    default ``label``, required flag, weight, payload shape.
  * ``Gap``          — a canon-mentioned entity missing ≥1 required dimension.
    ``entity_kind``/dimension tuples are free ``str``.
  * ``dimensions_for`` / ``resolve_dimensions`` — the static table for a kind
    (GENERIC fallback) and the profile-aware resolution (localize + overrides).
  * ``rank_score``   — DETERMINISTIC gap ordering.

Boundaries (locked): NO graph reads, NO DB I/O, NO LLM calls, NO embeddings, NO
model names. Imports only stdlib + pydantic.
"""

from __future__ import annotations

import math
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

__all__ = [
    "EntityKind",
    "Dimension",
    "DimensionSpec",
    "Gap",
    "GapRanking",
    "DIMENSIONS_BY_KIND",
    "LOCATION_DIMENSIONS",
    "CHARACTER_DIMENSIONS",
    "ITEM_DIMENSIONS",
    "FACTION_DIMENSIONS",
    "EVENT_DIMENSIONS",
    "GENERIC_DIMENSIONS",
    "GENERIC_KIND",
    "dimensions_for",
    "resolve_dimensions",
    "label_for",
    "kind_label_for",
    "rank_score",
    "rank_gaps",
]


# ── precision: every score is rounded to this many decimals so float equality
#    in tests and across calls is exact (never compare raw floats with ==). ──
_SCORE_PRECISION = 6


class EntityKind(str, Enum):
    """Built-in entity-kind CONSTANTS (not a validation gate, KB3).

    String values mirror the C2 schema's lowercase ``entity_kind`` vocabulary.
    A `Gap`'s ``entity_kind`` is a free ``str`` — these constants only key the
    built-in static dimension tables; an unknown kind resolves to GENERIC.
    """

    LOCATION = "location"
    CHARACTER = "character"
    ITEM = "item"
    FACTION = "faction"
    EVENT = "event"


#: The fallback kind key for any entity-kind without a built-in table (KB3 — never
#: skip an entity; give it a generic descriptive dimension set).
GENERIC_KIND = "generic"


class Dimension(str, Enum):
    """Built-in LOCATION dimension ids (str-enum, kept for the locked Fengshen
    golden tests). Other kinds' dimension ids are plain ``str`` constants. NOT a
    validation gate — a `Gap`'s dimension tuples are free ``str``."""

    HISTORY = "history"
    GEOGRAPHY = "geography"
    CULTURE = "culture"
    FEATURES = "features"
    INHABITANTS = "inhabitants"


class DimensionSpec(BaseModel):
    """Static metadata for one dimension of one entity-kind.

    ``dimension`` is the stable, language-neutral id (str). ``label`` is the
    DEFAULT display label (zh-native, matching the Fengshen demo); other languages
    are resolved via :func:`label_for`. ``weight`` is the fixed ranking
    contribution when this dimension is MISSING.
    """

    model_config = ConfigDict(frozen=True)

    dimension: str = Field(min_length=1)
    label: str = Field(min_length=1)
    required: bool
    weight: float = Field(gt=0.0)
    payload_shape: str = Field(min_length=1)


# ═══════════════════════════════════════════════════════════════════════════
# Built-in dimension tables (frozen). Default labels are zh-native (the Fengshen
# demo convention — no regression); :func:`label_for` localizes to other langs.
# Required dims carry heavier weight than enhancing dims.
# ═══════════════════════════════════════════════════════════════════════════
LOCATION_DIMENSIONS: tuple[DimensionSpec, ...] = (
    DimensionSpec(dimension=Dimension.HISTORY, label="历史", required=True, weight=3.0,
                  payload_shape="prose: founding, key events, era, lineage of the place"),
    DimensionSpec(dimension=Dimension.GEOGRAPHY, label="地理", required=True, weight=3.0,
                  payload_shape="prose: location, terrain, climate, layout/architecture"),
    DimensionSpec(dimension=Dimension.CULTURE, label="文化", required=True, weight=3.0,
                  payload_shape="prose: customs, beliefs, daily life, governance, faction"),
    DimensionSpec(dimension=Dimension.FEATURES, label="features", required=False, weight=2.0,
                  payload_shape="list: notable landmarks, relics, natural wonders"),
    DimensionSpec(dimension=Dimension.INHABITANTS, label="inhabitants", required=False, weight=2.0,
                  payload_shape="list: residents, factions, notable figures tied to place"),
)

CHARACTER_DIMENSIONS: tuple[DimensionSpec, ...] = (
    DimensionSpec(dimension="appearance", label="外貌", required=True, weight=3.0,
                  payload_shape="prose: physical appearance, attire, distinguishing marks"),
    DimensionSpec(dimension="personality", label="性格", required=True, weight=3.0,
                  payload_shape="prose: temperament, values, motivations, flaws"),
    DimensionSpec(dimension="abilities", label="能力", required=True, weight=3.0,
                  payload_shape="prose/list: powers, skills, equipment, weaknesses"),
    DimensionSpec(dimension="relationships", label="关系", required=False, weight=2.0,
                  payload_shape="list: allies, rivals, family, affiliations"),
    DimensionSpec(dimension="background", label="经历", required=False, weight=2.0,
                  payload_shape="prose: origin, formative events, arc to date"),
)

ITEM_DIMENSIONS: tuple[DimensionSpec, ...] = (
    DimensionSpec(dimension="origin", label="来历", required=True, weight=3.0,
                  payload_shape="prose: who/how it was made, history of the item"),
    DimensionSpec(dimension="powers", label="能力", required=True, weight=3.0,
                  payload_shape="prose/list: properties, powers, costs, limits"),
    DimensionSpec(dimension="appearance", label="外形", required=True, weight=3.0,
                  payload_shape="prose: form, material, distinguishing features"),
    DimensionSpec(dimension="owner", label="持有", required=False, weight=2.0,
                  payload_shape="list: current/past owners, how acquired"),
    DimensionSpec(dimension="significance", label="意义", required=False, weight=2.0,
                  payload_shape="prose: role in the world / plot significance"),
)

FACTION_DIMENSIONS: tuple[DimensionSpec, ...] = (
    DimensionSpec(dimension="history", label="历史", required=True, weight=3.0,
                  payload_shape="prose: founding, key events, era of the faction"),
    DimensionSpec(dimension="goals", label="宗旨", required=True, weight=3.0,
                  payload_shape="prose: purpose, ideology, agenda"),
    DimensionSpec(dimension="structure", label="组织", required=True, weight=3.0,
                  payload_shape="prose: hierarchy, governance, territory, resources"),
    DimensionSpec(dimension="members", label="成员", required=False, weight=2.0,
                  payload_shape="list: notable members, leadership, ranks"),
    DimensionSpec(dimension="relationships", label="关系", required=False, weight=2.0,
                  payload_shape="list: allies, enemies, rivals"),
)

EVENT_DIMENSIONS: tuple[DimensionSpec, ...] = (
    DimensionSpec(dimension="cause", label="起因", required=True, weight=3.0,
                  payload_shape="prose: what led to the event, antecedents"),
    DimensionSpec(dimension="timeline", label="经过", required=True, weight=3.0,
                  payload_shape="prose: sequence of what happened, when"),
    DimensionSpec(dimension="outcome", label="结果", required=True, weight=3.0,
                  payload_shape="prose: consequences, aftermath, impact"),
    DimensionSpec(dimension="participants", label="参与", required=False, weight=2.0,
                  payload_shape="list: people/factions/places involved"),
    DimensionSpec(dimension="significance", label="意义", required=False, weight=2.0,
                  payload_shape="prose: why it matters to the world"),
)

#: Generic fallback for any kind without a built-in table (KB3 — never skip).
GENERIC_DIMENSIONS: tuple[DimensionSpec, ...] = (
    DimensionSpec(dimension="description", label="概述", required=True, weight=3.0,
                  payload_shape="prose: what this is, an overview"),
    DimensionSpec(dimension="details", label="细节", required=True, weight=3.0,
                  payload_shape="prose: salient specifics"),
    DimensionSpec(dimension="significance", label="意义", required=False, weight=2.0,
                  payload_shape="prose: role / significance in the world"),
)


# Map of kind → its frozen dimension table. Keyed by the str-enum constants (which
# equal their string values, so a plain-str lookup like ``DIMENSIONS_BY_KIND
# ["location"]`` works too). GENERIC is the fallback for any unmodeled kind.
DIMENSIONS_BY_KIND: dict[Any, tuple[DimensionSpec, ...]] = {
    EntityKind.LOCATION: LOCATION_DIMENSIONS,
    EntityKind.CHARACTER: CHARACTER_DIMENSIONS,
    EntityKind.ITEM: ITEM_DIMENSIONS,
    EntityKind.FACTION: FACTION_DIMENSIONS,
    EntityKind.EVENT: EVENT_DIMENSIONS,
    GENERIC_KIND: GENERIC_DIMENSIONS,
}


# ── label localization (de-bias C1) ──────────────────────────────────────────
# Default labels (above) are zh-native; this maps a dimension id → per-language
# label for OTHER languages. A (id, language) miss falls back to the spec's
# default label, so the Fengshen demo (zh) is unchanged. Only English is seeded
# here; more languages are additive data (no code change).
_DIMENSION_LABELS: dict[str, dict[str, str]] = {
    # location
    "history": {"en": "History"}, "geography": {"en": "Geography"},
    "culture": {"en": "Culture"}, "features": {"en": "Features"},
    "inhabitants": {"en": "Inhabitants"},
    # character
    "appearance": {"en": "Appearance"}, "personality": {"en": "Personality"},
    "abilities": {"en": "Abilities"}, "relationships": {"en": "Relationships"},
    "background": {"en": "Background"},
    # item
    "origin": {"en": "Origin"}, "powers": {"en": "Powers"},
    "owner": {"en": "Owner"}, "significance": {"en": "Significance"},
    # faction
    "goals": {"en": "Goals"}, "structure": {"en": "Structure"},
    "members": {"en": "Members"},
    # event
    "cause": {"en": "Cause"}, "timeline": {"en": "Timeline"},
    "outcome": {"en": "Outcome"}, "participants": {"en": "Participants"},
    # generic
    "description": {"en": "Description"}, "details": {"en": "Details"},
}


#: Localized KIND labels for the prompt ("for the {kind_label} «name»"). zh
#: defaults match the Fengshen demo (location→地点); en seeded; a miss falls back
#: to the kind string itself.
_KIND_LABELS: dict[str, dict[str, str]] = {
    "location": {"zh": "地点", "en": "location"},
    "character": {"zh": "人物", "en": "character"},
    "item": {"zh": "物品", "en": "item"},
    "faction": {"zh": "势力", "en": "faction"},
    "event": {"zh": "事件", "en": "event"},
    GENERIC_KIND: {"zh": "条目", "en": "entry"},
}


def kind_label_for(kind: str, language: str) -> str:
    """The display label for an entity-kind in ``language`` (for the prompt).

    zh defaults match the demo (location→地点). ``auto``/unknown language → the zh
    label if defined (the Fengshen-native default), else the kind string. An
    unknown kind → the kind string itself."""
    lang = (language or "").strip().lower()
    by_lang = _KIND_LABELS.get(kind, {})
    if not lang or lang == "auto":
        return by_lang.get("zh", kind)
    return by_lang.get(lang, by_lang.get("zh", kind))


def label_for(dimension_id: str, language: str, *, default: str) -> str:
    """The display label for a dimension id in ``language``.

    Returns the per-language override if known, else ``default`` (the spec's
    zh-native default). ``auto`` / unknown language → ``default`` — so the Fengshen
    demo (zh) is byte-identical to today."""
    lang = (language or "").strip().lower()
    if not lang or lang == "auto":
        return default
    return _DIMENSION_LABELS.get(dimension_id, {}).get(lang, default)


def dimensions_for(kind: str) -> tuple[DimensionSpec, ...]:
    """The built-in static dimension table for ``kind`` (default labels).

    De-bias (KB3): an unknown/unmodeled kind falls back to GENERIC_DIMENSIONS
    rather than raising — enrichment never silently skips an entity. ``kind`` may
    be an ``EntityKind`` or a plain str (str-enum members hash/equal their value)."""
    return DIMENSIONS_BY_KIND.get(kind, GENERIC_DIMENSIONS)


def _apply_overrides(
    specs: tuple[DimensionSpec, ...], override: dict[str, Any] | None
) -> tuple[DimensionSpec, ...]:
    """Apply a per-kind override dict to a base spec tuple (the dynamic-dimension
    layer). Shape: ``{"remove": [id...], "relabel": {id: label}, "reweight":
    {id: weight}, "add": [{id,label,required,weight,payload_shape}...]}``.
    Deterministic + order-preserving (base order, then added). Malformed entries
    are skipped (never raise — overrides may come from an LLM suggestion)."""
    if not override:
        return specs
    remove = set(override.get("remove") or ())
    relabel = override.get("relabel") or {}
    reweight = override.get("reweight") or {}
    out: list[DimensionSpec] = []
    seen: set[str] = set()
    for s in specs:
        if s.dimension in remove:
            continue
        seen.add(s.dimension)
        label = relabel.get(s.dimension, s.label)
        weight = reweight.get(s.dimension, s.weight)
        out.append(s.model_copy(update={"label": str(label), "weight": float(weight)}))
    for add in override.get("add") or ():
        if not isinstance(add, dict):
            continue
        did = str(add.get("id") or add.get("dimension") or "").strip()
        if not did or did in seen:
            continue
        try:
            out.append(DimensionSpec(
                dimension=did,
                label=str(add.get("label") or did),
                required=bool(add.get("required", False)),
                weight=float(add.get("weight", 2.0)),
                payload_shape=str(add.get("payload_shape") or "prose: free-form detail"),
            ))
            seen.add(did)
        except Exception:  # noqa: BLE001 — a malformed suggested dim is dropped, not fatal
            continue
    return tuple(out)


def resolve_dimensions(
    kind: str,
    *,
    language: str = "auto",
    overrides: dict[str, Any] | None = None,
) -> tuple[DimensionSpec, ...]:
    """Profile-aware dimension table for ``kind`` (de-bias C1).

    Static table (GENERIC fallback) → localize each label to ``language`` →
    apply the per-kind ``overrides`` (add/remove/relabel/reweight). ``overrides``
    is the whole ``dimension_overrides`` dict (keyed by kind); the entry for this
    kind is used. Deterministic. The Fengshen profile (zh, no overrides) returns
    the static table byte-identical to :func:`dimensions_for`.
    """
    base = dimensions_for(kind)
    localized = tuple(
        s.model_copy(update={"label": label_for(s.dimension, language, default=s.label)})
        for s in base
    )
    per_kind = (overrides or {}).get(kind) if overrides else None
    return _apply_overrides(localized, per_kind)


# ── salience normalization (deterministic) ───────────────────────────────────
def _salience_factor(mention_count: int) -> float:
    """Map a raw mention count to a bounded [1.0, ~) salience factor.

    1 + log1p(n)/log1p(REF). Deterministic, monotonic, never < 1.0. REF is a fixed
    reference mention count (book-neutral — it only shapes log-damping)."""
    _SALIENCE_REF = 55.0  # a reference mention count for log-damping (book-neutral)
    if mention_count <= 0:
        return 1.0
    return 1.0 + (math.log1p(float(mention_count)) / math.log1p(_SALIENCE_REF))


class Gap(BaseModel):
    """A canon-mentioned entity missing one or more of its dimensions.

    PURE DATA — describes absence only (H0: no content/source_type/confidence).
    ``entity_kind`` and the dimension tuples are free ``str`` (dynamic kinds +
    dimensions, KB3); the built-in enums are merely the conventional values.
    """

    model_config = ConfigDict(frozen=True)

    entity_kind: str = Field(min_length=1)
    canonical_name: str = Field(min_length=1)
    target_ref: str | None = None
    mention_count: int = Field(ge=0, default=0)
    present_dimensions: tuple[str, ...] = ()
    missing_dimensions: tuple[str, ...] = ()

    @field_validator("present_dimensions", "missing_dimensions", mode="before")
    @classmethod
    def _coerce_tuple(cls, v: object) -> tuple[str, ...]:
        if v is None:
            return ()
        # A str-enum member's __str__ is "Dimension.HISTORY", not its value — use
        # .value for enums so a Dimension/EntityKind passes through as "history".
        return tuple(
            x.value if isinstance(x, Enum) else str(x) for x in v  # type: ignore[union-attr]
        )

    @field_validator("entity_kind", mode="before")
    @classmethod
    def _coerce_kind(cls, v: object) -> str:
        return v.value if isinstance(v, Enum) else str(v)

    @field_validator("missing_dimensions")
    @classmethod
    def _require_at_least_one_missing(cls, v: tuple[str, ...]) -> tuple[str, ...]:
        if len(v) == 0:
            raise ValueError(
                "a Gap must have at least one missing dimension "
                "(a fully-described entity has no gap)"
            )
        return v

    def _dimension_table(self) -> tuple[DimensionSpec, ...]:
        return dimensions_for(self.entity_kind)

    def missing_required_count(self) -> int:
        """How many REQUIRED dimensions are missing (deterministic)."""
        missing = set(self.missing_dimensions)
        return sum(
            1
            for spec in self._dimension_table()
            if spec.required and spec.dimension in missing
        )

    def completeness(self) -> float:
        """Fraction of the dimension set that is present, in [0.0, 1.0]."""
        table = self._dimension_table()
        if not table:
            return 0.0
        present = set(self.present_dimensions)
        n_present = sum(1 for spec in table if spec.dimension in present)
        return round(n_present / len(table), _SCORE_PRECISION)


class GapRanking(BaseModel):
    """A Gap paired with its deterministic ranking score."""

    model_config = ConfigDict(frozen=True)

    gap: Gap
    score: float
    rank: int = Field(ge=1)


# ═══════════════════════════════════════════════════════════════════════════
# Ranking model (deterministic).
#   raw = (REQUIRED_BONUS * missing_required_count + Σ weight(d) for d missing)
#         * salience_factor(mention_count)
#   score = round(raw, 6)
# Every term is order-independent and pure.
# ═══════════════════════════════════════════════════════════════════════════
_REQUIRED_BONUS = 1.0


def rank_score(gap: Gap) -> float:
    """Deterministic ranking score for a single gap (higher = fill first)."""
    table = dimensions_for(gap.entity_kind)
    missing = set(gap.missing_dimensions)
    weighted_missing = sum(
        spec.weight for spec in table if spec.dimension in missing
    )
    required_term = _REQUIRED_BONUS * gap.missing_required_count()
    raw = (required_term + weighted_missing) * _salience_factor(gap.mention_count)
    return round(raw, _SCORE_PRECISION)


def rank_gaps(gaps: list[Gap]) -> list[GapRanking]:
    """Score and order a list of gaps, highest score first (canonical_name
    tie-break). Total, deterministic order."""
    scored = [(rank_score(g), g) for g in gaps]
    scored.sort(key=lambda pair: (-pair[0], pair[1].canonical_name))
    return [
        GapRanking(gap=g, score=score, rank=i + 1)
        for i, (score, g) in enumerate(scored)
    ]
