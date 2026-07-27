"""error_block_heal — re-anchoring, overlap merge, and the guarded splice (D3b).

The anchor tests are the load-bearing ones. An error block's entire value is that it points at a
specific piece of prose; every failure mode here ends with the co-writer confidently editing the
wrong paragraph and reporting success, which nothing downstream can detect.
"""

from __future__ import annotations

import uuid

import pytest

from app.db.models import ErrorBlock
from app.engine.error_block_heal import (
    SkippedBlock,
    anchor_blocks,
    apply_block_edits,
    fingerprint,
    locate_nearest,
    merge_overlapping,
)
from app.engine.self_heal import EditProposal, locate_span

# Three identical short lines — the shape fiction produces constantly and the shape that breaks
# first-match anchoring.
REPEATED = (
    "Elara opened the ledger.\n\n"      # 0..24
    "She nodded.\n\n"                   # 26..37
    "The hall went quiet.\n\n"          # 39..59
    "She nodded.\n\n"                   # 61..72
    "Ash drifted past the window.\n\n"  # 74..102
    "She nodded.\n\n"                   # 104..115
    "The door closed."
)


def _block(**over) -> ErrorBlock:
    base = dict(
        id=uuid.uuid4(), created_by=uuid.uuid4(), project_id=uuid.uuid4(), book_id=uuid.uuid4(),
        target_kind="chapter_draft", chapter_id=uuid.uuid4(),
        start_offset=0, end_offset=5, quote="x", source_fingerprint="sha256:stale",
        kind="continuity", note="n",
    )
    base.update(over)
    return ErrorBlock.model_validate(base)


class TestLocateNearest:
    """E1 — the bug that would have shipped."""

    def test_the_PRIMITIVE_WE_REUSE_really_does_return_the_first_match(self):
        """Pins the precondition the fix exists for. If self-heal's locator ever gained
        nearest-match semantics this test goes red and `locate_nearest` can be reconsidered —
        reusing a primitive means owning its behaviour, not assuming it."""
        third = REPEATED.index("She nodded.", 100)
        assert locate_span("She nodded.", REPEATED) == (26, 37)
        assert locate_span("She nodded.", REPEATED)[0] != third

    def test_nearest_wins_over_first_when_the_hint_is_trustworthy(self):
        """A mark made on the THIRD 'She nodded.' must re-anchor to the third — not the first,
        which is what first-match would do and what would silently edit the wrong paragraph."""
        third = REPEATED.index("She nodded.", 100)
        got = locate_nearest("She nodded.", REPEATED, hint=third + 2, hint_trusted=True)
        assert got == (third, third + len("She nodded."))

    def test_the_middle_occurrence_is_reachable_too(self):
        second = REPEATED.index("She nodded.", 50)
        got = locate_nearest("She nodded.", REPEATED, hint=second, hint_trusted=True)
        assert got == (second, second + len("She nodded."))

    def test_an_ambiguous_quote_with_an_UNTRUSTED_hint_refuses_to_guess(self):
        """Fingerprint mismatch means the coordinate space moved wholesale, so the hint carries
        no information. With several candidates and nothing to choose between them, orphaning is
        the honest outcome — a wrong guess corrupts prose while reporting success."""
        assert locate_nearest("She nodded.", REPEATED, hint=999, hint_trusted=False) is None

    def test_an_UNambiguous_quote_still_anchors_without_a_trusted_hint(self):
        """Refusing to guess must not become refusing to work: one candidate is not a guess."""
        got = locate_nearest("The hall went quiet.", REPEATED, hint=99999, hint_trusted=False)
        assert got == (39, 39 + len("The hall went quiet."))

    def test_falls_back_to_fuzzy_only_when_there_is_no_exact_candidate(self):
        """Whitespace drift should still anchor — but fuzz must never outvote an exact match."""
        text = "Elara opened   the\nledger. She left."
        got = locate_nearest("Elara opened the ledger.", text, hint=0, hint_trusted=True)
        assert got is not None and text[got[0]:got[1]].startswith("Elara opened")

    def test_an_empty_quote_never_anchors(self):
        assert locate_nearest("", REPEATED, hint=0, hint_trusted=True) is None


class TestAnchorBlocks:
    def test_a_matching_fingerprint_and_slice_is_used_verbatim(self):
        fp = fingerprint(REPEATED)
        b = _block(start_offset=39, end_offset=59, quote="The hall went quiet.", source_fingerprint=fp)
        anchored, skipped = anchor_blocks([b], REPEATED)
        assert not skipped
        assert (anchored[0].start, anchored[0].end) == (39, 59)
        assert anchored[0].reanchored is False   # nothing moved → nothing to persist

    def test_drifted_offsets_are_reanchored_and_flagged_for_persistence(self):
        """The prose grew above the mark. The offsets are stale; the quote still finds it."""
        shifted = "A new opening paragraph.\n\n" + REPEATED
        b = _block(
            start_offset=39, end_offset=59, quote="The hall went quiet.",
            source_fingerprint=fingerprint(REPEATED),   # the OLD space
        )
        anchored, skipped = anchor_blocks([b], shifted)
        assert not skipped
        assert shifted[anchored[0].start:anchored[0].end] == "The hall went quiet."
        assert anchored[0].reanchored is True

    def test_a_vanished_quote_is_skipped_with_a_reason_never_dropped(self):
        b = _block(quote="A sentence that was deleted.", source_fingerprint=fingerprint(REPEATED))
        anchored, skipped = anchor_blocks([b], REPEATED)
        assert not anchored
        assert skipped == [SkippedBlock(b.id, "not_located", skipped[0].detail)]

    def test_an_ambiguous_quote_in_a_moved_space_is_reported_as_ambiguous_not_missing(self):
        """'we could not tell which one you meant' and 'it is gone' are different problems and
        deserve different words — the author can act on the first."""
        b = _block(quote="She nodded.", source_fingerprint="sha256:something-else")
        _, skipped = anchor_blocks([b], REPEATED)
        assert skipped[0].reason == "ambiguous"


