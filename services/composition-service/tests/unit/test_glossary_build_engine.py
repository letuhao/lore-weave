"""Glossary-build engine (spec 2026-07-27) — bounds, validation, degrade paths.

The engine's whole contract is the POC-locked discipline: one call per step, one
retry on invalid JSON then SKIP, closed-set relations by NAME, deep loop bounded
by its own outline. These prove the bounds with fake LLMs — no network."""
from __future__ import annotations

import json

import pytest

from app.services.glossary_build import engine
from app.services.glossary_build.prompts import RELATION_TYPES

KINDS = ["character", "organization", "terminology"]
# the kind's REAL attribute codes (what the executor is now told to fill)
FIELDS = ["name", "role", "description"]


def fake_llm(responses: list[str]):
    """Sequential fake — records call count + last messages."""
    state = {"n": 0, "messages": []}

    async def llm(messages, max_tokens):
        state["messages"].append(list(messages))  # snapshot — the deep convo mutates in place
        i = min(state["n"], len(responses) - 1)
        state["n"] += 1
        return responses[i]

    llm.state = state
    return llm


# ── planner ──────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_planner_validates_dedups_and_caps():
    rows = [
        {"name": "Tô Thanh Dao", "kind": "character", "depth": "deep", "why": "w"},
        {"name": "tô thanh dao", "kind": "character"},          # dup (casefold)
        {"name": "Lâm Uyên", "kind": "character"},              # already in glossary
        {"name": "Ghost", "kind": "not_a_kind"},                # invalid kind
        {"name": "", "kind": "character"},                      # blank name
        {"name": "Tô gia", "kind": "organization", "depth": "bogus"},  # depth → standard
    ]
    llm = fake_llm([json.dumps(rows)])
    out = await engine.run_planner(
        llm, source_text="s", kinds=KINDS, existing_names=["Lâm Uyên"], lang="vi")
    assert [(o["name"], o["depth"]) for o in out] == [
        ("Tô Thanh Dao", "deep"), ("Tô gia", "standard")]


@pytest.mark.asyncio
async def test_planner_invalid_json_gets_ONE_retry_then_empty():
    llm = fake_llm(["not json at all", "still not json"])
    out = await engine.run_planner(
        llm, source_text="s", kinds=KINDS, existing_names=[], lang="vi")
    assert out == []
    assert llm.state["n"] == 2  # exactly one retry — never a loop
    # the retry names the failure so the model can repair
    assert "not valid JSON" in llm.state["messages"][1][-1]["content"]


# ── standard executor ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_standard_build_cleans_relations_to_the_closed_set():
    built = {"name": "X", "kind": "character",
             "attributes": {"role": "hero", "empty": "  "},
             "relations": [
                 {"target_name": "Lâm gia", "type": "member_of", "note": "n"},
                 {"target_name": "Y", "type": "invented_type"},   # not closed-set → dropped
                 {"target_name": "X", "type": "loves"},           # self-relation → dropped
             ]}
    llm = fake_llm([json.dumps(built)])
    out = await engine.build_standard(
        llm, source_text="s", name="X", kind="character", fields=FIELDS, lang="vi")
    assert out["attributes"] == {"role": "hero"}
    assert out["relations"] == [{"target_name": "Lâm gia", "type": "member_of", "note": "n"}]
    assert all(r["type"] in RELATION_TYPES for r in out["relations"])


@pytest.mark.asyncio
async def test_standard_build_empty_attributes_is_a_skip_not_a_fake_entity():
    llm = fake_llm([json.dumps({"name": "X", "kind": "character", "attributes": {}})] * 2)
    out = await engine.build_standard(
        llm, source_text="s", name="X", kind="character", fields=FIELDS, lang="vi")
    assert out is None


# ── deep loop ────────────────────────────────────────────────────────────────

def _outline(n=3):
    return json.dumps([{"section": f"S{i}", "focus": f"f{i}"} for i in range(n)])


