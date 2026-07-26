"""Tests for the reusable reasoning policy primitives (loreweave_llm.reasoning)."""

from loreweave_llm import (
    bucket_effort,
    infer_reasoning_control,
    reasoning_fields,
    resolve_reasoning,
)


# ── capability inference ──

def test_anthropic_and_gemini_are_adaptive():
    assert infer_reasoning_control("anthropic", "claude-opus-4-8") == "adaptive"
    assert infer_reasoning_control("google", "gemini-2.5-pro") == "adaptive"


def test_effort_models():
    assert infer_reasoning_control("lm_studio", "qwen/qwen3.6-35b-a3b") == "effort"
    assert infer_reasoning_control("lm_studio", "deepseek-r1-distill-qwen-32b") == "effort"
    assert infer_reasoning_control("openai", "gpt-5") == "effort"


def test_non_reasoning_and_override():
    assert infer_reasoning_control("openai", "gpt-4o") == "none"
    assert infer_reasoning_control("lm_studio", "qwen2.5-coder-7b") == "none"
    assert infer_reasoning_control(None, None) == "none"
    # explicit registry override wins
    assert infer_reasoning_control("lm_studio", "qwen3.6-35b", {"reasoning_control": "none"}) == "none"


# ── bucketer ──

def test_bucket_effort_thresholds():
    assert bucket_effort(0) == "none"
    assert bucket_effort(1) == "low"
    assert bucket_effort(3) == "medium"
    assert bucket_effort(4) == "high"
    assert bucket_effort(10) == "high"
    # custom thresholds
    assert bucket_effort(2, high=5, medium=3, low=1) == "low"


# ── resolver ──

def test_user_override_beats_auto():
    for control in ("adaptive", "effort", "none"):
        d = resolve_reasoning(user_pref="high", model_control=control, auto_effort="low")  # type: ignore[arg-type]
        assert d.effort == "high" and not d.passthrough and d.source == "user"
    off = resolve_reasoning(user_pref="off", model_control="effort", auto_effort="high")
    assert off.effort == "none" and off.source == "user"


def test_auto_adaptive_passes_through():
    d = resolve_reasoning(user_pref="auto", model_control="adaptive", auto_effort="high")
    assert d.passthrough is True and d.effort is None and d.source == "adaptive"


def test_auto_effort_uses_caller_effort_and_source():
    d = resolve_reasoning(user_pref="auto", model_control="effort", auto_effort="high", auto_source="rule_based")
    assert d.passthrough is False and d.effort == "high" and d.source == "rule_based"


def test_auto_non_reasoning_is_noop():
    d = resolve_reasoning(user_pref="auto", model_control="none", auto_effort="high")
    assert d.effort is None and d.passthrough is False and d.source == "non_reasoning"


# ── reasoning_fields (directive → provider wire fields) ──

def test_reasoning_fields_passthrough_and_noop_omit():
    # adaptive (Anthropic self-decides) → omit; never send reasoning_effort.
    adaptive = resolve_reasoning(user_pref="auto", model_control="adaptive")
    assert reasoning_fields(adaptive) == {}
    # non-reasoning model → omit.
    none = resolve_reasoning(user_pref="auto", model_control="none")
    assert reasoning_fields(none) == {}


def test_reasoning_fields_effort_emits_knobs():
    d = resolve_reasoning(user_pref="high", model_control="effort")
    f = reasoning_fields(d)
    assert f["reasoning_effort"] == "high"
    assert f["chat_template_kwargs"] == {"thinking": True, "enable_thinking": True}


def test_reasoning_fields_off_disables_thinking():
    # An explicit "off" is a real directive (effort="none"): SEND it so a reasoning
    # model's hidden thinking is turned OFF (not omitted).
    d = resolve_reasoning(user_pref="off", model_control="effort")
    f = reasoning_fields(d)
    assert f["reasoning_effort"] == "none"
    assert f["chat_template_kwargs"] == {"thinking": False, "enable_thinking": False}
