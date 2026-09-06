"""Naming a tool must put that tool on the wire.

🔴 **MEASURED 2026-08-25.** Sampling 25 tools from the live catalogue and asking for each one by
name — *"Please use the &lt;name&gt; tool for me."* — **24 of 25 were not answerable**. Naming a tool
did not surface it.

Live at K=5 against a real turn, a prompt reading *"Use the composition_build_cast_and_graph tool
to build the cast and the knowledge graph for this book"* left that tool **surfaced 0/5**. The
model walked a six-call chain instead and never once called `tool_load` to fetch the thing it had
just been told to use. Asked in a second arm for the one capability only that tool has — plan a
worklist, show it, then build — it **simulated the worklist in prose** rather than finding the
tool that does it.

**THIS IS NOT THE CLASSIFIER `CP-4.d` DELETED**, and the distinction is the whole point. That was
a twelve-verb SUBSTRING test that INFERRED A PROPERTY — the read/write lane — from fragments of a
name: it saw *get* inside `memory_forget` and *view* inside `kg_view_delete`, promoting
destructive tools into the always-advertised safe set, and it disagreed with the declared lane on
29 of 315 tools. C-1 forbids precisely that: *"lane is data at registration, never inferred from a
name."* Nothing is inferred here. The WHOLE identifier must appear, on identifier boundaries, and
the only thing concluded is what the writer said: they named this tool.
"""
from __future__ import annotations

import pytest

from app.services.tool_surface import answerable_tools


def _tool(name: str, synonyms: list[str] | None = None, **meta):
    return {"type": "function", "function": {
        "name": name, "description": f"the {name} tool", "parameters": {},
        "_meta": {"synonyms": synonyms or [], **meta},
    }}


CATALOG = [
    _tool("composition_build_cast_and_graph", ["build the knowledge graph"]),
    _tool("book_list", ["list books"]),
    _tool("book_list_chapters", ["chapter index"], superseded_by="book_list", visibility="legacy"),
    _tool("glossary_get_entity", ["look up an entity"]),
]


def test_a_tool_named_outright_is_answerable():
    got = answerable_tools(
        "Use the composition_build_cast_and_graph tool to build the cast for this book.", CATALOG)
    assert "composition_build_cast_and_graph" in got


def test_every_tool_is_reachable_by_its_own_name():
    for td in CATALOG:
        name = td["function"]["name"]
        assert name in answerable_tools(f"Please use the {name} tool for me.", CATALOG), name


def test_a_name_matches_on_IDENTIFIER_boundaries_not_merely_word_ones():
    """`book_list` must NOT match inside `book_list_chapters`.

    The shared `_synonym_pattern` guards with `(?<![a-z0-9])...(?![a-z0-9])`, which is correct
    for a synonym and wrong for an identifier, because `_` is outside that class. Naming the
    chapters tool would have dragged its shorter sibling along by pure prefix.
    """
    from app.services.tool_surface import _answer_norm, _exact_name_pattern
    lp = _answer_norm("please run book_list_chapters for me")
    assert _exact_name_pattern("book_list_chapters").search(lp)
    assert _exact_name_pattern("book_list").search(lp) is None


def test_naming_a_retired_tool_still_surfaces_its_replacement():
    """R2 propagation, and it matters more now that legacy tools never reach the wire: someone
    who names the tool they remember must still be handed the one that replaced it."""
    got = answerable_tools("please run book_list_chapters for me", CATALOG)
    assert "book_list_chapters" in got
    assert "book_list" in got


def test_declared_synonyms_still_work():
    """The name rule is ADDITIVE — it must not disturb the declaration-driven path."""
    assert "composition_build_cast_and_graph" in answerable_tools(
        "Build the knowledge graph for me", CATALOG)


def test_chitchat_still_matches_nothing():
    assert answerable_tools("hello, how are you today", CATALOG) == set()


@pytest.mark.parametrize("text", ["", None, "   "])
def test_empty_requests_are_safe(text):
    assert answerable_tools(text, CATALOG) == set()
