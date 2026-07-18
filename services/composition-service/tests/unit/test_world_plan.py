"""27 V2-C3 · pass 3 — `world_plan.py`. The tolerant parse + the degrade-safe path.

Pass 3 is ADVISORY (PF-6) and its seeding may lag (PF-7), so an empty world plan must never block
the compiler. Everything here proves that "we could not read the model's answer" degrades to `[]`
rather than raising — and, equally, that a well-formed answer BADLY PACKAGED is still read.
"""

from __future__ import annotations

import json

import pytest

from app.engine.world_plan import (
    WORLD_KINDS,
    build_propose_world_messages,
    parse_world,
    propose_world,
    world_attributes,
    ProposedWorldEntity,
)


def _rows(*items):
    return json.dumps(list(items))


# ── the tolerant parse ────────────────────────────────────────────────────────


def test_parses_a_clean_json_array():
    out = parse_world(_rows(
        {"name": "Ironhold", "kind": "location", "summary": "a fortress", "is_new": False},
        {"name": "The Iron Court", "kind": "faction", "is_new": True},
    ))
    assert [(e.name, e.kind, e.is_new) for e in out] == [
        ("Ironhold", "location", False),
        ("The Iron Court", "faction", True),
    ]


def test_reads_json_wrapped_in_a_markdown_fence():
    # A model asked for bare JSON still fences it. That is a well-formed answer badly packaged;
    # throwing it away would degrade the pass over a formatting quibble.
    out = parse_world('```json\n[{"name": "Ironhold", "kind": "location"}]\n```')
    assert [e.name for e in out] == ["Ironhold"]


def test_reads_json_with_a_chatty_preamble():
    out = parse_world('Sure! Here is the world:\n[{"name": "Ironhold", "kind": "location"}]')
    assert [e.name for e in out] == ["Ironhold"]


def test_reads_JSONL_one_object_per_line():
    out = parse_world(
        '{"name": "Ironhold", "kind": "location"}\n'
        '{"name": "The Iron Court", "kind": "faction"}'
    )
    assert [e.name for e in out] == ["Ironhold", "The Iron Court"]


@pytest.mark.parametrize("junk", ["", "   ", "I could not do that.", "{", "null", "[]"])
def test_unreadable_content_degrades_to_empty_never_raises(junk):
    assert parse_world(junk) == []


# ── the coercions that exist because models actually do this ──────────────────


def test_the_STRING_false_is_coerced_to_False():
    # bool("false") is True. Without this coercion EVERY entity would be marked newly-invented,
    # and the seeder would propose creating entities the premise already named.
    out = parse_world(_rows({"name": "Ironhold", "kind": "location", "is_new": "false"}))
    assert out[0].is_new is False
    out = parse_world(_rows({"name": "X", "kind": "location", "is_new": "true"}))
    assert out[0].is_new is True


def test_an_unknown_kind_becomes_concept_rather_than_being_DROPPED():
    """The model named something real and mislabelled it. Discarding it loses a real entity;
    seeding the bad kind would be silently rejected by glossary at the far end of a long chain.
    Default to the widest of the three."""
    out = parse_world(_rows({"name": "The Third Rising", "kind": "event"}))
    assert len(out) == 1
    assert out[0].kind == "concept"
    assert out[0].kind in WORLD_KINDS


def test_a_row_with_no_usable_name_is_skipped():
    out = parse_world(_rows(
        {"kind": "location"}, {"name": "  ", "kind": "location"}, {"name": "Real", "kind": "location"},
    ))
    assert [e.name for e in out] == ["Real"]


def test_dedupes_on_NAME_AND_KIND_not_name_alone():
    """The same word can legitimately be a place AND a faction — "Ironhold" the fortress and
    "Ironhold" the house. Deduping on name alone would silently lose one of them."""
    out = parse_world(_rows(
        {"name": "Ironhold", "kind": "location"},
        {"name": "Ironhold", "kind": "faction"},
        {"name": "ironhold", "kind": "location"},  # a true case-insensitive duplicate
    ))
    assert [(e.name, e.kind) for e in out] == [("Ironhold", "location"), ("Ironhold", "faction")]


def test_non_string_traits_are_dropped_not_crashed_on():
    out = parse_world(_rows({"name": "X", "kind": "location", "traits": ["cold", 7, None, " "]}))
    assert out[0].traits == ["cold"]


# ── the prompt ────────────────────────────────────────────────────────────────


def test_the_cast_is_given_to_the_prompt_because_pass_3_DEPENDS_on_pass_2():
    # A world proposed blind to its characters invents a faction for nobody. PF-1's dependency
    # order is not decoration.
    system, user = build_propose_world_messages("a premise", cast_names=["Hà", "Lâm Uyển"])
    assert "Hà" in system and "Lâm Uyển" in system
    assert "a premise" in user


def test_genre_and_language_reach_the_prompt():
    system, _ = build_propose_world_messages("p", source_language="vi", genre_tags=["xianxia"])
    assert "xianxia" in system
    assert "'vi'" in system


def test_no_cast_still_builds_a_valid_prompt():
    system, user = build_propose_world_messages("p")
    assert system and user


# ── attribute mapping (the cast_attributes precedent) ─────────────────────────


def test_attributes_map_the_DEPTH_not_just_the_name():
    e = ProposedWorldEntity(
        name="Ironhold", kind="location", summary="a fortress",
        relationships="seat of the Iron Court", traits=["cold", "old"],
    )
    assert world_attributes(e) == {
        "description": "a fortress",
        "relationships": "seat of the Iron Court",
        "properties": "cold; old",
    }


def test_empty_fields_are_omitted_never_written_as_blanks():
    assert world_attributes(ProposedWorldEntity(name="X")) == {}


# ── degrade-safe: any LLM failure yields [] ───────────────────────────────────


class _LLM:
    def __init__(self, *, raises=None, status="completed", content="[]"):
        self._raises = raises
        self._status = status
        self._content = content

    async def submit_and_wait(self, **_kw):
        if self._raises:
            raise self._raises

        class _Job:
            status = self._status
            # The gateway puts the text at result["messages"][0]["content"], NOT
            # result["content"] and NOT an OpenAI-style `choices` array — a documented,
            # load-bearing gotcha (`gateway_response_messages_array_not_content_string`).
            # A fixture that invents the wrong shape tests nothing but itself.
            result = {"messages": [{"content": self._content}]}

        return _Job()


@pytest.mark.asyncio
async def test_an_llm_error_degrades_to_empty():
    from loreweave_llm.errors import LLMError

    out = await propose_world(
        _LLM(raises=LLMError("boom")), user_id="u", model_source="user_model",
        model_ref="m", premise="p",
    )
    assert out == []


@pytest.mark.asyncio
async def test_a_non_completed_job_degrades_to_empty():
    out = await propose_world(
        _LLM(status="failed"), user_id="u", model_source="user_model", model_ref="m", premise="p",
    )
    assert out == []


@pytest.mark.asyncio
async def test_a_completed_job_is_parsed():
    out = await propose_world(
        _LLM(content='[{"name":"Ironhold","kind":"location"}]'),
        user_id="u", model_source="user_model", model_ref="m", premise="p",
    )
    assert [e.name for e in out] == ["Ironhold"]
