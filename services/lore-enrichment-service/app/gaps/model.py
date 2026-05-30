"""Gap MODEL — typed, pure-data spec for lore-enrichment (RAID C6).

Anchored on entity-kind = LOCATION for the 封神演义 demo. Defines:

  * ``EntityKind``   — extensible enum; only ``LOCATION`` is fleshed out for the
    demo (matches the C2 schema's lowercase ``entity_kind = 'location'``).
  * ``Dimension``    — the LOCATION dimension set: 历史 / 地理 / 文化 / features /
    inhabitants (locked). Three core descriptive dims are *required*; the two
    enhancing dims are *optional*.
  * ``DimensionSpec``— per-dimension metadata: id, Chinese-or-locked label,
    required flag, fixed ranking weight, expected payload shape.
  * ``Gap``          — a canon-mentioned entity missing ≥1 required dimension.
    Pure data: which dims are present vs missing + the entity's canon-mention
    salience. NO generated content, NO source_type, NO confidence (H0).
  * ``rank_score``   — a DETERMINISTIC score that orders gaps (fill the biggest
    gaps first). Same input → same float, always.

Boundaries (locked):
  * NO graph reads, NO DB I/O, NO LLM calls, NO embeddings — that is the C7
    engine. This module imports only the stdlib + pydantic.
  * NO model names anywhere (this cycle has zero LLM calls).
  * H0: a Gap is the description of ABSENCE; it never emits a proposal nor
    carries ``source_type='enriched'``. Enrichment content is C8–C11.
"""

from __future__ import annotations

import math
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator

__all__ = [
    "EntityKind",
    "Dimension",
    "DimensionSpec",
    "Gap",
    "GapRanking",
    "DIMENSIONS_BY_KIND",
    "LOCATION_DIMENSIONS",
    "rank_score",
    "rank_gaps",
]


# ── precision: every score is rounded to this many decimals so float equality
#    in tests and across calls is exact (never compare raw floats with ==). ──
_SCORE_PRECISION = 6


class EntityKind(str, Enum):
    """The kind of canon entity a gap is measured against.

    Extensible by design — CHARACTER / ITEM / FACTION are reserved for later
    cycles — but ONLY ``LOCATION`` has a dimension set defined for the demo.
    String values mirror the C2 schema's lowercase ``entity_kind`` vocabulary
    (e.g. ``enrichment_proposal.entity_kind = 'location'``) so the model and
    the persistence layer agree without translation.
    """

    LOCATION = "location"
    # Reserved (NOT modeled this cycle — no speculative dimension sets):
    CHARACTER = "character"
    ITEM = "item"
    FACTION = "faction"


class Dimension(str, Enum):
    """The LOCATION dimension set (locked demo scope).

    ``历史`` / ``地理`` / ``文化`` are the source-faithful Chinese labels;
    ``features`` / ``inhabitants`` are intentionally English per the locked
    dimension set. The enum *declaration order* is the canonical iteration
    order used everywhere (ranking, fixtures, serialization) so behaviour is
    deterministic regardless of dict/set ordering.
    """

    HISTORY = "history"
    GEOGRAPHY = "geography"
    CULTURE = "culture"
    FEATURES = "features"
    INHABITANTS = "inhabitants"


class DimensionSpec(BaseModel):
    """Static metadata for one dimension of one entity-kind.

    ``weight`` is a fixed contribution to the ranking score when this dimension
    is MISSING. The weight table is frozen (documented in ``docs/gap_model.md``)
    so ``rank_score`` is reproducible. ``label`` is the display label
    (source-faithful Chinese for the three core dims).
    """

    model_config = ConfigDict(frozen=True)

    dimension: Dimension
    label: str = Field(min_length=1)
    required: bool
    weight: float = Field(gt=0.0)
    payload_shape: str = Field(min_length=1)


# ═══════════════════════════════════════════════════════════════════════════
# LOCATION dimension table (frozen). Order = Dimension declaration order.
#
# Weights are fixed and documented. Required dimensions (the three core
# descriptive axes of a place) carry heavier weight than the two enhancing
# dimensions, so a place missing its history/geography/culture ranks above a
# place missing only features/inhabitants.
# ═══════════════════════════════════════════════════════════════════════════
LOCATION_DIMENSIONS: tuple[DimensionSpec, ...] = (
    DimensionSpec(
        dimension=Dimension.HISTORY,
        label="历史",
        required=True,
        weight=3.0,
        payload_shape="prose: founding, key events, era, lineage of the place",
    ),
    DimensionSpec(
        dimension=Dimension.GEOGRAPHY,
        label="地理",
        required=True,
        weight=3.0,
        payload_shape="prose: location, terrain, climate, layout/architecture",
    ),
    DimensionSpec(
        dimension=Dimension.CULTURE,
        label="文化",
        required=True,
        weight=3.0,
        payload_shape="prose: customs, beliefs, daily life, governance, faction",
    ),
    DimensionSpec(
        dimension=Dimension.FEATURES,
        label="features",
        required=False,
        weight=2.0,
        payload_shape="list: notable landmarks, relics, natural wonders",
    ),
    DimensionSpec(
        dimension=Dimension.INHABITANTS,
        label="inhabitants",
        required=False,
        weight=2.0,
        payload_shape="list: residents, factions, notable figures tied to place",
    ),
)


# Map of entity-kind → its frozen dimension table. Only LOCATION is populated;
# the engine (C7) reads this table, it does not redefine dimensions.
DIMENSIONS_BY_KIND: dict[EntityKind, tuple[DimensionSpec, ...]] = {
    EntityKind.LOCATION: LOCATION_DIMENSIONS,
}


