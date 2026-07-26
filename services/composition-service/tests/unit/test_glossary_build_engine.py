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
        llm, source_text="s", name="X", kind="character", kinds=KINDS, lang="vi")
    assert out["attributes"] == {"role": "hero"}
    assert out["relations"] == [{"target_name": "Lâm gia", "type": "member_of", "note": "n"}]
    assert all(r["type"] in RELATION_TYPES for r in out["relations"])


@pytest.mark.asyncio
async def test_standard_build_empty_attributes_is_a_skip_not_a_fake_entity():
    llm = fake_llm([json.dumps({"name": "X", "kind": "character", "attributes": {}})] * 2)
    out = await engine.build_standard(
        llm, source_text="s", name="X", kind="character", kinds=KINDS, lang="vi")
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
        llm, source_text="s", name="X", kind="character", kinds=KINDS, lang="vi")
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
        llm, source_text="s", name="X", kind="character", kinds=KINDS, lang="vi")
    assert entity is not None and sections == []  # fallback recorded via empty sections


@pytest.mark.asyncio
async def test_deep_build_distill_failure_keeps_the_profile_honestly():
    llm = fake_llm([_outline(2), "long detail A", "long detail B", "bad", "bad again"])
    entity, sections = await engine.build_deep(
        llm, source_text="s", name="X", kind="character", kinds=KINDS, lang="vi")
    assert len(sections) == 2
    # the long-form work is never silently lost
    assert entity["attributes"]["description"].startswith("long detail A")


@pytest.mark.asyncio
async def test_deep_build_respects_max_sections_cap():
    llm = fake_llm([_outline(12)] + ["d"] * 4 + [json.dumps(
        {"name": "X", "kind": "character", "attributes": {"role": "r"}, "relations": []})])
    entity, sections = await engine.build_deep(
        llm, source_text="s", name="X", kind="character", kinds=KINDS, lang="vi",
        max_sections=4)
    assert len(sections) == 4  # the loop is bounded by the CAP, not the model's plan
