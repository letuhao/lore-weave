"""P5 REG-P5-01 runtime — `_run_subagent_call` nested-execution behaviour (M2/M3).

Drives the helper with a scripted stub in place of the nested `_stream_with_tools`
so we assert the isolation + clamp + scope contract WITHOUT a live model:
- unknown / empty inputs → a `result.error` (no silent no-op)
- the nested run is clamped read-only (`permission_mode='ask'`), gets the scoped
  tools as BOTH its advertised set and its execute-time `allowed_tool_names`, and
  runs at `subagent_depth+1`
- only the answer AFTER the last tool call is synthesized back; nested tokens sum;
  the persona's `model_ref` overrides the turn model; the result is capped.
"""

from __future__ import annotations

import pytest

import app.services.stream_service as ss
from app.services.subagent_runtime import SUBAGENT_RESULT_CHAR_CAP


class _Usage:
    def __init__(self, pin: int, pout: int) -> None:
        self.prompt_tokens = pin
        self.completion_tokens = pout


def _tool(name: str) -> dict:
    return {"type": "function", "function": {"name": name, "description": name, "parameters": {}}}


CATALOG = [
    _tool("glossary_search"),
    _tool("kg_search"),
    _tool("book_write"),
    _tool("find_tools"),
    _tool("propose_edit"),
]

DEFS = {
    "lore-scout": {
        "name": "lore-scout",
        "description": "reads lore",
        "system_prompt": "You are a lore scout.",
        "tool_scope": ["glossary_*", "kg_*"],
        "model_ref": "",
        "tier": "user",
    },
    "styled": {
        "name": "styled",
        "description": "rewrites",
        "system_prompt": "You rewrite.",
        "tool_scope": [],
        "model_ref": "sub-model-uuid",
        "tier": "user",
    },
}


def _install_stub(monkeypatch, script):
    """Replace the nested loop with a stub that records its kwargs and yields
    `script` (a list of chunk dicts)."""
    calls: list[dict] = []

    def _stub(**kwargs):
        calls.append(kwargs)

        async def _gen():
            for ch in script:
                yield ch

        return _gen()

    monkeypatch.setattr(ss, "_stream_with_tools", _stub)
    return calls


async def _run(**overrides):
    base = dict(
        args={"subagent": "lore-scout", "task": "find the dragon's name"},
        subagent_defs=DEFS,
        full_catalog=CATALOG,
        model_source="lm_studio",
        model_ref="turn-model",
        user_id="u1",
        gen_params={},
        knowledge_client=object(),
        session_id="s1",
        project_id="p1",
        caller_max_iterations=20,
        decision_check=None,
        hooks=None,
        effective_limit=None,
        subagent_depth=0,
        caller_permission_mode="ask",
    )
    base.update(overrides)
    return await ss._run_subagent_call(**base)


@pytest.mark.asyncio
async def test_unknown_subagent_returns_error(monkeypatch):
    _install_stub(monkeypatch, [])
    payload, sin, sout = await _run(args={"subagent": "ghost", "task": "x"})
    assert "unknown subagent 'ghost'" in payload["error"]
    assert "lore-scout" in payload["error"]  # names the available ones
    assert (sin, sout) == (0, 0)


@pytest.mark.asyncio
async def test_missing_task_returns_error(monkeypatch):
    _install_stub(monkeypatch, [])
    payload, _, _ = await _run(args={"subagent": "lore-scout", "task": "  "})
    assert "task" in payload["error"]


@pytest.mark.asyncio
async def test_nested_run_is_clamped_and_scoped(monkeypatch):
    calls = _install_stub(monkeypatch, [
        {"content": "The dragon is Vermithrax."},
        {"usage": _Usage(120, 40)},
    ])
    payload, sin, sout = await _run()
    assert payload["subagent"] == "lore-scout"
    assert payload["result"] == "The dragon is Vermithrax."
    assert (sin, sout) == (120, 40)
    # exactly one nested run
    assert len(calls) == 1
    kw = calls[0]
    # read-only clamp — never escalates
    assert kw["permission_mode"] == "ask"
    # depth advanced
    assert kw["subagent_depth"] == 1
    # persona system prompt + task, fresh isolated messages (no parent history)
    assert kw["messages"][0] == {"role": "system", "content": "You are a lore scout."}
    assert kw["messages"][1] == {"role": "user", "content": "find the dragon's name"}
    # scoped tools = glossary_* + kg_* only (book_write / find_tools / propose_edit excluded)
    scoped_names = {t["function"]["name"] for t in kw["tools"]}
    assert scoped_names == {"glossary_search", "kg_search"}
    # execute-time whitelist mirrors the scoped set
    assert kw["allowed_tool_names"] == {"glossary_search", "kg_search"}
    # book_write can never reach the sub-run
    assert "book_write" not in scoped_names
    assert "book_write" not in kw["allowed_tool_names"]


