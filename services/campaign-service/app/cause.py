"""G1 — normalize a chapter's `last_error` into a stable cause bucket for the
completion report's error grouping + remediation hint.

Pure (no I/O), exhaustively unit-tested — the bucketing is the load-bearing logic
the report's "re-run will fix N, skip M" guidance rests on. `remediable=True` means
a re-run is LIKELY to succeed (transient: rate-limit, breaker, model hiccup,
attempt-exhaustion); `False` means a source/data issue a re-run won't fix.
"""

from __future__ import annotations

# Cause labels (stable; the FE maps these to copy).
RATE_LIMIT = "rate_limit"
CIRCUIT_OPEN = "circuit_open"
EMPTY_BODY = "empty_body"
ZERO_OUTPUT = "zero_output"
ATTEMPTS_EXHAUSTED = "attempts_exhausted"
OTHER = "other"

# Each entry: (label, remediable, substrings-that-match). Checked in order — most
# specific / most-actionable first so a compound message buckets by its root cause.
_RULES: list[tuple[str, bool, tuple[str, ...]]] = [
    (RATE_LIMIT, True, ("429", "rate limit", "rate-limit", "ratelimit", "too many requests")),
    (CIRCUIT_OPEN, True, ("circuit", "llm_circuit_open", "breaker")),
    (EMPTY_BODY, False, ("empty body", "body rỗng", "body empty", "no content", "empty chapter", "blank")),
    (ZERO_OUTPUT, True, ("0-output", "zero output", "zero-output", "empty content", "empty output", "no output")),
    (ATTEMPTS_EXHAUSTED, True, ("attempts exhausted", "stuck-reconcile", "retry")),
]


def normalize_error_cause(last_error: str | None) -> tuple[str, bool]:
    """Return (cause_label, remediable). Empty/None → ('other', False)."""
    if not last_error or not last_error.strip():
        return (OTHER, False)
    e = last_error.lower()
    for label, remediable, needles in _RULES:
        if any(n in e for n in needles):
            return (label, remediable)
    return (OTHER, False)
