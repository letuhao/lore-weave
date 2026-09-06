"""A declared synonym must still REQUEST the operation after the matcher normalises it.

THE MATCHER STRIPS ARTICLES AND DEMONSTRATIVES from both the request and the synonym, on
purpose: the v1 incident was "update the description of my book" failing to match the declared
"update description" purely on an article. That strip is correct and is not under test here.

WHAT IS UNDER TEST is what a synonym DEGRADES INTO once it is applied. `memory_forget` — tier A,
whose entire job is invalidating a stored fact — declared `"that was wrong"`, which normalises to
the bare predicate `"was wrong"`. Measured live, that made it answerable on:

    "I just fixed a few paragraphs in chapter 3 — some dialogue WAS WRONG.
     Can you redo the translation for just those?"

a request about translation. R1 answerability then forces an answerable tool onto the wire
"whatever the budget decided", so an ordinary English predicate put a deletion tool in front of
the model on a turn that never asked for one.

The demonstrative was carrying the meaning: "that was wrong" points at a fact the user was just
shown. Stripped, it points at anything.

🔴 THIS FILE DOES NOT GENERALISE THE FINDING, AND THE MEASUREMENT IS WHY. Over 564 distinct live
requests, ZERO write-tier synonyms match 5% or more of the corpus, and the most promiscuous one
is `glossary_propose_entities`' "add a character" at 3% — which is correct, because those
requests are asking to add a character. One vivid instance is not a class. So this guards the
DECLARATION that was wrong and the shape it belongs to, and deliberately does not install a
registration-time gate for a population that does not exist.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

SERVER = Path(__file__).resolve().parents[2] / "app" / "mcp" / "server.py"

#: The words the answerability matcher removes. Mirrored rather than imported: knowledge-service
#: does not depend on chat-service, and the point of this test is that a synonym must stand up
#: WITHOUT them — which is a property of the phrase, checkable here.
_STRIPPED = {"a", "an", "the", "that", "this", "these", "those", "my", "your", "our", "its",
             "their", "it", "of", "to", "for", "in", "on", "please", "can", "you"}


def _synonyms_of(tool: str) -> list[str]:
    src = SERVER.read_text(encoding="utf-8")
    idx = src.index(f'name="{tool}"')
    block = src[idx: src.find("@mcp_server.tool(", idx + 1)]
    m = re.search(r"synonyms=\[(.*?)\]", block, re.S)
    assert m, f"{tool} declares no synonyms — re-anchor this test"
    return re.findall(r'"([^"]+)"', m.group(1))


def _after_strip(phrase: str) -> str:
    return " ".join(w for w in re.findall(r"[a-z0-9']+", phrase.lower()) if w not in _STRIPPED)


def test_memory_forget_no_longer_declares_a_bare_predicate():
    """🔴 THE ORIGINAL INSTANCE. 'that was wrong' -> 'was wrong'."""
    syns = _synonyms_of("memory_forget")
    assert "that was wrong" not in syns, (
        "memory_forget declares 'that was wrong' again. It normalises to 'was wrong', which is "
        "ordinary English, and it made a tier-A deletion tool answerable on a translation request"
    )
    assert syns, "all synonyms were removed — the tool is now unreachable by a user's words"


@pytest.mark.parametrize("survivor", ["forget that", "remove that fact", "retract that",
                                      "no longer true"])
def test_the_four_that_were_kept_are_still_declared(survivor):
    """The control against an over-broad repair. These lose their demonstrative too, and they
    are FINE: 'forget that' -> 'forget', 'retract that' -> 'retract', 'remove that fact' ->
    'remove fact' all still ask for this operation as VERBS. Deleting them to be safe would
    strand the tool, which is the opposite failure."""
    assert survivor in _synonyms_of("memory_forget")


def test_every_kept_synonym_still_asks_for_something_after_the_strip():
    """The invariant, stated so a future addition is checked by the same rule that removed the
    old one: what survives normalisation must still be a REQUEST, not a description of a
    situation. A bare 'was wrong' describes; 'forget' asks."""
    describing_only = {"was wrong", "wrong", "not true", "incorrect", "was incorrect", "bad"}
    for syn in _synonyms_of("memory_forget"):
        stripped = _after_strip(syn)
        assert stripped, f"{syn!r} disappears entirely once stripped"
        assert stripped not in describing_only, (
            f"{syn!r} normalises to {stripped!r}, which describes a situation rather than "
            f"requesting this tier-A deletion — the exact shape 'that was wrong' had"
        )
