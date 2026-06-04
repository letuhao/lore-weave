"""Unit tests for the capability-aware reasoning resolver (pure foundation)."""

from __future__ import annotations

from app.reasoning import (
    ReasoningSignals,
    infer_reasoning_control,
    resolve_reasoning,
    score_effort,
)


# ── capability inference ──

def test_anthropic_is_adaptive():
    assert infer_reasoning_control("anthropic", "claude-opus-4-8") == "adaptive"


def test_gemini_25_is_adaptive():
    assert infer_reasoning_control("google", "gemini-2.5-pro") == "adaptive"


def test_qwen3_local_is_effort():
    assert infer_reasoning_control("lm_studio", "qwen/qwen3.6-35b-a3b") == "effort"


def test_deepseek_r1_is_effort():
    assert infer_reasoning_control("lm_studio", "deepseek-r1-distill-qwen-32b") == "effort"


def test_openai_gpt5_is_effort():
    assert infer_reasoning_control("openai", "gpt-5") == "effort"


def test_plain_model_is_none():
    assert infer_reasoning_control("lm_studio", "qwen2.5-coder-7b-instruct") == "none"
    assert infer_reasoning_control("openai", "gpt-4o") == "none"


def test_explicit_capability_flag_overrides_heuristic():
    # registry/operator override beats the name heuristic
    assert infer_reasoning_control("lm_studio", "qwen3.6-35b", {"reasoning_control": "none"}) == "none"
    assert infer_reasoning_control("openai", "gpt-4o", {"reasoning_control": "effort"}) == "effort"


def test_unknown_provider_is_none():
    assert infer_reasoning_control(None, None) == "none"


# ── rule-based scorer ──

def test_continue_is_low_or_none():
    assert score_effort(ReasoningSignals(operation="continue")) == "none"


def test_canon_heavy_reveal_gate_scene_is_high():
    s = ReasoningSignals(operation="draft_scene", n_canon_rules=6, has_reveal_gate=True,
                         n_present_entities=5, tension=80)
    assert score_effort(s) == "high"


def test_plain_draft_scene_is_medium():
    assert score_effort(ReasoningSignals(operation="draft_scene")) == "medium"


def test_guidance_markers_bump_effort():
    light = ReasoningSignals(operation="continue")
    asked = ReasoningSignals(operation="continue", guide="carefully foreshadow the betrayal")
    assert score_effort(asked) != "none"
    assert score_effort(light) == "none"


# ── resolver ──

_SIG = ReasoningSignals(operation="draft_scene", n_canon_rules=6, has_reveal_gate=True, tension=85)


def test_user_override_beats_auto_everywhere():
    for control in ("adaptive", "effort", "none"):
        d = resolve_reasoning(user_pref="high", model_control=control, signals=_SIG)  # type: ignore[arg-type]
        assert d.effort == "high" and not d.passthrough and d.source == "user"


def test_off_forces_none():
    d = resolve_reasoning(user_pref="off", model_control="effort", signals=_SIG)
    assert d.effort == "none" and d.source == "user"


def test_auto_adaptive_passes_through():
    d = resolve_reasoning(user_pref="auto", model_control="adaptive", signals=_SIG)
    # never out-think a self-orchestrating model
    assert d.passthrough is True and d.effort is None and d.source == "adaptive"


def test_auto_effort_runs_the_scorer():
    d = resolve_reasoning(user_pref="auto", model_control="effort", signals=_SIG)
    assert d.passthrough is False and d.effort == "high" and d.source == "rule_based"


def test_auto_non_reasoning_is_noop():
    d = resolve_reasoning(user_pref="auto", model_control="none", signals=_SIG)
    assert d.effort is None and d.passthrough is False and d.source == "non_reasoning"


def test_llm_judge_falls_back_to_rule_based_v0():
    d = resolve_reasoning(user_pref="auto", model_control="effort", signals=_SIG, engine="llm_judge")
    assert d.effort == "high" and d.source == "rule_based"