@pytest.mark.asyncio
async def test_deep_build_outline_steer_distill_happy_path():
    distilled = {"name": "X", "kind": "character", "attributes": {"role": "r"},
                 "relations": []}
    llm = fake_llm([_outline(3), "detail one", "detail two", "detail three",
                    json.dumps(distilled)])
    entity, sections = await engine.build_deep(
        llm, source_text="s", name="X", kind="character", fields=FIELDS, lang="vi")
    assert entity["attributes"] == {"role": "r"}
    assert [s["section"] for s in sections] == ["S0", "S1", "S2"]
    # 1 outline + 3 sections + 1 distill = 5 calls, no more (bounded by the outline)
    assert llm.state["n"] == 5
    # the craft instruction VARIES across steering turns (spec weakness #1)
    steers = [m[-1]["content"] for m in llm.state["messages"][1:4]]
    assert len({s.split("Write 4-7 SPECIFIC sentences. ")[1] for s in steers}) == 3


@pytest.mark.asyncio
async def test_deep_build_outline_failure_falls_back_to_standard():
    single = {"name": "X", "kind": "character", "attributes": {"role": "r"}, "relations": []}
    llm = fake_llm(["nope", "still nope", json.dumps(single)])
    entity, sections = await engine.build_deep(
        llm, source_text="s", name="X", kind="character", fields=FIELDS, lang="vi")
    assert entity is not None and sections == []  # fallback recorded via empty sections


@pytest.mark.asyncio
async def test_deep_build_distill_failure_keeps_the_profile_honestly():
    llm = fake_llm([_outline(2), "long detail A", "long detail B", "bad", "bad again"])
    entity, sections = await engine.build_deep(
        llm, source_text="s", name="X", kind="character", fields=FIELDS, lang="vi")
    assert len(sections) == 2
    # the long-form work is never silently lost
    assert entity["attributes"]["description"].startswith("long detail A")


@pytest.mark.asyncio
async def test_deep_build_respects_max_sections_cap():
    llm = fake_llm([_outline(12)] + ["d"] * 4 + [json.dumps(
        {"name": "X", "kind": "character", "attributes": {"role": "r"}, "relations": []})])
    entity, sections = await engine.build_deep(
        llm, source_text="s", name="X", kind="character", fields=FIELDS, lang="vi",
        max_sections=4)
    assert len(sections) == 4  # the loop is bounded by the CAP, not the model's plan


# ── M6 steering fixes (live-caught 2026-07-27) ───────────────────────────────

@pytest.mark.asyncio
async def test_a_list_typed_value_stays_a_LIST_not_a_python_repr():
    """Live bug: `aliases` (field_type=tags) came back as a JSON array and the
    postprocess did str(v) → "['a', 'b']", which the glossary then wrapped again
    into ["['a', 'b']"]. A typed value must survive the boundary intact."""
    built = {"attributes": {"aliases": ["Hạt nhân nguyên thủy", "Mã nguồn gốc"],
                            "description": "một hằng số"}}
    llm = fake_llm([json.dumps(built)])
    out = await engine.build_standard(
        llm, source_text="s", name="Chân Linh", kind="power_system",
        fields=["aliases", "description"], lang="vi",
        types={"aliases": "tags", "description": "textarea"})
    assert out["attributes"]["aliases"] == ["Hạt nhân nguyên thủy", "Mã nguồn gốc"]
    assert isinstance(out["attributes"]["description"], str)


def test_the_prompt_shows_a_tags_field_as_an_ARRAY():
    """The model has to be TOLD the shape — with no marker it guessed, and the
    guess is what the postprocess then mangled."""
    from app.services.glossary_build.prompts import executor_messages
    sysmsg = executor_messages("s", "X", "power_system", ["aliases", "description"],
                               "vi", {"aliases": "tags", "description": "textarea"})[0]["content"]
    assert '"aliases": ["...", "..."]' in sysmsg      # array shape, explicitly
    assert '"description": "... (2-4 câu)"' in sysmsg  # prose shape


# ── declared absence (approved 2026-07-27) ───────────────────────────────────

@pytest.mark.asyncio
@pytest.mark.parametrize("empty", [None, "", "   ", "null", "Không có", "chưa xác định"])
async def test_an_empty_field_is_DECLARED_absent_not_silently_missing(empty):
    """Fiction is not a form: a kind may define an attribute the story has not
    established. The model is allowed to say so — and the word forms count too, or
    "chưa xác định" would land in the glossary as canon text."""
    llm = fake_llm([json.dumps({"attributes": {"name": "Pháp khí", "owner": empty}})])
    out = await engine.build_standard(
        llm, source_text="s", name="Pháp khí", kind="item",
        fields=["name", "owner", "description"], lang="vi")
    assert out["attributes"] == {"name": "Pháp khí"}      # never stored as a value
    assert out["absent"] == ["owner"]                     # the human's authoring prompt
    assert out["missing"] == ["description"]              # never mentioned = attention drop


