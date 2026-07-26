"""Track B B1(2) — the multi-project (multi-KG) union merge/dedup/rank + shared budget.

These lock the ONLY new logic the multi-project mode adds over the reused single-project
selectors: cross-project dedup (world-bible vs member overlap), global re-rank, and the
one shared-budget reverse-priority trim.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.context.modes import multi_project as mp
from app.context.modes.multi_project import (
    _enforce_shared_budget,
    _merge_entities,
    _merge_facts,
    _merge_passages,
    _merge_summaries,
)
from loreweave_context import scale_by_window

USER_ID = uuid4()


def _ent(name, score):
    return SimpleNamespace(
        cached_name=name, rank_score=score, entity_id=name,
        kind_code="character", short_description="", cached_aliases=[], tier="user",
    )


def _proj(name):
    return SimpleNamespace(project_id=name, name=name, instructions="", tool_calling_enabled=True)


def _l2(current=None, recent=None, background=None, negative=None):
    return SimpleNamespace(
        current=current or [], recent=recent or [],
        background=background or [], negative=negative or [],
    )


def test_merge_entities_dedups_by_name_keeps_highest_and_global_sorts():
    """EC-B4: the same entity across two projects collapses to ONE row (highest
    salience wins); the merged list is globally sorted by score."""
    pA = {"project": _proj("A"), "entities": [_ent("Hero", 0.5), _ent("Sword", 0.9)]}
    pB = {"project": _proj("B"), "entities": [_ent("hero", 0.8), _ent("Villain", 0.3)]}
    merged = _merge_entities([pA, pB])

    ordered = [(proj.name, e.cached_name, e.rank_score) for proj, e in merged]
    assert [o[1] for o in ordered] == ["Sword", "hero", "Villain"]  # global score-desc
    hero = next(o for o in ordered if o[1].lower() == "hero")
    assert hero == ("B", "hero", 0.8)  # case-insensitive dedup; highest-score copy won


def test_merge_facts_dedups_by_text_across_projects_and_buckets():
    pA = {"project": _proj("A"), "l2": _l2(current=["X loves Y", "shared fact"])}
    pB = {"project": _proj("B"), "l2": _l2(recent=["shared fact"], background=["B only"])}
    merged = _merge_facts([pA, pB])

    texts = [f for _p, f in merged]
    assert texts.count("shared fact") == 1  # deduped across projects + buckets
    assert "X loves Y" in texts and "B only" in texts
    # tagged with the FIRST (highest-priority bucket) project it appeared in
    shared_owner = next(p for p, f in merged if f == "shared fact")
    assert shared_owner == "A"  # current(A) beats recent(B)


def test_merge_passages_dedups_by_source_and_global_sorts():
    p = SimpleNamespace
    pA = {"project": _proj("A"), "l3": [p(source_id="s1", score=0.4, text="a"), p(source_id="s2", score=0.9, text="b")]}
    pB = {"project": _proj("B"), "l3": [p(source_id="s1", score=0.7, text="a"), p(source_id="s3", score=0.2, text="c")]}
    merged = _merge_passages([pA, pB])
    ids = [(pname, pas.source_id, pas.score) for pname, pas in merged]
    assert [i[1] for i in ids] == ["s2", "s1", "s3"]  # global score-desc
    s1 = next(i for i in ids if i[1] == "s1")
    assert s1 == ("B", "s1", 0.7)  # deduped, highest-score copy


def test_merge_summaries_dedups_by_level_path_global_sort():
    h = SimpleNamespace
    pA = {"project": _proj("A"), "summaries": [h(level="book", node_path="/", weighted_score=0.6, summary_text="A")]}
    pB = {"project": _proj("B"), "summaries": [h(level="book", node_path="/", weighted_score=0.9, summary_text="B"),
                                               h(level="chapter", node_path="/c1", weighted_score=0.3, summary_text="c")]}
    merged = _merge_summaries([pA, pB])
    assert len(merged) == 2  # (book,/) deduped
    assert merged[0][1].summary_text == "B"  # highest weighted_score wins + first


def test_shared_budget_trims_lowest_score_passages_first():
    """One SHARED budget across the union — trim the lowest-scored tail items to fit."""
    p = SimpleNamespace
    passages = [("A", p(source_id=f"s{i}", score=1.0 - i * 0.1, text="lorem ipsum dolor sit amet " * 8))
                for i in range(6)]
    ctx, tokens, sections = _enforce_shared_budget(
        projects=[_proj("A")], l0=None, entities=[], facts=[], passages=passages,
        summaries=[], project_summaries={}, budget_tokens=80,
    )
    assert "<memory" in ctx
    kept = ctx.count("<passage ")
    assert kept < 6  # over-budget → some passages dropped
    # whichever survived are the highest-scored (s0..); the lowest (s5) is gone
    assert "s5" not in ctx


@pytest.mark.asyncio
async def test_build_multi_project_mode_scales_shared_budget_with_context_length(monkeypatch):
    """/review-impl LOW: build_multi_project_mode's `context_length` ->
    `scale_by_window(mode3_token_budget, ...)` wiring (multi_project.py) had no test
    proving it actually reaches `_enforce_shared_budget` with the SCALED value — this
    proves the wiring end-to-end, mirroring test_mode_full.py's sibling coverage."""
    p1, p2 = _proj("A"), _proj("B")
    empty_l2 = SimpleNamespace(current=[], recent=[], background=[], negative=[])
    monkeypatch.setattr(mp, "load_global_summary", AsyncMock(return_value=None))
    monkeypatch.setattr(mp, "load_project_summary", AsyncMock(return_value=None))
    monkeypatch.setattr(
        mp, "_retrieve_one",
        AsyncMock(side_effect=lambda *, project, **_kw: {
            "project": project, "entities": [], "l2": empty_l2, "l3": [], "summaries": [],
        }),
    )
    seen_budgets: list[int] = []
    real_enforce = mp._enforce_shared_budget

    def _spy_enforce(**kwargs):
        seen_budgets.append(kwargs["budget_tokens"])
        return real_enforce(**kwargs)

    monkeypatch.setattr(mp, "_enforce_shared_budget", _spy_enforce)
    monkeypatch.setattr(mp.settings, "mode3_token_budget", 1000)

    await mp.build_multi_project_mode(
        summaries_repo=MagicMock(), glossary_client=MagicMock(),
        user_id=USER_ID, projects=[p1, p2], message="hi",
        context_length=1_000_000,
    )

    assert seen_budgets == [scale_by_window(1000, 1_000_000)]
    assert seen_budgets[0] > 1000  # the exact bug class: must NOT stay flat


