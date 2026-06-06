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
