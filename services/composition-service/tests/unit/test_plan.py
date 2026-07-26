"""Unit tests for the A3 decompose planner (engine/plan.py).

Focus: the tolerant-parse + reconcile + cast-resolution + degrade paths (the
load-bearing surfaces), not the LLM itself.
"""

import json
from types import SimpleNamespace

import pytest

from app.engine import plan
from app.engine.plan import ChapterPlan

# asyncio auto-mode (pytest.ini) collects the async tests; the sync parse tests
# must NOT carry an asyncio mark, so no module-level pytestmark here.

BEATS = [
    {"key": "setup", "purpose": "establish"},
    {"key": "midpoint", "purpose": "raise stakes"},
    {"key": "climax", "purpose": "payoff"},
]


def _chapters(n):
    return [ChapterPlan(chapter_id=f"ch{i}", title=f"Ch {i}", sort_order=i,
                        beat_role=None, intent="") for i in range(1, n + 1)]


class FakeLLM:
    """Routes by prompt content: a user prompt containing 'STRUCTURE BEATS' is
    the L1 chapter-map; one containing 'CAST ROSTER' is an L2 scene call."""

    def __init__(self, *, l1=None, l2=None, l1_status="completed", l2_status="completed",
                 l1_raises=False, l2_raises=False):
        self._l1, self._l2 = l1, l2
        self._l1_status, self._l2_status = l1_status, l2_status
        self._l1_raises, self._l2_raises = l1_raises, l2_raises
        self.l1_calls = self.l2_calls = 0

    async def submit_and_wait(self, **kw):
        from loreweave_llm.errors import LLMError
        user = kw["input"]["messages"][1]["content"]
        if "STRUCTURE BEATS" in user:
            self.l1_calls += 1
            if self._l1_raises:
                raise LLMError("down")
            res = {"messages": [{"content": self._l1}]} if self._l1 is not None else {}
            return SimpleNamespace(status=self._l1_status, result=res)
        self.l2_calls += 1
        if self._l2_raises:
            raise LLMError("down")
        res = {"messages": [{"content": self._l2}]} if self._l2 is not None else {}
        return SimpleNamespace(status=self._l2_status, result=res)


# ── L1 parse / reconcile ──

def test_parse_chapter_map_assigns_and_surfaces_unmapped():
    chapters = _chapters(2)
    content = json.dumps({"chapters": [
        {"index": 1, "beat": "setup", "intent": "open"},
        {"index": 2, "beat": "climax", "intent": "end"},
    ], "unmapped_beats": ["midpoint"]})
    mapped, unmapped = plan.parse_chapter_map(content, chapters, {"setup", "midpoint", "climax"})
    assert [c.beat_role for c in mapped] == ["setup", "climax"]
    assert [c.intent for c in mapped] == ["open", "end"]
    assert unmapped == ["midpoint"]


def test_parse_chapter_map_keeps_every_chapter_when_model_omits_rows():
    chapters = _chapters(3)
    content = json.dumps({"chapters": [{"index": 1, "beat": "setup", "intent": "x"}]})
    mapped, _ = plan.parse_chapter_map(content, chapters, {"setup", "midpoint", "climax"})
    assert len(mapped) == 3  # no chapter dropped
    assert mapped[0].beat_role == "setup"
    assert mapped[1].beat_role is None and mapped[1].intent == ""  # omitted → null beat
    assert mapped[2].beat_role is None


def test_parse_chapter_map_rejects_unknown_beat_key():
    chapters = _chapters(1)
    content = json.dumps({"chapters": [{"index": 1, "beat": "not_a_beat", "intent": "x"}]})
    mapped, _ = plan.parse_chapter_map(content, chapters, {"setup"})
    assert mapped[0].beat_role is None  # invalid key → not accepted
    assert mapped[0].intent == "x"


def test_parse_chapter_map_cgtb_chapters_share_a_beat():
    # C>B: 4 chapters, model assigns the same beat to two of them — allowed
    chapters = _chapters(4)
    content = json.dumps({"chapters": [
        {"index": 1, "beat": "setup", "intent": "a"},
        {"index": 2, "beat": "setup", "intent": "b"},
        {"index": 3, "beat": "midpoint", "intent": "c"},
        {"index": 4, "beat": "climax", "intent": "d"},
    ]})
    mapped, _ = plan.parse_chapter_map(content, chapters, {"setup", "midpoint", "climax"})
    assert [c.beat_role for c in mapped] == ["setup", "setup", "midpoint", "climax"]


