"""Wiki generation — the deterministic rule-gate (wiki-llm M3 / §C2).

Pure structural check of a parsed :class:`WikiArticleIR` BEFORE the (M4)
CanonVerifier and the writeback. The parser already dropped hallucinated cite
labels and flagged non-trivial uncited spans (``grounded=False``); this gate
turns those signals into a pass/fail verdict.

Pass bar (PO Q2-A, permissive — the CanonVerifier is the real quality gate):
a body is acceptable iff it is **non-empty** AND carries **≥1 grounded, cited
claim** (the no-hollow-stub rule — never persist an article that grounds
nothing). The ungrounded-claim ratio is computed and surfaced as a soft signal
(a reason string + the counts) but does NOT by itself fail the gate at M3.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.wiki.ir import WikiArticleIR


class GateResult(BaseModel):
    """Verdict + the counts that drove it. ``grounded_claims`` = spans that
    resolved ≥1 cite; ``ungrounded_nontrivial`` = non-trivial spans the parser
    flagged as uncited (the hallucination surface); ``reasons`` explains a
    failure or notes a soft concern (high ungrounded ratio)."""

    passed: bool
    grounded_claims: int
    ungrounded_nontrivial: int
    block_count: int
    reasons: list[str] = Field(default_factory=list)

    @property
    def nontrivial_claims(self) -> int:
        return self.grounded_claims + self.ungrounded_nontrivial

    @property
    def ungrounded_ratio(self) -> float:
        total = self.nontrivial_claims
        return self.ungrounded_nontrivial / total if total else 0.0


#: Above this uncited-ratio the gate adds a soft warning (NOT a fail at M3).
SOFT_UNGROUNDED_RATIO = 0.5


def evaluate(ir: WikiArticleIR) -> GateResult:
    """Structural pass/fail for a generated article IR (M3 rule-gate)."""
    grounded = ir.grounded_claim_count
    ungrounded = sum(
        1 for b in ir.blocks for s in b.all_spans() if not s.grounded
    )
    block_count = len(ir.blocks)
    reasons: list[str] = []

    if block_count == 0:
        reasons.append("empty: parser produced no blocks")
    if grounded == 0:
        reasons.append("no grounded claims: nothing cites a provided source")

    passed = block_count > 0 and grounded > 0

    result = GateResult(
        passed=passed,
        grounded_claims=grounded,
        ungrounded_nontrivial=ungrounded,
        block_count=block_count,
        reasons=reasons,
    )
    # Soft signal only (Q2-A): a high uncited ratio is logged via `reasons`
    # but does not fail an otherwise-grounded article — M4's CanonVerifier is
    # the real quality/contradiction gate.
    if passed and result.ungrounded_ratio > SOFT_UNGROUNDED_RATIO:
        result.reasons.append(
            f"soft: {ungrounded}/{result.nontrivial_claims} non-trivial claims "
            "are uncited (high hallucination surface)"
        )
    return result
