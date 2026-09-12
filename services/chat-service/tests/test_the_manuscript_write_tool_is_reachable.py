"""T3 — the tool that writes prose into the manuscript must be ON THE WIRE in the Studio.

WHY THIS EXISTS, and why it is a guard rather than a change. A 2026-09-06 human-sim run wrote a
5-arc novel by drafting in Co-writer Chat and hand-pasting every scene into the editor, because the
assistant said it had no way to write into the manuscript. The remediation plan sealed a decision
(D3) to hot-seed the `book` domain so that could not happen.

**D3's premise was false.** `book` was ALREADY hot on the studio surface -- added by F14
(round-4 dogfood, 2026-07-20) for exactly this reason -- and `book_chapter_save_draft` is
ADDITIONALLY on the `ALWAYS_HOT_WRITES` allowlist, which is applied outside the token budget so the
seed cannot starve it. Proven by executing `surface_hot_domains`, not by reading a comment: the
comment in `tool_discovery.py` describing these tools as lazy predates F14 and was never updated,
which is how the plan came to seal a decision to build something that already existed.

So the row's GOAL -- reachability -- holds, and what was missing is that **nothing asserted it**.
Both halves are one narrowing away from silently reverting, and the failure mode is invisible: the
model simply stops being able to write, says so politely, and a human pastes prose for a week.

What this does NOT claim: that the model USES the tool. The same run shows it does not, reliably --
the corpus has sessions repeating a refused call 14 and 71 times, and the run's own turn asserted
it had no access while holding the tool. That is a model-capability problem, addressed separately
by T14/T15's escalating refusal, and no amount of seeding fixes it.
"""
from __future__ import annotations

from app.services.tool_discovery import surface_hot_domains
from app.services.tool_surface import ALWAYS_HOT_WRITES

#: The tool that writes prose into `chapter_drafts.body` -- the Manuscript editor's own document.
MANUSCRIPT_WRITE_TOOL = "book_chapter_save_draft"


class TestTheDomainIsHotWhereAnAuthorWrites:
    def test_studio_seeds_the_book_domain(self):
        """The workbench a novelist actually writes in."""
        assert "book" in surface_hot_domains(studio=True, book_scoped=True), (
            "the Studio no longer seeds `book`, so the manuscript write tool needs a find_tools "
            "round-trip the model has been measured NOT to take -- it asserts it cannot write "
            "instead (human-sim, 2026-09-06)"
        )

    def test_the_chapter_editor_seeds_it_too(self):
        assert "book" in surface_hot_domains(editor=True, book_scoped=True)

    def test_a_book_scoped_surface_seeds_it(self):
        assert "book" in surface_hot_domains(book_scoped=True)

    def test_the_universal_surface_does_NOT(self):
        """NV-7 -- an assertion that held on every surface would prove nothing about the ones that
        matter. Universal chat has no book open, so seeding book tools there would be the context
        bloat the discovery design exists to avoid."""
        assert "book" not in surface_hot_domains()


class TestTheWriteToolCannotBeStarvedByTheBudget:
    def test_it_is_on_the_always_hot_allowlist(self):
        """Being in a hot DOMAIN is not sufficient on its own: the seed is token-bounded and orders
        by schema size, which has starved central tools before (`book_update_details`, dogfood
        2026-07-21). The allowlist is applied outside that budget."""
        assert MANUSCRIPT_WRITE_TOOL in ALWAYS_HOT_WRITES

    def test_the_allowlist_is_small_and_deliberate(self):
        """It competes with discovery for the same ceiling, so it must stay a curated set rather
        than becoming the place tools are added to when they are hard to find."""
        assert len(ALWAYS_HOT_WRITES) <= 10, (
            "ALWAYS_HOT_WRITES has grown past a curated set; every entry eats the seed that "
            "starves the next tool"
        )
