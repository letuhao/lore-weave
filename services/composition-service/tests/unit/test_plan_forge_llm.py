"""Unit tests for PlanForge BYOK LLM adapter + async worker path."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.engine.plan_forge.llm import ProviderPlanForgeLLM
from app.engine.plan_forge.propose_llm_async import propose_spec_llm_async, refine_spec_async
from app.worker.constants import SUPPORTED_OPERATIONS
from app.worker.operations import run_plan_forge_propose, run_plan_forge_refine

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "plan-forge"
MOCK_ANALYZE = json.loads((FIXTURES / "llm_mock_analyze.json").read_text(encoding="utf-8"))
MOCK_SPEC = json.loads((FIXTURES / "llm_mock_spec.json").read_text(encoding="utf-8"))
SOURCE = (FIXTURES / "story-plan-v1.md").read_text(encoding="utf-8")


class _MockLLMClient:
  def __init__(self, responses: list[str]) -> None:
    self._responses = list(responses)
    self.calls: list[dict] = []

  async def submit_and_wait(self, **kwargs):
    self.calls.append(kwargs)
    content = self._responses.pop(0)
    return SimpleNamespace(status="completed", result={"messages": [{"role": "assistant", "content": content}]})


@pytest.mark.asyncio
async def test_provider_plan_forge_llm_chat():
    client = ProviderPlanForgeLLM(
        _MockLLMClient([json.dumps({"version": 1})]),
        user_id="user-1",
        model_source="byok",
        model_ref="model-uuid",
    )
    out = await client.chat(step="analyze", system="sys", user="usr")
    assert "version" in out
    assert client.io_log[0]["step"] == "analyze"


@pytest.mark.asyncio
async def test_propose_spec_llm_async_mock():
    llm = _MockLLMClient([json.dumps(MOCK_ANALYZE), json.dumps(MOCK_SPEC)])
    pf = ProviderPlanForgeLLM(llm, user_id="u", model_source="byok", model_ref="m")
    spec, analyze, io = await propose_spec_llm_async(SOURCE[:8000], pf)
    assert analyze["version"] == 1
    assert spec["version"] == 1
    assert len(io) == 2


@pytest.mark.asyncio
async def test_refine_spec_async_focus_paths_smaller_prompt():
    llm = _MockLLMClient([json.dumps(MOCK_SPEC)])
    pf = ProviderPlanForgeLLM(llm, user_id="u", model_source="byok", model_ref="m")
    big_spec = json.loads(json.dumps(MOCK_SPEC))
    revision = {
        "version": 1,
        "target": "spec",
        "instruction": "fix event 3",
        "scope": ["events"],
        "frozen_paths": ["variables"],
        "focus_paths": ["events[0]"],
    }
    await refine_spec_async(big_spec, revision, client=pf, source_checksum="abc")
    user_msg = llm.calls[0]["input"]["messages"][1]["content"]
    assert len(user_msg) < len(json.dumps(big_spec)) + 500


@pytest.mark.asyncio
async def test_run_plan_forge_propose_worker():
    llm = _MockLLMClient([json.dumps(MOCK_ANALYZE), json.dumps(MOCK_SPEC)])
    result = await run_plan_forge_propose(
        llm,  # type: ignore[arg-type]
        user_id="u",
        input={"source_markdown": SOURCE[:5000], "model_ref": "m", "model_source": "byok"},
    )
    assert result["status"] == "completed"
    assert result["novel_system_spec"]["version"] == 1


@pytest.mark.asyncio
async def test_run_plan_forge_propose_requires_model_ref():
    with pytest.raises(ValueError, match="model_ref"):
        await run_plan_forge_propose(_MockLLMClient([]), user_id="u", input={"source_markdown": "x"})  # type: ignore[arg-type]


def test_plan_forge_worker_ops_registered():
    assert "plan_forge_propose" in SUPPORTED_OPERATIONS
    assert "plan_forge_refine" in SUPPORTED_OPERATIONS