# ── L2 parse / cast / tolerance ──

CAST = {"alice": "id-a", "bob": "id-b"}


def test_parse_scenes_resolves_cast_and_surfaces_unresolved():
    content = json.dumps({"scenes": [
        {"title": "S1", "intent": "meet", "tension": 90, "present": ["Alice", "Carol"]},
    ]})
    scenes = plan.parse_scenes(content, CAST, min_scenes=1, max_scenes=6,
                               beat_role="climax", k_ceiling=3, high_threshold=70)
    assert len(scenes) == 1
    s = scenes[0]
    assert s.present_entity_ids == ["id-a"]            # Alice resolved
    assert s.present_entity_names_unresolved == ["Carol"]  # surfaced, not dropped
    assert s.tension == 90 and s.suggested_k == 3      # high tension (0..100) → ceiling


def test_parse_scenes_drops_malformed_keeps_good():
    content = json.dumps({"scenes": [
        {"title": "ok", "intent": "good", "tension": 20, "present": []},
        {"title": "bad", "present": []},           # no intent → dropped
        "not even an object",                       # dropped
        {"intent": "titleless ok", "tension": 150}, # title defaulted, tension clamped
    ]})
    scenes = plan.parse_scenes(content, CAST, min_scenes=1, max_scenes=6,
                               beat_role=None, k_ceiling=3, high_threshold=70)
    assert [s.synopsis for s in scenes] == ["good", "titleless ok"]
    assert scenes[1].tension == 100  # 150 clamped to 100 (0..100 scale)
    assert scenes[1].title  # defaulted from intent


def test_parse_scenes_default_tension_when_missing():
    content = json.dumps({"scenes": [{"intent": "x", "present": []}]})
    scenes = plan.parse_scenes(content, CAST, min_scenes=1, max_scenes=6,
                               beat_role=None, k_ceiling=3, high_threshold=70)
    assert scenes[0].tension == 50  # neutral default (0..100)


def test_parse_scenes_clamps_to_max():
    content = json.dumps({"scenes": [
        {"intent": f"s{i}", "tension": 1, "present": []} for i in range(10)
    ]})
    scenes = plan.parse_scenes(content, CAST, min_scenes=1, max_scenes=4,
                               beat_role=None, k_ceiling=3, high_threshold=70)
    assert len(scenes) == 4


# ── orchestration / degrade ──

async def test_decompose_happy_path():
    l1 = json.dumps({"chapters": [{"index": 1, "beat": "midpoint", "intent": "turn"}],
                     "unmapped_beats": ["setup", "climax"]})
    l2 = json.dumps({"scenes": [{"title": "s", "intent": "do", "tension": 90, "present": ["Bob"]}]})
    llm = FakeLLM(l1=l1, l2=l2)
    res = await plan.decompose(
        llm, user_id="u", model_source="user_model", model_ref="m",
        premise="p", arc_title="Arc", beats=BEATS, chapters=_chapters(1),
        cast=[{"entity_id": "id-b", "name": "Bob"}],
        k_ceiling=3, high_threshold=70, min_scenes=1, max_scenes=6,
    )
    assert res.arc_title == "Arc"
    assert res.unmapped_beats == ["setup", "climax"]
    assert llm.l1_calls == 1 and llm.l2_calls == 1
    ch = res.chapters[0]
    assert ch.chapter.beat_role == "midpoint"
    assert ch.scenes[0].present_entity_ids == ["id-b"]
    assert ch.scenes[0].suggested_k == 3  # tension 90 (>=70) → ceiling


async def test_decompose_l1_degraded_still_attempts_scenes():
    # L1 returns nothing → chapters keep beat_role=None, L2 still runs
    l2 = json.dumps({"scenes": [{"intent": "x", "tension": 1, "present": []}]})
    llm = FakeLLM(l1=None, l2=l2)
    res = await plan.decompose(
        llm, user_id="u", model_source="user_model", model_ref="m",
        premise="p", arc_title="A", beats=BEATS, chapters=_chapters(2), cast=[],
        k_ceiling=3, high_threshold=4, min_scenes=1, max_scenes=6,
    )
    assert all(c.chapter.beat_role is None for c in res.chapters)
    assert all(len(c.scenes) == 1 for c in res.chapters)
    assert llm.l2_calls == 2  # one per chapter


