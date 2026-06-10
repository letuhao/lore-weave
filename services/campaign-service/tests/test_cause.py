"""G1 — error-cause normalizer (the report's error-grouping + remediation logic)."""

import pytest

from app.cause import (
    normalize_error_cause,
    RATE_LIMIT, CIRCUIT_OPEN, EMPTY_BODY, ZERO_OUTPUT, ATTEMPTS_EXHAUSTED, OTHER,
)


@pytest.mark.parametrize("msg,cause,remediable", [
    ("HTTP 429 Too Many Requests", RATE_LIMIT, True),
    ("provider rate-limit at 02:00", RATE_LIMIT, True),
    ("LLM_CIRCUIT_OPEN", CIRCUIT_OPEN, True),
    ("breaker open for lm_studio", CIRCUIT_OPEN, True),
    ("empty body — nothing to translate", EMPTY_BODY, False),
    ("body rỗng", EMPTY_BODY, False),
    ("model returned zero output", ZERO_OUTPUT, True),
    ("empty content from model", ZERO_OUTPUT, True),
    ("attempts exhausted", ATTEMPTS_EXHAUSTED, True),
    ("stuck-reconcile: translation job gone", ATTEMPTS_EXHAUSTED, True),
    ("some unrecognized boom", OTHER, False),
])
def test_buckets(msg, cause, remediable):
    assert normalize_error_cause(msg) == (cause, remediable)


@pytest.mark.parametrize("empty", [None, "", "   "])
def test_empty_is_other_nonremediable(empty):
    assert normalize_error_cause(empty) == (OTHER, False)


def test_precedence_rate_limit_before_generic():
    # a compound message mentioning 429 buckets as rate_limit (most actionable first)
    assert normalize_error_cause("429 after retry attempts")[0] == RATE_LIMIT
