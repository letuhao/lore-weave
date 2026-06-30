"""Unit tests for planning Stage 4 — grounded_decompose (engine/grounded_plan.py)
+ the grounding block of build_scene_decompose_messages.

Pins: the per-beat motif filter, the introduction-schedule mapping, the grounding
directives reaching the L2 prompt, and that the orchestrator threads all of it.
"""

import json
from types import SimpleNamespace

from app.engine.plan import ChapterPlan, build_scene_decompose_messages
from app.engine.grounded_plan import grounded_decompose, intros_by_chapter, motifs_for_beat

_MOTIFS = [
    {"name": "Xấu hóa mỹ", "arc_role": "central spine"},
    {"name": "Phục thù", "arc_role": "climax payoff"},
    {"name": "Ma công", "arc_role": "foil"},
]


# ── pure helpers ──

def test_motifs_for_beat_by_role():
    setup = [m["name"] for m in motifs_for_beat(_MOTIFS, "establishment")]
    assert setup == ["Xấu hóa mỹ"]                       # only the spine (foil/payoff don't fit)
    conflict = [m["name"] for m in motifs_for_beat(_MOTIFS, "rising_conflict")]
    assert conflict == ["Xấu hóa mỹ", "Ma công"]         # spine + foil
    climax = [m["name"] for m in motifs_for_beat(_MOTIFS, "climax")]
    assert climax == ["Xấu hóa mỹ", "Phục thù"]          # spine + climax payoff


def test_motifs_for_beat_unrecognised_role_is_always_offered():
    # an off-vocabulary arc_role must NOT be silently dropped from every chapter
    odd = [{"name": "Subplot motif", "arc_role": "thematic undercurrent"}]
    assert [m["name"] for m in motifs_for_beat(odd, "establishment")] == ["Subplot motif"]
    assert [m["name"] for m in motifs_for_beat(odd, "climax")] == ["Subplot motif"]


def test_intros_by_chapter_filters_range_and_from_start():
    arcs = [
        {"name": "MC", "introduce_at_chapter": 1},           # from start → not staged
        {"name": "Foil", "introduce_at_chapter": 7},
        {"name": "Ally", "introduce_at_chapter": 7},
        {"name": "OutOfRange", "introduce_at_chapter": 99},  # > n → dropped
        {"name": "NoIntro"},                                 # None → not staged
    ]
    out = intros_by_chapter(arcs, n_chapters=12)
    assert out == {7: ["Foil", "Ally"]}


# ── the grounding prompt ──

def test_build_messages_grounding_block_present_and_optional():
    ch = ChapterPlan(chapter_id="c", title="t", sort_order=1, beat_role="climax", intent="i")
    sys_, usr = build_scene_decompose_messages(
        "p", ch, "bp", ["Lâm Uyển"], 1, 6, "vi",
        tension_target=88, motifs=[{"name": "Phục thù", "arc_role": "climax payoff"}],
        new_intros=["Lục Vô Trần"])
    assert "GROUNDING DIRECTIVES:" in usr
    assert "TENSION TARGET" in usr and "88/100" in usr
    assert "Phục thù (climax payoff)" in usr
    assert "INTRODUCE THIS CHAPTER" in usr and "Lục Vô Trần" in usr
    # back-compat: no grounding args → no block
    sys0, usr0 = build_scene_decompose_messages("p", ch, "bp", ["Lâm Uyển"], 1, 6, "vi")
    assert "GROUNDING DIRECTIVES" not in usr0


# ── orchestrator ──

class _GroundedLLM:
    """L1 (STRUCTURE BEATS) → a fixed chapter-map; L2 → scenes+exit, capturing each L2 user prompt."""

    def __init__(self, l1, l2):
        self._l1, self._l2 = l1, l2
        self.l2_prompts: list[str] = []

    async def submit_and_wait(self, **kw):
        user = kw["input"]["messages"][1]["content"]
        if "STRUCTURE BEATS" in user:
            return SimpleNamespace(status="completed", result={"messages": [{"content": self._l1}]})
        self.l2_prompts.append(user)
        return SimpleNamespace(status="completed", result={"messages": [{"content": self._l2}]})


async def test_grounded_decompose_threads_all_inputs_into_l2():
    l1 = json.dumps({"chapters": [{"index": 1, "beat": "setup", "intent": "open"},
                                  {"index": 2, "beat": "climax", "intent": "peak"}]})
    l2 = json.dumps({"scenes": [{"title": "s", "intent": "do", "tension": 50, "present": ["Lâm Uyển"]}],
                     "chapter_exit": {"characters": "c", "world": "w", "plot": "p", "advances": ["a1"]}})
    llm = _GroundedLLM(l1, l2)
    beats = [{"key": "setup", "purpose": "establish"}, {"key": "climax", "purpose": "payoff"}]
    chapters = [ChapterPlan(chapter_id=f"c{i}", title=f"Ch{i}", sort_order=i, beat_role=None, intent="")
                for i in (1, 2)]
    res = await grounded_decompose(
        llm, user_id="u", model_source="user_model", model_ref="m",
        premise="p", arc_title="A", beats=beats, chapters=chapters,
        cast=[{"entity_id": "e1", "name": "Lâm Uyển"}],
        motifs=_MOTIFS, char_arcs=[{"name": "Lục Vô Trần", "introduce_at_chapter": 2}],
        k_ceiling=3, high_threshold=70, min_scenes=1, max_scenes=6, source_language="vi")
    assert len(res.chapters) == 2 and res.chapters[0].scenes[0].present_entity_ids == ["e1"]
    ch1_prompt, ch2_prompt = llm.l2_prompts
    # ch1 (setup): spine motif only, no intro, a capped tension target
    assert "Xấu hóa mỹ" in ch1_prompt and "Phục thù" not in ch1_prompt
    assert "INTRODUCE THIS CHAPTER" not in ch1_prompt
    # ch2 (climax): spine + climax-payoff motif, the scheduled intro, tension 100, threaded
    assert "Xấu hóa mỹ" in ch2_prompt and "Phục thù (climax payoff)" in ch2_prompt
    assert "INTRODUCE THIS CHAPTER" in ch2_prompt and "Lục Vô Trần" in ch2_prompt
    assert "100/100" in ch2_prompt
    assert "STORY SO FAR" in ch2_prompt and "a1" in ch2_prompt   # threaded from ch1's exit
    assert res.chapters[1].exit_state.advances == ["a1"]


async def test_grounded_decompose_skip_l1_does_not_run_l1_on_all_none():
    # skip_l1=True with all-None chapters must NOT re-run L1 (the orchestrator owns it) —
    # the fake would raise on an L1 call, proving none was made.
    l2 = json.dumps({"scenes": [{"title": "s", "intent": "do", "tension": 40, "present": []}]})

    class _NoL1LLM:
        async def submit_and_wait(self, **kw):
            user = kw["input"]["messages"][1]["content"]
            assert "STRUCTURE BEATS" not in user, "L1 must be skipped"
            return SimpleNamespace(status="completed", result={"messages": [{"content": l2}]})

    chapters = [ChapterPlan(chapter_id="c1", title="Ch1", sort_order=1, beat_role=None, intent="")]
    res = await grounded_decompose(
        _NoL1LLM(), user_id="u", model_source="user_model", model_ref="m",
        premise="p", arc_title="A", beats=[{"key": "hook", "purpose": ""}], chapters=chapters,
        cast=[], motifs=[], char_arcs=[], skip_l1=True,
        k_ceiling=3, high_threshold=70, min_scenes=1, max_scenes=4, source_language="vi")
    assert len(res.chapters) == 1 and res.chapters[0].chapter.beat_role is None
