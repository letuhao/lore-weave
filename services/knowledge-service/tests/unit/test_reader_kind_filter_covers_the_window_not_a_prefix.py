"""TOOLV2 LOOP #266 — the kind filter searched the first 50 rows and called it the cast.

lore_browse_entities is correct on the safety axis, verified with a positive control the same way
#265 verified lore_ask: with no reading position it returns window_available false and an empty
list even when a kind is requested; with a position seeded at chapter 5 of 100 it returns 50
entities across 7 kinds.

The filter itself works — kind='character' returns only characters, kind='no_such_kind' returns
nothing rather than everything. What it does NOT do is search the window. Measured against the
tool's own producer (glossary known-entities at before_chapter_index=6), the reader's window holds
101 entities:

    character 24 | event 16 | organization 13 | terminology 13 | location 12 | item 12 |
    species 7 | power_system 4

and the tool answered:

    kind='character', limit=50  ->  15   (of 24)
    kind='location',  limit=50  ->   3   (of 12)

`_windowed_canon` fetched `limit` rows and filtered them in Python, so the filter ran over an
arbitrary 50-row PREFIX of the window rather than the window. known-entities has no kind parameter
— alive / min_frequency / before_chapter_index / recency_window / limit / offset only — so the
filtering has to happen here; it just has to happen over the right set.

The reason this is worse than a plain cap: the caller asked for 50 and received 15. Nothing looks
truncated. A silent under-count is indistinguishable from "that is all there is", and for a
reader-facing cast list the wrong answer is "you have met 15 characters" when they have met 24.

The unfiltered path was already correct — `limit` rows of the window is exactly what it promises —
so the over-fetch is taken only when a kind is actually supplied.
"""

from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "app" / "tools" / "reader_tools.py"


def _canon_fn() -> str:
    body = SRC.read_text(encoding="utf-8").replace("\r\n", "\n")
    start = body.index("async def _windowed_canon(")
    return body[start: body.index("\n# ── lore_ask", start)]


def test_the_filtered_path_fetches_the_whole_window():
    fn = _canon_fn()
    assert "fetch_limit = KNOWN_ENTITIES_MAX_PAGE if kind else limit" in fn, (
        "the kind filter is back to running over a `limit`-sized prefix; it under-counts the "
        "cast with no truncation signal"
    )
    assert "limit=fetch_limit," in fn, "the fetch still passes the caller's limit downstream"


def test_the_truncation_happens_after_the_filter():
    """Filtering then truncating bounds what the CALLER receives. Truncating then filtering
    bounds what we happened to fetch — the defect."""
    fn = _canon_fn()
    assert fn.index("if kind:") < fn.index("rows = rows[:limit]"), (
        "the truncation moved above the filter"
    )
    assert "rows = rows[:limit]" in fn


def test_the_unfiltered_path_is_unchanged():
    """`limit` rows of the window is exactly what the no-kind path promises, and over-fetching
    500 rows for a reader who asked for 50 would be a real cost on the hot reader surface."""
    fn = _canon_fn()
    assert "else limit" in fn, "the no-kind path must still fetch only what was asked for"


def test_the_fail_closed_guard_is_untouched():
    """The spoiler guarantee outranks the count fix: an unpinned position must still return []
    and never the full cast."""
    fn = _canon_fn()
    assert "if scope.book_id is None or scope.before_sort_order < 0:" in fn
    assert "return []" in fn


def test_the_glossary_outage_still_degrades_to_empty():
    """A larger fetch is a larger blast radius for a glossary failure — it must still degrade to
    empty rather than raising, and never leak an unwindowed list."""
    fn = _canon_fn()
    assert "except (GlossaryAnchorUnavailable, GlossaryAnchorMalformed) as exc:" in fn
    assert "return []" in fn.split("except (GlossaryAnchorUnavailable")[1]


def test_the_kind_code_field_note_survives():
    """The rows serialize the kind as `kind_code`; filtering on `kind`/`entity_kind` would drop
    every row. That note is why the filter works at all — losing it invites the old bug back."""
    fn = _canon_fn()
    assert "kind_code" in fn
