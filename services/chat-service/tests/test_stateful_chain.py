"""Provider Context Strategy P2 §5a — stateful chain decision (head-validity predicate)."""
import pytest

from app.services.stateful_chain import decide_chain

_CAPS = {"responses_api": True}
_ML = 200_000  # effective limit


def _row(**kw):
    base = {"response_id": "resp_1", "model_ref": "m1", "input_tokens": 1000,
            "sequence_num": 10, "context_size": 1000}
    base.update(kw)
    return base


@pytest.fixture(autouse=True)
def _flag_on(monkeypatch):
    monkeypatch.setenv("LLM_STATEFUL_CACHE", "1")


def test_stateless_when_capability_absent(monkeypatch):
    assert decide_chain(capabilities={}, latest_assistant=_row(),
                        current_model_ref="m1", compacted_before_seq=None,
                        effective_limit=_ML) == (False, None, "stateless")


def test_stateless_when_flag_off(monkeypatch):
    monkeypatch.setenv("LLM_STATEFUL_CACHE", "0")
    assert decide_chain(capabilities=_CAPS, latest_assistant=_row(),
                        current_model_ref="m1", compacted_before_seq=None,
                        effective_limit=_ML) == (False, None, "stateless")


def test_first_turn_establishes():
    assert decide_chain(capabilities=_CAPS, latest_assistant=None,
                        current_model_ref="m1", compacted_before_seq=None,
                        effective_limit=_ML) == (True, None, "establish_first")


def test_continue_from_valid_head():
    assert decide_chain(capabilities=_CAPS, latest_assistant=_row(),
                        current_model_ref="m1", compacted_before_seq=None,
                        effective_limit=_ML) == (True, "resp_1", "continue")


def test_rule1_intervening_stateless_turn_reestablishes():
    # the latest assistant turn was stateless (null response_id) → the provider chain
    # doesn't contain it → establish (not continue from some older head).
    assert decide_chain(capabilities=_CAPS, latest_assistant=_row(response_id=None),
                        current_model_ref="m1", compacted_before_seq=None,
                        effective_limit=_ML) == (True, None, "reestablish_stateless_prev")


def test_rule2_model_switch_reestablishes():
    assert decide_chain(capabilities=_CAPS, latest_assistant=_row(model_ref="m1"),
                        current_model_ref="m2", compacted_before_seq=None,
                        effective_limit=_ML) == (True, None, "reestablish_model_switch")


def test_rule3_compaction_past_head_reestablishes():
    # compacted_before_seq advanced PAST the head turn (compact-everything) → re-establish
    assert decide_chain(capabilities=_CAPS, latest_assistant=_row(sequence_num=10),
                        current_model_ref="m1", compacted_before_seq=20,
                        effective_limit=_ML) == (True, None, "reestablish_compaction")
    # a compaction boundary BELOW the head leaves the chain valid
    assert decide_chain(capabilities=_CAPS, latest_assistant=_row(sequence_num=10),
                        current_model_ref="m1", compacted_before_seq=5,
                        effective_limit=_ML) == (True, "resp_1", "continue")


def test_rule4_near_window_reestablishes():
    # head turn's accumulated context_size over the compaction trigger → re-establish
    assert decide_chain(capabilities=_CAPS,
                        latest_assistant=_row(context_size=190_000),
                        current_model_ref="m1", compacted_before_seq=None,
                        effective_limit=_ML) == (True, None, "reestablish_window")


def test_rule4_uses_context_size_not_summed_input(monkeypatch):
    # P3 R1: a tool-heavy turn's input_tokens SUMS the loop (e.g. 4×48K=192K) but the
    # true single-call context_size is 48K — well under the window. rule-4 must use the
    # true size and CONTINUE (not re-establish on the inflated sum).
    assert decide_chain(capabilities=_CAPS,
                        latest_assistant=_row(input_tokens=192_000, context_size=48_000),
                        current_model_ref="m1", compacted_before_seq=None,
                        effective_limit=_ML) == (True, "resp_1", "continue")


def test_rule4_falls_back_to_input_tokens_when_no_context_size():
    # pre-P3 rows have no context_size → fall back to input_tokens (safe, conservative)
    row = _row(context_size=None, input_tokens=190_000)
    assert decide_chain(capabilities=_CAPS, latest_assistant=row,
                        current_model_ref="m1", compacted_before_seq=None,
                        effective_limit=_ML) == (True, None, "reestablish_window")


def test_rule4_deploy_cap_reestablishes_below_window(monkeypatch):
    # P3: LLM_STATEFUL_MAX_CHAIN_TOKENS bounds the chain below the model window (a
    # provider may load a smaller n_ctx than context_length advertises).
    monkeypatch.setenv("LLM_STATEFUL_MAX_CHAIN_TOKENS", "45000")
    # 48K > 45K cap → re-establish, even though 48K << 0.75×200K window
    assert decide_chain(capabilities=_CAPS, latest_assistant=_row(context_size=48_000),
                        current_model_ref="m1", compacted_before_seq=None,
                        effective_limit=_ML) == (True, None, "reestablish_window")
    # 40K < 45K cap AND < window → continue
    assert decide_chain(capabilities=_CAPS, latest_assistant=_row(context_size=40_000),
                        current_model_ref="m1", compacted_before_seq=None,
                        effective_limit=_ML) == (True, "resp_1", "continue")
