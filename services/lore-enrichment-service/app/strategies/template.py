"""Strategy (a) — TEMPLATE scaffolding (RAID C9, Q-R2 P1 technique #1).

The FIRST concrete :class:`~app.strategies.base.EnrichmentStrategy`. It is the
cheapest tier: pure, deterministic, LLM-free scaffolding. Given a :class:`Gap`
(an entity + its MISSING dimensions, from the C7 engine) it emits a *proposal
SKELETON* — one structured slot per missing dimension, **keyed by the dimension's
source-faithful Chinese label** (历史 / 地理 / 文化 …), with **EMPTY placeholder
values**. Filling those slots with grounded content is a LATER cycle (retrieval =
C10, generation = C11); this cycle only fixes the SHAPE.

Boundaries (locked — see docs/raid/cycle_briefs/09_strategy-template.md):
  * NO LLM / embedding call, NO model-name string, NO retrieval, NO write-back.
    Imports only the stdlib + pydantic + the C6 gap model + the C8 interface.
  * Dimension KEYS are NOT hardcoded here — they derive from the C6 frozen
    dimension table (``dimensions_for`` → ``DimensionSpec.label``), the single
    source of truth, so they can never drift from C6.
  * H0 (enriched lore != canon): every :class:`ScaffoldedProposal` is born
    ``origin='enrichment'``, ``technique='template'``, ``review_status='proposed'``,
    ``confidence`` strictly between 0 and 1.0 (a near-zero scaffold confidence —
    the values are EMPTY, nothing has been generated yet), ``pending_validation=
    True``. It is NEVER ``source_type='glossary'`` / confidence=1.0. Only the
    author's later PROMOTE (C13) canonizes.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.gaps.model import Dimension, Gap, dimensions_for
from app.strategies.base import (
    CostEstimate,
    EnrichmentStrategy,
    StrategyContext,
    Technique,
)

__all__ = [
    "ScaffoldedProposal",
    "TemplateStrategy",
    "SCAFFOLD_CONFIDENCE",
    "SCAFFOLD_PLACEHOLDER",
]


# ── H0 constants (single source of truth for the makeup-lore markers) ─────────
#: The empty placeholder a scaffold slot carries. EMPTY — not an English stub,
#: not generated content. C10/C11 fill it; until then a slot is visibly unfilled.
SCAFFOLD_PLACEHOLDER: str = ""

#: A scaffold's confidence. The C2 schema CHECKs ``confidence > 0 AND < 1.0`` —
#: it cannot be exactly 0 — so we use the smallest meaningful positive value to
#: express "this is an empty shell, near-zero confidence, NEVER canon (1.0)".
#: H0: strictly < 1.0 by construction.
SCAFFOLD_CONFIDENCE: float = 0.01

#: The fixed origin marker for all enriched (makeup) proposals — never 'glossary'
#: (authored canon). Mirrors the C2 schema's ``origin`` default.
_ENRICHED_ORIGIN: str = "enrichment"

#: Per-gap scaffolding is in-memory only — no LLM/eval call — so its abstract
#: cost is zero. (The guardrail still sees a CostEstimate; it just adds nothing.)
_SCAFFOLD_UNIT_COST: float = 0.0


class ScaffoldedProposal(BaseModel):
    """An EMPTY, H0-stamped enrichment proposal skeleton (the C9 output unit).

    One per gap. Carries the Q3 scope, the H0 distinguishing markers, and a
    ``dimensions`` map of **Chinese dimension key → empty placeholder** — one
    entry per MISSING dimension of the gap. It maps onto the C2
    ``enrichment_proposal`` row (origin/technique/review_status/confidence/
    provenance_json) so a later cycle can persist it without translation; the
    ``dimensions`` map is the un-filled content the generation cycle will fill.

    H0 by construction: the canon-distinguishing fields are model defaults that
    a caller cannot flip to canon — ``technique`` is fixed to ``template``,
    ``origin`` to ``enrichment``, ``review_status`` to ``proposed``, and
    ``confidence`` is validated strictly < 1.0 (and > 0 to match the DB CHECK).
    """

    model_config = ConfigDict(frozen=True)

    # ── identity + Q3 scope (carried from the gap + the run context) ──────────
    user_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    entity_kind: str = Field(min_length=1)
    canonical_name: str = Field(min_length=1)
    target_ref: str | None = None

    # ── the scaffold: Chinese dimension key → EMPTY placeholder value ─────────
    #    one entry per MISSING dimension; insertion order = C6 declaration order.
    dimensions: dict[str, str]

    # ── H0 distinguishing markers (never canon) ───────────────────────────────
    origin: str = Field(default=_ENRICHED_ORIGIN)
    technique: str = Field(default=Technique.TEMPLATE.value)
    review_status: str = Field(default="proposed")
    confidence: float = Field(default=SCAFFOLD_CONFIDENCE, gt=0.0, lt=1.0)
    pending_validation: bool = Field(default=True)
    provenance_json: dict[str, object] = Field(default_factory=dict)

    def is_empty_scaffold(self) -> bool:
        """True iff every dimension slot is still the empty placeholder.

        A freshly-scaffolded proposal is always empty (C9 generates no content);
        this lets a later cycle / test assert the scaffold has not been filled.
        """
        return all(v == SCAFFOLD_PLACEHOLDER for v in self.dimensions.values())


class TemplateStrategy(EnrichmentStrategy):
    """Technique (a): deterministic, LLM-free proposal scaffolding (tier P1).

    Registers under the ``template`` key. :meth:`run` turns each gap into one
    :class:`ScaffoldedProposal` whose ``dimensions`` map has one EMPTY slot per
    missing dimension, keyed by the dimension's Chinese label from C6. No I/O,
    no model call, no randomness — same gap + context → same proposal.
    """

    technique = Technique.TEMPLATE

    def estimate_cost(self, gap_batch: list[Gap]) -> CostEstimate:
        """Scaffolding is free (no LLM/eval). Cost is zero; ``units`` counts the
        gaps so the guardrail/UI can report batch size. Pure + side-effect-free.
        """
        n = len(gap_batch)
        return CostEstimate(
            technique=self.technique,
            gap_count=n,
            units=float(n),
            cost=_SCAFFOLD_UNIT_COST * n,
        )

    async def run(
        self,
        gap_batch: list[Gap],
        context: StrategyContext,
    ) -> list[ScaffoldedProposal]:
        """Scaffold each gap into an empty, H0-stamped proposal skeleton.

        Async to satisfy the C8 interface; performs NO awaitable I/O (pure
        scaffolding). Returns one :class:`ScaffoldedProposal` per gap, in input
        order. NEVER returns canon — every proposal is born quarantined (H0).
        """
        return [self._scaffold(gap, context) for gap in gap_batch]

    # ── internal: one gap → one empty H0 proposal skeleton ────────────────────
    @staticmethod
    def _scaffold(gap: Gap, context: StrategyContext) -> ScaffoldedProposal:
        dimensions = TemplateStrategy._dimension_slots(gap)
        provenance = {
            "technique": Technique.TEMPLATE.value,
            "source_gap": {
                "entity_kind": gap.entity_kind,
                "canonical_name": gap.canonical_name,
                "target_ref": gap.target_ref,
                "missing_dimensions": list(gap.missing_dimensions),
            },
            "scaffold": True,  # values are empty placeholders, not generated yet
        }
        return ScaffoldedProposal(
            user_id=context.user_id,
            project_id=context.project_id,
            entity_kind=gap.entity_kind,
            canonical_name=gap.canonical_name,
            target_ref=gap.target_ref,
            dimensions=dimensions,
            provenance_json=provenance,
            # H0 markers come from the model defaults (origin/technique/
            # review_status/confidence/pending_validation) — never set to canon.
        )

    @staticmethod
    def _dimension_slots(gap: Gap) -> dict[str, str]:
        """Build the ``{Chinese-label: empty-placeholder}`` map for a gap.

        Keys derive from the C6 frozen dimension table (``dimensions_for`` →
        ``DimensionSpec.label``) — the single source of truth, never a hardcoded
        literal — and are emitted in the C6 declaration order, restricted to the
        gap's MISSING dimensions (one slot per missing dimension). Values are the
        EMPTY placeholder; C10/C11 fill them.
        """
        missing: set[Dimension] = set(gap.missing_dimensions)
        slots: dict[str, str] = {}
        for spec in dimensions_for(gap.entity_kind):
            if spec.dimension in missing:
                slots[spec.label] = SCAFFOLD_PLACEHOLDER
        return slots
