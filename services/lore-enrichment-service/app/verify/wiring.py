"""Wire canon-verify into the proposal-creation path (RAID C12).

After C11 generates a proposal's facts, :func:`verify_and_annotate` runs the
:class:`~app.verify.canon_verify.CanonVerifier` and folds the
:class:`~app.verify.canon_verify.VerifyResult` into the data a later cycle
persists onto the ``enrichment_proposal`` row:

  * the verify result is recorded under ``provenance_json['canon_verify']``
    (annotation only — carries NO ``source_type`` / confidence / canon marker);
  * a ``verify_status`` is derived for the row so downstream C13 review can
    prioritise flagged proposals.

H0 (LOCKED): every ``verify_status`` this module can produce keeps the proposal
QUARANTINED. There is no status here that admits a proposal to canon — only the
human PROMOTE gate (C13) does that, and only from a clean review. A flagged
proposal is marked ``needs_review`` (or ``quarantined`` when injection fired),
NOT dropped and NEVER promoted. The proposal's ``review_status`` stays at the C2
lifecycle entry (``proposed``); ``verify_status`` is an ADDITIONAL annotation, it
does not advance the lifecycle DAG.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Sequence

from app.verify.canon_verify import CanonVerifier, FlagKind, Severity, VerifyResult

if TYPE_CHECKING:
    # Annotation-only (PEP 563 active above). Importing these leaf types eagerly runs
    # the generation/retrieval package __init__ trees, which descend into strategies
    # and import back into this still-initializing module (fabrication imports
    # AnnotatedVerify from here) → circular ImportError on any entry point that loads
    # app.verify before the strategies tree. Deferring them breaks the cycle with no
    # behaviour change (CanonVerifier/FlagKind/VerifyResult stay eager — FlagKind is
    # used at runtime in _derive_status). See QC F-LIVE-2.
    from app.generation.provenance import EnrichedFact
    from app.retrieval.strategy import GroundedProposal

__all__ = [
    "VerifyStatus",
    "AnnotatedVerify",
    "RejectDecision",
    "decide_auto_reject",
    "AUTO_REJECT_ANACHRONISM_MIN_MARKERS",
    "verify_and_annotate",
]

#: C3: how many DISTINCT anachronism markers make a proposal egregiously
#: anachronistic (auto-reject). One conservative-list marker stays advisory; two
#: distinct out-of-era concepts in one proposal is a strong egregious signal.
AUTO_REJECT_ANACHRONISM_MIN_MARKERS: int = 2


class VerifyStatus(str, Enum):
    """The annotation a verify run attaches to a proposal (NONE are canon).

    All keep the proposal out of canon. ``verified_clean`` means the three checks
    found nothing AND ran against real canon — NOT an admission to canon, only
    "nothing inconsistent was detected". ``auto_rejected`` (C3) is the EGREGIOUS
    case: the proposal is persisted as a terminal ``rejected`` row (audited) and
    never surfaced to the human queue — still never canon (it is suppressed, not
    promoted). The human gate decides every non-rejected case.
    """

    #: No flags AND contradiction ran against real canon (not degraded).
    VERIFIED_CLEAN = "verified_clean"
    #: Contradiction/anachronism flags fired — raise for human attention.
    NEEDS_REVIEW = "needs_review"
    #: Injection neutralized — quarantine harder; the SAFE text is persisted.
    QUARANTINED = "quarantined"
    #: KG/canon read unavailable — contradiction unverifiable; conservative.
    DEGRADED = "degraded"
    #: C3: egregiously-unreasonable (injection / HIGH contradiction / >=2 distinct
    #: anachronism markers) — auto-rejected (terminal `rejected`, never surfaced).
    AUTO_REJECTED = "auto_rejected"


@dataclass(frozen=True)
class RejectDecision:
    """The verdict that a proposal is EGREGIOUS enough to AUTO-REJECT (C3).

    ``reason`` is a concise, human-readable evidence string persisted to the
    ``rejected_reason`` column (audit: what tripped the auto-reject + why). It is
    derived from the firing flags — never an opaque boolean.
    """

    reason: str


def decide_auto_reject(result: VerifyResult) -> RejectDecision | None:
    """Classify a verify result as EGREGIOUS (auto-reject) or not (advisory).

    H0-safe: auto-reject is the CONSERVATIVE direction — it suppresses surfacing,
    never admits canon — so the bar is high (false-positive-averse). Egregious iff:
      * ANY injection flag (a neutralized payload is never legitimate lore), OR
      * a CONTRADICTION flag at HIGH severity (direct canon negation), OR
      * >= ``AUTO_REJECT_ANACHRONISM_MIN_MARKERS`` DISTINCT anachronism markers, OR
      * a HIGH-severity REGURGITATION flag (copyright-safety ③: the output copied
        substantial verbatim source EXPRESSION — a derivative-work liability).
    Returns a :class:`RejectDecision` (with evidence) when egregious, else None
    (the proposal stays on the advisory flag-for-human path)."""
    reasons: list[str] = []

    injection = [f for f in result.flags if f.kind is FlagKind.INJECTION]
    if injection:
        reasons.append(f"injection ({injection[0].evidence})")

    high_contradiction = [
        f
        for f in result.flags
        if f.kind is FlagKind.CONTRADICTION and f.severity is Severity.HIGH
    ]
    if high_contradiction:
        reasons.append(f"high-severity contradiction ({high_contradiction[0].evidence})")

    distinct_anachronisms = {
        f.evidence for f in result.flags if f.kind is FlagKind.ANACHRONISM
    }
    if len(distinct_anachronisms) >= AUTO_REJECT_ANACHRONISM_MIN_MARKERS:
        reasons.append(
            f"{len(distinct_anachronisms)} distinct anachronism markers"
        )

    # Copyright-safety ③: an EGREGIOUS (HIGH) regurgitation flag = the output copied
    # substantial verbatim source EXPRESSION — a derivative-work liability that must
    # NEVER reach canon. Softer (MEDIUM) overlap stays advisory (human gate).
    high_regurgitation = [
        f
        for f in result.flags
        if f.kind is FlagKind.REGURGITATION and f.severity is Severity.HIGH
    ]
    if high_regurgitation:
        reasons.append(f"verbatim source regurgitation ({high_regurgitation[0].evidence})")

    if not reasons:
        return None
    return RejectDecision(reason="auto-reject: " + "; ".join(reasons))


class AnnotatedVerify:
    """The verify outcome packaged for persistence — annotation, never canon.

    Holds the :class:`VerifyResult`, the derived :class:`VerifyStatus`, and a
    ``provenance_patch`` to merge into the proposal's ``provenance_json``. Exposes
    NO method that changes ``source_type`` / ``confidence`` / ``pending_validation``
    — by construction it can only annotate.
    """

    def __init__(self, result: VerifyResult, status: VerifyStatus) -> None:
        self.result = result
        self.status = status

    @property
    def provenance_patch(self) -> dict[str, object]:
        """The dict to merge into ``provenance_json`` (verify annotation only)."""
        patch = dict(self.result.as_provenance())
        patch["verify_status"] = self.status.value
        return patch

    @property
    def is_quarantined(self) -> bool:
        """Always True — every verify outcome keeps the proposal quarantined.

        H0 guard: there is no code path where a verify result admits a proposal to
        canon. Exposed so a caller (and a test) can assert the invariant holds for
        every status, including ``verified_clean``.
        """
        return True


def _derive_status(result: VerifyResult) -> VerifyStatus:
    """Map a verify result to its annotation status (none admit canon).

    Priority: AUTO_REJECTED (C3 egregious — injection / HIGH contradiction / >=2
    distinct anachronism markers) > quarantined (any injection) > other flags
    (needs_review) > degraded (conservative) > clean. A clean result is
    ``verified_clean`` only when it has no flags AND was not degraded
    (``result.passed``)."""
    if decide_auto_reject(result) is not None:
        return VerifyStatus.AUTO_REJECTED
    if any(f.kind is FlagKind.INJECTION for f in result.flags):
        return VerifyStatus.QUARANTINED
    if result.flags:
        return VerifyStatus.NEEDS_REVIEW
    if result.verify_degraded:
        return VerifyStatus.DEGRADED
    return VerifyStatus.VERIFIED_CLEAN


async def verify_and_annotate(
    verifier: CanonVerifier,
    proposal: GroundedProposal,
    facts: Sequence[EnrichedFact],
    *,
    jwt: str = "",
) -> AnnotatedVerify:
    """Run canon-verify over a proposal at creation and package the annotation.

    Returns an :class:`AnnotatedVerify` whose ``provenance_patch`` a later cycle
    merges into the row's ``provenance_json`` and whose ``status`` drives review
    prioritisation. The proposal/facts are NOT mutated, quarantine is NOT lifted,
    nothing is canonized — annotation only (H0).
    """
    result = await verifier.verify(proposal, facts, jwt=jwt)
    status = _derive_status(result)
    return AnnotatedVerify(result, status)
