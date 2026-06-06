"""loreweave_grounding — shared grounding port (mui #3).

Consolidates the grounding (evidence/citation) + canon-verification logic that
was reimplemented per-service (lore-enrichment, knowledge, composition) into one
service-agnostic package. Pure-Python; any LLM call is injected by the caller —
no HTTP/LLM hard dependency (the `loreweave_eval` model).

- `cites`  — `GroundingCite` (unified evidence shape) + `merge_cites` /
  `compose_cites` (dedup → rank → top-K) + per-consumer adapters.
- `verify` — `CanonVerifier` (contradiction / anachronism / injection /
  regurgitation), markers + canon-lookup injected (no hardcoded worldview).
- `sanitize` / `regurgitation` — the pure text-defense primitives the verifier uses.
- `ports`  — duck-typed Protocols so a consumer passes its own domain objects.
"""

from .cites import (
    CiteProviderFn,
    GroundingCite,
    compose_cites,
    from_glossary_evidence,
    from_grounding_ref,
    from_l3_passage,
    merge_cites,
)
from .ports import FactLike, GroundingItemLike, GroundingReadPort, ProposalLike
from .regurgitation import RegurgitationResult, detect_regurgitation
from .sanitize import neutralize_proposal_text, scan_injection
from .verify import (
    ANACHRONISM_MARKERS,
    FENGSHEN_ANACHRONISM_MARKERS,
    CanonFact,
    CanonLookupFn,
    CanonVerifier,
    FlagKind,
    Severity,
    VerifyFlag,
    VerifyResult,
)

__all__ = [
    # cites
    "GroundingCite", "CiteProviderFn", "merge_cites", "compose_cites",
    "from_glossary_evidence", "from_l3_passage", "from_grounding_ref",
    # verify
    "CanonVerifier", "VerifyResult", "VerifyFlag", "FlagKind", "Severity",
    "CanonFact", "CanonLookupFn",
    "ANACHRONISM_MARKERS", "FENGSHEN_ANACHRONISM_MARKERS",
    # primitives
    "detect_regurgitation", "RegurgitationResult",
    "neutralize_proposal_text", "scan_injection",
    # ports
    "GroundingReadPort", "ProposalLike", "FactLike", "GroundingItemLike",
]
