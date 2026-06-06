"""K15.6 prompt-injection neutralizer — SHIM over `loreweave_grounding.sanitize`
(mui #3 K-adopt).

knowledge's original defense (KSA §5.1.5) was the NARROWER ancestor of the shared
SDK's. This shim delegates to `loreweave_grounding.sanitize` — gaining the
SDK's stronger detection (base64-decode scan, zero-width / full-width NFKC
pre-normalization, classical-Chinese 文言文 + Korean patterns, more role/template
shapes) as a security upgrade — while PRESERVING knowledge's public contract:

  * `neutralize_injection(text, *, project_id=None) -> (sanitized, hit_count)` —
    same signature + return shape every call site expects.
  * the per-pattern `knowledge_injection_pattern_matched_total{project_id,pattern}`
    metric (the pure SDK doesn't emit metrics) — driven off the SDK's
    `scan_injection` span names.
  * **clean text is returned UNCHANGED** (not NFKC-normalized). The SDK's
    `neutralize_proposal_text` returns the pre-normalized form even when clean,
    which would fold full-width punctuation in *stored* extracted text; knowledge
    returns the raw input on a clean scan (matching its prior behavior). Only the
    DETECTION strengthens, and only flagged text is returned in normalized+tagged
    form (correct — that's the whole point of de-obfuscating an evasion before
    tagging it).

Behavior change (accepted, PO 2026-06-07): evasions knowledge previously passed
as clean (full-width / zero-width / base64 / classical-Chinese) are now caught +
tagged; some Prometheus `pattern` labels are renamed/added to the SDK set.
"""

from __future__ import annotations

from collections import Counter as _Counter

from loreweave_grounding.sanitize import (  # the shared, stronger defense
    INJECTION_PATTERNS,
    neutralize_proposal_text,
    scan_injection,
)

from app.metrics import injection_pattern_matched_total

__all__ = [
    "INJECTION_PATTERNS",
    "neutralize_injection",
]


def neutralize_injection(
    text: str,
    *,
    project_id: str | None = None,
) -> tuple[str, int]:
    """Tag injection phrases in `text` with `[FICTIONAL] ` — `(sanitized, hits)`.

    Delegates to the shared SDK (stronger patterns + evasion pre-normalization)
    and keeps knowledge's metric + clean-text-unchanged contract. Idempotent
    (the SDK's lookbehind guard); empty/None → `("", 0)`.
    """
    if not text:
        return "", 0

    # Per-pattern observability (the SDK scan yields the pattern names, incl. the
    # new base64_injection / classical / role-template shapes). Bumped once per
    # match so overlapping-but-distinct hits each register, as before.
    label_project = project_id or "unknown"
    spans = scan_injection(text)
    for name, count in _Counter(name for name, _s, _e in spans).items():
        injection_pattern_matched_total.labels(
            project_id=label_project,
            pattern=name,
        ).inc(count)

    if not spans:
        # Clean text → return the RAW input unchanged (do NOT NFKC-normalize
        # stored extraction text; only flagged text is de-obfuscated + tagged).
        return text, 0

    return neutralize_proposal_text(text)
