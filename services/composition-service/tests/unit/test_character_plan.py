"""Unit tests for planning Stage 3 — plan_character_arcs (engine/character_plan.py).

Focus: name-mapping (drop invented names — never invent a character), introduce-chapter
clamping, role carry-through, and the degrade path.
"""

import json
from types import SimpleNamespace

from app.engine.character_plan import (
    build_character_arc_messages, parse_character_arcs, plan_character_arcs,
)

_VALID = {"Lâm Uyển", "Mộ Dung Tuyết"}


def test_parse_maps_names_clamps_intro_and_drops_invented():
    content = json.dumps([
        {"name": "Lâm Uyển", "arc": "phế vật → hoàn mỹ", "introduce_at_chapter": 1},
        {"name": "Mộ Dung Tuyết", "arc": "foil", "introduce_at_chapter": 99},   # clamp → 12
        {"name": "Kẻ Bịa Đặt", "arc": "nope", "introduce_at_chapter": 3},        # invented → drop
        {"name": "lâm uyển", "arc": "dup (case-folded)", "introduce_at_chapter": 2},  # dup → drop
    ])
    out = parse_character_arcs(content, _VALID, n_chapters=12)
    assert [c.name for c in out] == ["Lâm Uyển", "Mộ Dung Tuyết"]
    assert out[0].introduce_at_chapter == 1
    assert out[1].introduce_at_chapter == 12          # 99 clamped to n_chapters
    assert parse_character_arcs("no json", _VALID, 12) == []


def test_parse_intro_none_when_missing_or_bad():
    content = json.dumps([
        {"name": "Lâm Uyển", "arc": "a"},                      # missing intro → None
        {"name": "Mộ Dung Tuyết", "arc": "b", "introduce_at_chapter": "soon"},  # non-int → None
    ])
    out = parse_character_arcs(content, _VALID, 12)
    assert out[0].introduce_at_chapter is None and out[1].introduce_at_chapter is None


def test_build_messages_lists_cast_and_beats():
    cast = [{"name": "Lâm Uyển", "role": "protagonist", "is_new": False},
            {"name": "Hắc Sát", "role": "ally", "is_new": True}]
    system, user = build_character_arc_messages("a premise", cast, ["hook", "climax"], "vi")
    assert "2 chapters" in system
    assert "Lâm Uyển (role: protagonist, in-premise)" in user
    assert "Hắc Sát (role: ally, NEW)" in user
    assert "ch1:hook, ch2:climax" in user


class _LLM:
    def __init__(self, content, status="completed"):
        self._content, self._status = content, status

    async def submit_and_wait(self, **kw):
        return SimpleNamespace(status=self._status, result={"messages": [{"content": self._content}]})


async def test_plan_character_arcs_carries_role_and_degrades():
    cast = [{"name": "Lâm Uyển", "role": "protagonist", "is_new": False},
            {"name": "Hắc Sát", "role": "ally", "is_new": True}]
    llm = _LLM(json.dumps([
        {"name": "Lâm Uyển", "arc": "phế vật → hoàn mỹ", "introduce_at_chapter": 1},
        {"name": "Hắc Sát", "arc": "trung thành", "introduce_at_chapter": 5},
    ]))
    out = await plan_character_arcs(
        llm, user_id="u", model_source="user_model", model_ref="m",
        premise="p", cast=cast, beat_roles=["hook"] * 6, source_language="vi")
    assert {c.name: c.role for c in out} == {"Lâm Uyển": "protagonist", "Hắc Sát": "ally"}
    assert next(c for c in out if c.name == "Hắc Sát").introduce_at_chapter == 5

    # empty cast → [] (no LLM call needed); non-completion → []
    assert await plan_character_arcs(llm, user_id="u", model_source="s", model_ref="m",
                                     premise="p", cast=[], beat_roles=["hook"]) == []
    bad = _LLM("", "failed")
    assert await plan_character_arcs(bad, user_id="u", model_source="s", model_ref="m",
                                     premise="p", cast=cast, beat_roles=["hook"]) == []
