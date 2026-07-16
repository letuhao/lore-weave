"""Executive unit tests (M5) — the safe-when-wrong guarantees (EC-1) + skips.

The executive writes `state` only and `covered` is monotonic, so even a
hallucinating model can never move the goal or un-cover progress.
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from app.working_memory import executive as ex

_CHARTER = {
    "goal": "Senior backend interview",
    "phases": ["warmup", "technical", "behavioral", "wrap"],
    "checklist": ["system design", "conflict story", "REST vs gRPC"],
    "time_budget_min": 60,
    "language": "vi",
}


# ── merge_state: the safe-when-wrong core ────────────────────────────────────

def test_merge_covered_is_monotonic_never_drops():
    old = {"phase": "technical", "covered": ["system design", "REST vs gRPC"]}
    # the LLM "forgets" system design and only reports REST — must NOT shrink
    llm = {"phase": "technical", "covered": ["REST vs gRPC"]}
    merged = ex.merge_state(_CHARTER, old, llm)
    assert "system design" in merged["covered"]
    assert "REST vs gRPC" in merged["covered"]


def test_merge_covered_adds_new_items():
    old = {"phase": "warmup", "covered": ["system design"]}
    llm = {"phase": "technical", "covered": ["system design", "conflict story"]}
    merged = ex.merge_state(_CHARTER, old, llm)
    assert set(merged["covered"]) == {"system design", "conflict story"}


def test_merge_rejects_phase_not_in_charter():
    old = {"phase": "technical", "covered": []}
    llm = {"phase": "ESCAPED_THE_SCRIPT", "covered": []}
    merged = ex.merge_state(_CHARTER, old, llm)
    assert merged["phase"] == "technical"  # kept the prior valid phase


def test_merge_drops_non_string_covered_and_hint():
    old = {"phase": "warmup", "covered": []}
    llm = {"phase": "warmup", "covered": ["ok", 123, None], "redirect_hint": {"x": 1}}
    merged = ex.merge_state(_CHARTER, old, llm)
    assert merged["covered"] == ["ok"]
    assert merged["redirect_hint"] is None


def test_merge_never_emits_a_charter_key():
    merged = ex.merge_state(_CHARTER, {"phase": "", "covered": []}, {"phase": "warmup", "covered": []})
    # the merged STATE must not carry goal/phases/checklist — those are charter.
    assert set(merged.keys()) == {"phase", "covered", "elapsed_min", "drift_note", "redirect_hint"}


# ── run_executive: skips + happy path ────────────────────────────────────────

def _block(state=None):
    return {"version": 1, "charter": _CHARTER, "state": state or {"phase": "", "covered": []}}


def _job(content: str, status="completed"):
    job = AsyncMock()
    job.status = status
    job.result = {"messages": [{"content": content}]}
    return job


_MODEL = {"model_source": "user_model", "model_ref": "m-1"}


@pytest.mark.asyncio
async def test_no_block_skips():
    repo = AsyncMock()
    repo.get.return_value = None
    status = await ex.run_executive(repo=repo, llm_client=AsyncMock(),
                                    session_id="s", user_id="u", recent_turns=[], **_MODEL)
    assert status == "no_block"
    repo.update_state.assert_not_awaited()


@pytest.mark.asyncio
async def test_no_model_skips():
    repo = AsyncMock()
    repo.get.return_value = _block()
    # session carried no model → skip (the dead default-models/chat lookup is gone)
    status = await ex.run_executive(repo=repo, llm_client=AsyncMock(),
                                    session_id="s", user_id="u", recent_turns=[],
                                    model_source="user_model", model_ref=None)
    assert status == "no_model"
    repo.update_state.assert_not_awaited()


@pytest.mark.asyncio
async def test_bad_json_skips():
    repo = AsyncMock()
    repo.get.return_value = _block()
    llm = AsyncMock()
    llm.submit_and_wait.return_value = _job("not json at all")
    status = await ex.run_executive(repo=repo, llm_client=llm,
                                    session_id="s", user_id="u", recent_turns=[], **_MODEL)
    assert status == "bad_json"
    repo.update_state.assert_not_awaited()


@pytest.mark.asyncio
async def test_executive_runs_on_the_session_model():
    repo = AsyncMock()
    repo.get.return_value = _block()
    llm = AsyncMock()
    llm.submit_and_wait.return_value = _job(json.dumps({"phase": "warmup", "covered": []}))
    await ex.run_executive(repo=repo, llm_client=llm, session_id="s", user_id="u",
                           recent_turns=[], model_source="user_model", model_ref="the-session-model")
    # the executive must call the gateway with the session's own model — not a
    # separate default (provider-registry has no 'chat' default capability).
    kw = llm.submit_and_wait.call_args.kwargs
    assert kw["model_source"] == "user_model"
    assert kw["model_ref"] == "the-session-model"
    # Footgun disable PINNED (no_thinking_fields): a reasoning model must NOT think
    # out loud — max_tokens=500 would be spent on hidden reasoning → empty → bad_json.
    # If this goes red, someone dropped the **_NO_THINKING spread and re-opened it.
    assert kw["input"]["chat_template_kwargs"]["thinking"] is False
    assert kw["input"]["reasoning_effort"] == "none"


@pytest.mark.asyncio
async def test_happy_path_updates_state_only():
    repo = AsyncMock()
    repo.get.return_value = _block(state={"phase": "warmup", "covered": ["system design"]})
    llm = AsyncMock()
    llm.submit_and_wait.return_value = _job(json.dumps({
        "phase": "technical",
        "covered": ["conflict story"],  # the model omits the prior item
        "redirect_hint": "quay lại system design",
    }))
    status = await ex.run_executive(repo=repo, llm_client=llm,
                                    session_id="s", user_id="u",
                                    recent_turns=[{"role": "user", "content": "hi"}], **_MODEL)
    assert status == "updated"
    repo.update_state.assert_awaited_once()
    # RV-H4: update_state is now (session_id, user_id, state) — owner-scoped write.
    assert repo.update_state.call_args.args[1] == "u"  # the owner we read the block under
    written = repo.update_state.call_args.args[2]
    # monotonic: the prior covered item survives even though the LLM dropped it
    assert "system design" in written["covered"]
    assert "conflict story" in written["covered"]
    assert written["phase"] == "technical"
    assert written["redirect_hint"] == "quay lại system design"
    # update_state receives STATE only — never the charter
    assert "charter" not in written and "goal" not in written


@pytest.mark.asyncio
async def test_llm_failed_status_skips():
    repo = AsyncMock()
    repo.get.return_value = _block()
    llm = AsyncMock()
    llm.submit_and_wait.return_value = _job("{}", status="failed")
    status = await ex.run_executive(repo=repo, llm_client=llm,
                                    session_id="s", user_id="u", recent_turns=[], **_MODEL)
    assert status == "llm_failed"
    repo.update_state.assert_not_awaited()


def test_parse_json_object_handles_fences_and_prose():
    # bare object
    assert ex._parse_json_object('{"phase": "warmup"}')["phase"] == "warmup"
    # ```json fenced (lm_studio / many local models do this)
    assert ex._parse_json_object('```json\n{"phase": "technical"}\n```')["phase"] == "technical"
    # prose-wrapped — extract the outermost { ... }
    assert ex._parse_json_object('Here is the progress: {"phase": "wrap"} done.')["phase"] == "wrap"


def test_parse_json_object_raises_on_no_object():
    import pytest as _pytest
    with _pytest.raises(ValueError):
        ex._parse_json_object("no json here")


@pytest.mark.asyncio
async def test_build_messages_caps_turn_size():
    huge = "x" * 50000
    msgs = ex.build_messages(_CHARTER, {"phase": "", "covered": []},
                             [{"role": "user", "content": huge}])
    # the pasted wall is truncated so the prompt stays bounded
    assert len(msgs[1]["content"]) < 10000
