"""A whole-run reader must see the whole run, not its last arc.

THE INVARIANT. A run emits ONE PACKAGE ARTIFACT PER ARC, so any read that hands a package to a
model or a rule must fold latest-per-arc. `latest_artifact(book_id, run_id, "package")` returns
the LAST arc and silently drops the rest.

OWNER RULING DQ-T85 (a), 2026-08-31: fold latest-per-arc, chapters concatenated in arc order, and
fix BOTH readers in the same change — "leaving one of two identical reads unfixed is how OBS-T1
sat unfiled inside another row's prose for weeks."

🔴 MEASURED IN THE LIVE STORE, and the denominator is not the obvious one. 34 runs hold more than
one package ARTIFACT, but 18 of those are re-compiles of a SINGLE arc, which the fold collapses
and where the old read was already complete. The affected population is the 16 runs holding more
than one ARC, and on those the latest read carried 21 of 64 chapters — 32.8%.
"""
from __future__ import annotations

import ast
import inspect
import pathlib

from app.services.bootstrap_service import (
    _PER_ARC_LISTS,
    compiled_package_across_arcs,
    folded_package_across_arcs,
)


class _Art:
    """The duck type both readers get from `list_artifacts`: oldest first, `.content`, `.id`."""

    def __init__(self, content, ident="a"):
        self.content = content
        self.id = ident


def _arc(arc_id, chapters, events=(), premise="p", beats=None):
    pkg = {"arc_id": arc_id, "premise": premise,
           "chapters": list(chapters), "events": list(events)}
    if beats is not None:
        pkg["beats"] = list(beats)
    return _Art({"planning_package": pkg})


class TestTheFoldSeesEveryArc:
    def test_chapters_are_concatenated_in_ARC_ORDER(self):
        """Oldest-first is compile order, which is the author's arc order — `apply` creates
        chapters in list order, so this ordering IS the book's order."""
        got = folded_package_across_arcs([
            _arc("A1", [{"t": "one"}, {"t": "two"}]),
            _arc("A2", [{"t": "three"}]),
            _arc("A3", [{"t": "four"}]),
        ])
        assert [c["t"] for c in got["chapters"]] == ["one", "two", "three", "four"]

    def test_events_fold_too_because_the_store_says_they_are_per_arc(self):
        """On a 3-arc run the store holds 3 distinct `events` blobs, one per arc — the same
        shape as chapters, and the row measured the same 218-vs-84 split on both."""
        got = folded_package_across_arcs([
            _arc("A1", [], events=[{"e": 1}]),
            _arc("A2", [], events=[{"e": 2}]),
        ])
        assert [e["e"] for e in got["events"]] == [1, 2]

    def test_a_RECOMPILED_arc_replaces_itself_and_is_not_offered_twice(self):
        """🔴 THE RULE A PLAIN CONCAT GETS WRONG, and the majority case in the live store: 18 of
        the 34 multi-artifact runs are re-compiles of ONE arc. Concatenating every artifact would
        offer that arc's chapters two or three times."""
        got = folded_package_across_arcs([
            _arc("A1", [{"t": "draft"}]),
            _arc("A2", [{"t": "other"}]),
            _arc("A1", [{"t": "revised"}]),
        ])
        assert [c["t"] for c in got["chapters"]] == ["revised", "other"], (
            "a re-compile did not replace its own arc in place — either the arc appeared twice "
            "or it moved out of authored order")

    def test_an_artifact_with_no_arc_id_is_neither_dropped_nor_deduped(self):
        """A pre-per-arc run, or a whole-run compile. Every artifact in today's store carries an
        arc_id (0 of 84 without), but the fallback must not silently merge two such artifacts."""
        got = folded_package_across_arcs([
            _Art({"planning_package": {"chapters": [{"t": "x"}]}}, ident="i1"),
            _Art({"planning_package": {"chapters": [{"t": "y"}]}}, ident="i2"),
        ])
        assert [c["t"] for c in got["chapters"]] == ["x", "y"]

    def test_no_package_artifacts_is_None_not_an_empty_package(self):
        """Both callers previously got None from `latest_artifact(...) if pkg_art else None`, and
        `run_rules` branches on `if package:`. An empty dict would change that branch."""
        assert folded_package_across_arcs([]) is None
        assert folded_package_across_arcs([_Art({"no_package": True})]) is None


