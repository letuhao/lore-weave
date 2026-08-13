"""T7-D5 — the tool_list repeat-breaker must key on the whole request, not on the category.

F18 treats a re-list of an already-listed category as a loop: it withholds the listing and
returns a steer that says "its complete tool list is above, unchanged — tool_list is not
paginated, so there is nothing more to fetch. … Do NOT call tool_list for this category again."

That sentence is only true if the second call would have returned the same list. Keyed on the
category alone it was applied to `tool_list(book)` followed by
`tool_list(book, include_deprecated=true)` — two requests that return 16 and 35 tools.

MEASURED LIVE 2026-08-13 (session 019ff9fe, gemma-4-26b-a4b-qat), prose: "Put the two side by
side for me: first the current book tools, then the book category again with the deprecated ones
included, so I can compare what changed."

    tool_list({"category":"book"})                              -> count 16
    tool_list({"category":"book"})                              -> count 16
    tool_list({"category":"book","include_deprecated":true})    -> BREAKER, no listing

Having no second list, the model built its answer from the steer's auto-loaded set and produced
a comparison table WITH THE TWO COLUMNS INVERTED — book_get / book_list_chapters /
book_list_revisions / book_scene_get (all deprecated) filed under "Current Active Tools", and
book_read / book_list / book_structure_edit (all current) under "Full Category (Including
Deprecated)" — then invented an explanation for the discrepancy.

Harmless before T7-D1, when both values returned the same list and "unchanged" was true. Once
the default started hiding deprecated tools the two requests diverged and the claim became a lie.
"""
from __future__ import annotations

import ast
import pathlib

_STREAM = pathlib.Path(__file__).resolve().parents[1] / "app" / "services" / "stream_service.py"

_CAP_NAME = "TOOL_LIST_CATEGORY_CAP"


def _breaker_keys() -> list[ast.expr]:
    """Every subscript/`.get` key used against `listed_categories` in the shipped code."""
    tree = ast.parse(_STREAM.read_text(encoding="utf-8"))
    keys: list[ast.expr] = []
    for node in ast.walk(tree):
        # listed_categories.get(<key>, 0)
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == "get"
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "listed_categories"):
            keys.append(node.args[0])
        # listed_categories[<key>] = ...
        if (isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name)
                and node.value.id == "listed_categories"):
            keys.append(node.slice)
    return keys


def test_the_repeat_key_is_not_the_bare_category():
    """The original defect: `listed_categories[_norm_cat]`, so a different argument set counted
    as the same request."""
    keys = _breaker_keys()
    assert keys, "no `listed_categories` access found — this guard has gone blind"
    for key in keys:
        assert not (isinstance(key, ast.Name) and key.id == "_norm_cat"), (
            "the tool_list repeat-breaker is keyed on the category alone again, so "
            "tool_list(x) and tool_list(x, include_deprecated=true) collapse into one "
            "request and the second is refused with a false 'unchanged' (T7-D5)."
        )


def _resolved_key() -> ast.expr:
    """The breaker's key expression, following one level of local binding.

    The shipped code builds `_list_key = (_norm_cat, include_deprecated)` and then uses the
    NAME. Asserting on the name alone would pass over any tuple; asserting a literal tuple at
    the access site would fail on the correct code. So resolve it.
    """
    keys = _breaker_keys()
    assert keys, "no `listed_categories` access found — this guard has gone blind"
    key = keys[0]
    if isinstance(key, ast.Tuple):
        return key
    assert isinstance(key, ast.Name), ast.dump(key)
    tree = ast.parse(_STREAM.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == key.id for t in node.targets
        ):
            return node.value
    raise AssertionError(f"`{key.id}` is used as the breaker key but never assigned")


def test_the_repeat_key_includes_include_deprecated():
    names = {sub.id for sub in ast.walk(_resolved_key()) if isinstance(sub, ast.Name)}
    assert "include_deprecated" in names, sorted(names)
    assert "_norm_cat" in names, sorted(names)


def test_every_access_uses_the_same_key():
    """A read and a write that disagree would silently never trip the breaker at all — the
    opposite failure, and invisible because nothing errors."""
    rendered = {ast.dump(k) for k in _breaker_keys()}
    assert len(rendered) == 1, rendered


def test_f18_is_not_weakened():
    """CONTROL. The breaker must still exist and still trip at the same cap — a fix that
    widened the key into never firing would 'pass' every test above."""
    src = _STREAM.read_text(encoding="utf-8")
    assert f">= {_CAP_NAME}" in src, "the F18 category cap comparison is gone"
    assert "TOOL_LIST_TOTAL_CAP" in src, "the per-turn total cap is gone"


def test_the_key_is_a_pair_so_the_flag_cannot_be_used_to_evade_the_cap():
    """`include_deprecated` is a boolean, so a category affords at most two distinct keys.
    A key built from free-form arguments would let a model loop forever by varying them."""
    key = _resolved_key()
    assert isinstance(key, ast.Tuple), ast.dump(key)
    assert len(key.elts) == 2, ast.dump(key)
