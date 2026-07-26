"""Tests for the anchoring helper (M3) — parse, render, resolve priority.

The shared renderer used by BOTH the text and voice paths. Covers the goal
being present in both placements, the kctx>seed priority, the degraded fallback,
and defensive parsing.
"""
from __future__ import annotations

import json

from app.services.working_memory import (
    parse_working_memory,
    render_pinned,
    render_tail,
    resolve_anchor,
)

_CHARTER = {
    "goal": "Senior backend interview",
    "phases": ["warmup", "technical", "behavioral", "wrap"],
    "checklist": ["system design", "conflict story", "REST vs gRPC"],
    "time_budget_min": 60,
    "language": "vi",
}


def _seed_json(**state) -> str:
    block = {"version": 1, "charter": _CHARTER, "state": {"phase": "", "covered": [], **state}}
    return json.dumps(block)


def test_parse_accepts_json_string_and_dict():
    assert parse_working_memory(_seed_json()) is not None
    assert parse_working_memory(json.loads(_seed_json())) is not None


def test_parse_is_defensive():
    assert parse_working_memory(None) is None
    assert parse_working_memory("") is None
    assert parse_working_memory("not json {{{") is None
    assert parse_working_memory("[1,2,3]") is None          # not a dict
    assert parse_working_memory('{"charter": {}}') is None  # invalid charter


def test_pinned_contains_goal_phase_and_remaining():
    wm = parse_working_memory(_seed_json(phase="technical", covered=["REST vs gRPC"]))
    pinned = render_pinned(wm)
    assert "Senior backend interview" in pinned
    assert "technical" in pinned
    # remaining = checklist - covered
    assert "system design" in pinned and "conflict story" in pinned
    assert "REST vs gRPC" in pinned  # appears in 'Covered'
    assert "Respond in: vi" in pinned


def test_tail_is_terse_instruction_with_goal_and_no_narration_leak():
    wm = parse_working_memory(_seed_json(redirect_hint="bring them back to system design"))
    tail = render_tail(wm)
    assert tail.startswith("[Director")
    assert "Senior backend interview" in tail
    assert "bring them back to system design" in tail
    # instructs the model NOT to read it aloud (EC-7)
    assert "do not mention this note" in tail


def test_resolve_prefers_kctx_over_seed():
    # live block (kctx) has progress; seed is the frozen charter only
    live = _seed_json(phase="behavioral", covered=["system design", "REST vs gRPC"])
    pinned, tail = resolve_anchor(live, _seed_json())
    assert "behavioral" in pinned
    # remaining now only the conflict story
    assert "Still to cover: conflict story" in pinned
    assert tail  # goal present


def test_resolve_falls_back_to_seed_when_kctx_empty():
    # degraded EC-4: knowledge returns "", seed carries the goal anchor
    pinned, tail = resolve_anchor("", _seed_json())
    assert "Senior backend interview" in pinned
    assert "Senior backend interview" in tail


def test_resolve_returns_empty_for_non_roleplay_session():
    assert resolve_anchor("", None) == ("", "")
    assert resolve_anchor(None, None) == ("", "")


def test_resolve_returns_empty_on_malformed_both():
    assert resolve_anchor("garbage", "also garbage") == ("", "")
