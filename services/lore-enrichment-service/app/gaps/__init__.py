"""Gap MODEL (RAID C6) — the pure-data spec the gap-detection engine (C7) consumes.

This package defines WHAT a gap is (a canon-mentioned entity missing one or more
of its entity-kind's dimensions) and HOW gaps are ranked (a deterministic score),
but NOT how gaps are detected from a live knowledge graph — that traversal is the
C7 engine and is explicitly OUT of scope here.

H0 boundary (locked): a Gap describes ABSENCE only. It carries no generated
content, no `source_type`, no `confidence`, and emits no proposals. Enriched-as-
canon tagging belongs to C11/C13, never to this model.
"""

from app.gaps.model import (
    DIMENSIONS_BY_KIND,
    LOCATION_DIMENSIONS,
    Dimension,
    DimensionSpec,
    EntityKind,
    Gap,
    GapRanking,
    rank_gaps,
    rank_score,
)

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
