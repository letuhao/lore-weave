"""Q8 / D-T32-REVEAL-AXIS — the reveal position is ONE parameter.

The spoiler window and the author-curation opt-out were two query flags saying one
thing: how far into the story may this reader see? Two parameters for one axis is how
they drift — `curation=true` had to document *"when true, before_chapter_id is
ignored"*, a precedence rule that exists only because there are two of them.

These pin the collapse, including the case that makes `all` more than "+infinity":
an author-written fact carries no `from_order`, so no finite ceiling ever admits it.
"""

from __future__ import annotations

from uuid import UUID, uuid4

from app.spoiler_window import REVEAL_ALL, parse_reveal_at


def _p(reveal_at=None, before=None, curation=False):
    return parse_reveal_at(reveal_at, before_chapter_id=before, curation=curation)


# ── the three states of one parameter ─────────────────────────────────

def test_absent_is_fail_closed():
    """A reader whose position is unknown sees NOTHING. The whole spoiler gate
    inverts book_client's fail-OPEN posture for exactly this reason."""
    assert _p() == (None, None)


def test_a_chapter_uuid_reads_through_that_chapter():
    ch = uuid4()
    assert _p(reveal_at=str(ch)) == ("chapter", ch)


def test_all_is_the_unbounded_author_read():
    assert _p(reveal_at="all") == (REVEAL_ALL, None)
    assert _p(reveal_at="ALL") == (REVEAL_ALL, None)     # case-insensitive
    assert _p(reveal_at="  all  ") == (REVEAL_ALL, None)  # and whitespace-tolerant


def test_an_unparseable_position_fails_CLOSED_not_open():
    """The one direction this must never get wrong. A malformed position is not a
    licence to show everything."""
    assert _p(reveal_at="not-a-uuid") == (None, None)
    assert _p(reveal_at="") == (None, None)


# ── the legacy flags are mapped, not branched on ──────────────────────

def test_curation_true_maps_onto_all():
    assert _p(curation=True) == (REVEAL_ALL, None)


def test_before_chapter_id_maps_onto_a_chapter_position():
    ch = uuid4()
    assert _p(before=ch) == ("chapter", ch)


def test_reveal_at_wins_over_both_legacy_flags():
    """A caller that has migrated is STATING the position it means. Silently
    preferring the old flag would make the migration unobservable."""
    new, old = uuid4(), uuid4()
    assert _p(reveal_at=str(new), before=old, curation=True) == ("chapter", new)
    assert _p(reveal_at="all", before=old) == (REVEAL_ALL, None)


def test_curation_still_beats_a_bare_chapter_window():
    """The legacy precedence — "when true, before_chapter_id is ignored" — is
    PRESERVED for callers that have not migrated, and now lives in one tested
    function instead of a sentence in a docstring."""
    assert _p(before=uuid4(), curation=True) == (REVEAL_ALL, None)


# ── the statuses read maps `all` differently, and that is not an inconsistency ──

def test_reveal_all_means_a_CEILING_on_the_status_read_not_a_null():
    """/review-impl caught this before it shipped. The facts read passes
    `before_order=None` for `all` because its Cypher branches on
    `$before_order IS NULL` and that is how unplaced facts get in.
    `statuses_detail_at_order` does NOT: it takes `at_order: int` and compares
    `from_order <= at_order`, so a null ceiling matches nothing and every entity
    would read 'active' — a fail-OPEN wearing an author view's clothes.

    Every status carries a position, so there is nothing unplaced to rescue and
    "unbounded" is genuinely +infinity. Same constant the temporal chain uses.
    """
    from app.db.graph_repos.temporal import ORDINAL_OPEN_CEILING
    assert isinstance(ORDINAL_OPEN_CEILING, int)
    assert ORDINAL_OPEN_CEILING > 10 ** 12, "must exceed any real event_order"


# ── the five surfaces share the POSITION, not the DEFAULT ─────────────
#
# The deep dive that finished this migration found the surfaces are not uniform, and
# flattening them would have broken two of them. These record the three axes of
# difference so a later "simplification" has to argue with a test.


def test_absent_means_different_things_by_surface_and_that_is_deliberate():
    """`parse_reveal_at` returns `None` for absent — it does NOT decide what absent
    MEANS. Each surface answers that for itself:

        facts, statuses (reader-facing)  absent → FAIL-CLOSED   (see nothing)
        browse list, raw search, timeline (author-facing)
                                         absent → UNFILTERED    (see everything)

    Collapsing them either empties every editor cast list or leaks later-introduced
    characters into every reader one. The parser stays out of it on purpose.
    """
    assert _p() == (None, None)          # the parser reports ABSENT, not a policy
    assert _p(reveal_at="all") == (REVEAL_ALL, None)   # explicit is distinguishable


def test_the_two_axes_use_different_resolvers():
    """`reveal_at=<chapter>` is one vocabulary over TWO scales, and mixing them is
    wrong by a factor of the stride:

        entity reads  → resolve_before_order      → (sort_order+1)*STRIDE-1  (event_order)
        raw search    → resolve_before_sort_order → sort_order               (chapter_index)

    Passages carry `chapter_index`; events and facts carry `event_order`. Feeding one
    ceiling to the other filter silently returns the wrong window rather than failing.
    """
    from app.spoiler_window import (
        FAIL_CLOSED_BEFORE_ORDER,
        FAIL_CLOSED_BEFORE_SORT_ORDER,
    )
    # Both fail closed at -1, but they are separate constants for separate scales —
    # a single shared one would invite exactly the mix-up above.
    assert FAIL_CLOSED_BEFORE_ORDER == FAIL_CLOSED_BEFORE_SORT_ORDER == -1


def test_the_timeline_keeps_a_raw_ceiling_that_outranks_reveal_at():
    """Three spellings of one axis live on the timeline: a raw `before_order`, a
    `before_chapter_id`, and now `reveal_at`. The raw ordinal still wins — a caller
    that already HOLDS the ceiling (pagination) is not guessing, and demoting it
    would break those callers to make a naming point."""
    ch = uuid4()
    # The parser has no opinion about `before_order`; the endpoint resolves it first
    # and only consults the parser when it is absent. This pins the parser's half.
    assert _p(reveal_at=str(ch)) == ("chapter", ch)
