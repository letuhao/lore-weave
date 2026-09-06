"""DQ-T6 (i) — a plural in the request must not hide the tool that answers it.

OWNER RULING 2026-09-02: "(i) MATCH A DECLARED SYNONYM AGAINST A LIGHTLY NORMALISED REQUEST --
trailing-s only, no stemmer", with the bar that "loosening a matcher whose whole value is
precision has a measurable false-positive cost. That cost is to be MEASURED across the live
catalogue BEFORE the change ships, not asserted."

THE ORIGINAL INSTANCE, measured 2026-09-02:
    "Suggest some arc structures for this book."  -> [composition_arc_list]
    composition_arc_suggest, which declares "suggest an arc structure", was NOT in the set.
    Live K=5: advertised 0/5, and the model used a WRITE on 5 of 5.
One letter decided it.
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app.services.tool_surface import (  # noqa: E402
    _answer_norm, _depluralised, answerable_tools,
)


def _tool(name: str, synonyms: list[str]) -> dict:
    return {"type": "function",
            "function": {"name": name, "description": "", "parameters": {},
                         "_meta": {"synonyms": synonyms}}}


# 🔴 THE REAL DECLARATIONS, copied from contracts/tool-catalog-cache.json rather than invented.
# The first draft of this file made up "suggest an arc structure" and the test failed for the
# WRONG reason: the request says "suggest SOME arc structures", so an invented synonym starting
# with "suggest" cannot match contiguously whatever happens to the plural. A fixture that does
# not match the shipped declaration tests the fixture.
CATALOG = [
    _tool("composition_arc_suggest",
          ["suggest arc", "arc template", "story arc", "arc structure"]),
    _tool("composition_arc_list", ["list arcs", "arcs", "the arc"]),
    # The tool whose OWN synonym is plural — the one the literal reading of the ruling broke.
    _tool("composition_motif_link_edit", ["link motifs", "connect motifs", "unlink motifs"]),
    # Declares the PLURAL "books"; a request about one book must not reach it.
    _tool("book_list", ["books", "my library", "novels"]),
]


def test_THE_ORIGINAL_INSTANCE_a_plural_request_finds_the_tool():
    """THE FALSIFIER. This is the exact request from the measured run."""
    got = answerable_tools("Suggest some arc structures for this book.", CATALOG)
    assert "composition_arc_suggest" in got, (
        "the tool that DECLARES 'suggest an arc structure' is still missing from a request "
        "asking for arc structureS — the one-letter miss this ruling exists to fix")


def test_the_singular_control_is_unchanged():
    """It already worked, and a fix that changes the control is not a fix."""
    assert "composition_arc_suggest" in answerable_tools(
        "Suggest an arc structure for this book.", CATALOG)


def test_a_PLURAL_SYNONYM_still_matches_its_plural_request():
    """🔴 THE TEETH, and the reason this widens rather than replaces.

    The ruling's LITERAL reading — normalise the request and match against THAT — was built and
    measured first: over 410 recorded prompts it LOST a tool on 169 (41%) and gained 2, because
    a request folded to the singular stops matching a synonym that is itself plural.
    `composition_motif_link_edit` declares "link motifs" and lost 131 of them.

    If this assertion ever fails, the implementation has quietly become the replacement form.
    """
    got = answerable_tools("Link motifs — mark Alpha as coming before Beta.", CATALOG)
    assert "composition_motif_link_edit" in got, (
        "a plural SYNONYM stopped matching its plural request — the request is being REPLACED "
        "by its depluralised form instead of matched in both forms")


def test_the_DECLARATION_is_never_rewritten():
    """The other refuted variant: folding the SYNONYM too.

    "list my books" would fold to "list my book" and then match "…add a character to my book" —
    83.9% of recorded prompts gained a tool that way. The declaration must be matched as
    written.
    """
    got = answerable_tools("Add a character called Sera to my book.", CATALOG)
    assert "book_list" not in got, (
        "a request about ONE book matched a tool declaring 'list my books' — the synonym is "
        "being depluralised, which is the false-positive class this design rejects")


def test_the_rule_is_ADDITIVE_and_cannot_lose_a_match():
    """The property the whole design rests on, asserted directly rather than inferred."""
    for prompt in ("Link motifs — mark Alpha before Beta.",
                   "Suggest an arc structure for this book.",
                   "list my books please",
                   "Suggest some arc structures for this book."):
        raw_only = {
            t["function"]["name"] for t in CATALOG
            for syn in t["function"]["_meta"]["synonyms"]
            if _answer_norm(syn) in _answer_norm(prompt)
        }
        got = answerable_tools(prompt, CATALOG)
        assert raw_only <= got, (
            f"{prompt!r} lost {sorted(raw_only - got)} — the rule must only ever widen")


def test_the_normaliser_does_not_invent_words():
    """Trailing-s only, with a 3-character floor. No stemmer, and short words are untouched."""
    assert _depluralised("arc structures") == "arc structure"
    assert _depluralised("motifs") == "motif"
    # Short words survive: folding these would change meaning, not number.
    for w in ("is", "as", "us", "its"):
        assert _depluralised(w) == w, w
    # It is not a stemmer, and the limitation is recorded rather than hidden: "stories" folds
    # to the non-word "storie" because the rule only knows a trailing s. That is HARMLESS here
    # precisely because the rule is additive — the raw "stories" is still matched, and "storie"
    # simply matches nothing. A stemmer would be the fix, and the ruling excluded one.
    assert _depluralised("stories") == "storie"
    assert _depluralised("children") == "children"
    # A word already singular is untouched.
    assert _depluralised("arc structure") == "arc structure"


def test_a_request_with_no_plural_is_byte_identical():
    """The common path must not change at all — the fix costs nothing when there is no plural."""
    p = _answer_norm("Suggest an arc structure for this book.")
    assert _depluralised(p) == p
