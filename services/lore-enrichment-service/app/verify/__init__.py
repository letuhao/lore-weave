"""Canon-verify (RAID C12, M2) — consistency annotation at proposal creation.

A proposal's generated facts are checked for (a) CONTRADICTION vs existing
glossary/KG canon, (b) ANACHRONISM vs the locked 商周/封神演义 frame, and (c)
INJECTION (the corpus text + LLM output are UNTRUSTED — prompt-injection /
canon-spoofing / control sequences are neutralized). The result ANNOTATES the
proposal (flags + degraded marker), it never lifts quarantine or canonizes
anything (H0). Correctness rests on the human PROMOTE gate (C13), not here.

Two modules:
  * ``sanitize`` — injection-defense (mirror knowledge-service ``pending_facts``,
    Q1): tag-not-delete, idempotent, scan-then-tag, CJK-safe.
  * ``canon_verify`` — :class:`CanonVerifier` (the three checks) +
    :class:`VerifyResult`/:class:`VerifyFlag` + :func:`verify_and_annotate` wiring.
"""

from app.verify.canon_verify import (
    ANACHRONISM_MARKERS,
    CanonFact,
    CanonLookupFn,
    CanonVerifier,
    FlagKind,
    Severity,
    VerifyFlag,
    VerifyResult,
)
from app.verify.sanitize import (
    FICTIONAL_MARKER,
    INJECTION_PATTERNS,
    neutralize_proposal_text,
    scan_injection,
)
from app.verify.wiring import verify_and_annotate

__all__ = [
    # canon_verify
    "CanonVerifier",
    "VerifyResult",
    "VerifyFlag",
    "FlagKind",
    "Severity",
    "CanonFact",
    "CanonLookupFn",
    "ANACHRONISM_MARKERS",
    # sanitize
    "neutralize_proposal_text",
    "scan_injection",
    "INJECTION_PATTERNS",
    "FICTIONAL_MARKER",
    # wiring
    "verify_and_annotate",
]
