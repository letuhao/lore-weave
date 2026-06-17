"""M1b: V3 Corrector — rule-triggered targeted re-translation."""
import pytest

from app.workers.chunk_splitter import estimate_tokens
from app.workers.v3.corrector import (
    correct_high_severity_blocks, build_corrector_submit_kwargs,
    _CORRECTOR_OUT_FLOOR, _CORRECTOR_OUT_FACTOR, _TRANSLATION_MAX_OUTPUT_TOKENS,
)
from app.workers.v3.quality import Issue, IssueReport
from tests.test_session_translator import FakeLLMClient

_MSG = {"user_id": "u", "model_source": "platform_model", "model_ref": "m"}
_ISSUE = [Issue(0, "untranslated", "high", "leak")]


@pytest.mark.asyncio
async def test_corrector_retranslates_flagged_block():
    report = IssueReport([
        Issue(0, "wrong_name", "high", "'提拉米' should render as 'Tirami'", expected="Tirami"),
    ])
    fake = FakeLLMClient()
    fake.queue_translation(content="Tirami đã đến.")
    out = await correct_high_severity_blocks(
        {0}, {0: "提拉米来了。"}, {0: "Tirana đã đến."}, report,
        "zh", "vi", _MSG, "", llm_client=fake,
    )
    assert out == {0: "Tirami đã đến."}
    assert len(fake.calls) == 1


@pytest.mark.asyncio
async def test_corrector_best_effort_on_llm_failure():
    report = IssueReport([Issue(0, "untranslated", "high", "leak")])
    fake = FakeLLMClient()
    fake.queue_exception(RuntimeError("provider down"))
    out = await correct_high_severity_blocks(
        {0}, {0: "x"}, {0: "y"}, report, "zh", "vi", _MSG, "", llm_client=fake,
    )
    assert out == {}  # failure → no correction (the chapter keeps the original draft)


@pytest.mark.asyncio
async def test_corrector_only_acts_on_high_severity():
    # A med-only block must not be re-translated (no LLM call).
    report = IssueReport([Issue(0, "number_mismatch", "med", "num")])
    fake = FakeLLMClient()
    out = await correct_high_severity_blocks(
        {0}, {0: "x"}, {0: "y"}, report, "zh", "vi", _MSG, "", llm_client=fake,
    )
    assert out == {}
    assert len(fake.calls) == 0


# ── D-TRANSL-CORRECTOR-LIMITS: bounded output (max_tokens) ─────────────────────

def _kwargs(source_text: str) -> dict:
    return build_corrector_submit_kwargs(
        source_text, "draft", _ISSUE, "zh", "vi", "", block_idx=0,
    )


def test_corrector_max_tokens_present():
    assert "max_tokens" in _kwargs("提拉米来了。")["input"]


def test_corrector_max_tokens_floor_for_short_block():
    # A tiny source → the floor, never starved below it.
    assert _kwargs("短")["input"]["max_tokens"] == _CORRECTOR_OUT_FLOOR


def test_corrector_max_tokens_scales_with_source():
    # A mid-size block → scales with the source estimate (between floor and ceiling).
    src = "字" * 2000
    expected = estimate_tokens(src) * _CORRECTOR_OUT_FACTOR
    assert _CORRECTOR_OUT_FLOOR < expected < _TRANSLATION_MAX_OUTPUT_TOKENS
    assert _kwargs(src)["input"]["max_tokens"] == expected


def test_corrector_max_tokens_capped_at_global_ceiling():
    # A huge block can never exceed the translator's own output ceiling.
    assert _kwargs("字" * 40000)["input"]["max_tokens"] == _TRANSLATION_MAX_OUTPUT_TOKENS


def test_corrector_system_prompt_preserves_structure():
    msgs = _kwargs("提拉米来了。")["input"]["messages"]
    system = next(m["content"] for m in msgs if m["role"] == "system")
    assert "structure" in system.lower()
