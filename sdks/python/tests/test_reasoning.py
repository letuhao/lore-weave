"""Tests for the reusable reasoning policy primitives (loreweave_llm.reasoning)."""

from loreweave_llm import (
    bucket_effort,
    directive_from_parts,
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
    assert infer_reasoning_control(None, None) == "none"
    # explicit registry override wins
    assert infer_reasoning_control("lm_studio", "qwen3.6-35b", {"reasoning_control": "none"}) == "none"


def test_unclassified_local_model_suppresses_rather_than_guessing():
    """The empty-draft regression. A local model whose NAME matches no reasoning pattern is
    unknown, not proven-non-reasoning — and gemma-4-26b-a4b-qat really does think. Sending
    nothing let its chat template decide, which burned the whole output budget on hidden
    reasoning and returned empty prose. Unknown-on-a-local-endpoint now fails SAFE."""
    assert infer_reasoning_control("lm_studio", "gemma-4-26b-a4b-qat") == "suppress"
    assert infer_reasoning_control("lm_studio", "qwen2.5-coder-7b") == "suppress"
    assert infer_reasoning_control("ollama", "some-model-we-have-never-seen") == "suppress"
    # ...and suppression must reach the wire as a real OFF, not an omission.
    d = resolve_reasoning(user_pref="auto", model_control="suppress")
    assert d.effort == "none" and d.passthrough is False
    assert d.source == "suppress_unclassified"  # the DECISION is visible in telemetry
    assert reasoning_fields(d) == {
        "reasoning_effort": "none",
        "chat_template_kwargs": {"thinking": False, "enable_thinking": False},
    }


def test_suppress_never_reaches_a_cloud_model():
    """Suppression is only safe where the endpoint accepts the knobs. Real OpenAI 400s on
    `reasoning_effort` for gpt-*, so a non-local unknown must stay "none"."""
    for kind, name in (("openai", "gpt-4o"), ("google", "gemini-1.5-pro"), ("cohere", "command-r")):
        assert infer_reasoning_control(kind, name) != "suppress"


def test_registry_override_can_restore_thinking_on_a_suppressed_model():
    """`capability_flags.reasoning_control` — not a wider name regex — is the supported way to
    correct a model this heuristic guesses wrong about."""
    assert infer_reasoning_control(
        "lm_studio", "gemma-4-26b-a4b-qat", {"reasoning_control": "effort"}) == "effort"


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
    for control in ("adaptive", "effort", "suppress", "none"):
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


# ── directive_from_parts (the persistence boundary) ──

def test_directive_round_trips_through_serialized_parts():
    """A queued job stores the directive as three flat columns. Rebuilding it must be one
    function, not a hand-rolled collapse re-invented at each read site."""
    for control in ("adaptive", "effort", "suppress", "none"):
        original = resolve_reasoning(user_pref="auto", model_control=control, auto_effort="medium")  # type: ignore[arg-type]
        rebuilt = directive_from_parts(
            source=original.source, effort=original.effort, passthrough=original.passthrough)
        assert rebuilt == original
        assert reasoning_fields(rebuilt) == reasoning_fields(original)


def test_directive_from_parts_tolerates_a_job_enqueued_before_this_existed():
    """In-flight work must drain unchanged: an older job carries a null effort and no
    passthrough flag, and has to rebuild to the same no-op it would have had."""
    d = directive_from_parts(source=None, effort=None, passthrough=None)
    assert d.effort is None and d.passthrough is False
    assert reasoning_fields(d) == {}


def test_directive_from_parts_rejects_a_non_wire_effort_value():
    """The session vocabulary (off|auto) is NOT wire vocabulary (none|low|medium|high). A
    stray "off"/"auto" must not become a wire value — it degrades to omit, never crashes."""
    for bad in ("off", "auto", "", "HIGH", "maximum"):
        assert directive_from_parts(source="x", effort=bad, passthrough=False).effort is None


def test_reasoning_fields_off_disables_thinking():
    # An explicit "off" is a real directive (effort="none"): SEND it so a reasoning
    # model's hidden thinking is turned OFF (not omitted).
    d = resolve_reasoning(user_pref="off", model_control="effort")
    f = reasoning_fields(d)
    assert f["reasoning_effort"] == "none"
    assert f["chat_template_kwargs"] == {"thinking": False, "enable_thinking": False}
