"""Provider Context Strategy P2 §5a — stateful chain decision (head-validity predicate)."""
import pytest

from app.services.stateful_chain import decide_chain

_CAPS = {"responses_api": True}
_ML = 200_000  # effective limit


def _row(**kw):
    base = {"response_id": "resp_1", "model_ref": "m1", "input_tokens": 1000, "sequence_num": 10}
    base.update(kw)
    return base


@pytest.fixture(autouse=True)
def _flag_on(monkeypatch):
    monkeypatch.setenv("LLM_STATEFUL_CACHE", "1")


def test_stateless_when_capability_absent(monkeypatch):
    assert decide_chain(capabilities={}, latest_assistant=_row(),
                        current_model_ref="m1", compacted_before_seq=None,
                        effective_limit=_ML) == (False, None)


def test_stateless_when_flag_off(monkeypatch):
    monkeypatch.setenv("LLM_STATEFUL_CACHE", "0")
    assert decide_chain(capabilities=_CAPS, latest_assistant=_row(),
                        current_model_ref="m1", compacted_before_seq=None,
                        effective_limit=_ML) == (False, None)


def test_first_turn_establishes():
    assert decide_chain(capabilities=_CAPS, latest_assistant=None,
                        current_model_ref="m1", compacted_before_seq=None,
                        effective_limit=_ML) == (True, None)


def test_continue_from_valid_head():
    assert decide_chain(capabilities=_CAPS, latest_assistant=_row(),
                        current_model_ref="m1", compacted_before_seq=None,
                        effective_limit=_ML) == (True, "resp_1")


def test_rule1_intervening_stateless_turn_reestablishes():
    # the latest assistant turn was stateless (null response_id) → the provider chain
    # doesn't contain it → establish (not continue from some older head).
    assert decide_chain(capabilities=_CAPS, latest_assistant=_row(response_id=None),
                        current_model_ref="m1", compacted_before_seq=None,
                        effective_limit=_ML) == (True, None)


def test_rule2_model_switch_reestablishes():
    assert decide_chain(capabilities=_CAPS, latest_assistant=_row(model_ref="m1"),
                        current_model_ref="m2", compacted_before_seq=None,
                        effective_limit=_ML) == (True, None)


def test_rule3_compaction_past_head_reestablishes():
    # compacted_before_seq advanced PAST the head turn (compact-everything) → re-establish
    assert decide_chain(capabilities=_CAPS, latest_assistant=_row(sequence_num=10),
                        current_model_ref="m1", compacted_before_seq=20,
                        effective_limit=_ML) == (True, None)
    # a compaction boundary BELOW the head leaves the chain valid
    assert decide_chain(capabilities=_CAPS, latest_assistant=_row(sequence_num=10),
                        current_model_ref="m1", compacted_before_seq=5,
                        effective_limit=_ML) == (True, "resp_1")


def test_rule4_near_window_reestablishes():
    # head turn's accumulated input_tokens over the compaction trigger → re-establish
    assert decide_chain(capabilities=_CAPS,
                        latest_assistant=_row(input_tokens=190_000),
                        current_model_ref="m1", compacted_before_seq=None,
                        effective_limit=_ML) == (True, None)