def dimensions_for(kind: EntityKind) -> tuple[DimensionSpec, ...]:
    """Return the frozen dimension table for ``kind``.

    Raises ``KeyError`` for an entity-kind that has no modeled dimension set
    (only LOCATION is modeled this cycle) — callers must not silently treat an
    unmodeled kind as having zero dimensions.
    """
    return DIMENSIONS_BY_KIND[kind]


# ── salience normalization (deterministic): log-damped so a place with 55
#    mentions does not dwarf one with 7, but more-referenced places still rank
#    higher, all else equal. log1p is monotonic and pure. ──────────────────
def _salience_factor(mention_count: int) -> float:
    """Map a raw canon-mention count to a bounded [1.0, ~) salience factor.

    1 + log1p(n) / log1p(REF) where REF is a fixed reference mention count.
    Deterministic, monotonic, and never < 1.0 (a gap on an unmentioned-but-
    targeted place is not down-weighted below baseline).
    """
    _SALIENCE_REF = 55.0  # 玉虛宮's mention count — the most-referenced demo place
    if mention_count <= 0:
        return 1.0
    return 1.0 + (math.log1p(float(mention_count)) / math.log1p(_SALIENCE_REF))


class Gap(BaseModel):
    """A canon-mentioned entity missing one or more of its dimensions.

    PURE DATA — describes absence only. It deliberately carries no generated
    content, no ``source_type``, no ``confidence``, and no proposal id (H0):
    a gap is "this place lacks X", not "here is invented X".

    ``present_dimensions`` / ``missing_dimensions`` partition the entity-kind's
    full dimension set. A Gap is only meaningful when at least one dimension is
    missing (validated).
    """

    model_config = ConfigDict(frozen=True)

    entity_kind: EntityKind
    canonical_name: str = Field(min_length=1)  # source-faithful (Chinese) name
    target_ref: str | None = None  # canon entity ref (aligns C2 proposal.target_ref)
    mention_count: int = Field(ge=0, default=0)  # canon-mention salience
    present_dimensions: tuple[Dimension, ...] = ()
    missing_dimensions: tuple[Dimension, ...] = ()

    @field_validator("present_dimensions", "missing_dimensions", mode="before")
    @classmethod
    def _coerce_tuple(cls, v: object) -> tuple[Dimension, ...]:
        if v is None:
            return ()
        return tuple(v)  # type: ignore[arg-type]

    @field_validator("missing_dimensions")
    @classmethod
    def _require_at_least_one_missing(
        cls, v: tuple[Dimension, ...]
    ) -> tuple[Dimension, ...]:
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
        """Fraction of the dimension set that is present, in [0.0, 1.0].

        Rounded to fixed precision for stable equality. Computed from the
        dimension table (not from list lengths) so it is robust to a Gap that
        omits a dimension from both present and missing.
        """
        table = self._dimension_table()
        if not table:
            return 0.0
        present = set(self.present_dimensions)
        n_present = sum(1 for spec in table if spec.dimension in present)
        return round(n_present / len(table), _SCORE_PRECISION)


class GapRanking(BaseModel):
    """A Gap paired with its deterministic ranking score.

    Produced by :func:`rank_gaps`. The ``rank`` is the 1-based position after
    sorting (highest score first); ties break by ``canonical_name`` for a
    total, reproducible order.
    """

    model_config = ConfigDict(frozen=True)

    gap: Gap
    score: float
    rank: int = Field(ge=1)


# ═══════════════════════════════════════════════════════════════════════════
# Ranking model (deterministic).
#
#   raw = ( REQUIRED_BONUS * missing_required_count
#           + Σ weight(d) for d in missing_dimensions )
#         * salience_factor(mention_count)
#
#   score = round(raw, 6)
#
# Every term is order-independent and pure: weights come from the frozen
# LOCATION_DIMENSIONS table (iterated in enum-declaration order), the salience
# factor is a pure log function, and the result is rounded to fixed precision.
# No dict/set iteration affects the value, no random, no wall-clock.
# ═══════════════════════════════════════════════════════════════════════════
_REQUIRED_BONUS = 1.0


def rank_score(gap: Gap) -> float:
    """Deterministic ranking score for a single gap (higher = fill first).

    Combines (a) the count of MISSING REQUIRED dimensions, (b) the summed fixed
    weights of all missing dimensions, and (c) a log-damped canon-mention
    salience factor. Pure function: same ``gap`` always yields the same float.
    """
    table = dimensions_for(gap.entity_kind)
    missing = set(gap.missing_dimensions)

    # Iterate the frozen table in fixed declaration order (NOT the set) so the
    # sum is order-stable even though float addition is not associative. A
    # missing dim not in the table contributes nothing — by construction the
    # score never depends on set/dict iteration order.
    weighted_missing = sum(
        spec.weight for spec in table if spec.dimension in missing
    )

    required_term = _REQUIRED_BONUS * gap.missing_required_count()
    raw = (required_term + weighted_missing) * _salience_factor(gap.mention_count)
    return round(raw, _SCORE_PRECISION)


def rank_gaps(gaps: list[Gap]) -> list[GapRanking]:
    """Score and order a list of gaps, highest score first.

    Total, deterministic order: primary key is descending score, tie-break is
    ascending ``canonical_name`` (a stable, content-derived key — never list
    position or object identity). Returns ``GapRanking`` rows with 1-based rank.
    """
    scored = [(rank_score(g), g) for g in gaps]
    # Sort by (-score, canonical_name) — both keys are deterministic.
    scored.sort(key=lambda pair: (-pair[0], pair[1].canonical_name))
    return [
        GapRanking(gap=g, score=score, rank=i + 1)
        for i, (score, g) in enumerate(scored)
    ]
