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


# ── E6b · the existing world + the canon anchors ───────────────────────────────
#
# The bug: `is_new` meant "not named in the PREMISE", and a premise is ONE arc's summary. Forty
# chapters in, the capital the story has been set in since chapter three came back marked
# `is_new` — a planned INTRODUCTION of a place the reader already knows, frequently under a new
# name. The fix anchors `is_new` to the book's actual world instead.


def test_known_world_redefines_is_new_against_the_BOOK_not_the_premise():
    """The premise is one arc. Judging "new" against it re-invents the whole standing world."""
    system, _ = build_propose_world_messages("P", known_world={"location": ["Hoa Sơn"]})
    assert "named neither in the premise nor" in system
    assert "in the EXISTING WORLD listed below" in system
    # …and the premise-only wording is GONE when a roster exists — not merely accompanied by the
    # new sentence, which would leave the model two conflicting definitions.
    assert "true ONLY for entries you invented (not named in the premise)" not in system


def test_without_a_roster_the_prompt_is_UNCHANGED_from_before_E6b():
    """A fresh book has no world, and an empty "EXISTING WORLD" heading reads as "this book has
    none" — a lie that would push the model to invent over the top of it."""
    system, user = build_propose_world_messages("p", known_world={}, canon="")
    assert "`is_new` is true ONLY for entries you invented (not named in the premise). " in system
    assert "EXISTING WORLD" not in user and "CANON" not in user
    assert user == "PREMISE:\np"
    # A roster whose buckets are all empty is the same as no roster at all.
    _, user2 = build_propose_world_messages("p", known_world={"location": [], "faction": []})
    assert user2 == "PREMISE:\np"


def test_the_existing_world_is_listed_BY_KIND_not_flattened():
    """Telling the model "Hoa Sơn already exists" without saying it is a *location* is how a
    mountain gets written as a person. The cast can be flat; a world cannot."""
    _, user = build_propose_world_messages("p", known_world={
        "location": ["Hoa Sơn"], "faction": ["Thanh Vân Môn"], "concept": ["Kiếm Đạo"],
    })
    assert "PLACES: Hoa Sơn" in user
    assert "FACTIONS / ORGANISATIONS: Thanh Vân Môn" in user
    assert "CONCEPTS: Kiếm Đạo" in user
    assert "do NOT rename or re-invent them" in user
    assert "is_new=false" in user
    # Fixed order regardless of dict insertion order — the same book must build the same prompt.
    _, other = build_propose_world_messages("p", known_world={
        "concept": ["Kiếm Đạo"], "faction": ["Thanh Vân Môn"], "location": ["Hoa Sơn"],
    })
    assert other == user


def test_a_kind_pass_3_may_not_propose_is_not_listed_back_to_it():
    """WORLD_KINDS is a closed set. Listing a `character` under EXISTING WORLD would be an
    instruction the model cannot obey — it is forbidden to return that kind."""
    _, user = build_propose_world_messages("p", known_world={
        "character": ["Lâm Uyển"], "location": ["Hoa Sơn"],
    })
    assert "Hoa Sơn" in user
    assert "Lâm Uyển" not in user


def test_the_roster_is_capped_PER_KIND_so_a_thin_bucket_survives_a_fat_one():
    """A book with ninety locations and three factions must still show the factions. An overall
    cap would spend the whole budget on locations and silently drop the rest."""
    _, user = build_propose_world_messages("p", known_world={
        "location": [f"L{i}" for i in range(200)],
        "faction": ["Thanh Vân Môn"],
    })
    assert "L0" in user and "L39" in user
    assert "L40" not in user and "L199" not in user
    assert "Thanh Vân Môn" in user           # not starved by the fat bucket
    assert len(user) < 4000


def test_canon_anchors_reach_the_pass_that_does_the_INVENTING():
    """Consistency anchors bite hardest here: "the empire fell in year 300" is a constraint on
    invented factions and concepts, and this is the pass that invents them. It was compiled on
    every run and read by nobody."""
    _, user = build_propose_world_messages("p", canon="The empire fell in year 300.")
    assert "CANON" in user and "The empire fell in year 300." in user
    # Whitespace-only is not canon.
    _, blank = build_propose_world_messages("p", canon="   \n  ")
    assert "CANON" not in blank


