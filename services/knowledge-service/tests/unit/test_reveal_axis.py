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
    from app.db.neo4j_repos.temporal import ORDINAL_OPEN_CEILING
    assert isinstance(ORDINAL_OPEN_CEILING, int)
    assert ORDINAL_OPEN_CEILING > 10 ** 12, "must exceed any real event_order"
