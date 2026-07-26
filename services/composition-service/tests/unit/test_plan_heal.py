"""Unit tests for planning Stage 5 — run_plan_self_heal (engine/plan_heal.py).

Pins: outline rendering, tolerant finding parse (drop non-int addresses), and the
orchestrator invariants — in-place synopsis replace, the skip guards (out-of-range
address / runaway expansion), and the no-findings / degrade paths.
"""

import json
from types import SimpleNamespace

from app.engine.plan import ChapterPlan, ChapterScenes, DecomposeResult, ScenePlan
from app.engine.plan_heal import parse_plan_findings, render_outline, run_plan_self_heal


def _scene(title, synopsis, tension=50):
    return ScenePlan(title=title, synopsis=synopsis, tension=tension,
                     present_entity_ids=[], present_entity_names_unresolved=[], suggested_k=2)


def _result():
    ch1 = ChapterScenes(
        chapter=ChapterPlan(chapter_id="c1", title="Ch1", sort_order=1, beat_role="hook", intent="i"),
        scenes=[_scene("s1", "expulsion at max tension", 100), _scene("s2", "she flees", 60)])
    ch2 = ChapterScenes(
        chapter=ChapterPlan(chapter_id="c2", title="Ch2", sort_order=2, beat_role="climax", intent="j"),
        scenes=[_scene("s3", "the demon appears with no setup", 80)])
    return DecomposeResult(arc_title="A", chapters=[ch1, ch2])


def test_render_outline_addresses_each_scene():
    out = render_outline(_result())
    assert "CH01 S1 [hook] (tension 100): expulsion at max tension" in out
    assert "CH02 S1 [climax] (tension 80): the demon appears with no setup" in out


def test_parse_plan_findings_drops_non_int_address():
    content = json.dumps([
        {"chapter": 1, "scene": 1, "type": "pacing", "issue": "ch1 maxed", "fix": "lower it"},
        {"chapter": "two", "scene": 1, "issue": "bad addr"},   # non-int → drop
        {"scene": 3, "issue": "no chapter"},                   # missing → drop
    ])
    out = parse_plan_findings(content)
    assert len(out) == 1 and out[0].chapter == 1 and out[0].scene == 1
    assert parse_plan_findings("no json") == []


class _HealLLM:
    def __init__(self, judge, edit_fn):
        self._judge, self._edit_fn = judge, edit_fn

    async def submit_and_wait(self, **kw):
        system = kw["input"]["messages"][0]["content"]
        user = kw["input"]["messages"][1]["content"]
        if "demanding story editor" in system:
            return SimpleNamespace(status="completed", result={"messages": [{"content": self._judge}]})
        return SimpleNamespace(status="completed", result={"messages": [{"content": self._edit_fn(user)}]})


async def test_run_plan_self_heal_edits_valid_and_skips_out_of_range():
    judge = json.dumps([
        {"chapter": 1, "scene": 1, "issue": "ch1 maxed", "fix": "lower tension"},
        {"chapter": 9, "scene": 9, "issue": "ghost", "fix": "n/a"},    # out of range → skip
    ])
    res = _result()
    llm = _HealLLM(judge, edit_fn=lambda u: "a calmer humiliation, tension building")
    healed, rep = await run_plan_self_heal(
        llm, res, user_id="u", model_source="user_model", model_ref="m", source_language="en")
    assert rep.edits_applied == 1
    assert healed.chapters[0].scenes[0].synopsis == "a calmer humiliation, tension building"
    assert any(f.skip_reason == "not_found" for f in rep.findings)


async def test_run_plan_self_heal_rejects_runaway_expansion():
    judge = json.dumps([{"chapter": 1, "scene": 1, "issue": "x", "fix": "y"}])
    res = _result()
    orig = res.chapters[0].scenes[0].synopsis
    llm = _HealLLM(judge, edit_fn=lambda u: "z" * 500)
    healed, rep = await run_plan_self_heal(
        llm, res, user_id="u", model_source="user_model", model_ref="m")
    assert rep.edits_applied == 0
    assert healed.chapters[0].scenes[0].synopsis == orig         # original kept
    assert rep.findings[0].skip_reason == "edit_expanded"


async def test_run_plan_self_heal_no_findings_is_noop():
    res = _result()
    llm = _HealLLM("[]", edit_fn=lambda u: "X")
    healed, rep = await run_plan_self_heal(llm, res, user_id="u", model_source="s", model_ref="m")
    assert rep.edits_applied == 0 and healed.chapters[0].scenes[0].synopsis == "expulsion at max tension"
