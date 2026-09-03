"""A flag that accuses must say what it is accusing.

    THE INVARIANT. When 'READ-INTENT TURN WROTE TO THE STORE' fires, it names the table(s) the
    verdict actually rests on, and names separately anything it touched but EXCUSED.

OWNER RULING 2026-08-31, DQ-T43: "NAME THE EVENT TYPE. The runner's flag must not fire silently
on the platform's own per-turn lifecycle event — either exclude platform events or say which
event wrote, so a reader can tell a tool's write from the turn's own bookkeeping."

THE MEASUREMENT THAT RAISED IT: batch c-regwf5 flagged 'READ-INTENT TURN WROTE in 3/5 runs —
loreweave_knowledge.extraction_pending'. All five runs called registry_list_workflows and nothing
else, so no tool in the turn wrote anything. The row was the platform's own `chat.turn_completed`
event, parked because extraction is disabled for the fixture project.

🔴 HALF THE RULING WAS ALREADY BUILT AND THE OTHER HALF WAS NOT, which is why this exists rather
than a new exclusion: `loreweave_knowledge.extraction_pending` is in TURN_BOOKKEEPING_TABLES, so
the lifecycle event no longer trips the flag at all. But the FIRING path still ended at "a defect
whatever it said" with no table named — and that is the path a reader actually meets when
something is wrong.
"""
from __future__ import annotations

import inspect
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from scripts.toolloop import fe_runner as fr  # noqa: E402


class TestTheExclusionHalfIsReallyBuilt:
    def test_the_lifecycle_table_is_excluded_from_the_verdict(self):
        assert "loreweave_knowledge.extraction_pending" in fr.TURN_BOOKKEEPING_TABLES

    def test_a_run_that_touched_ONLY_the_lifecycle_table_is_not_a_violation(self):
        """Driving the SHIPPED predicate, not a copy of it — the module's own docstring records
        that a guard which re-implemented this logic passed an over-broad injection."""
        run = {"turn_started_at": None,
               "store_diff": {"loreweave_knowledge.extraction_pending":
                              {"before": {"rows": 0}, "after": {"rows": 1}}}}
        assert fr.read_intent_violations([run]) == [], (
            "the platform's own per-turn bookkeeping is counted as a read-intent violation")

    def test_a_REAL_write_beside_the_lifecycle_table_still_violates(self):
        """The exclusion must not swallow a genuine write that happens to share the run. The
        module records that an over-broad version would have hidden 54 such runs."""
        run = {"turn_started_at": None,
               "store_diff": {"loreweave_knowledge.extraction_pending":
                              {"before": {"rows": 0}, "after": {"rows": 1}},
                              "loreweave_book.chapters":
                              {"before": {"rows": 1}, "after": {"rows": 2}}}}
        assert fr.read_intent_violations([run]), (
            "a real write was excused because a bookkeeping table was written in the same run")


class TestTheFiringPathNamesWhatWrote:
    @staticmethod
    def _src() -> str:
        return inspect.getsource(fr.summarise) if hasattr(fr, "summarise") else \
            pathlib.Path(inspect.getfile(fr)).read_text(encoding="utf-8")

    def test_the_verdict_line_names_the_tables(self):
        """🔴 THE HALF THAT WAS MISSING. Firing said only 'a defect whatever it said', so a
        reader could not tell which table carried the verdict without opening the raw JSON."""
        src = self._src()
        i = src.index("READ-INTENT TURN WROTE TO THE STORE")
        window = src[i - 900:i + 600]
        assert "_tables" in window, (
            "the firing line does not collect the tables the verdict rests on")
        assert "join(_tables)" in window or "', '.join(_tables)" in window, (
            "the tables are collected and not printed")

    def test_it_names_an_EXCUSED_table_separately_rather_than_silently(self):
        """Naming only the accusation leaves a reader wondering whether the bookkeeping row
        counted. It did not, and the line now says so in the same breath."""
        src = self._src()
        i = src.index("READ-INTENT TURN WROTE TO THE STORE")
        window = src[i:i + 900]
        assert "NOT part of this flag" in window
        assert "chat.turn_completed" in window, (
            "the excused row is named without naming the EVENT that writes it, which is the "
            "thing the ruling asked for by name")

    def test_the_named_tables_are_the_ones_the_VERDICT_used(self):
        """A line that named every touched table would re-introduce the defect: the reader
        would see the bookkeeping table in the accusation again. The accusation must list only
        tables that survive the same exclusion `read_intent_violations` applies."""
        src = self._src()
        i = src.index("READ-INTENT TURN WROTE TO THE STORE")
        window = src[i - 900:i]
        for name in ("TURN_BOOKKEEPING_TABLES", "READ_AUDIT_TABLES",
                     "UNATTRIBUTABLE_GLOBAL_COUNTS"):
            assert name in window, (
                f"the accusation's table list does not apply {name}, so an excused table would "
                "be named as the defect")
        assert "_changed_during_the_turn" in window, (
            "a change that PREDATES the turn would be named as this turn's write")


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))
