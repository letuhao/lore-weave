"""T7-D2 — an always-on tool withheld from a listing must be NAMED, never read as absent.

MEASURED LIVE 2026-08-13 (session 019ff9da, gemma-4-26b-a4b-qat). The `research` category holds
exactly one tool, `web_search`, which is in ALWAYS_ON_CORE_NAMES and so is excluded from
listings as redundant — it is already advertised on every turn. `tool_list(category="research")`
therefore returned `count: 0` with `reason: "no tools currently available in this category"`.

That is contradicted by the system prompt the model reads in the SAME turn. `group_directory_text`
injects "Tool domains (call tool_list with category=<name> to see every tool in one)" followed by
"research: External web research — search the open web for background facts (web_search). PAID."
Asked "What research tools do I have? List everything in the research category", the model
answered: "there are actually **no tools** currently listed under a specific 'research' category."

The exclusion is right — re-listing a tool the model already holds is noise. Doing it INVISIBLY
was the defect: `reason` is the field a caller uses to tell "no such tools" from "bad guess", and
it asserted the first when the exclusion was what emptied the category.

Same class as the `incomplete` stamp in this module, whose own comment says why: a listing that
omits without saying so reads as a complete, healthy answer.
"""
from __future__ import annotations

from app.services.tool_discovery import ALWAYS_ON_CORE_NAMES, tool_list_result


def _tool(name: str, meta: dict | None = None) -> dict:
    """Catalog entry in the PRODUCER's shape — the OpenAI function envelope `_fn` unwraps.
    A bare MCP dict yields an empty visible set, which reads as "the filter worked"."""
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": f"{name} description",
            "parameters": {"type": "object", "properties": {}},
            "_meta": meta or {"tier": "R"},
        },
    }


# `web_search` is the real always-on member of `research`; `book_read` is an ordinary tool.
_WEB = _tool("web_search")
_BOOK = _tool("book_read")
_BOOK2 = _tool("book_list")
_HELD = {"web_search"}


def test_a_category_emptied_by_the_exclusion_does_not_claim_it_is_empty():
    payload = tool_list_result([_WEB, _BOOK], "research", include_deprecated=False, exclude=_HELD)
    assert payload["count"] == 0
    assert "no tools currently available" not in payload["reason"], payload["reason"]
    assert "web_search" in payload["reason"]


def test_the_held_tool_is_named_in_the_payload():
    payload = tool_list_result([_WEB, _BOOK], "research", include_deprecated=False, exclude=_HELD)
    assert payload["always_available"] == ["web_search"]


def test_a_genuinely_empty_category_still_says_so():
    """CONTROL. The fix must not blanket-delete the empty case — a category with nothing in it
    has to keep reading as empty, or the caller loses the other half of the distinction."""
    payload = tool_list_result([_BOOK], "research", include_deprecated=False, exclude=_HELD)
    assert payload["count"] == 0
    assert payload["reason"] == "no tools currently available in this category"
    assert "always_available" not in payload


def test_a_name_in_exclude_that_is_not_in_the_catalog_is_absent_not_held():
    """CONTROL. `exclude` is a wish-list; the catalog decides. Reporting a name the catalog
    never had would tell the model a tool exists when it does not — the inverse defect."""
    payload = tool_list_result([_BOOK], "research", include_deprecated=False,
                               exclude={"web_search", "totally_made_up_tool"})
    assert "always_available" not in payload
    assert payload["reason"] == "no tools currently available in this category"


def test_a_partially_held_category_lists_the_rest_and_still_names_the_held():
    payload = tool_list_result([_BOOK, _BOOK2], "book", include_deprecated=False,
                               exclude={"book_list"})
    assert [t["name"] for t in payload["tools"]] == ["book_read"]
    assert payload["always_available"] == ["book_list"]
    assert "reason" not in payload


def test_the_held_names_never_leak_across_categories():
    """`always_available` is scoped by the same `_domain_of` rule the listing uses, so a
    `book` request can never be told about a held `research` tool."""
    payload = tool_list_result([_WEB, _BOOK], "book", include_deprecated=False, exclude=_HELD)
    assert [t["name"] for t in payload["tools"]] == ["book_read"]
    assert "always_available" not in payload


def test_the_whole_catalog_view_also_names_what_it_withheld():
    payload = tool_list_result([_WEB, _BOOK], None, include_deprecated=False, exclude=_HELD)
    listed = {t["name"] for v in payload["categories"].values() for t in v}
    assert listed == {"book_read"}
    assert payload["always_available"] == ["web_search"]


def test_no_exclusion_means_no_stamp():
    payload = tool_list_result([_WEB, _BOOK], None, include_deprecated=False, exclude=set())
    assert "always_available" not in payload


def test_the_real_always_on_set_is_what_the_dispatch_withholds():
    """Ties the guard to the actual set, so adding a tool to ALWAYS_ON_CORE_NAMES cannot
    reintroduce a silently-emptied category."""
    payload = tool_list_result([_WEB, _BOOK], "research", include_deprecated=False,
                               exclude=set(ALWAYS_ON_CORE_NAMES))
    assert payload["always_available"] == ["web_search"]
    assert "no tools currently available" not in payload["reason"]
