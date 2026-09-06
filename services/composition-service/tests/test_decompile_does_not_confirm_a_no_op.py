"""D-EXTRACTION-CONFIRMS-A-NO-OP — a confirm card minted for provably zero work.

composition_decompile_arcs computes a dry-run count so the card can say "M chapters -> ~N arcs".
Its own code comment says that count "also gives a clean 'nothing to decompile' answer up front
for a book with no chapters". It did not: the count was computed, found to be 0, and a
confirm_token was minted anyway.

MEASURED 2026-08-14 against the live MCP surface:

    composition_decompile_arcs(book_id=<a book with 3 chapters>, chapters_per_arc=2)
      -> {"confirm_token": "...",
          "title": "Decompile 0 chapter(s) into ~0 arc(s)",
          "dry_run": {"chapters": 0, "would_create_arcs": 0}}

The author is asked to approve a card that states its own zero. Approving it can only produce the
engine's {"arcs": 0, "chapters_assigned": 0, "reason": "no chapters to decompile"}.

🔴 WHY THE ZERO WAS CORRECT, chased before anything was called a bug. The engine groups
`outline_node` rows of kind='chapter'. Those are minted by scene_decompile AT IMPORT, so a
genuinely imported book — the case this tool exists for — has them. My fixture's chapters came
from book_chapter_create, which does not create them. Three controls settled it: the count was
stable across three attempts with delays (not a sync lag), composition_package_tree on the SAME
book and service reported chapter_count=3 and unplanned_chapter_count=3 (the service can see the
book), and the engine reads the same table as the dry-run (so the two agree with each other).

So the counting is right and the fixture was wrong. What remains wrong is offering a confirmation
for work that is already known to be nothing.
"""
from __future__ import annotations

import pathlib
import re

SRC = (pathlib.Path(__file__).resolve().parents[1]
       / "app" / "mcp" / "server.py").read_text(encoding="utf-8")


def _handler() -> str:
    i = SRC.index("async def composition_decompile_arcs(")
    return SRC[i:i + 4000]


class TestZeroWorkIsAnswered:
    """THE FALSIFIER. Delete the guard and the tool mints a token for a card titled
    "Decompile 0 chapter(s) into ~0 arc(s)", which is the measured defect exactly."""

    def test_the_guard_exists_and_is_keyed_on_the_count(self):
        assert re.search(r"if would_arcs == 0:", _handler()), (
            "no zero-work guard — a card is minted for a book with nothing to decompile")

    def test_it_returns_before_minting(self):
        """Order is the whole fix: the guard must precede mint_confirm_token, not follow it."""
        h = _handler()
        assert h.index("if would_arcs == 0:") < h.index("mint_confirm_token"), (
            "the guard runs AFTER the token is minted, which changes nothing")

    def test_the_no_op_answer_carries_no_token(self):
        h = _handler()
        block = h[h.index("if would_arcs == 0:"):h.index("payload = {")]
        assert "confirm_token" not in block, "the no-op branch still hands back a token"
        assert '"reason": "no chapters to decompile"' in block, (
            "the no-op must carry the engine's own reason, so the two paths agree")

    def test_it_says_why_rather_than_only_that(self):
        """A bare 'nothing to do' sends the author looking for a fault that is not there — the
        distinction between an imported book and a directly-created one is the actual answer."""
        h = _handler()
        block = h[h.index("if would_arcs == 0:"):h.index("payload = {")]
        assert "guidance" in block
        assert "import" in block.lower()


class TestTheNormalPathIsUntouched:
    def test_a_nonzero_count_still_mints_a_token(self):
        h = _handler()
        assert "mint_confirm_token(" in h, "the confirm path was removed, not guarded"

    def test_the_title_still_reports_the_real_numbers(self):
        h = _handler()
        assert 'f"Decompile {int(n_chapters)} chapter(s) into ~{would_arcs} arc(s)"' in h, (
            "the card must keep stating what it will actually do")

    def test_the_dry_run_is_still_returned(self):
        h = _handler()
        assert '"dry_run": {"chapters": int(n_chapters), "would_create_arcs": would_arcs}' in h


class TestTheCountSourceIsPinned:
    """Pinned because I nearly 'fixed' this by changing the source. The dry-run and the engine
    MUST read the same rows, or the card would promise work the engine then declines to do."""

    def test_the_dry_run_counts_outline_node_chapters(self):
        h = _handler()
        assert "FROM outline_node WHERE book_id=$1 AND kind='chapter' AND NOT is_archived" in h

    def test_the_engine_counts_the_same_rows(self):
        eng = (pathlib.Path(__file__).resolve().parents[1]
               / "app" / "engine" / "arc_decompile.py").read_text(encoding="utf-8")
        assert "FROM outline_node WHERE book_id=$1 AND kind='chapter' AND NOT is_archived" in eng, (
            "the engine and the dry-run have drifted apart — the card would promise work the "
            "engine will not do")
