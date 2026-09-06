"""T7-D3 — an unknown category must read as a bad guess, never as an empty domain.

`tool_list_result`'s contract is that `reason` lets a caller "tell 'no tools' from a bad guess"
(the wording is the ai-gateway twin's own docstring). It could not: an out-of-enum category and
a genuinely empty one returned the identical string.

MEASURED in recorded traffic 2026-08-13 (loreweave_chat.chat_messages.tool_calls). The model
sent these categories and was told each domain was empty:

    book}       x2   -> "no tools currently available in this category"
    learning         -> "no tools currently available in this category"
    media            -> "no tools currently available in this category"

`book}` is a mangled `book`. The `book` domain holds 16 current tools, so one stray brace told
the model the platform has no book tools at all — on the surface F17 made the only way to
discover a tool that is not already advertised.

`category` declares an `enum`, which is why this looked impossible. A consumer-local tool is
dispatched inside chat-service WITHOUT the gateway's JSON-schema validation, so an out-of-enum
value arrives intact and is answered as if it named a real, empty domain.
"""
from __future__ import annotations

import pytest

from app.services.tool_discovery import CATEGORY_ENUM, GROUP_DIRECTORY, tool_list_result


def _tool(name: str) -> dict:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": f"{name} description",
            "parameters": {"type": "object", "properties": {}},
            "_meta": {"tier": "R"},
        },
    }


_CATALOG = [_tool("book_read"), _tool("book_list")]


@pytest.mark.parametrize("guess", ["book}", "learning", "media", "Book", "books", "", "  "])
def test_an_unknown_category_is_named_as_unknown(guess):
    payload = tool_list_result(_CATALOG, guess)
    assert "no tools currently available" not in payload["reason"], payload["reason"]
    assert "unknown category" in payload["reason"]
    assert payload["count"] == 0
    assert payload["tools"] == []


def test_the_valid_set_is_handed_back_so_the_model_can_recover():
    payload = tool_list_result(_CATALOG, "book}")
    assert payload["valid_categories"] == list(CATEGORY_ENUM)
    # The recovery has to be usable from the reason prose alone, not only from a sibling field.
    assert "book" in payload["reason"]


@pytest.mark.parametrize("known", sorted(GROUP_DIRECTORY))
def test_every_advertised_domain_is_accepted(known):
    """CONTROL, and the one that matters most: the guard must not reject a real domain. Every
    key in GROUP_DIRECTORY is a category the injected prompt tells the model to ask for."""
    payload = tool_list_result(_CATALOG, known)
    assert "unknown category" not in payload.get("reason", "")


def test_a_real_but_empty_domain_still_reports_itself_empty():
    """CONTROL. The two cases must stay distinguishable in BOTH directions — collapsing them
    the other way would be the same defect wearing the opposite label."""
    payload = tool_list_result(_CATALOG, "translation")
    assert payload["reason"] == "no tools currently available in this category"
    assert "valid_categories" not in payload


def test_all_and_omitted_are_not_treated_as_a_guess():
    for arg in (None, "all"):
        payload = tool_list_result(_CATALOG, arg)
        assert "categories" in payload, arg
        assert "reason" not in payload, arg


def test_the_accepted_set_is_exactly_what_the_schema_advertises():
    """Ties the check to the advertised enum, so a new domain cannot be accepted by the schema
    and rejected by the handler — the K22/T7-D1 drift shape."""
    from app.services.tool_discovery import TOOL_LIST_TOOL

    advertised = TOOL_LIST_TOOL["function"]["parameters"]["properties"]["category"]["enum"]
    assert list(advertised) == list(CATEGORY_ENUM)
    for name in advertised:
        assert "unknown category" not in tool_list_result(_CATALOG, name).get("reason", "")