async def test_decompose_l2_degraded_yields_warning():
    l1 = json.dumps({"chapters": [{"index": 1, "beat": "setup", "intent": "x"}]})
    llm = FakeLLM(l1=l1, l2=None)  # L2 returns nothing
    res = await plan.decompose(
        llm, user_id="u", model_source="user_model", model_ref="m",
        premise="p", arc_title="A", beats=BEATS, chapters=_chapters(1), cast=[],
        k_ceiling=3, high_threshold=4, min_scenes=1, max_scenes=6,
    )
    assert res.chapters[0].scenes == []
    assert res.chapters[0].warning == "scene_decompose_degraded"


# ── Phase-0 slice-2: cross-chapter threading (typed exit-state) ──

def test_parse_chapter_exit_tolerant():
    full = json.dumps({"scenes": [], "chapter_exit": {
        "characters": "Lâm Uyển: hận → quyết tâm", "world": "đêm; vực sâu",
        "plot": "mở: cuốn ma điển", "advances": ["nhặt ma điển", "  ", 3]}})
    ex = plan.parse_chapter_exit(full)
    assert ex is not None
    assert ex.characters.startswith("Lâm Uyển")
    assert ex.world == "đêm; vực sâu"
    assert ex.advances == ["nhặt ma điển"]  # blank + non-str dropped
    # missing / all-empty / non-dict → None (degrade-safe)
    assert plan.parse_chapter_exit(json.dumps({"scenes": []})) is None
    assert plan.parse_chapter_exit(json.dumps({"chapter_exit": {
        "characters": "", "world": "", "plot": "", "advances": []}})) is None
    assert plan.parse_chapter_exit("not json") is None


def test_render_story_so_far():
    assert plan.render_story_so_far(None, []) == ""
    ex = plan.ChapterExitState(characters="c", world="w", plot="p", advances=["A1", "A2"])
    out = plan.render_story_so_far(ex, ["A1", "A2"])
    assert "Characters: c" in out and "World: w" in out and "Plot: p" in out
    assert "ALREADY-USED DEVELOPMENTS" in out and "- A1" in out and "- A2" in out


def test_build_scene_decompose_threading_switches():
    ch = ChapterPlan(chapter_id="c1", title="t", sort_order=1, beat_role="setup", intent="i")
    # default: no exit emission, no story-so-far conditioning
    sys0, usr0 = plan.build_scene_decompose_messages("p", ch, "bp", [], 1, 6, "vi")
    assert "chapter_exit" not in sys0 and "STORY SO FAR" not in usr0 and "CONTINUE THE STORY" not in sys0
    # emit_exit only (chapter 1 of a threaded run): asks for the delta, still no continue-from
    sys1, usr1 = plan.build_scene_decompose_messages("p", ch, "bp", [], 1, 6, "vi", "", emit_exit=True)
    assert "chapter_exit" in sys1 and "STORY SO FAR" not in usr1 and "CONTINUE THE STORY" not in sys1
    # both (chapter 2+): emit + continue-from conditioning
    sys2, usr2 = plan.build_scene_decompose_messages(
        "p", ch, "bp", [], 1, 6, "vi", "Characters: prior", emit_exit=True)
    assert "chapter_exit" in sys2 and "CONTINUE THE STORY" in sys2
    assert "STORY SO FAR" in usr2 and "Characters: prior" in usr2


class CapturingLLM:
    """Records (system, user) per L2 call and replays a queue of L2 responses in
    order — so a sequential threaded decompose can be inspected call-by-call."""

    def __init__(self, *, l1, l2_queue):
        self._l1 = l1
        self._l2_queue = list(l2_queue)
        self.l2_prompts: list[tuple[str, str]] = []
        self.l1_calls = self.l2_calls = 0

    async def submit_and_wait(self, **kw):
        msgs = kw["input"]["messages"]
        system, user = msgs[0]["content"], msgs[1]["content"]
        if "STRUCTURE BEATS" in user:
            self.l1_calls += 1
            return SimpleNamespace(status="completed", result={"messages": [{"content": self._l1}]})
        self.l2_calls += 1
        self.l2_prompts.append((system, user))
        nxt = self._l2_queue.pop(0)
        if nxt is None:  # simulate a degraded L2 (non-completion → _llm_json returns None)
            return SimpleNamespace(status="failed", result={})
        return SimpleNamespace(status="completed", result={"messages": [{"content": nxt}]})