@pytest.mark.asyncio
async def test_write_delegation_clamp_write_caller(monkeypatch):
    # D-REG-P5-SUBAGENT-WRITE-DELEGATION — a WRITE-turn caller lets the sub-run run
    # in write mode (it may auto-commit ALLOWLISTED Tier-A tools within scope).
    calls = _install_stub(monkeypatch, [{"content": "done"}, {"usage": _Usage(1, 1)}])
    await _run(caller_permission_mode="write")
    assert calls[0]["permission_mode"] == "write"


@pytest.mark.asyncio
async def test_write_delegation_clamp_never_exceeds_caller(monkeypatch):
    # ask/plan callers keep the sub-run read-only — the clamp is min(caller, write),
    # never an escalation. plan collapses to ask (a subagent never writes plans).
    for caller, expected in (("ask", "ask"), ("plan", "ask")):
        calls = _install_stub(monkeypatch, [{"content": "x"}, {"usage": _Usage(1, 1)}])
        await _run(caller_permission_mode=caller)
        assert calls[0]["permission_mode"] == expected, caller


@pytest.mark.asyncio
async def test_only_post_last_tool_text_is_synthesized(monkeypatch):
    _install_stub(monkeypatch, [
        {"content": "let me look...."},                       # pre-tool chatter
        {"tool_call": {"tool": "glossary_search", "ok": True}},
        {"content": "Final answer: Vermithrax."},             # the real answer
        {"usage": _Usage(10, 5)},
    ])
    payload, _, _ = await _run()
    assert payload["result"] == "Final answer: Vermithrax."
    assert payload["tools_used"] == ["glossary_search"]


@pytest.mark.asyncio
async def test_persona_model_ref_overrides_turn_model(monkeypatch):
    calls = _install_stub(monkeypatch, [{"content": "ok"}, {"usage": _Usage(1, 1)}])
    await _run(args={"subagent": "styled", "task": "rewrite this"})
    assert calls[0]["model_ref"] == "sub-model-uuid"
    # empty tool_scope → a valid text-only run (no tools)
    assert calls[0]["tools"] == []
    assert calls[0]["allowed_tool_names"] == set()


@pytest.mark.asyncio
async def test_empty_persona_model_ref_falls_back_to_turn_model(monkeypatch):
    calls = _install_stub(monkeypatch, [{"content": "ok"}, {"usage": _Usage(1, 1)}])
    await _run()  # lore-scout has model_ref=""
    assert calls[0]["model_ref"] == "turn-model"


@pytest.mark.asyncio
async def test_result_is_capped(monkeypatch):
    big = "y" * (SUBAGENT_RESULT_CHAR_CAP + 1000)
    _install_stub(monkeypatch, [{"content": big}, {"usage": _Usage(1, 1)}])
    payload, _, _ = await _run()
    assert payload.get("truncated") is True
    assert "truncated" in payload["result"].lower()


@pytest.mark.asyncio
async def test_result_cap_scales_with_context_length(monkeypatch):
    # A 1M-context caller must NOT get the same result cap a 200K caller would —
    # the same text that truncates by default must survive uncapped once
    # context_length is large enough to scale the cap past its length.
    big = "y" * (SUBAGENT_RESULT_CHAR_CAP + 1000)
    _install_stub(monkeypatch, [{"content": big}, {"usage": _Usage(1, 1)}])
    payload, _, _ = await _run(context_length=1_000_000)
    assert not payload.get("truncated")
    assert payload["result"] == big


@pytest.mark.asyncio
async def test_nested_suspend_ends_run_gracefully(monkeypatch):
    _install_stub(monkeypatch, [
        {"content": "partial"},
        {"suspend": {"working": [], "input_tokens": 7, "output_tokens": 3}},
        {"content": "never reached"},
    ])
    payload, sin, sout = await _run()
    assert payload["result"] == "partial"
    assert "error" not in payload
    # tokens from the suspend chunk are still attributed
    assert (sin, sout) == (7, 3)


@pytest.mark.asyncio
async def test_nested_exception_degrades_to_error(monkeypatch):
    def _boom(**kwargs):
        async def _gen():
            raise RuntimeError("nested blew up")
            yield  # pragma: no cover

        return _gen()

    monkeypatch.setattr(ss, "_stream_with_tools", _boom)
    payload, _, _ = await _run()
    assert "failed to run" in payload["error"]
