"""T7-D4 — the tool_list repeat-breaker must auto-load the SAME set the listing showed.

On a re-list of a category the model already listed, F18 does not error (two reverted fixes
proved that backfires). It AUTO-LOADS the category's tools and steers: "Its tools are now LOADED
and callable: … Call one of them now." So the runtime is picking tools on the model's behalf.

`tool_load_result` LABELS legacy tools rather than dropping them — correct for `tool_load`, where
a caller names a tool and gets it with its replacement attached. Nobody names anything here.

RECORDED FIRING, measured 2026-08-13 in loreweave_chat:

    "Its tools are now LOADED and callable: book_chapter_save_draft, book_get,
     book_list_chapters, book_list_revisions, book_scene_get, book_steering_list,
     book_update_details"

Four of those seven are deprecated (`book_get` → `book_read`, `book_list_chapters` → `book_list`,
`book_list_revisions` → `book_list`, `book_scene_get` → `book_read`).

Before T7-D1 both halves showed legacy and merely agreed with each other. Once the listing
started hiding it, the breaker became the runtime recommending the exact surface its own listing
had just withheld — so this guard is part of that fix, not a separate nicety.
"""
from __future__ import annotations

import ast
import pathlib

import pytest

from app.services.tool_discovery import tool_load_result


def _tool(name: str, meta: dict | None = None) -> dict:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": f"{name} description",
            "parameters": {"type": "object", "properties": {}},
            "_meta": meta or {"tier": "R"},
        },
    }


_CATALOG = [
    _tool("book_read"),
    _tool("book_get", {"tier": "R", "visibility": "legacy", "superseded_by": "book_read"}),
    _tool("book_list"),
    _tool("book_scene_get", {"tier": "R", "visibility": "legacy", "superseded_by": "book_read"}),
]


def _breaker_load(catalog, category, include_deprecated):
    """The breaker's own selection step, in the order stream_service applies it.

    `tool_load_result` returns (payload, NAMES) — only the payload's `tools` entries carry the
    `deprecated` label. Writing this against the wrong half is not theoretical: the first draft
    of the fix filtered the name list with `.get("deprecated")` and would have raised
    AttributeError on every breaker firing. This helper mirrors the shipped code exactly so the
    guard cannot pass over a shape the runtime does not have.
    """
    payload, loaded = tool_load_result(catalog, category=category)
    if not include_deprecated:
        legacy = {t["name"] for t in payload.get("tools", []) if t.get("deprecated")}
        loaded = [n for n in loaded if n not in legacy]
    return loaded


def test_the_breaker_does_not_activate_a_deprecated_tool():
    assert _breaker_load(_CATALOG, "book", include_deprecated=False) == ["book_read", "book_list"]


def test_an_explicit_opt_in_is_still_honoured():
    """The caller asked for the legacy surface; the breaker must not second-guess that."""
    assert _breaker_load(_CATALOG, "book", include_deprecated=True) == [
        "book_read", "book_get", "book_list", "book_scene_get",
    ]


def test_the_recorded_firing_can_no_longer_recommend_its_deprecated_half():
    """The four names from the measured 2026-08-13 steer, as a direct regression."""
    recorded = ["book_get", "book_list_chapters", "book_list_revisions", "book_scene_get"]
    catalog = _CATALOG + [
        _tool(n, {"tier": "R", "visibility": "legacy", "superseded_by": "book_read"})
        for n in ("book_list_chapters", "book_list_revisions")
    ]
    loaded = _breaker_load(catalog, "book", include_deprecated=False)
    assert not (set(recorded) & set(loaded)), sorted(set(recorded) & set(loaded))


def test_a_wholly_deprecated_category_loads_nothing_rather_than_recommending_legacy():
    """The steer renders "(none available in this category)" — honest, and better than naming
    tools the listing withheld."""
    catalog = [_tool("zz_old", {"tier": "R", "visibility": "legacy", "superseded_by": "zz_new"})]
    assert _breaker_load(catalog, "zz", include_deprecated=False) == []


def test_tool_loads_own_contract_is_untouched():
    """CONTROL. The filter lives at the BREAKER's call site, so `tool_load` — where a caller
    names a tool by name — must still return it, labelled."""
    payload, loaded = tool_load_result(_CATALOG, name="book_get")
    assert loaded == ["book_get"]
    by_name = {t["name"]: t for t in payload["tools"]}
    assert by_name["book_get"]["deprecated"] is True
    assert by_name["book_get"]["superseded_by"] == "book_read"
    assert "not_found" not in payload


@pytest.mark.parametrize("category", ["book", "all"])
def test_a_current_tool_is_never_dropped(category):
    """CONTROL in the other direction: the filter keys on the `deprecated` label, never on
    anything that could take a live tool with it."""
    loaded = _breaker_load(_CATALOG, category, include_deprecated=False)
    assert "book_read" in loaded and "book_list" in loaded


_STREAM = pathlib.Path(__file__).resolve().parents[1] / "app" / "services" / "stream_service.py"


def test_the_shipped_breaker_actually_applies_the_filter():
    """CALL-SITE guard. Every test above runs a MIRROR of the breaker's selection step, so all
    of them would stay green if the real block were deleted — and the mirror has already drifted
    from the shipped code once (the first draft filtered the name list as if it held dicts).

    So assert the shipped code structurally: inside the tool_list dispatch there must be an
    `if not include_deprecated:` that reassigns `loaded`.
    """
    tree = ast.parse(_STREAM.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.If):
            continue
        test = node.test
        if not (isinstance(test, ast.UnaryOp) and isinstance(test.op, ast.Not)
                and isinstance(test.operand, ast.Name)
                and test.operand.id == "include_deprecated"):
            continue
        for inner in ast.walk(node):
            if isinstance(inner, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "loaded" for t in inner.targets
            ):
                return
    raise AssertionError(
        "stream_service.py no longer filters the breaker's auto-loaded set on "
        "`if not include_deprecated:` — the repeat-breaker is free to activate and recommend "
        "the deprecated tools tool_list had just withheld (T7-D4)."
    )