@pytest.mark.asyncio
async def test_build_multi_project_mode_disables_canon_capture(monkeypatch):
    """WS-4C Half A — capture writes into ONE book's glossary inbox, but a multi
    turn grounds on a union of projects with no single book. `tool_calling_enabled`
    unions permissively (`any`); capture must NOT copy that pattern, or a multi turn
    would silently capture into whichever project happened to sort first."""
    p1, p2 = _proj("A"), _proj("B")
    empty_l2 = SimpleNamespace(current=[], recent=[], background=[], negative=[])
    monkeypatch.setattr(mp, "load_global_summary", AsyncMock(return_value=None))
    monkeypatch.setattr(mp, "load_project_summary", AsyncMock(return_value=None))
    monkeypatch.setattr(
        mp, "_retrieve_one",
        AsyncMock(side_effect=lambda *, project, **_kw: {
            "project": project, "entities": [], "l2": empty_l2, "l3": [], "summaries": [],
        }),
    )
    # Both projects have capture ON — the mode must still refuse.
    p1.canon_capture_enabled = True
    p2.canon_capture_enabled = True

    built = await mp.build_multi_project_mode(
        summaries_repo=MagicMock(), glossary_client=MagicMock(),
        user_id=USER_ID, projects=[p1, p2], message="hi",
    )
    assert built.canon_capture_enabled is False
    assert built.tool_calling_enabled is True  # the permissive union still applies here
