"""Two ways the scene path silently starved its own output. Both are architecture, not tuning.

**D-SCENE-OUTPUT-BUDGET-FLAT** — the ceiling had no relationship to the length being asked
for. In `job.input` the two sat ADJACENT and disagreed:

    "target_words": 900,     # what the LENGTH directive asks the model for
    "max_out": 1024,         # what the wire actually allows

900 Vietnamese words is ~2300 tokens, so the model was cut off at roughly a third of the ask
— and it read as the model writing short. Measured on the Mị Đế book: targets of
900/850/800/750/800 produced 445/414/532/618/736 words. The chapter path already sizes its
budget from the plan; the scene path simply never got it.

**D-RECENT-STUB-SUPPRESSES-FALLBACK** — "is there an accepted draft?" was `if paras:`, i.e.
any non-blank line. A chapter holding one stray sentence therefore beat the S1 prior-scene
reinjection, and the whole mechanism went dark while looking healthy. Measured: five drafted
scenes, and every prompt's `<recent>` block held the same 25-word test sentence instead of
the preceding scenes' prose. It had never once run.

Same shape, and the shape is the lesson: **guidance and capability must move as one signal.**
A prompt that asks for 900 words while the wire allows 1024 tokens is not a length
instruction, it is a truncation; a fallback keyed on "any text at all" is not a fallback.
"""
from __future__ import annotations

import pytest

from loreweave_llm import ReasoningDirective

from app.engine.cowrite import DEFAULT_SCENE_TARGET_WORDS, scene_output_budget
from app.packer.lenses import _is_substantial_draft


def _directive(effort: str) -> ReasoningDirective:
    """The budget takes the RESOLVED directive, not a bare effort string — the
    reasoning-SSOT gate bans threading a loose effort through the engine, and it is right
    to: that is exactly how the sixteen drifting copies consolidated earlier came about."""
    return ReasoningDirective(effort=effort, passthrough=False, source="test")


class TestSceneOutputBudget:
    def test_the_ceiling_can_contain_the_length_it_asks_for(self):
        """THE FIX, stated as the invariant: a Vietnamese scene of 900 words needs well
        more than the 1024 tokens the flat default allowed."""
        assert scene_output_budget(900, "vi") > 2000

    def test_it_is_language_aware(self):
        """A word is not a token, and the ratio is not close to 1 outside English.
        Vietnamese carries a diacritic on most syllables, each costing extra BPE pieces."""
        assert scene_output_budget(900, "vi") > scene_output_budget(900, "en")
        assert scene_output_budget(900, "zh") > scene_output_budget(900, "vi")

    def test_a_regional_tag_still_resolves(self):
        assert scene_output_budget(900, "vi-VN") == scene_output_budget(900, "vi")

    def test_an_unknown_or_missing_language_still_gets_room(self):
        """Never fall back to something that truncates: an unknown language must still
        clear the old flat 1024 for a full-length scene."""
        for lang in (None, "", "auto", "qqq"):
            assert scene_output_budget(900, lang) > 1024, lang

    def test_it_scales_with_the_target(self):
        assert scene_output_budget(400, "vi") < scene_output_budget(1200, "vi")

    def test_no_target_uses_the_scene_default_not_zero(self):
        assert scene_output_budget(None, "vi") == scene_output_budget(
            DEFAULT_SCENE_TARGET_WORDS, "vi")

    def test_it_never_exceeds_the_request_bound(self):
        """The computed value must stay inside the schema's own bound, or it would 422 a
        request the author never made."""
        from app.engine.cowrite import SCENE_OUTPUT_CEILING
        assert scene_output_budget(100_000, "zh") <= SCENE_OUTPUT_CEILING

    def test_it_is_always_at_least_one(self):
        assert scene_output_budget(1, "en") >= 1

    def test_reasoning_gets_its_own_room_on_top(self):
        """Thinking tokens are spent BEFORE the prose and drawn from the SAME allowance.
        Unaccounted, enabling reasoning silently halves the space left for the passage —
        the 'empty ghost' this repo has already shipped once (a reasoning model spending
        its whole budget on hidden reasoning and returning text='', billed as success)."""
        plain = scene_output_budget(900, "vi", reasoning=_directive("none"))
        low = scene_output_budget(900, "vi", reasoning=_directive("low"))
        high = scene_output_budget(900, "vi", reasoning=_directive("high"))
        assert plain < low < high
        # The prose allowance must SURVIVE the thinking, not be shared with it.
        assert high - plain >= plain, "high-effort thinking needs room comparable to the prose"

    def test_an_unknown_effort_is_provisioned_not_ignored(self):
        """A new effort label must not silently fall back to 'no thinking room' — that is
        the failure mode this allowance exists to prevent."""
        assert scene_output_budget(
            900, "vi", reasoning=_directive("xhigh"),
        ) > scene_output_budget(900, "vi", reasoning=_directive("none"))

    def test_the_ceiling_is_a_runaway_guard_not_a_budget(self):
        """A real 5-scene Vietnamese chapter at ~900 words each needs ~12k tokens before
        any thinking. A ceiling a real book can REACH is shaping output, not guarding."""
        from app.engine.cowrite import SCENE_OUTPUT_CEILING
        five_scene_chapter = 5 * scene_output_budget(
            900, "vi", reasoning=_directive("medium"))
        assert SCENE_OUTPUT_CEILING > five_scene_chapter / 2, (
            "the guard is close enough to real usage to start truncating"
        )