class TestWhatIsDeliberatelyNotFolded:
    def test_BEATS_IS_NOT_FOLDED_because_folding_it_would_TRIPLE_it(self):
        """🔴 THE BUG THIS GUARD EXISTS FOR was one edit away from shipping. `beats` looks like a
        per-arc list and is not: on the genuinely multi-arc runs the store holds ONE distinct
        beats blob across all three arcs (or none), while chapters and events hold three. It is
        whole-plan, so concatenating it repeats the same beats once per arc."""
        assert "beats" not in _PER_ARC_LISTS
        whole_plan_beats = [{"b": 1}, {"b": 2}]
        got = folded_package_across_arcs([
            _arc("A1", [{"t": "one"}], beats=whole_plan_beats),
            _arc("A2", [{"t": "two"}], beats=whole_plan_beats),
            _arc("A3", [{"t": "three"}], beats=whole_plan_beats),
        ])
        assert got["beats"] == whole_plan_beats, (
            f"beats was repeated per arc: {len(got['beats'])} entries where the plan has "
            f"{len(whole_plan_beats)}")

    def test_PREMISE_is_carried_not_concatenated(self):
        """🔴 THE CONTROL THAT DECIDED THIS. `validate()`'s only package-derived rule is
        `premise_max` (len <= 4000). Summed across arcs the longest run in the store reaches
        6,292 chars, so concatenating premises would make ONE OF THE 34 RUNS newly FAIL a rule it
        passes today. Turning a passing plan into a failing one is not a bug fix, and no ruling
        asked for it — the owner ruled on chapters."""
        got = folded_package_across_arcs([
            _arc("A1", [], premise="x" * 3000),
            _arc("A2", [], premise="y" * 3000),
        ])
        assert len(got["premise"]) == 3000, (
            "premises were concatenated — premise_max now measures the whole run instead of an "
            "arc, and a plan that passes today would start failing")
        assert got["premise"] == "y" * 3000, "the carried scalar is not the LAST arc's"

    def test_it_records_which_arcs_it_folded(self):
        """A reader that folded 3 arcs should be able to say so, rather than a later measurement
        re-deriving it."""
        got = folded_package_across_arcs([_arc("A1", []), _arc("A2", [])])
        assert got["folded_arc_ids"] == ["A1", "A2"]


class TestBothRuledReadersUseIt:
    """The ruling names TWO sites and the reason is explicit: an unfixed twin is how the sibling
    observation went unqueued. A guard on one of them would repeat that."""

    @staticmethod
    def _forge_source() -> str:
        import app.services.plan_forge_service as pf
        return pathlib.Path(inspect.getfile(pf)).read_text(encoding="utf-8")

    def test_neither_validate_nor_refine_still_reads_a_single_package(self):
        tree = ast.parse(self._forge_source())
        bad = [
            n.lineno for n in ast.walk(tree)
            if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Attribute) and n.func.attr == "latest_artifact"
            and any(isinstance(a, ast.Constant) and a.value == "package" for a in n.args)
        ]
        assert not bad, (
            f'latest_artifact(..., "package") still called at line(s) {bad} — that read returns '
            "ONE ARC, and a run emits one package per arc")

    def test_both_sites_call_the_fold(self):
        src = self._forge_source()
        assert src.count("folded_package_across_arcs(") >= 2, (
            "only one of the two ruled readers folds — the ruling fixed both in the same change "
            "precisely so the twin could not be forgotten")


class TestTheRuleHasONEHome:
    def test_the_two_folds_share_their_latest_per_arc_logic(self):
        """Consolidation claimed in a docstring is not consolidation. `compiled_package_across_arcs`
        and `folded_package_across_arcs` must both go through `_latest_content_per_arc`, or the
        latest-per-arc rule has two implementations and one of them will drift."""
        for fn in (compiled_package_across_arcs, folded_package_across_arcs):
            assert "_latest_content_per_arc" in inspect.getsource(fn), (
                f"{fn.__name__} restates the arc rule instead of sharing it")

    def test_the_two_agree_on_the_chapters_they_return(self):
        """The behavioural half of the same claim: the older fold and the new one must never
        disagree about what a run's chapters are."""
        arts = [_arc("A1", [{"t": "one"}]), _arc("A2", [{"t": "two"}]), _arc("A1", [{"t": "1b"}])]
        chapters, _ = compiled_package_across_arcs(arts)
        assert chapters == folded_package_across_arcs(arts)["chapters"]


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))