@pytest.mark.asyncio
async def test_propose_world_FORWARDS_the_roster_and_canon_to_the_prompt(monkeypatch):
    """The layer between the adapter and the builder. Mutation-checked: dropping `known_world=`
    and `canon=` from this call left every builder test above green, because they call the builder
    directly — the exact wired-here/dead-there shape this sweep exists to catch."""
    import app.engine.world_plan as wp

    seen: dict = {}
    real = wp.build_propose_world_messages

    def _spy(*a, **kw):
        seen.update(kw)
        return real(*a, **kw)

    monkeypatch.setattr(wp, "build_propose_world_messages", _spy)

    class _LLM:
        # propose_cast/propose_world thread the model window into the
        # output budget; None = 'unknown', which applies no clamp.
        async def resolve_context_length(self, *a, **k):
            return None

        async def submit_and_wait(self, **kw):
            self.input = kw["input"]
            return type("J", (), {"status": "failed", "result": None})()

    llm = _LLM()
    await propose_world(
        llm, user_id="u", model_source="user_model", model_ref="m", premise="p",
        known_world={"location": ["Hoa Sơn"]}, canon="The empire fell in year 300.",
    )
    assert seen["known_world"] == {"location": ["Hoa Sơn"]}
    assert seen["canon"] == "The empire fell in year 300."
    # …and they actually reached the wire, not just the builder call.
    sent = "\n".join(m["content"] for m in llm.input["messages"])
    assert "Hoa Sơn" in sent and "The empire fell in year 300." in sent


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
    # propose_cast/propose_world thread the model window into the
    # output budget; None = 'unknown', which applies no clamp.
    async def resolve_context_length(self, *a, **k):
        return None

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


# ── the model's window actually bounds the output budget ──────────────────────────────────

async def test_a_small_context_model_CLAMPS_the_world_budget():
    """Proof by EFFECT, not by the call being made.

    Sizing `propose_world` on its item count is what this budget change is for, and on an
    established book it resolves to ~32k output tokens — the SDK's runaway ceiling. A cap the
    model's window cannot honour trades an under-budget bug for a failed request, so the
    window is threaded in and `_MAX_WINDOW_SHARE` clamps it.

    Asserting that `resolve_context_length` was CALLED would pass just as well with the result
    thrown away, which is how a threaded signal becomes decoration. So this reads the number
    that reached the wire, and carries its own control: the same call on a large-window model
    must NOT be clamped, or the assertion below is about the ceiling rather than the window.
    """
    sent: dict = {}

    def _client(window: int | None):
        class _LLM:
            async def resolve_context_length(self, *a, **k):
                return window

            async def submit_and_wait(self, **kw):
                sent[window] = kw["input"]["max_tokens"]
                return type("J", (), {"status": "failed", "result": None})()
        return _LLM()

    big_roster = {k: [f"n{i}" for i in range(40)] for k in ("location", "faction", "concept")}
    for window in (8192, None):
        await propose_world(
            _client(window), user_id="u", model_source="user_model", model_ref="m",
            premise="p", known_world=big_roster,
        )

    assert sent[8192] == 4096, "an 8k-window model was not clamped to its half-window share"
    assert sent[None] > sent[8192], (
        "the unclamped control resolved no higher than the clamped run — then the clamp is "
        "not what produced the smaller number and this test proves nothing"
    )


# ── the schema-shaped answer must parse ───────────────────────────────────────────────────

def test_the_SCHEMA_shaped_response_parses():
    """`_WORLD_SCHEMA` requires `{"items": [...]}`, so that is the shape every grammar-honouring
    provider returns — and this parser read a bare array, so it produced `[]` for all of them.

    Measured live on gemma-4-26b before the fix: `finish_reason=stop`, 2864 characters of valid
    JSON, ZERO entities. Pass 3 degrades to `[]` on any failure, so a dead pass was
    indistinguishable from a premise with no world in it.
    """
    payload = json.dumps({"items": [
        {"name": "Thanh Vân Môn", "kind": "faction", "summary": "s", "is_new": False},
        {"name": "Hoa Sơn", "kind": "location", "summary": "s", "is_new": True},
    ]}, ensure_ascii=False)
    out = parse_world(payload)
    assert [e.name for e in out] == ["Thanh Vân Môn", "Hoa Sơn"]
    assert [e.kind for e in out] == ["faction", "location"]


def test_the_bare_array_shape_still_parses():
    """The CONTROL. The prompt asks for a bare array and a provider without grammar support
    still returns one, so the wrapper fix must not become a wrapper REQUIREMENT."""
    payload = json.dumps([{"name": "Hoa Sơn", "kind": "location", "summary": "s"}],
                         ensure_ascii=False)
    assert [e.name for e in parse_world(payload)] == ["Hoa Sơn"]


def test_an_AMBIGUOUS_wrapper_is_refused_rather_than_guessed():
    """Two candidate lists and no `items` key — picking one would be a coin flip that reads as
    a successful parse. `[]` is the honest answer and the degrade path already handles it."""
    payload = json.dumps({"alpha": [{"name": "A", "kind": "location"}],
                          "beta": [{"name": "B", "kind": "faction"}]})
    assert parse_world(payload) == []
