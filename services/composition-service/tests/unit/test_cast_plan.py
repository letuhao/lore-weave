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
        # propose_cast/propose_world thread the model window into the
        # output budget; None = 'unknown', which applies no clamp.
        async def resolve_context_length(self, *a, **k):
            return None

        async def submit_and_wait(self, **kw):
            return SimpleNamespace(status="failed", result={})
    out = await propose_cast(_LLM(), user_id="u", model_source="user_model", model_ref="m",
                             premise="p", source_language="vi")
    assert out == []


async def test_propose_cast_happy_parses_array():
    payload = json.dumps([{"name": "Lâm Uyển", "role": "protagonist", "is_new": False}])

    class _LLM:
        # propose_cast/propose_world thread the model window into the
        # output budget; None = 'unknown', which applies no clamp.
        async def resolve_context_length(self, *a, **k):
            return None

        async def submit_and_wait(self, **kw):
            # the genre/language steer must reach the prompt
            assert "PREMISE:" in kw["input"]["messages"][1]["content"]
            return SimpleNamespace(status="completed", result={"messages": [{"content": payload}]})
    out = await propose_cast(_LLM(), user_id="u", model_source="user_model", model_ref="m",
                             premise="Lâm Uyển bị ghẻ lạnh...", source_language="vi",
                             genre_tags=["xianxia"])
    assert len(out) == 1 and out[0].name == "Lâm Uyển"


# ── E6: the pass can finally SEE the book it is planning ────────────────────────────────────────

def test_known_cast_redefines_is_new_against_the_BOOK_not_the_premise():
    """The bug E6 fixes, stated as a test.

    `is_new` meant "not named in the PREMISE" — and a premise is ONE arc's summary. So for a book
    thirty chapters deep, every established character the premise happened not to mention came back
    `is_new=true`: the planner proposed INTRODUCING people the reader already knows, under freshly
    invented names. The rule has to be anchored to the roster, and it can only say that when a
    roster was actually supplied.
    """
    system, _ = cast_plan.build_propose_cast_messages("P", known_cast=["Lâm Uyển"])
    assert "EXISTING CAST below" in system
    assert "i.e. not named in the premise" not in system


def test_the_existing_cast_reaches_the_USER_message_with_a_do_not_rename_rule():
    _, user = cast_plan.build_propose_cast_messages("P", known_cast=["Lâm Uyển", "Mị Đế"])
    assert "Lâm Uyển" in user and "Mị Đế" in user
    assert "do NOT rename or re-invent them" in user
    # The roster is DATA about this book, so it belongs beside the premise, not in the system
    # prompt where the behavioural rules live.
    assert "PREMISE:" in user


def test_canon_anchors_reach_the_prompt_at_all():
    """`package["canon"]` was compiled on every run and read by nobody — the author's own
    "these facts are fixed" block never travelled. Absence of this assertion is the whole bug."""
    _, user = cast_plan.build_propose_cast_messages("P", canon="The empire fell in year 300.")
    assert "The empire fell in year 300." in user
    assert "must not contradict" in user


def test_a_FRESH_book_is_byte_identical_to_before_E6():
    """No roster and no anchors is the normal state of a new book. It must not gain an empty
    EXISTING CAST section, which would read to the model as 'this book has no characters' — a
    different claim from saying nothing at all."""
    system, user = cast_plan.build_propose_cast_messages("P", "auto", ["xianxia"])
    assert user == "PREMISE:\n\nP"
    assert "EXISTING CAST" not in user and "CANON" not in user
    assert "i.e. not named in the premise" in system


def test_the_roster_is_capped_so_a_long_book_cannot_blow_the_prompt():
    _, user = cast_plan.build_propose_cast_messages("P", known_cast=[f"C{i}" for i in range(200)])
    assert "- C0" in user and "- C39" in user
    assert "- C40" not in user


async def test_propose_cast_THREADS_the_roster_and_canon_into_the_real_call():
    """The builder having the parameters proves nothing if `propose_cast` never passes them.

    Mutation-checked: cutting `known_cast=` or `canon=` at that call site left every other test in
    this file green, because they all exercise the builder directly. That is the exact shape this
    codebase keeps rediscovering — a capability wired at one layer and dead at the next — so the
    assertion is on the messages ACTUALLY SENT to the model.
    """
    captured: dict = {}

    class _LLM:
        # propose_cast/propose_world thread the model window into the
        # output budget; None = 'unknown', which applies no clamp.
        async def resolve_context_length(self, *a, **k):
            return None

        async def submit_and_wait(self, **kw):
            captured["user"] = kw["input"]["messages"][1]["content"]
            captured["system"] = kw["input"]["messages"][0]["content"]
            return SimpleNamespace(status="completed", result={"messages": [{"content": "[]"}]})

    await propose_cast(
        _LLM(), user_id="u", model_source="user_model", model_ref="m",
        premise="an arc summary that never mentions her",
        known_cast=["Lâm Uyển"], canon="The empire fell in year 300.",
    )
    assert "Lâm Uyển" in captured["user"], "the established cast never reached the model"
    assert "The empire fell in year 300." in captured["user"], "canon never reached the model"
    assert "EXISTING CAST below" in captured["system"], "is_new was still judged on the premise"
