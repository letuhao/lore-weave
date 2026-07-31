"""D-CROSS-SCENE-CONTRADICTION — the seam check, and the control that killed its first version.

The first implementation asked the judge "report only DIRECT CONTRADICTIONS". Run live against
the exact pair that shipped unnoticed, plus a hand-consistent control:

    SEEDED (he→she)        contradictions=0
    CONTROL (consistent)   contradictions=0

Identical answers on a seeded defect and its control. That is not a weak detector, it is one
that cannot fail — so the comparison moved into code, where these tests can pin it.

Every test here runs `compare_people` directly: no model, no network. That is the point of the
redesign — the half that decides is deterministic.
"""
from __future__ import annotations

import pytest

from app.engine.cross_scene_check import (
    CrossSceneResult,
    build_extract_prompt,
    check_chapter_consistency,
    compare_people,
)


def P(who, pronoun="none", role=""):
    return {"who": who, "pronoun": pronoun, "role": role}


# ══ it must FIRE — the half the first version could not do ══

def test_a_named_character_who_changes_gender_is_caught():
    r = compare_people([P("Elara", "she"), P("Cassius", "he")],
                       [P("Elara", "he"), P("Cassius", "he")])
    assert len(r.contradictions) == 1
    c = r.contradictions[0]
    assert "Elara" in c.what and "she" in c.what and "he" in c.what


def test_the_finding_quotes_both_sides_so_an_author_can_judge_it():
    r = compare_people([P("Elara", "she", "cartographer")], [P("Elara", "he", "scribe")])
    c = r.contradictions[0]
    assert "she" in c.earlier and "cartographer" in c.earlier
    assert "he" in c.later and "scribe" in c.later


def test_a_possessive_or_article_does_not_hide_the_match():
    r = compare_people([P("Elara’s", "she")], [P("the Elara", "he")])
    assert len(r.contradictions) == 1


# ══ the negative control — a detector that only ever fires is not a detector ══

def test_a_consistent_seam_is_quiet():
    r = compare_people([P("Elara", "she"), P("Cassius", "he")],
                       [P("Elara", "she"), P("Cassius", "he")])
    assert r.contradictions == [] and r.clean is True


def test_an_ambiguous_pronoun_is_not_a_contradiction():
    """`they`/`none` are a plural, an unresolved referent, or a deliberate withholding.
    Claiming a fact changed from those would manufacture findings."""
    for later in ("they", "none"):
        r = compare_people([P("Elara", "she")], [P("Elara", later)])
        assert r.contradictions == [], later


def test_a_role_change_alone_is_not_a_contradiction():
    """People gain roles — that is a story moving, not a defect."""
    r = compare_people([P("Elara", "she", "apprentice")], [P("Elara", "she", "anchor")])
    assert r.contradictions == []


def test_two_different_people_sharing_a_pronoun_are_not_linked():
    """Matching on "she" would fuse every woman in the chapter into one person."""
    r = compare_people([P("she", "she"), P("the woman", "she")],
                       [P("she", "he"), P("the figure", "he")])
    assert r.contradictions == []
    assert r.linked == 0


# ══ coverage — the honest half ══

def test_an_unlinkable_seam_reports_unlinked_rather_than_clean():
    """THE measured case: "the anchor" (he) → "the Scribe" (she). Linking those needs
    coreference the model demonstrably cannot do, so this check does NOT catch it — and must
    not report a clean seam. `clean` is False because nothing was compared."""
    r = compare_people([P("the anchor", "he")], [P("the Scribe", "she")])
    assert r.contradictions == []
    assert r.linked == 0
    assert r.unlinked_earlier == 1 and r.unlinked_later == 1
    assert r.clean is False, "nothing was compared — that is not a clean seam"


def test_clean_requires_something_to_have_been_compared():
    assert compare_people([], []).clean is False
    assert compare_people([P("Elara", "she")], [P("Elara", "she")]).clean is True


def test_pronouns_and_bare_role_words_are_not_names():
    r = compare_people([P("her", "she"), P("the man", "he")],
                       [P("her", "he"), P("the man", "she")])
    assert r.linked == 0 and r.contradictions == []


# ══ degrade-safe ══

class _LLM:
    def __init__(self, replies, status="completed"):
        self._replies = list(replies)
        self._status = status
        self.calls = 0

    async def submit_and_wait(self, **kw):
        from types import SimpleNamespace
        self.calls += 1
        body = self._replies.pop(0) if self._replies else '{"people": []}'
        return SimpleNamespace(status=self._status,
                               result={"messages": [{"content": body}]})


@pytest.mark.asyncio
async def test_one_scene_is_skipped_not_checked():
    r = await check_chapter_consistency(_LLM([]), user_id="u", model_source="s",
                                        model_ref="m", scenes=["only one"])
    assert r.status == "skipped_single_scene"


@pytest.mark.asyncio
async def test_a_non_completed_extraction_degrades_and_never_reads_clean():
    llm = _LLM(['{"people": []}'], status="failed")
    r = await check_chapter_consistency(llm, user_id="u", model_source="s", model_ref="m",
                                        scenes=["a", "b"])
    assert r.status == "degraded" and r.clean is False


@pytest.mark.asyncio
async def test_the_live_path_fires_on_a_gender_flip():
    # `name` is not decoration in this fixture: the identity key is the PROPER NAME, and the
    # real `extract_people` always emits the field. A fake that omits it describes a producer
    # that does not exist, and would make this test pass or fail for reasons the live path
    # never sees. (Measured: without it, `linked` is 0 and this assertion goes red.)
    llm = _LLM(['{"people": [{"who": "Elara", "name": "Elara", "pronoun": "she", "role": "scribe"}]}',
                '{"people": [{"who": "Elara", "name": "Elara", "pronoun": "he", "role": "scribe"}]}'])
    r = await check_chapter_consistency(llm, user_id="u", model_source="s", model_ref="m",
                                        scenes=["earlier", "later"])
    assert r.status == "checked" and len(r.contradictions) == 1
    assert llm.calls == 2, "one extraction per side of the seam"


def test_the_prompt_asks_for_extraction_not_for_a_verdict():
    """The regression that matters most: reverting to "find the contradictions" restores a
    check that returned 0 on a seeded defect AND on its control."""
    p = build_extract_prompt("en")
    assert "For each PERSON" in p and '"pronoun"' in p
    assert "contradiction" not in p.lower(), "the model must extract, never judge"


def test_the_result_defaults_are_not_a_green():
    r = CrossSceneResult(status="degraded")
    assert r.clean is False
