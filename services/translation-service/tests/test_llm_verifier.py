"""M2: V3 LLM Verifier — Tier-2 semantic QA (JSON parse + best-effort call)."""
import pytest

from app.workers.v3.llm_verifier import parse_issues, llm_verify
from tests.test_session_translator import FakeLLMClient

_MSG = {"user_id": "u", "model_source": "platform_model", "model_ref": "m"}


# ── parse_issues (tolerant) ───────────────────────────────────────────────────

def test_parse_issues_valid_json():
    issues = parse_issues(
        '[{"block":0,"type":"omission","severity":"high","detail":"dropped"}]', {0})
    assert len(issues) == 1
    assert issues[0].type == "omission"
    assert issues[0].severity == "high"
    assert issues[0].detected_by == "llm"


def test_parse_issues_strips_code_fence():
    issues = parse_issues(
        '```json\n[{"block":1,"type":"wrong_name","severity":"med","detail":"x"}]\n```', {0, 1})
    assert len(issues) == 1 and issues[0].block_index == 1


def test_parse_issues_filters_invalid_block_and_coerces_type():
    issues = parse_issues(
        '[{"block":5,"type":"omission","severity":"high","detail":"x"},'
        ' {"block":0,"type":"bogus","severity":"med","detail":"y"}]', {0})
    assert len(issues) == 1
    assert issues[0].block_index == 0
    assert issues[0].type == "mistranslation"   # unknown type coerced


def test_parse_issues_malformed_returns_empty():
    assert parse_issues("not json at all", {0}) == []
    assert parse_issues("", {0}) == []
    assert parse_issues("[{bad json}]", {0}) == []


def test_parse_issues_empty_array():
    assert parse_issues("[]", {0}) == []


# ── llm_verify (best-effort) ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_llm_verify_returns_issues():
    fake = FakeLLMClient()
    fake.queue_translation(
        content='[{"block":0,"type":"omission","severity":"high","detail":"dropped a sentence"}]')
    issues = await llm_verify(
        {0: "源文"}, {0: "draft"}, "zh", "vi", ("platform_model", "m"), _MSG, llm_client=fake)
    assert len(issues) == 1 and issues[0].type == "omission"


@pytest.mark.asyncio
async def test_llm_verify_best_effort_on_failure():
    fake = FakeLLMClient()
    fake.queue_exception(RuntimeError("verifier down"))
    issues = await llm_verify(
        {0: "源文"}, {0: "draft"}, "zh", "vi", ("platform_model", "m"), _MSG, llm_client=fake)
    assert issues == []


@pytest.mark.asyncio
async def test_llm_verify_no_drafts_skips_call():
    fake = FakeLLMClient()
    issues = await llm_verify({}, {}, "zh", "vi", ("platform_model", "m"), _MSG, llm_client=fake)
    assert issues == []
    assert len(fake.calls) == 0


@pytest.mark.asyncio
async def test_llm_verify_injects_knowledge_brief(monkeypatch):
    fake = FakeLLMClient()
    fake.queue_translation(content="[]")
    await llm_verify(
        {0: "源"}, {0: "draft"}, "zh", "vi", ("platform_model", "m"), _MSG,
        llm_client=fake, knowledge_brief="CHARACTER CONTEXT: Tirami leads Paladins")
    user_msg = fake.calls[0]["input"]["messages"][1]["content"]
    assert "CHARACTER CONTEXT: Tirami leads Paladins" in user_msg


@pytest.mark.asyncio
async def test_llm_verify_no_brief_omits_preamble():
    fake = FakeLLMClient()
    fake.queue_translation(content="[]")
    await llm_verify({0: "源"}, {0: "draft"}, "zh", "vi", ("platform_model", "m"), _MSG,
                     llm_client=fake)
    user_msg = fake.calls[0]["input"]["messages"][1]["content"]
    assert user_msg.startswith("Review these blocks:")