class TestSubstantialDraft:
    """What separates 'the author has written into this chapter' from 'there is a line in
    here'. Deliberately low bars — this is not judging quality."""

    def test_a_single_stray_sentence_is_NOT_a_draft(self):
        """The live case, verbatim: one line typed to check that Save works. It used to
        beat the prior-scene reinjection and switch the mechanism off."""
        stub = ["Máu đã ngừng chảy từ lâu, nhưng mùi tanh vẫn đọng lại trong không khí "
                "như một lời buộc tội không ai dám nói ra."]
        assert not _is_substantial_draft(stub)

    def test_an_empty_draft_is_not_a_draft(self):
        assert not _is_substantial_draft([])

    def test_a_real_scene_is_a_draft_by_length_alone(self):
        assert _is_substantial_draft([" ".join(["chữ"] * 200)])

    def test_two_paragraphs_are_a_draft_even_if_short(self):
        """A chapter with several paragraphs is being written in, whatever their length —
        and its own tail is the better 'story so far' than regenerated scenes."""
        assert _is_substantial_draft(["Mở đầu.", "Rồi nàng quay đi."])


@pytest.mark.asyncio
async def test_a_stub_draft_is_kept_AND_the_prior_scenes_are_reinjected():
    """Below the floor the two sources are UNIONED, not exchanged: a stub is usually a
    heading or opening line the author does want honoured, so dropping it would trade one
    silent loss for another. Order matters — the author's line leads."""
    from unittest.mock import AsyncMock

    from app.packer.lenses import gather_recent

    book = AsyncMock()
    book.get_draft = AsyncMock(return_value={"text_content": "Chương 1"})
    jobs = AsyncMock()
    jobs.prior_scene_drafts = AsyncMock(return_value=["Cảnh một.", "Cảnh hai."])

    import uuid
    out = await gather_recent(
        book, uuid.uuid4(), uuid.uuid4(), "bearer",
        jobs_repo=jobs, project_id=uuid.uuid4(), story_order=3,
    )
    assert out == ["Chương 1", "Cảnh một.", "Cảnh hai."]


@pytest.mark.asyncio
async def test_a_real_draft_still_wins_outright():
    """The primary source is unchanged for a chapter that genuinely has prose: its own
    tail is more accurate than regenerated scene winners."""
    from unittest.mock import AsyncMock

    from app.packer.lenses import gather_recent

    body = "\n".join(f"Đoạn {i}." for i in range(6))
    book = AsyncMock()
    book.get_draft = AsyncMock(return_value={"text_content": body})
    jobs = AsyncMock()
    jobs.prior_scene_drafts = AsyncMock(return_value=["KHÔNG ĐƯỢC DÙNG"])

    import uuid
    out = await gather_recent(
        book, uuid.uuid4(), uuid.uuid4(), "bearer",
        jobs_repo=jobs, project_id=uuid.uuid4(), story_order=3,
    )
    assert "KHÔNG ĐƯỢC DÙNG" not in out
    jobs.prior_scene_drafts.assert_not_awaited()
