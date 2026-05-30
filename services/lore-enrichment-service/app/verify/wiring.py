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

from enum import Enum
from typing import Sequence

from app.generation.provenance import EnrichedFact
from app.retrieval.strategy import GroundedProposal
from app.verify.canon_verify import CanonVerifier, FlagKind, VerifyResult

__all__ = [
    "VerifyStatus",
    "AnnotatedVerify",
    "verify_and_annotate",
]


class VerifyStatus(str, Enum):
    """The annotation a verify run attaches to a proposal (NONE are canon).

    All four keep the proposal quarantined. ``verified_clean`` means the three
    checks found nothing AND ran against real canon — it is NOT an admission to
    canon, only "nothing inconsistent was detected". The human gate still decides.
    """

    #: No flags AND contradiction ran against real canon (not degraded).
    VERIFIED_CLEAN = "verified_clean"
    #: Contradiction/anachronism flags fired — raise for human attention.
    NEEDS_REVIEW = "needs_review"
    #: Injection neutralized — quarantine harder; the SAFE text is persisted.
    QUARANTINED = "quarantined"
    #: KG/canon read unavailable — contradiction unverifiable; conservative.
    DEGRADED = "degraded"


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
    """Map a verify result to its (always-quarantined) annotation status.

    Priority: injection (hardest quarantine) > other flags (needs_review) >
    degraded (conservative) > clean. A clean result is ``verified_clean`` only
    when it both has no flags AND was not degraded (``result.passed``)."""
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
