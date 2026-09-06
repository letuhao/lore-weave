"""A declared synonym must match a WORD, not a character span.

MEASURED LIVE 2026-08-14, K=3, real chat path. Prompt: "I want to start tracking the factions in
this world. Add Factions as a new category alongside characters and items."

    book_read            declares "cat"  ->  matched inside "**cat**egory"
    book_media_generate  declares "art"  ->  matched inside "st**art**"

Those two were the ENTIRE answerable set for that request. `glossary_ontology_upsert` — which
declares "add a kind", "add a genre", "new entity type", and is exactly the tool being asked for —
was surfaced on 0 of 3 runs. The model reached for `glossary_adopt_standards` instead and adopted
a whole genre pack: kinds 4 -> 5, attributes 29 -> 36, genres 1 -> 3, kind_genres 4 -> 13, from a
request to add ONE category.

The failure is worst exactly where the surface is already weakest. When the right tool declares
nothing matchable, the noise is all that survives — and a confident set of false positives is
indistinguishable from a correct answer, both to the model and to anyone reading the surface.

THE INVARIANT: a synonym matches on word boundaries in latin script. CJK is exempt, because `\\b`
is defined on word characters with spaces around them and a boundary rule would silently stop
matching Vietnamese and Chinese requests — the same defect with a different victim.
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app.services.tool_surface import answerable_tools  # noqa: E402

PROMPT = ("I want to start tracking the factions in this world. "
          "Add Factions as a new category alongside characters and items.")


def _td(name, synonyms):
    return {"type": "function",
            "function": {"name": name, "description": f"{name}.",
                         "_meta": {"synonyms": synonyms, "tier": "A", "scope": "book"}}}


CATALOG = [
    _td("book_read", ["read", "open", "cat", "read chapter"]),
    _td("book_media_generate", ["illustration", "generate image", "art"]),
    _td("glossary_ontology_upsert",
        ["add a kind", "add a genre", "add an attribute", "new entity type"]),
]


def test_cat_does_not_match_inside_category():
    """THE FALSIFIER. Original defect = raw substring test; then book_read is forced hot by the
    word 'category', which has nothing to do with reading a book."""
    got = answerable_tools(PROMPT, CATALOG)
    assert "book_read" not in got, (
        "'cat' is a declared synonym of book_read and 'category' contains it. Live, this and "
        "'art' inside 'start' were the entire answerable set for a request about adding a kind."
    )


def test_art_does_not_match_inside_start():
    got = answerable_tools(PROMPT, CATALOG)
    assert "book_media_generate" not in got


def test_the_tool_that_actually_answers_still_matches():
    """The point of the fix is not fewer matches — it is the RIGHT ones. This request literally
    contains 'add a kind'-shaped language via 'add ... category'; assert the real declaration
    still wins on a phrasing it does claim."""
    got = answerable_tools("Add a genre to this book, please.", CATALOG)
    assert got == {"glossary_ontology_upsert"}


def test_a_whole_word_synonym_still_matches():
    """Boundaries must not break the ordinary case."""
    got = answerable_tools("Please read chapter three.", CATALOG)
    assert "book_read" in got


def test_a_hyphenated_or_multiword_synonym_still_matches():
    cat = [_td("t", ["read-aloud", "generate image"])]
    assert answerable_tools("Can you read-aloud this scene?", cat) == {"t"}
    assert answerable_tools("Generate image for chapter one.", cat) == {"t"}


def test_cjk_is_exempt_from_word_boundaries():
    """Vietnamese and Chinese requests are first-class here. `\\b` is defined on word characters
    with spaces around them, so applying it to CJK would silently stop matching — the same defect
    this fixes, aimed at a different set of users."""
    cat = [_td("glossary_search", ["查找实体", "tra cứu"])]
    assert answerable_tools("帮我查找实体列表", cat) == {"glossary_search"}
    assert answerable_tools("Giúp tôi tra cứu nhân vật này", cat) == {"glossary_search"}
