"""K26 (2026-07-24) — story_search must not over-claim its search scope.

Its description called it "the universal find tool". It searches MANUSCRIPT PROSE only, so a
model reading "universal find" would use it to look for a character, get prose hits, and
conclude it had already searched everything — never calling glossary_search / memory_search
for the glossary entity or the known facts. That is a false negative, the same
advertise-reach-you-lack class this migration kept finding (K16/K20/K22/K23), just in prose.

The intent was ALWAYS "universal MANUSCRIPT search" — the sibling tests document exactly that
phrase; the word "manuscript" had simply dropped out of the description. This pins the scope
so it cannot silently regress.

Single instance, verified by a catalog-wide sweep — hence a focused assertion, not a gate
(a generic "no over-claim" detector would false-positive on legitimately-broad tools like
kg_world_query, which really is cross-book).
"""
from __future__ import annotations


async def _story_search_description() -> str:
    from app.mcp.server import mcp_server

    tools = {t.name: t for t in await mcp_server.list_tools()}
    assert "story_search" in tools, "story_search is no longer advertised"
    return tools["story_search"].description


async def test_does_not_claim_to_be_a_universal_find_tool():
    desc = (await _story_search_description()).lower()
    assert "universal find" not in desc, (
        "story_search claims to be a 'universal find tool' — it searches manuscript prose "
        "only, so that phrase makes a model skip glossary_search / memory_search and miss "
        "glossary entities and known facts (a false negative)."
    )


async def test_scopes_itself_to_the_manuscript():
    desc = (await _story_search_description()).lower()
    assert "manuscript" in desc, "story_search must state it searches the manuscript"


async def test_redirects_to_the_sibling_stores():
    # The redirect is the actual fix for the false-negative: it tells the model where the
    # things this tool does NOT cover actually live.
    desc = (await _story_search_description()).lower()
    assert "glossary_search" in desc, "must point cross-store queries at glossary_search"
    assert "memory_search" in desc, "must point fact queries at memory_search"