@pytest.mark.asyncio
async def test_an_all_empty_tag_list_counts_as_absent_not_an_empty_list():
    llm = fake_llm([json.dumps({"attributes": {"name": "X", "aliases": ["", "  "]}})])
    out = await engine.build_standard(
        llm, source_text="s", name="X", kind="item", fields=["name", "aliases"],
        lang="vi", types={"aliases": "tags"})
    assert "aliases" not in out["attributes"] and out["absent"] == ["aliases"]


@pytest.mark.asyncio
async def test_an_out_of_schema_key_is_REPORTED_not_silently_dropped():
    """The glossary's own policy for an unknown code is preserve-into-fallback
    (D-GLOSSARY-UNMATCHED-ATTR-FALLBACK). Dropping it here with no record would make
    this path strictly more lossy than the service it writes to."""
    built = {"attributes": {"name": "X", "description": "d",
                            "secrets": "nàng phản bội gia tộc",   # no such field on `item`
                            "goals": "   "}}                      # blank → not worth reporting
    llm = fake_llm([json.dumps(built)])
    out = await engine.build_standard(
        llm, source_text="s", name="X", kind="item", fields=["name", "description"], lang="vi")
    assert out["attributes"] == {"name": "X", "description": "d"}
    assert out["extra"] == ["secrets"]


def test_the_prompt_OFFERS_null_with_a_high_bar():
    """A retry/nudge that can only succeed by producing text is a hallucination
    pump — so the escape hatch must exist, but must not read as a free pass."""
    from app.services.glossary_build.prompts import batch_messages, executor_messages
    for msgs in (executor_messages("s", "X", "item", ["name"], "vi"),
                 batch_messages("s", ["X", "Y"], "item", ["name"], "vi")):
        sysmsg = msgs[0]["content"]
        assert "return null for that field" in sysmsg
        assert "not a way to avoid work" in sysmsg


def test_slicing_keeps_PROSE_fields_and_drops_tag_lists():
    """Live bug: slicing `item` by sort_order kept name/aliases/type/owner and
    dropped BOTH description and symbolic_meaning — every field that carries
    meaning. sort_order is form layout, not information value."""
    from app.services.glossary_build.prompts import select_fields
    item = [
        {"code": "name", "field_type": "text", "is_required": True, "sort_order": 1},
        {"code": "aliases", "field_type": "tags", "is_required": False, "sort_order": 2},
        {"code": "type", "field_type": "text", "is_required": False, "sort_order": 3},
        {"code": "owner", "field_type": "text", "is_required": False, "sort_order": 4},
        {"code": "symbolic_meaning", "field_type": "textarea", "is_required": False, "sort_order": 5},
        {"code": "description", "field_type": "textarea", "is_required": False, "sort_order": 6},
    ]
    kept = select_fields(item, deep=False)
    assert "description" in kept and "symbolic_meaning" in kept   # the prose survives
    assert "aliases" not in kept                                   # the tag list is cut first
    assert kept[0] == "name"                                       # required still first


def test_the_prompt_NAMES_related_to_as_the_fallback_verb():
    """Adding `related_to` to the closed set was not enough — live-caught on run
    019fa2f7, the executor emitted `Chân Linh enemy_of Thanh Tâm Ấn` while its own note
    said "khác biệt hoàn toàn với" ("completely different from"). It meant *is distinct
    from* and reached for the nearest specific verb instead of the catch-all sitting
    right there. A closed set does not produce silence when nothing fits; it produces
    the closest wrong answer. The escape has to be named, and saying nothing has to be
    a legal outcome."""
    from app.services.glossary_build.prompts import batch_messages, executor_messages
    for msgs in (executor_messages("s", "X", "item", ["name"], "vi"),
                 batch_messages("s", ["X", "Y"], "item", ["name"], "vi")):
        sysmsg = msgs[0]["content"]
        assert "MOST SPECIFIC type that is literally true" in sysmsg
        assert "use `related_to`" in sysmsg
        assert "emit no relation for them at all" in sysmsg