class TestMergeOverlapping:
    def test_overlapping_marks_MERGE_rather_than_one_being_dropped(self):
        """self-heal drops the later overlapping finding. Here both notes must survive: the
        author marked one passage for two reasons and answering half is answering wrong."""
        fp = fingerprint(REPEATED)
        a = _block(start_offset=0, end_offset=24, quote="Elara opened the ledger.",
                   source_fingerprint=fp, note="she cannot read yet", kind="continuity")
        b = _block(start_offset=6, end_offset=24, quote="opened the ledger.",
                   source_fingerprint=fp, note="too modern a phrasing", kind="voice")
        anchored, _ = anchor_blocks([a, b], REPEATED)
        merged = merge_overlapping(anchored)
        assert len(merged) == 1
        assert (merged[0].start, merged[0].end) == (0, 24)
        assert set(merged[0].notes) == {"she cannot read yet", "too modern a phrasing"}
        assert len(merged[0].block_ids) == 2
        assert "she cannot read yet" in merged[0].guide

    def test_disjoint_marks_stay_separate(self):
        fp = fingerprint(REPEATED)
        a = _block(start_offset=0, end_offset=24, quote="Elara opened the ledger.", source_fingerprint=fp)
        b = _block(start_offset=39, end_offset=59, quote="The hall went quiet.", source_fingerprint=fp)
        anchored, _ = anchor_blocks([a, b], REPEATED)
        assert len(merge_overlapping(anchored)) == 2

    def test_abutting_spans_are_not_merged(self):
        """Touching is not overlapping — merging them would widen the edit past what was marked."""
        text = "AAAA BBBB"
        fp = fingerprint(text)
        a = _block(start_offset=0, end_offset=4, quote="AAAA", source_fingerprint=fp)
        b = _block(start_offset=4, end_offset=9, quote=" BBBB", source_fingerprint=fp)
        anchored, _ = anchor_blocks([a, b], text)
        assert len(merge_overlapping(anchored)) == 2


class TestApplyBlockEdits:
    def _p(self, start, end, before, after, pid="eb0"):
        return EditProposal(id=pid, type="error_block", tier="semantic",
                            start=start, end=end, before=before, after=after)

    def test_a_clean_proposal_splices(self):
        out = apply_block_edits(REPEATED, [self._p(39, 59, "The hall went quiet.", "Silence fell.")])
        assert "Silence fell." in out
        assert "The hall went quiet." not in out

    def test_a_DRIFTED_proposal_is_skipped_and_the_prose_is_left_intact(self):
        """The guard self_heal's Python splice lacks. Between propose and apply a human reviews,
        which means arbitrary time and possibly other edits. Without this check the replacement
        lands on whatever now occupies those offsets — silent corruption."""
        stale = self._p(39, 59, "The hall went quiet.", "Silence fell.")
        edited = REPEATED.replace("The hall went quiet.", "The hall was silent.")
        assert apply_block_edits(edited, [stale]) == edited   # untouched, not corrupted

    def test_rightmost_first_so_earlier_offsets_stay_valid(self):
        ps = [
            self._p(0, 24, "Elara opened the ledger.", "Elara shut the ledger.", "eb0"),
            self._p(39, 59, "The hall went quiet.", "Silence fell.", "eb1"),
        ]
        out = apply_block_edits(REPEATED, ps)
        assert "Elara shut the ledger." in out and "Silence fell." in out

    def test_only_accepted_ids_are_applied(self):
        ps = [
            self._p(0, 24, "Elara opened the ledger.", "Elara shut the ledger.", "eb0"),
            self._p(39, 59, "The hall went quiet.", "Silence fell.", "eb1"),
        ]
        out = apply_block_edits(REPEATED, ps, accepted_ids=["eb1"])
        assert "Elara opened the ledger." in out    # rejected → untouched
        assert "Silence fell." in out


class TestFingerprint:
    def test_differs_when_the_flattening_differs(self):
        """The E3 signal: a doc that loses its `_text` snapshots flattens differently, moving
        every offset at once. The hash is what makes that detectable in one comparison."""
        assert fingerprint("a\n\nb") != fingerprint("ab")

    def test_is_stable_for_identical_text(self):
        assert fingerprint(REPEATED) == fingerprint(REPEATED)


@pytest.mark.parametrize("quote,hint,trusted", [("She nodded.", 26, True), ("She nodded.", 104, True)])
def test_every_repeated_occurrence_is_individually_addressable(quote, hint, trusted):
    got = locate_nearest(quote, REPEATED, hint=hint, hint_trusted=trusted)
    assert got is not None and got[0] == hint
