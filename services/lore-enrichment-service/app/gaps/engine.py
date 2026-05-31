"""Gap-detection ENGINE (RAID C7 — M1b).

Turns per-entity dimension *coverage* (what the knowledge graph knows about each
canon-mentioned LOCATION) into a typed, ranked :class:`~app.gaps.model.Gap`
list, using the C6 model's frozen dimension table + deterministic ranking.

Data flow (locked):

  * Input ``EntityCoverage`` records describe, per entity, which dimensions are
    PRESENT in the KG (plus canon-mention salience + identity). The engine
    derives the MISSING dimensions itself from the entity-kind's frozen
    dimension table (``dimensions_for`` in C6) — it never trusts a precomputed
    missing list.
  * A gap = a canon-mentioned entity missing ≥1 dimension. A fully-described
    entity (all dimensions present) is silently skipped — it is not a gap.
  * Ranking is C6's ``rank_gaps`` (descending score, ``canonical_name``
    tie-break): a total, reproducible order. The engine adds NO ranking logic.

Boundaries (locked):
  * LLM-free, DB-write-free: this module reads platform state ONLY through the
    C1 :class:`~app.clients.port.KnowledgeReadPort` Protocol and otherwise does
    pure in-memory derivation. NO network/DB/LLM client imports, NO model
    names, NO persistence writes. Generation starts at C8/C9.
  * Q6 graceful degradation: the project entrypoint reads graph-stats through
    the port; an empty/zero graph (or a Null port, or a degraded HTTP port that
    fell back to empties) yields ``[]`` — never a crash. There is nothing to
    detect against an empty KG.
  * H0: the engine emits only ``Gap`` (absence) data — no content, no
    ``source_type``, no proposal. Enrichment is C8–C11/C13.
"""

from __future__ import annotations

from typing import Iterable
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.clients.knowledge import GraphStats
from app.clients.port import KnowledgeReadPort
from app.gaps.model import (
    Dimension,
    EntityKind,
    Gap,
    GapRanking,
    dimensions_for,
    rank_gaps,
)

__all__ = [
    "EntityCoverage",
    "GapDetectionEngine",
    "detect_gaps",
    "detect_ranked_gaps",
]


class EntityCoverage(BaseModel):
    """What the KG currently knows about one canon entity (engine input).

    Carries identity + canon-mention salience + the set of dimensions the graph
    already covers for this entity. The engine derives the MISSING dimensions
    from the entity-kind's frozen dimension table — a future C1 per-entity read
    yields this shape; in tests it is hydrated from the C6 fixture.

    PURE DATA: it describes coverage only, never generated content (H0).
    """

    model_config = ConfigDict(frozen=True)

    entity_kind: EntityKind
    canonical_name: str = Field(min_length=1)
    target_ref: str | None = None
    mention_count: int = Field(ge=0, default=0)
    present_dimensions: tuple[Dimension, ...] = ()


class GapDetectionEngine:
    """Deterministic, LLM-free engine: coverage → typed, ranked gaps.

    Stateless (no per-call mutation, no I/O of its own). Reads platform state
    only through the injected C1 :class:`KnowledgeReadPort` in the project
    entrypoint; the pure derivation methods take coverage directly so they are
    trivially testable against fixtures.
    """

    def detect(self, coverages: Iterable[EntityCoverage]) -> list[Gap]:
        """Derive the typed (unranked) gap list from coverage.

        For each coverage, ``missing = dimension_set − present`` (iterated in the
        frozen table's declaration order, so the resulting tuple is itself
        deterministic). A coverage whose entity is fully described (no missing
        dimension) is skipped — it is not a gap, and never reaches the ``Gap``
        validator (which rejects zero-missing). Never raises on valid coverage.
        """
        gaps: list[Gap] = []
        for cov in coverages:
            gap = self._gap_from_coverage(cov)
            if gap is not None:
                gaps.append(gap)
        return gaps

    def detect_ranked(self, coverages: Iterable[EntityCoverage]) -> list[GapRanking]:
        """Detect gaps and rank them with the C6 ranking (descending score,
        ``canonical_name`` tie-break). Total, reproducible order."""
        return rank_gaps(self.detect(coverages))

    async def detect_ranked_for_project(
        self,
        port: KnowledgeReadPort,
        *,
        jwt: str,
        project_id: UUID,
        coverages: Iterable[EntityCoverage],
    ) -> list[GapRanking]:
        """Project entrypoint with Q6 graceful degradation.

        Reads graph-stats through the C1 port. If the graph is empty (zero
        stats — a project with no extraction history, a Null port, or an HTTP
        port that degraded to empties on an outage), there is no canon graph to
        detect gaps against, so we return ``[]`` without touching the
        coverages. Otherwise we run pure detection. The port never raises (its
        impls degrade to typed empties), so neither does this method.
        """
        stats: GraphStats = await port.get_graph_stats(jwt=jwt, project_id=project_id)
        if stats.is_empty:
            return []
        return self.detect_ranked(coverages)

    # ── internal: single-coverage derivation ────────────────────────────────

    @staticmethod
    def _gap_from_coverage(cov: EntityCoverage) -> Gap | None:
        """Build a ``Gap`` from one coverage, or ``None`` if fully described.

        ``missing`` and the echoed ``present`` are both filtered through the
        frozen dimension table in declaration order, so:
          * a present dimension not in the table is ignored (no drift),
          * both tuples come out in canonical order (deterministic),
          * an entity with every dimension present yields ``None`` (no gap).
        """
        table = dimensions_for(cov.entity_kind)
        present_set = set(cov.present_dimensions)
        present = tuple(s.dimension for s in table if s.dimension in present_set)
        missing = tuple(s.dimension for s in table if s.dimension not in present_set)
        if not missing:
            return None  # fully described → not a gap
        return Gap(
            entity_kind=cov.entity_kind,
            canonical_name=cov.canonical_name,
            target_ref=cov.target_ref,
            mention_count=cov.mention_count,
            present_dimensions=present,
            missing_dimensions=missing,
        )


# ── module-level convenience wrappers (thin; share the engine) ───────────────

_DEFAULT_ENGINE = GapDetectionEngine()


def detect_gaps(coverages: Iterable[EntityCoverage]) -> list[Gap]:
    """Module-level shortcut over a shared stateless engine — typed gaps."""
    return _DEFAULT_ENGINE.detect(coverages)


def detect_ranked_gaps(coverages: Iterable[EntityCoverage]) -> list[GapRanking]:
    """Module-level shortcut over a shared stateless engine — ranked gaps."""
    return _DEFAULT_ENGINE.detect_ranked(coverages)
