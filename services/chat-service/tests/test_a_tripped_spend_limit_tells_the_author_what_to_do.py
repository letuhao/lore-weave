"""A failure the author can act on must say so, and say where.

🔴 THE ORIGINAL INSTANCE. When the spend guardrail trips, provider-registry returns
402 with operator prose:

    insufficient budget: estimated $0.11920000, available daily $0.00000000 / monthly $0.00000000

That string reached the author verbatim (it trips no _UNSAFE_ERROR_MARKERS), under a
RUN_ERROR code hardcoded to "STREAM_ERROR". So the author saw eight decimal places of
dollars, no indication the limit is THEIR OWN configurable setting rather than a
platform cap, and no place to change it — and the FE could not tell it apart from an
upstream 500, because every failure carried the same code.

🔴 AND THE CODE WAS OVERLOADED. provider-registry returned LLM_QUOTA_EXCEEDED for
"model pricing not configured" too — the opposite problem with the opposite fix. Any
author-facing message keyed on that code was guaranteed wrong for one of the two, so
splitting it (LLM_MODEL_UNPRICED) is load-bearing for this test, not a tidy-up.
"""

from app.services.stream_service import _author_facing_error, _GENERIC_ERROR_TEXT
from app.services.stream_events import AgUiEmitter
import json


class _Exc(Exception):
    def __init__(self, message, code):
        super().__init__(message)
        self.code = code


GATEWAY_BUDGET_PROSE = (
    "insufficient budget: estimated $0.11920000, "
    "available daily $0.00000000 / monthly $0.00000000"
)


def test_a_tripped_spend_limit_names_the_users_own_setting():
    msg, code = _author_facing_error(_Exc(GATEWAY_BUDGET_PROSE, "LLM_QUOTA_EXCEEDED"))
    assert code == "LLM_QUOTA_EXCEEDED"
    assert "$0.11920000" not in msg, (
        "the raw gateway estimate reached the author — eight decimal places of dollars "
        "is operator prose, not an explanation"
    )
    low = msg.lower()
    assert "your" in low, "the author is not told the limit is their own setting"
    assert "usage" in low, "the author is not told WHERE to change it"
    assert "charged" in low or "nothing was sent" in low, (
        "a pre-flight refusal spends nothing; not saying so invites the author to "
        "assume they were billed for the failed turn"
    )


def test_an_unpriced_model_does_not_claim_the_user_overspent():
    msg, code = _author_facing_error(_Exc("model pricing not configured", "LLM_MODEL_UNPRICED"))
    assert code == "LLM_MODEL_UNPRICED"
    low = msg.lower()
    assert "spend limit" not in low and "daily" not in low, (
        "an unpriced model was reported as a spend-limit trip — opposite cause, "
        "opposite fix. This is what the shared LLM_QUOTA_EXCEEDED code produced."
    )
    assert "pricing" in low


def test_an_unrecognised_failure_keeps_the_previous_behaviour():
    # No regression for the cases we do not understand: same sanitized text as before.
    msg, code = _author_facing_error(_Exc("upstream exploded", "LLM_UPSTREAM_ERROR"))
    assert msg == "upstream exploded"
    assert code == "LLM_UPSTREAM_ERROR"
    # …and a leaky message is still replaced, not passed through.
    leaky, _ = _author_facing_error(_Exc("Traceback (most recent call last)", ""))
    assert leaky == _GENERIC_ERROR_TEXT


def test_the_run_error_frame_carries_the_real_code_not_a_constant():
    lines = AgUiEmitter(thread_id="t", message_id="m").error("nope", "LLM_QUOTA_EXCEEDED")
    payload = json.loads("".join(lines).removeprefix("data: ").strip())
    assert payload["type"] == "RUN_ERROR"
    assert payload["code"] == "LLM_QUOTA_EXCEEDED", (
        "RUN_ERROR.code was the literal 'STREAM_ERROR' for every failure, so the FE "
        "could not distinguish an actionable spend cap from an upstream crash"
    )
    # The default must stay STREAM_ERROR so existing callers are unchanged.
    default = json.loads("".join(
        AgUiEmitter(thread_id="t", message_id="m").error("nope")
    ).removeprefix("data: ").strip())
    assert default["code"] == "STREAM_ERROR"