def _l2_with_exit(scene_intent, advances):
    return json.dumps({
        "scenes": [{"title": "s", "intent": scene_intent, "tension": 50, "present": []}],
        "chapter_exit": {"characters": "c", "world": "w", "plot": "p", "advances": advances},
    })


async def test_decompose_thread_state_threads_exit_forward():
    l1 = json.dumps({"chapters": [
        {"index": 1, "beat": "setup", "intent": "open"},
        {"index": 2, "beat": "midpoint", "intent": "rise"},
    ]})
    llm = CapturingLLM(l1=l1, l2_queue=[
        _l2_with_exit("ch1 scene", ["expulsion"]),
        _l2_with_exit("ch2 scene", ["new alliance"]),
    ])
    res = await plan.decompose(
        llm, user_id="u", model_source="user_model", model_ref="m",
        premise="p", arc_title="A", beats=BEATS, chapters=_chapters(2), cast=[],
        k_ceiling=3, high_threshold=70, min_scenes=1, max_scenes=6,
        thread_state=True,
    )
    # sequential: 2 L2 calls, in order
    assert llm.l2_calls == 2
    # chapter 1 prompt: emit_exit on, no continue-from
    sys1, usr1 = llm.l2_prompts[0]
    assert "chapter_exit" in sys1 and "STORY SO FAR" not in usr1
    # chapter 2 prompt: threaded with chapter 1's exit + spent development
    sys2, usr2 = llm.l2_prompts[1]
    assert "STORY SO FAR" in usr2 and "expulsion" in usr2 and "Characters: c" in usr2
    # both chapters captured their typed exit-state
    assert res.chapters[0].exit_state.advances == ["expulsion"]
    assert res.chapters[1].exit_state.advances == ["new alliance"]


async def test_decompose_thread_state_degrade_retains_prev_exit():
    # ch2's L2 degrades (None) → its scenes empty + exit_state None, but the chain must
    # keep threading from ch1's exit into ch3 (degrade-safe invariant), and ch3 sees BOTH
    # ch1's and (only) ch1's spent advances (ch2 contributed none).
    l1 = json.dumps({"chapters": [
        {"index": 1, "beat": "setup", "intent": "a"},
        {"index": 2, "beat": "midpoint", "intent": "b"},
        {"index": 3, "beat": "climax", "intent": "c"},
    ]})
    llm = CapturingLLM(l1=l1, l2_queue=[
        _l2_with_exit("ch1", ["A1"]),
        None,                              # ch2 degrades
        _l2_with_exit("ch3", ["A3"]),
    ])
    res = await plan.decompose(
        llm, user_id="u", model_source="user_model", model_ref="m",
        premise="p", arc_title="A", beats=BEATS, chapters=_chapters(3), cast=[],
        k_ceiling=3, high_threshold=70, min_scenes=1, max_scenes=6,
        thread_state=True,
    )
    assert llm.l2_calls == 3
    # ch2 degraded cleanly
    assert res.chapters[1].scenes == [] and res.chapters[1].warning == "scene_decompose_degraded"
    assert res.chapters[1].exit_state is None
    # ch3 still threaded — from ch1's retained exit + only ch1's advance (ch2 added none)
    _sys3, usr3 = llm.l2_prompts[2]
    assert "STORY SO FAR" in usr3 and "A1" in usr3 and "A3" not in usr3
    assert res.chapters[2].exit_state.advances == ["A3"]


async def test_decompose_thread_state_off_is_unthreaded():
    l1 = json.dumps({"chapters": [{"index": 1, "beat": "setup", "intent": "open"}]})
    llm = CapturingLLM(l1=l1, l2_queue=[_l2_with_exit("ch1", ["x"])])
    res = await plan.decompose(
        llm, user_id="u", model_source="user_model", model_ref="m",
        premise="p", arc_title="A", beats=BEATS, chapters=_chapters(1), cast=[],
        k_ceiling=3, high_threshold=70, min_scenes=1, max_scenes=6,
    )  # thread_state defaults False
    sys1, usr1 = llm.l2_prompts[0]
    assert "chapter_exit" not in sys1 and "STORY SO FAR" not in usr1
    assert res.chapters[0].exit_state is None  # not parsed when threading off
