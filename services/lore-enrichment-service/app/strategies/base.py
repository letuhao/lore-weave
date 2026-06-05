"""The ``EnrichmentStrategy`` interface + the value types it trades in (RAID C8).

A *strategy* is one pluggable enrichment technique. It declares WHICH technique
it is (``technique``) and WHICH rollout tier it belongs to (``tier`` = P1/P2/P3),
estimates the cost of filling a batch of gaps (``estimate_cost``), and — in a
later cycle — runs to produce proposal content (``run``). Here ``run`` is a
signature only; the bodies land in C9/C10/C16/C17.

Boundaries (locked):
  * NO LLM/embedding calls and NO model-name strings — a strategy resolves its
    model via provider-registry in its own cycle; this module imports only the
    stdlib + pydantic.
  * H0 — a strategy produces *proposals* (later); it NEVER marks output canon.
    There is no ``source_type``/confidence handling in this interface; the H0
    carrier is the C2 ``enrichment_proposal`` schema, written downstream.
  * ``CostEstimate`` is provider-agnostic: it counts *units* (e.g. token budget
    or eval calls) and an abstract ``cost`` figure. The cost UNIT is opaque to
    the guardrail (C8 cost_guardrail) — it only compares against a cap.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field

from app.db.book_profile import NEUTRAL_PROFILE, BookProfile

if TYPE_CHECKING:  # avoid importing the gap model at runtime (keeps base lean)
    from app.gaps.model import Gap

__all__ = [
    "Tier",
    "Technique",
    "CostEstimate",
    "StrategyContext",
    "EnrichmentStrategy",
]


class Tier(str, Enum):
    """Rollout tier for a technique (Q-R2 phased rollout by effectiveness/cost).

    P1 ships active; P2/P3 register but stay dark behind feature-flags until the
    C15 cost/quality gate clears them. The tier is declared by the strategy and
    is the natural grouping the flags + the gate reason about.
    """

    P1 = "P1"
    P2 = "P2"
    P3 = "P3"


class Technique(str, Enum):
    """The four enrichment techniques (Q-R2). Values mirror the C2 schema's
    ``technique`` CHECK vocabulary so a strategy key round-trips to persistence
    without translation.

    Tier mapping is fixed by the locked rollout and exposed via :meth:`tier`:
      * P1 — ``template``, ``retrieval``, ``compose_draft``
      * P2 — ``fabrication``
      * P3 — ``recook``
    """

    TEMPLATE = "template"
    RETRIEVAL = "retrieval"
    FABRICATION = "fabrication"
    RECOOK = "recook"
    # Compose mode D (draft expansion). P1 + UNGATED: it expands the AUTHOR's own
    # draft (not corpus/canon-fabricated), so it carries the same low-risk tier as
    # retrieval. Still H0-quarantined + ③(N/A — no corpus) + ④ promote-gate.
    COMPOSE_DRAFT = "compose_draft"

    @property
    def tier(self) -> Tier:
        """The locked rollout tier for this technique (single source of truth)."""
        return _TECHNIQUE_TIER[self]


# Frozen tier mapping (Q-R2). Kept beside the enum so ``Technique.tier`` and the
# feature-flag defaults derive from ONE table — no drift between "which tier" and
# "which is active by default".
_TECHNIQUE_TIER: dict[Technique, Tier] = {
    Technique.TEMPLATE: Tier.P1,
    Technique.RETRIEVAL: Tier.P1,
    Technique.FABRICATION: Tier.P2,
    Technique.RECOOK: Tier.P3,
    Technique.COMPOSE_DRAFT: Tier.P1,  # ungated — expands the author's own draft
}


class CostEstimate(BaseModel):
    """A strategy's projected cost of enriching a gap batch.

    Provider-agnostic and unit-opaque on purpose: ``units`` is the abstract
    quantity the strategy will consume (token budget, eval calls, …) and
    ``cost`` is the figure the per-job guardrail compares against the job's cap.
    Both are non-negative; the guardrail treats ``cost`` as the spend a run of
    this batch would add. NO currency assumption is baked in — the cap config
    and the estimate must agree on units (validated by the guardrail's contract,
    not here).

    ``gap_count`` is informational (how many gaps the estimate covers) so a
    caller can derive a per-gap average without re-deriving it.
    """

    model_config = ConfigDict(frozen=True)

    technique: Technique
    gap_count: int = Field(ge=0)
    units: float = Field(ge=0.0)
    cost: float = Field(ge=0.0)


class StrategyContext(BaseModel):
    """Per-run context handed to a strategy (scope + provider-registry seam).

    Carries the Q3 scope (``user_id`` / ``project_id``) and the
    ``model_ref`` — a provider-registry reference, NOT a model NAME. The literal
    model id is resolved by the strategy's later cycle via provider-registry;
    storing a ``model_ref`` here keeps the no-hardcoded-model-names invariant.
    """

    model_config = ConfigDict(frozen=True)

    user_id: str
    project_id: str
    # An opaque provider-registry reference (e.g. a registry entry id), resolved
    # to a concrete endpoint+model downstream. NEVER a model name. Optional here
    # because the interface predates any real generation.
    model_ref: str | None = None
    # The per-book worldview profile (de-bias C1). Read by the prompt builders +
    # the dimension resolver to de-bias generation away from the hardcoded 封神/商周/
    # 中文/地点 universe. Defaults to the NEUTRAL profile (language auto, anachronism
    # OFF) so a context built without a book behaves like a generic worldbuilder.
    profile: BookProfile = NEUTRAL_PROFILE
    # Compose mode D (draft expansion): the author's own draft prose to expand +
    # how (``add_only`` keep-verbatim | ``rewrite`` voice-sync). Additive + frozen,
    # ignored by every other strategy (exactly like ``profile`` was in C1) — only
    # the DraftExpandStrategy reads them. None on a non-compose-draft run.
    seed_text: str | None = None
    expand_mode: str | None = None


class EnrichmentStrategy(ABC):
    """One pluggable enrichment technique.

    Subclasses declare their identity via :attr:`technique` (which fixes
    :attr:`tier`), estimate the cost of a gap batch, and — in their own cycle —
    implement :meth:`run` to produce proposal content. Here :meth:`run` is
    abstract with a fixed signature only; no body ships in C8.

    The registry keys a strategy by :attr:`key` (== the technique value), so a
    technique has at most one registered strategy.
    """

    #: Concrete subclasses MUST set this to their :class:`Technique`.
    technique: Technique

    @property
    def key(self) -> str:
        """The registry key for this strategy (the technique's string value)."""
        return self.technique.value

    @property
    def tier(self) -> Tier:
        """The rollout tier, derived from the technique (never hand-set)."""
        return self.technique.tier

    @abstractmethod
    def estimate_cost(self, gap_batch: list["Gap"]) -> CostEstimate:
        """Project the cost of enriching ``gap_batch`` with this technique.

        Pure + side-effect-free: no I/O, no LLM call. Returns a
        :class:`CostEstimate` whose ``cost`` the per-job guardrail accumulates
        and compares against the job's cap BEFORE the batch is run.
        """
        raise NotImplementedError

    @abstractmethod
    async def run(
        self,
        gap_batch: list["Gap"],
        context: StrategyContext,
    ) -> object:
        """Produce enrichment proposals for ``gap_batch`` (DEFERRED to C9+).

        Signature only in C8 — no body, no LLM/embedding call here. The return
        shape (proposal content) is defined by the technique's own cycle; it
        MUST always be *proposal* data (H0: never canon, never confidence=1.0).
        """
        raise NotImplementedError
