"""K22 — chat-service's copy of `tool_list` must not drift from the handler that RUNS it.

`tool_list` exists twice: chat-service advertises a definition to the model, and ai-gateway
(`handleToolList`) executes the call. Only the second one decides behaviour. When they
disagree, the model is told one contract and gets another — and nothing reds, because each
side is internally consistent.

That is not hypothetical. Found 2026-07-23:

    chat-service   include_deprecated  default: True   "Default true."
    ai-gateway     includeDeprecated   default: false  (deliberate — spec 2026-07-22 review:
                                                       "a browsing agent should see the CURRENT
                                                       surface, not the shrunk-away legacy
                                                       tools as noise")

Opposite defaults on the same named arg. A model that trusts "default true", omits the arg,
and searches for a tool it remembers by its OLD name is told the tool does not exist —
on `tool_list`, which F17 made the ONLY discovery surface, immediately after a unification
renamed tools en masse. The blast radius is discovery itself.

Same structural bug as K10 (`propose_edit`'s description drifting from ai-gateway's copy),
so it gets the same guard: read the TS source directly, because the JSON contract file pins
only the frontend tools' args and would never have seen this.

T7-D1 (2026-08-13) — AND THE FIRST VERSION OF THIS FILE GUARDED THE WRONG HANDLER. `tool_list`
is dispatched consumer-locally by `stream_service.py` on a chat turn; `handleToolList` runs
only for a raw MCP caller. Asserting the advertisement against ai-gateway alone let the chat
dispatch keep `True` and reported green. Both handlers are now asserted, and the chat one
behaviourally rather than by regex. See `test_tool_list_default_hides_deprecated.py`.
"""
from __future__ import annotations

import pathlib
import re

import pytest

_TS = (
    pathlib.Path(__file__).resolve().parents[2]
    / "ai-gateway" / "src" / "federation" / "find-tools.ts"
)


def _ts_source() -> str:
    assert _TS.exists(), (
        f"{_TS} is missing — ai-gateway's find-tools.ts moved. This guard is now blind; "
        "re-point it rather than deleting it."
    )
    return _TS.read_text(encoding="utf-8")


def _chat_tool_list() -> dict:
    from app.services.tool_discovery import TOOL_LIST_TOOL

    return TOOL_LIST_TOOL["function"]["parameters"]["properties"]


def test_ts_source_is_present():
    # Guards the guard: a moved/renamed file must fail loudly, not silently skip.
    assert "TOOL_LIST_TOOL" in _ts_source()


def test_include_deprecated_default_matches_the_handler_that_runs_for_a_CHAT_turn():
    """T7-D1 — `tool_list` has TWO executing handlers, and this guard used to watch only the
    one a chat turn never reaches.

    A chat turn dispatches `tool_list` CONSUMER-LOCALLY in `stream_service.py`; ai-gateway's
    `handleToolList` serves only a raw MCP caller. This test asserted chat's advertisement
    against ai-gateway's handler, called that "the executing handler", and stayed green while
    the chat dispatch defaulted the arg the opposite way for three weeks — measured live
    2026-08-13 as 116 deprecated tools in a 307-tool listing the model never asked for.

    Behavioural, not a regex: the dispatch's default is now read by CALLING it.
    """
    from app.services.stream_service import _tool_list_include_deprecated

    advertised = _chat_tool_list()["include_deprecated"]["default"]
    assert _tool_list_include_deprecated({"category": "all"}) is advertised, (
        f"chat-service advertises include_deprecated default={advertised!r} but its own "
        "consumer-local dispatch — the handler that runs for every chat turn — applies the "
        "opposite. The model is being told the opposite of what happens, on the primary "
        "discovery tool."
    )


def test_include_deprecated_default_matches_the_handler_that_runs_for_a_RAW_MCP_caller():
    """The other executing handler. Kept because both must agree with the advertisement —
    two handlers behind one advertised contract is exactly how K22 and T7-D1 both happened."""
    handlers = (
        pathlib.Path(__file__).resolve().parents[2]
        / "ai-gateway" / "src" / "mcp" / "handlers.ts"
    ).read_text(encoding="utf-8")
    m = re.search(
        r"const includeDeprecated\s*=.*?:\s*(true|false);", handlers, re.S
    )
    assert m, "could not read handleToolList's include_deprecated fallback"
    executed_default = m.group(1) == "true"

    advertised = _chat_tool_list()["include_deprecated"]["default"]
    assert advertised is executed_default, (
        f"chat-service advertises include_deprecated default={advertised!r} but the handler "
        f"that runs applies {executed_default!r}. The model is being told the opposite of "
        "what happens, on the primary discovery tool."
    )


def test_the_advertised_default_also_matches_ai_gateways_own_tool_def():
    """Both DEFINITIONS should agree too, so a future reader isn't misled by either copy."""
    src = _ts_source()
    block = src[src.index("export const TOOL_LIST_TOOL"):]
    block = block[: block.index("} as const;")]
    m = re.search(r"include_deprecated:\s*\{.*?default:\s*(true|false)", block, re.S)
    assert m, "could not read ai-gateway's include_deprecated default"
    assert _chat_tool_list()["include_deprecated"]["default"] is (m.group(1) == "true")


def test_the_description_does_not_promise_the_opposite():
    # The default lives in TWO places a model reads — the `default` key AND the prose. A
    # correct default under prose that says "Default true." is still a lie.
    desc = _chat_tool_list()["include_deprecated"]["description"].lower()
    assert "default false" in desc, f"prose contradicts the default: {desc!r}"


@pytest.mark.parametrize("arg", ["category", "include_deprecated"])
def test_both_copies_advertise_the_same_arg_set(arg):
    src = _ts_source()
    block = src[src.index("export const TOOL_LIST_TOOL"):]
    block = block[: block.index("} as const;")]
    assert f"{arg}:" in block, f"ai-gateway's tool_list no longer takes {arg}"
    assert arg in _chat_tool_list(), f"chat-service's tool_list no longer advertises {arg}"
