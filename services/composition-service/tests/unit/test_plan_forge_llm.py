"""Unit tests for PlanForge BYOK LLM adapter + async worker path."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.engine.plan_forge.llm import PlanForgeLLMError, ProviderPlanForgeLLM
from app.engine.plan_forge.propose_llm_async import propose_spec_llm_async, refine_spec_async
from app.engine.plan_forge.refine import merge_refine_output
from app.worker.constants import SUPPORTED_OPERATIONS
from app.worker.job_consumer import _BUSINESS_ERRORS
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
        if not self._responses:
            raise PlanForgeLLMError("no mock response")
        content = self._responses.pop(0)
        return SimpleNamespace(status="completed", result={"messages": [{"role": "assistant", "content": content}]})


@pytest.mark.asyncio
async def test_provider_plan_forge_llm_chat():
    llm = _MockLLMClient([json.dumps({"version": 1})])
    client = ProviderPlanForgeLLM(
        llm,  # type: ignore[arg-type]
        user_id="user-1",
        model_source="user_model",
        model_ref="model-uuid",
    )
    out = await client.chat(step="analyze", system="sys", user="usr")
    assert "version" in out
    assert client.io_log[0]["step"] == "analyze"
    assert llm.calls[0]["model_source"] == "user_model"


@pytest.mark.asyncio
async def test_propose_spec_llm_async_mock():
    llm = _MockLLMClient([json.dumps(MOCK_ANALYZE), json.dumps(MOCK_SPEC)])
    pf = ProviderPlanForgeLLM(llm, user_id="u", model_source="user_model", model_ref="m")
    spec, analyze, io = await propose_spec_llm_async(SOURCE[:8000], pf)
    assert analyze["version"] == 1
    assert spec["version"] == 1
    assert len(io) == 2


@pytest.mark.asyncio
async def test_refine_spec_async_focus_paths_merges_event():
    before = json.loads(json.dumps(MOCK_SPEC))
    patched_event = json.loads(json.dumps(before["events"][0]))
    patched_event["title"] = "Event 3 — Thử Nghiệm (patched)"
    slice_patch = {"events[ev_2_1]": patched_event}
    llm = _MockLLMClient([json.dumps(slice_patch)])
    pf = ProviderPlanForgeLLM(llm, user_id="u", model_source="user_model", model_ref="m")
    revision = {
        "version": 1,
        "target": "spec",
        "instruction": "fix event 3",
        "scope": ["events"],
        "frozen_paths": ["variables"],
        "focus_paths": ["events[ev_2_1]"],
    }
    after = await refine_spec_async(before, revision, client=pf, source_checksum="abc")
    assert after["events"][0]["title"] == "Event 3 — Thử Nghiệm (patched)"
    assert len(after["events"]) == len(before["events"])
    assert after["arcs"] == before["arcs"]


def test_merge_refine_output_preserves_full_spec_on_slice_patch():
    before = json.loads(json.dumps(MOCK_SPEC))
    patch = {"events[ev_2_1]": {**before["events"][0], "synopsis": "updated synopsis"}}
    revision = {"focus_paths": ["events[ev_2_1]"]}
    merged = merge_refine_output(before, patch, revision)
    assert merged["events"][0]["synopsis"] == "updated synopsis"
    assert merged["layers"] == before["layers"]


@pytest.mark.asyncio
async def test_run_plan_forge_propose_worker():
    llm = _MockLLMClient([json.dumps(MOCK_ANALYZE), json.dumps(MOCK_SPEC)])
    result = await run_plan_forge_propose(
        llm,  # type: ignore[arg-type]
        user_id="u",
        input={"source_markdown": SOURCE[:5000], "model_ref": "m", "model_source": "user_model"},
    )
    assert result["status"] == "completed"
    assert result["novel_system_spec"]["version"] == 1


@pytest.mark.asyncio
async def test_run_plan_forge_propose_llm_error_raises():
    llm = _MockLLMClient([])
    with pytest.raises(PlanForgeLLMError):
        await run_plan_forge_propose(
            llm,  # type: ignore[arg-type]
            user_id="u",
            input={"source_markdown": "x", "model_ref": "m"},
        )


@pytest.mark.asyncio
async def test_run_plan_forge_propose_requires_model_ref():
    with pytest.raises(ValueError, match="model_ref"):
        await run_plan_forge_propose(_MockLLMClient([]), user_id="u", input={"source_markdown": "x"})  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_run_plan_forge_refine_worker():
    llm = _MockLLMClient([json.dumps(MOCK_SPEC)])
    before = json.loads(json.dumps(MOCK_SPEC))
    result = await run_plan_forge_refine(
        llm,  # type: ignore[arg-type]
        user_id="u",
        input={
            "spec": before,
            "revision": {
                "version": 1,
                "instruction": "noop",
                "scope": ["meta"],
                "frozen_paths": ["variables"],
            },
            "model_ref": "m",
            "source_checksum": "abc",
        },
    )
    assert "accepted" in result
    assert result["spec"]["version"] == 1


def test_plan_forge_worker_ops_registered():
    assert "plan_forge_propose" in SUPPORTED_OPERATIONS
    assert "plan_forge_refine" in SUPPORTED_OPERATIONS


def test_plan_forge_llm_error_is_business_error():
    assert PlanForgeLLMError in _BUSINESS_ERRORS
