"""When knowledge-service grows a SECOND finding type, it needs one locator. Not before.

The state, measured 2026-08-03
------------------------------
Composition has five finding producers carrying five locators, so S3's `Locator` union earned
its place there — with a consumer that needed it (the Polish panel was reporting "clean" on a
run whose findings nothing could place). Knowledge has exactly ONE: `ExtractionCanonCandidate`,
whose position already reaches a human hand-written into the quarantine row's context
(`entity_id`, `name`, `span`).

A union of one is ceremony. Building `Locator` here today would be the same
shape-with-no-consumer defect the composition slice deliberately avoided by looking for the
reader first — and the argument would be symmetry, which is not a consumer.

Why this file exists anyway
---------------------------
Because the alternative is a sentence in a doc, and this repo has measured what that is worth:
S9's SDK-extraction criterion was a spec sentence until it became `guard-sdk-entry-gate.py`,
after the run recorded that nobody re-reads a July spec line to discover a condition became
true. The same reasoning applies to a criterion that says "not yet".

So the condition is asserted rather than remembered: the moment a second finding-shaped class
appears here, this test reds and asks for the union — pointing at the one that already exists
in `composition/app/engine/finding.py` rather than at a fresh invention.
"""
from __future__ import annotations

import ast
import pathlib

APP = pathlib.Path(__file__).resolve().parents[2] / "app"

#: What makes a class a FINDING here: it says so in its name, or it extends the shared canon
#: candidate base. Not "Candidate" by name — the first draft used that and matched
#: `CandidatePair` (two mentions considered for coreference) and `EntityCandidate` (a name the
#: pattern detector surfaced). Neither is a finding about a POSITION; they are candidates for
#: a decision, and counting them would have fired this criterion for the wrong reason on the
#: day it was written. Judged by what the class IS, which for the one real finding here is
#: `CanonCandidateBase` — the SDK type both services already share.
_NAME = ("Finding", "Violation")
_FINDING_BASE = {"CanonCandidateBase"}

#: Exceptions are not findings: they are raised and caught, never collected into a list a
#: report renders. Judged by BASE, not by a name ending in "Error" — a class called
#: `SomethingViolation(Exception)` slips a name check.
_NOT_A_FINDING_BASE = {"Exception", "ValueError", "RuntimeError", "KeyError"}


def _finding_classes() -> dict[str, str]:
    out: dict[str, str] = {}
    for p in sorted(APP.rglob("*.py")):
        if "/tests/" in p.as_posix():
            continue
        try:
            tree = ast.parse(p.read_text(encoding="utf-8", errors="ignore"))
        except SyntaxError:
            continue
        for n in ast.walk(tree):
            if not isinstance(n, ast.ClassDef):
                continue
            bases = {getattr(b, "id", getattr(b, "attr", "")) for b in n.bases}
            if not (any(w in n.name for w in _NAME) or bases & _FINDING_BASE):
                continue
            if bases & _NOT_A_FINDING_BASE:
                continue
            out[n.name] = p.relative_to(APP).as_posix()
    return out


def test_the_detector_finds_the_one_we_know_about():
    """Without this the criterion below passes by counting nothing."""
    found = _finding_classes()
    assert "ExtractionCanonCandidate" in found, (
        f"the known finding type is not in the detected set — the predicate drifted. "
        f"Found: {sorted(found)}"
    )


def test_a_SECOND_finding_type_here_means_this_service_needs_the_locator_union():
    found = _finding_classes()
    assert len(found) == 1, (
        f"knowledge-service now has {len(found)} finding-shaped types: {sorted(found)}.\n"
        f"One was a union of one, which is why `Locator` was NOT built here. Two is the "
        f"point at which their positions can disagree — adopt the union that already exists "
        f"in `composition-service/app/engine/finding.py` (`Locator` / `LocatorKind`) rather "
        f"than inventing a second one, and give `ExtractionCanonCandidate` a projection at "
        f"the same time. `UNLOCATED` is the member to carry over first: a candidate with no "
        f"entity to point at is a hole in coverage, not a finding about nobody."
    )
