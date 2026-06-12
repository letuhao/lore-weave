"""Composition reasoning — the domain scorer + its integration with the SDK
resolver. The generic resolver/capability/bucketer are tested in the SDK
(sdks/python/tests/test_reasoning.py); here we cover the creative-writing weights
and the end-to-end glue."""

from __future__ import annotations

from loreweave_llm import infer_reasoning_control, resolve_reasoning

from app.reasoning import ReasoningSignals, score_effort


# ── domain scorer (creative-writing weights) ──

def test_continue_is_none():
    assert score_effort(ReasoningSignals(operation="continue")) == "none"


def test_plain_draft_scene_is_medium():
    assert score_effort(ReasoningSignals(operation="draft_scene")) == "medium"


def test_canon_heavy_reveal_gate_high_tension_is_high():
    s = ReasoningSignals(operation="draft_scene", n_canon_rules=6, has_reveal_gate=True,
                         n_present_entities=5, tension=80)
    assert score_effort(s) == "high"


def test_author_guidance_markers_lift_a_light_op():
    assert score_effort(ReasoningSignals(operation="continue",
                                         guide="carefully foreshadow the betrayal")) != "none"


# ── integration: domain scorer feeding the SDK resolver ──

def test_auto_on_qwen3_effort_model_uses_scorer():
    control = infer_reasoning_control("lm_studio", "qwen/qwen3.6-35b-a3b")
    assert control == "effort"
    signals = ReasoningSignals(operation="draft_scene", n_canon_rules=6, has_reveal_gate=True, tension=85)
    d = resolve_reasoning(user_pref="auto", model_control=control,
                          auto_effort=score_effort(signals), auto_source="rule_based")
    assert d.effort == "high" and not d.passthrough and d.source == "rule_based"


def test_auto_on_anthropic_passes_through_ignoring_signals():
    control = infer_reasoning_control("anthropic", "claude-opus-4-8")
    d = resolve_reasoning(user_pref="auto", model_control=control,
                          auto_effort=score_effort(ReasoningSignals(operation="draft_scene")))
    # never out-think a self-orchestrating model
    assert d.passthrough is True and d.effort is None and d.source == "adaptive"


def test_user_override_beats_scorer():
    control = infer_reasoning_control("lm_studio", "qwen/qwen3.6-35b-a3b")
    d = resolve_reasoning(user_pref="off", model_control=control,
                          auto_effort=score_effort(ReasoningSignals(operation="draft_scene", n_canon_rules=9)))
    assert d.effort == "none" and d.source == "user"
