"""M1b: V3 Corrector — rule-triggered targeted re-translation."""
import pytest

from app.workers.v3.corrector import correct_high_severity_blocks
from app.workers.v3.quality import Issue, IssueReport
from tests.test_session_translator import FakeLLMClient

_MSG = {"user_id": "u", "model_source": "platform_model", "model_ref": "m"}


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
