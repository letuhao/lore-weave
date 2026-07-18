"""F7c (2026-07-19) lazy-context enforcement — index+load-on-demand for skills,
frontend studio panel, and the workflow directive.

docs/plans/2026-07-19-lazy-context-enforcement.md. These pin the THREE levers'
behavior: each is off-by-default (baseline byte-identical) and, when on, defers the
verbose block while keeping the capability reachable.
"""
from __future__ import annotations

import json

import pytest

from app.services.frontend_tools import (
    UI_OPEN_STUDIO_PANEL_TOOL,
    _is_panel_nav_intent,
    _studio_panel_tool,
    frontend_tool_defs,
)
from app.services.skill_registry import (
    LOAD_SKILL_TOOL,
    LOADABLE_SKILL_CODES,
    load_skill_result,
    resolve_skills_to_inject,
    skill_metadata_block,
)


def _est_tokens(s: str) -> int:
    return len(s) // 4  # rough, only used for relative size assertions


# ── load_skill control tool ──────────────────────────────────────────────────
class TestLoadSkill:
    def test_enum_is_the_closed_loadable_set(self):
        # Frontend-Tool-Contract discipline: closed-set arg ⇒ enum. admin +
        # glossary_shaping (internal companion) are excluded, like the L1 index.
        enum = LOAD_SKILL_TOOL["function"]["parameters"]["properties"]["skill"]["enum"]
        assert enum == LOADABLE_SKILL_CODES
        assert "glossary" in enum and "composition" in enum
        assert "admin" not in enum
        assert "glossary_shaping" not in enum

    def test_loads_full_body(self):
        payload = load_skill_result(["glossary"])
        assert payload["skills"][0]["skill"] == "glossary"
        assert len(payload["skills"][0]["body"]) > 200  # the real L2 prose
        assert "not_found" not in payload

    def test_multiple_and_dedup(self):
        payload = load_skill_result(["glossary", "composition", "glossary"])
        got = [s["skill"] for s in payload["skills"]]
        assert got == ["glossary", "composition"]  # deduped, order preserved

    def test_unknown_code_reported_never_silently_dropped(self):
        payload = load_skill_result(["nope"])
        assert payload["skills"] == []
        assert payload["not_found"] == ["nope"]

    def test_empty_request_guided_not_silent(self):
        payload = load_skill_result([])
        assert payload["skills"] == []
        assert "note" in payload


# ── lazy_bodies gating of skill injection ────────────────────────────────────
class TestLazySkillBodies:
    def _resolve(self, *, lazy, **kw):
        base = dict(
            enabled_skills=[],
            stream_format="agui",
            disable_tools=False,
            tool_calling_enabled=True,
            editor=False,
            book_scoped=True,
            admin=False,
            permission_mode="write",
            lazy_bodies=lazy,
        )
        base.update(kw)
        return resolve_skills_to_inject(**base)

    def test_baseline_off_is_unchanged(self):
        # book surface, write mode: the pre-F7c auto-inject (glossary+knowledge+co_write).
        codes = self._resolve(lazy=False)
        assert "glossary" in codes and "knowledge" in codes

    def test_lazy_suppresses_blanket_surface_defaults(self):
        codes = self._resolve(lazy=True)
        assert "glossary" not in codes  # deferred to L1 index + load_skill
        assert "knowledge" not in codes

    def test_lazy_keeps_write_mode_binding(self):
        # co_write is the WRITE-mode binding (propose→compile), not a blanket default.
        codes = self._resolve(lazy=True, permission_mode="write")
        assert "co_write" in codes

    def test_lazy_keeps_plan_mode_binding(self):
        codes = self._resolve(lazy=True, permission_mode="plan", editor=True)
        assert "plan_forge" in codes

    def test_lazy_keeps_explicit_pins(self):
        # An explicit pin is a deliberate selection — never lazy.
        codes = self._resolve(lazy=True, enabled_skills=["glossary"])
        assert "glossary" in codes

    def test_lazy_keeps_admin(self):
        codes = self._resolve(lazy=True, admin=True, book_scoped=False)
        assert codes[:1] == ["admin"]


# ── L1 index gains the load_skill directive when lazy ────────────────────────
class TestSkillMetadataLazyGuidance:
    def test_lazy_names_load_skill(self):
        block = skill_metadata_block(editor=False, book_scoped=True, admin=False, lazy=True)
        assert block is not None
        assert "load_skill(" in block

    def test_non_lazy_does_not(self):
        block = skill_metadata_block(editor=False, book_scoped=True, admin=False, lazy=False)
        assert block is not None
        assert "load_skill(" not in block


