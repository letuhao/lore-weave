"""TOOLV2 LOOP #210 — motif_search called `q` a filter. It is a ranker.

The description listed "genre, kind, free text (q), language, or status" as one set of filters.
Measured against scope='mine':

    no q                -> 20 rows, first "Ambush"
    q="zzznomatch"      -> 20 rows, first "打脸 escalation 1784225978399"
    kind="situation"    ->  7 rows

`kind` subtracts. `q` does not: it returns the same page in a DIFFERENT ORDER. That is deliberate
and well-reasoned — MotifRepo._rank_by_query documents the change at length:

    "`q` was an ILIKE in the WHERE clause ... and a WHERE clause can only ever SUBTRACT. Type a
     phrase whose words are not literally in a name or summary and you get nothing: searching
     `witness contradicts testimony` returned 0 rows while `mystery.witness_who_lies` sat right
     there ... move `q` from FILTER to RANK."

So the behaviour is right and the sentence was stale. It matters because the two readings lead to
opposite conclusions from the same response: a caller who believes q filters treats twenty
unrelated-looking rows as a bug, or worse trusts that everything returned matches its query. A
caller who knows q ranks reads the top of the list.

This is the same class as #144 (arc_delete describing a mechanism it does not use) and #163
(run_close claiming a sibling silently no-ops): a factual correction, not a rewording.
"""

from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "app" / "mcp" / "server.py"
BODY = SRC.read_text(encoding="utf-8").replace("\r\n", "\n")


def _search_description() -> str:
    start = BODY.index('"Search the narrative motif library')
    return BODY[start: BODY.index("meta=require_meta", start)]


def test_q_is_not_listed_among_the_subtractive_filters():
    desc = _search_description()
    assert "free text (q), language, or status" not in desc, (
        "q is described as a filter again; measured, it re-orders rather than narrowing"
    )


def test_the_description_says_q_ranks_and_what_that_implies():
    desc = _search_description()
    assert "RANKS" in desc, "the caller needs to know q sorts rather than narrows"
    # The consequence is the part that changes behaviour: a non-matching query still returns rows.
    assert "still returns rows" in desc
    # ...and the precedence rule, because an exact code hit sorting first is what makes it usable.
    assert "exact name or code" in desc


def test_the_genuinely_subtractive_filters_are_still_named_as_such():
    """The correction must not blur the distinction the other way — genre/kind/language/status
    really do narrow, and #210 measured kind cutting 20 rows to 7."""
    desc = _search_description()
    assert "SUBTRACT" in desc
    for f in ("genre", "kind", "language", "status"):
        assert f in desc, f"{f} must still be named as a filter"
