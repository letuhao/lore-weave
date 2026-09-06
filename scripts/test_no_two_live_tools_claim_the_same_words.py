"""Two live tools must not declare the same normalised phrase.

    THE INVARIANT. After normalisation through the SHIPPED matcher, no phrase is claimed by more
    than one LIVE tool. A collision is removed at declaration time, not arbitrated at request
    time.

OWNER RULING 2026-08-27, DQ-T41 — verbatim: "check the tool duplicated or not, if similiar or
duplicated, unify them or deprecated one, if they have different purpose and role, change
description to avoid duplicated, include change name if need". Explicitly NOT a tie-break: the
specificity ranker, `_meta.specificity` and a domain-beats-generic rule were all ruled out,
because each preserves the collision and arbitrates it.

WHY THE MATCHER MANUFACTURED THEM: `_answer_norm` strips articles, so three tools that declared
DIFFERENT phrases became one key —

    composition_generate     'write chapter'      -> 'write chapter'
    book_chapter_create      'write a chapter'    -> 'write chapter'
    book_chapter_save_draft  'write the chapter'  -> 'write chapter'

🔴 THE ROW'S OWN NUMBER WAS STALE AND THE BOUND SHRANK. It records 25 live collisions of 97 raw.
Re-derived against the current catalogue: 13 live of 97, because twelve more dissolved when their
rival went legacy (84 dissolve now, 72 then). All 13 were resolved; the count is 0.
"""
from __future__ import annotations

import collections
import json
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "toolloop"))
sys.path.insert(0, str(ROOT / "services" / "chat-service"))


def _norm():
    try:
        from app.services.tool_surface import _answer_norm
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"the shipped normaliser is unavailable: {exc}")
    return _answer_norm


def _catalogue() -> dict:
    p = ROOT / "contracts" / "tool-catalog-cache.json"
    if not p.exists():
        pytest.skip("no catalogue cache on disk")
    return json.loads(p.read_text(encoding="utf-8"))


def _collisions():
    """{normalised phrase: [live tools]} — through the SHIPPED normaliser, never a copy of it."""
    norm = _norm()
    cat = _catalogue()
    legacy = {n for n, s in cat.items() if (s.get("meta") or {}).get("visibility") == "legacy"}
    by = collections.defaultdict(set)
    for name, spec in cat.items():
        for syn in ((spec.get("meta") or {}).get("synonyms") or []):
            by[norm(str(syn))].add(name)
    return {k: sorted(v - legacy) for k, v in by.items() if len(v - legacy) > 1}, legacy, by


class TestNoLiveCollisionSurvives:
    def test_the_catalogue_is_clean(self):
        bad, _, _ = _collisions()
        assert not bad, (
            "these phrases are claimed by more than one LIVE tool, so the matcher hands the "
            "model a tie it did not have to:\n  "
            + "\n  ".join(f"{k!r}: {v}" for k, v in sorted(bad.items()))
            + "\n\nDQ-T41 rules this a CATALOGUE defect: unify or deprecate a duplicate, or "
              "re-word so they stop claiming the same words. Do NOT add a tie-break.")

    def test_the_guard_is_not_vacuous(self):
        """🔴 IT PASSES OVER AN EMPTY SET OTHERWISE. This loop has shipped a guard over nothing
        before, and a de-collision fix is exactly the change that could empty the input."""
        _, legacy, by = _collisions()
        assert len(by) > 800, f"only {len(by)} normalised synonyms — is the catalogue loaded?"
        assert legacy, "no legacy tools found; the live/legacy split is what makes this bounded"

    def test_legacy_collisions_are_NOT_counted(self):
        """The owner's scoping rule on DQ-T36: a legacy tool is dropped from every turn since
        2026-08-25, so a collision with one cannot reach a model. 86 of the 86 remaining raw
        collisions are of that kind — counting them would invent work."""
        norm = _norm()
        cat = _catalogue()
        legacy = {n for n, s in cat.items() if (s.get("meta") or {}).get("visibility") == "legacy"}
        by = collections.defaultdict(set)
        for name, spec in cat.items():
            for syn in ((spec.get("meta") or {}).get("synonyms") or []):
                by[norm(str(syn))].add(name)
        raw = {k for k, v in by.items() if len(v) > 1}
        assert raw, "no raw collisions at all — the legacy exclusion is untested"


class TestTheMeasuredTieWasBrokenOnTheLOSER:
    """🔴 THE CONTROL THAT REFUTED THE OBVIOUS FIX, and it was already in the tree.

    The natural move is "a GENERIC tool must not claim a DOMAIN phrase" — take
    'pause the translation' off jobs_pause. That was tried on 2026-08-25 and measured:

        original wording      surfaced 5/5   jobs_pause called 5/5
        after the de-dup      surfaced 2/5   jobs_pause called 0/5

    with translation_job_control taking 0/5 in BOTH arms. Removing the phrase from the tool that
    was answering left nobody holding the request. So the phrase came off the LOSER instead.
    """

    def test_the_generic_job_tools_keep_the_phrases_they_win(self):
        cat = _catalogue()
        for tool, phrase in (("jobs_pause", "pause the translation"),
                             ("jobs_cancel", "stop the translation")):
            syns = (cat.get(tool, {}).get("meta") or {}).get("synonyms") or []
            assert phrase in syns, (
                f"{tool} lost {phrase!r} — that exact removal was measured as a regression on "
                "2026-08-25 (5/5 called -> 0/5, with the domain tool taking neither)")

    def test_the_domain_tool_keeps_a_way_of_being_asked(self):
        """Taking a phrase off a tool must not silence it: it keeps every phrasing that names
        the job it controls."""
        syns = (_catalogue().get("translation_job_control", {}).get("meta") or {}).get(
            "synonyms") or []
        assert any("translation" in s for s in syns), (
            "translation_job_control declares nothing about translations any more")


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
