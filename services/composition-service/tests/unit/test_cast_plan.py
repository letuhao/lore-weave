"""Unit tests for planning Stage 0 — propose_cast (engine/cast_plan.py).

Focus: tolerant parse (drop nameless, dedup, coerce traits/is_new) + the degrade path.
"""

import json
from types import SimpleNamespace

from app.engine import cast_plan
from app.engine.cast_plan import ProposedChar, cast_attributes, parse_cast, propose_cast


def test_cast_attributes_maps_fields_to_glossary_codes():
    c = ProposedChar(name="Lâm Uyển", role="protagonist", archetype="phế vật nghịch thiên",
                     traits=["kiên cường", "lạnh lùng"], relationships="đích nữ Lâm gia",
                     summary="nữ chính bị ruồng bỏ")
    a = cast_attributes(c)
    assert a["role"] == "protagonist"
    assert a["relationships"] == "đích nữ Lâm gia"
    assert a["personality"] == "kiên cường; lạnh lùng; phế vật nghịch thiên"  # traits + archetype
    assert a["description"] == "nữ chính bị ruồng bỏ"
    assert cast_attributes(ProposedChar(name="X")) == {}    # all-empty → no attrs


def test_parse_cast_extracts_and_flags_new():
    content = json.dumps([
        {"name": "Lâm Uyển", "role": "protagonist", "archetype": "ugly duckling",
         "traits": ["bị ghẻ lạnh", "kiên cường"], "relationships": "đích nữ Lâm gia",
         "summary": "nữ chính", "is_new": False},
        {"name": "Hắc Diện Tu La", "role": "antagonist", "traits": ["tàn nhẫn"],
         "relationships": "kẻ thù", "summary": "phản diện mới", "is_new": True},
    ])
    out = parse_cast(content)
    assert [c.name for c in out] == ["Lâm Uyển", "Hắc Diện Tu La"]
    assert out[0].is_new is False and out[1].is_new is True
    assert out[0].traits == ["bị ghẻ lạnh", "kiên cường"]
    assert out[0].role == "protagonist"


def test_parse_cast_tolerant_drops_and_dedups():
    content = ('prose before ['
               '{"name":"Tô Yến","role":"mother"},'
               '{"role":"no name here"},'              # dropped — no name
               '{"name":"  ","summary":"blank"},'      # dropped — blank name
               '"not a dict",'
               '{"name":"Tô Yến","role":"dup"}'        # dropped — duplicate (first wins)
               '] prose after')
    out = parse_cast(content)
    assert [c.name for c in out] == ["Tô Yến"]
    assert out[0].role == "mother"
    assert out[0].traits == []          # missing traits → []
    assert parse_cast("no json") == [] and parse_cast("") == []


def test_parse_cast_coerces_bad_traits_and_isnew():
    content = json.dumps([
        {"name": "X", "traits": "not a list", "is_new": "yes-ish"},   # truthy string → True
        {"name": "Y", "is_new": "false"},                              # textual negative → False (NOT bool("false")=True)
        {"name": "Z", "is_new": "no"},
        {"name": "W", "is_new": True},
    ])
    out = parse_cast(content)
    assert out[0].traits == [] and out[0].is_new is True
    assert out[1].is_new is False and out[2].is_new is False  # the string-"false" coercion bug guard
    assert out[3].is_new is True


def test_parse_cast_salvages_truncated_array():
    # the token cap cut the closing ] mid-third-object → salvage the 2 complete ones
    content = ('```json\n['
               '{"name":"Lâm Uyển","role":"protagonist","traits":["a","b"]},'
               '{"name":"Tô Yến","role":"antagonist","traits":["c"]},'
               '{"name":"Lâm Tử')  # truncated
    out = parse_cast(content)
    assert [c.name for c in out] == ["Lâm Uyển", "Tô Yến"]
    assert out[0].traits == ["a", "b"]


async def test_propose_cast_degrades_to_empty_on_non_completion():
    class _LLM:
        async def submit_and_wait(self, **kw):
            return SimpleNamespace(status="failed", result={})
    out = await propose_cast(_LLM(), user_id="u", model_source="user_model", model_ref="m",
                             premise="p", source_language="vi")
    assert out == []


async def test_propose_cast_happy_parses_array():
    payload = json.dumps([{"name": "Lâm Uyển", "role": "protagonist", "is_new": False}])

    class _LLM:
        async def submit_and_wait(self, **kw):
            # the genre/language steer must reach the prompt
            assert "PREMISE:" in kw["input"]["messages"][1]["content"]
            return SimpleNamespace(status="completed", result={"messages": [{"content": payload}]})
    out = await propose_cast(_LLM(), user_id="u", model_source="user_model", model_ref="m",
                             premise="Lâm Uyển bị ghẻ lạnh...", source_language="vi",
                             genre_tags=["xianxia"])
    assert len(out) == 1 and out[0].name == "Lâm Uyển"