# ── compact studio panel description keeps the enum, shrinks the prose ────────
class TestCompactStudioPanel:
    def _enum(self, td):
        return td["function"]["parameters"]["properties"]["panel_id"]["enum"]

    def test_compact_keeps_identical_enum(self):
        full = _studio_panel_tool(compact=False)
        compact = _studio_panel_tool(compact=True)
        assert self._enum(full) == self._enum(compact)  # closed set NEVER trimmed
        assert full is UI_OPEN_STUDIO_PANEL_TOOL  # off ⇒ the exact original object

    def test_compact_is_much_smaller(self):
        full = json.dumps(_studio_panel_tool(compact=False))
        compact = json.dumps(_studio_panel_tool(compact=True))
        assert _est_tokens(compact) < _est_tokens(full) * 0.55  # ~2.4k → <~1.3k

    def test_frontend_tool_defs_threads_flag(self):
        defs = frontend_tool_defs(studio=True, compact_studio_panel=True)
        panel = next(d for d in defs if d["function"]["name"] == "ui_open_studio_panel")
        desc = panel["function"]["parameters"]["properties"]["panel_id"]["description"]
        assert "PLAN/STRUCTURE" in desc  # the compact area-grouped guide
        # default (off) is byte-identical to the original object
        defs_off = frontend_tool_defs(studio=True)
        panel_off = next(d for d in defs_off if d["function"]["name"] == "ui_open_studio_panel")
        assert panel_off is UI_OPEN_STUDIO_PANEL_TOOL


# ── M4: the ui_open_studio_panel navigation-intent gate ──────────────────────
class TestPanelNavIntent:
    # Real navigation requests must fire (recall) — the 6 A/B nav probes.
    @pytest.mark.parametrize("msg", [
        "Open the knowledge-graph timeline of in-story events.",
        "Show me the per-chapter critic quality scores.",
        "Open the motif relationship graph canvas.",
        "I want to manage the what-if versions of this book.",
        "Open the translation coverage matrix.",
        "Let me import chapters from a docx file.",
        "go to the glossary panel",
        "switch to the wiki tab",
    ])
    def test_nav_requests_fire(self, msg):
        assert _is_panel_nav_intent(msg) is True

    # Plain writing / lore-edit turns must NOT fire (precision — the harmful error is
    # opening a panel mid-write). Note "opening" contains "open" but carries no panel noun.
    @pytest.mark.parametrize("msg", [
        "Add a new character to this book: Kael, a fire mage and the protagonist's rival.",
        "Record a new location in the glossary: the Ashen Spire.",  # 'glossary' noun but no nav verb
        "Remember that Kael betrayed the protagonist in chapter 12.",
        "Write chapter 2 with a dramatic opening scene.",  # 'opening'⊃'open' but 'scene' is not a panel noun
        "Draft the next scene where the arc reaches its climax.",
        "Continue the story from where we left off.",
        "",
    ])
    def test_writing_turns_do_not_fire(self, msg):
        assert _is_panel_nav_intent(msg) is False

    def test_gate_omits_navigator_but_keeps_chapter_focus(self):
        # studio_panel_nav=False (a writing turn) drops the ~880-tok navigator but keeps
        # ui_focus_manuscript_unit (part of the writing loop).
        off = [d["function"]["name"] for d in frontend_tool_defs(studio=True, studio_panel_nav=False)]
        assert "ui_open_studio_panel" not in off
        assert "ui_focus_manuscript_unit" in off
        on = [d["function"]["name"] for d in frontend_tool_defs(studio=True, studio_panel_nav=True)]
        assert "ui_open_studio_panel" in on


# ── wiring seam: the advertise chokepoint gates load_skill on the flag ────────
class TestAdvertiseWiring:
    def test_load_skill_advertised_only_when_flag_on(self, monkeypatch):
        from app.services import stream_service as ss

        monkeypatch.setattr(ss.settings, "lazy_skill_bodies", True)
        names_on = [t["function"]["name"] for t in ss._advertise_discovery_tools({}, set(), [])]
        assert "load_skill" in names_on

        monkeypatch.setattr(ss.settings, "lazy_skill_bodies", False)
        names_off = [t["function"]["name"] for t in ss._advertise_discovery_tools({}, set(), [])]
        assert "load_skill" not in names_off  # baseline byte-identical
