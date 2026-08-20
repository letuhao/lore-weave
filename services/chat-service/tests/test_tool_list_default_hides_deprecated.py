"""T7-D1 — omitting `include_deprecated` must hide deprecated tools, because that is what
`tool_list` tells the model it does.

MEASURED LIVE 2026-08-13 (session 019ff9c5, gemma-4-26b-a4b-qat, plain prose "give me the
complete list of everything available"). The model called `tool_list({"category": "all"})` —
no `include_deprecated` — and received 307 tools of which **116 were deprecated**. 38% of the
primary discovery surface was the shrunk-away legacy catalog (`book_get` → `book_read`,
`book_list_chapters` → `book_list`, `composition_arc_create` → `composition_arc_edit`, …),
handed to a weak model under the description "List EVERY tool in a category, complete and
deterministic — the reliable way to see what you can do here."

Both advertised copies of the schema say `default: false`, in the `default` key AND in prose
the model reads: "omit to see only the CURRENT tools; set true only when migrating off an old
tool name."

THIS IS K22 INVERTED, WHICH IS WHY IT SURVIVED. K22 (2026-07-23) found the advertised default
(True) disagreeing with the executing handler and corrected the ADVERTISEMENT to False. Its
regression guard — `test_tool_list_contract_drift.py`, whose test is literally named
`test_include_deprecated_default_matches_the_executing_handler` — reads ai-gateway's
`handleToolList`. But `tool_list` is dispatched CONSUMER-LOCALLY in `stream_service.py`;
`handleToolList` never runs for a chat turn. The guard watched a handler that does not execute,
stayed green, and the half that does execute kept defaulting True.
"""
from __future__ import annotations

import ast
import pathlib

import pytest

from app.services.stream_service import _tool_list_include_deprecated
from app.services.tool_discovery import TOOL_LIST_TOOL, tool_list_result

_STREAM = pathlib.Path(__file__).resolve().parents[1] / "app" / "services" / "stream_service.py"

def _tool(name: str, meta: dict) -> dict:
    """A catalog entry in the shape the PRODUCER emits — the OpenAI function envelope that
    `tool_discovery._fn` unwraps. Writing these as bare MCP dicts silently yields an empty
    visible set, which reads as "the filter worked"."""
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": f"{name} description",
            "parameters": {"type": "object", "properties": {}},
            "_meta": meta,
        },
    }


_LEGACY = _tool("book_get", {"tier": "R", "visibility": "legacy", "superseded_by": "book_read"})
_CURRENT = _tool("book_read", {"tier": "R"})


def test_omitted_argument_hides_deprecated():
    """The measured live case: the model sent only `category`."""
    assert _tool_list_include_deprecated({"category": "all"}) is False


def test_explicit_true_is_honoured():
    # The migration case the description explicitly invites must still work.
    assert _tool_list_include_deprecated({"include_deprecated": True}) is True


def test_explicit_false_is_honoured():
    assert _tool_list_include_deprecated({"include_deprecated": False}) is False


@pytest.mark.parametrize("sent", ["true", "True", " TRUE ", "yes", "1"])
def test_a_string_true_is_coerced_not_dropped(sent):
    """With the default now False, silently dropping a non-bool would re-create the same lie
    in the other direction — and a string is exactly what the caller the prose invites (an
    agent migrating off an old tool name) is most likely to send."""
    assert _tool_list_include_deprecated({"include_deprecated": sent}) is True


@pytest.mark.parametrize("sent", ["false", "no", "0", "", "maybe", 3, None, [], {}])
def test_anything_unreadable_falls_back_to_the_advertised_default(sent):
    assert _tool_list_include_deprecated({"include_deprecated": sent}) is False


def test_the_default_matches_what_the_model_is_advertised():
    """Behavioural cross-check, so the advertisement and the executing handler cannot drift
    apart again the way K22's pair did."""
    advertised = TOOL_LIST_TOOL["function"]["parameters"]["properties"]["include_deprecated"]["default"]
    assert _tool_list_include_deprecated({}) is advertised


def test_the_composed_result_actually_drops_the_legacy_tool():
    """The helper's answer must reach the payload — a correct default that fed the wrong
    argument would still ship the 116 deprecated tools."""
    payload = tool_list_result(
        [_LEGACY, _CURRENT], "book",
        include_deprecated=_tool_list_include_deprecated({"category": "book"}),
    )
    listed = [t["name"] for t in payload["tools"]]
    assert listed == ["book_read"], listed


def test_opting_in_still_labels_rather_than_hides():
    payload = tool_list_result(
        [_LEGACY, _CURRENT], "book",
        include_deprecated=_tool_list_include_deprecated({"include_deprecated": True}),
    )
    by_name = {t["name"]: t for t in payload["tools"]}
    assert set(by_name) == {"book_get", "book_read"}
    assert by_name["book_get"]["deprecated"] is True
    assert by_name["book_get"]["superseded_by"] == "book_read"


def _include_deprecated_assignments() -> list[ast.Assign]:
    tree = ast.parse(_STREAM.read_text(encoding="utf-8"))
    found: list[ast.Assign] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == "include_deprecated":
                found.append(node)
    return found


def test_the_dispatch_site_is_wired_to_the_helper():
    """CALL-SITE guard, not a helper guard. A correct helper that the dispatch never calls is
    the shape this defect already took once: K22's fix was real and simply not wired into the
    path that runs."""
    assigns = _include_deprecated_assignments()
    assert assigns, ("no `include_deprecated = ...` assignment survives in stream_service.py"
                     " — this guard has gone blind; re-point it rather than deleting it.")
    for node in assigns:
        assert isinstance(node.value, ast.Call), ast.dump(node.value)
        assert isinstance(node.value.func, ast.Name)
        assert node.value.func.id == "_tool_list_include_deprecated", ast.dump(node.value)


def test_no_literal_default_survives_at_the_dispatch():
    """The original defect was a bare `include_deprecated = True` fallback. Re-inlining one
    anywhere in this module must red, even if the helper stays correct."""
    for node in _include_deprecated_assignments():
        assert not isinstance(node.value, ast.Constant), (
            "a literal `include_deprecated = <const>` is back in stream_service.py; the wire "
            "default must come from _tool_list_include_deprecated so it tracks the schema."
        )
