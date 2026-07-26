"""Kill-switch coverage — every deploy-time lever must be tested in BOTH states.

WHY THIS FILE EXISTS. `config.py` documents these flags as levers with a revert path:
"Set the env var to 0 to revert a lever to the pre-F7c behavior (the kill-switch, and how
the A/B control run is measured)." A kill-switch whose OFF path is never exercised is not
a kill-switch — it is an untested branch you would first run during an incident.

Audited 2026-07-23: of 15 boolean flags in `config.py`, **8 appeared in no test file at
all**, in either state — `rail_driver_enabled`, `compact_task_elastic_enabled`,
`compact_recovery_hint_enabled`, `compact_persist_enabled`, `compact_breadcrumb_enabled`,
`compact_studio_panel_desc`, `lazy_workflow_directive`, `studio_panel_intent_gated`.

That gap is the same class as the `lazy_skill_bodies` one found while clearing the red
baseline: a "stale test" was really MISSING COVERAGE. Tests that only ever run the
default silently stop testing anything the moment the default flips — exactly how
`test_tasks_gate_disabled_sends_no_meta` turned into a false negative.

Each case asserts the lever's DOCUMENTED effect and, where the flag guards a stated
invariant, that the invariant survives BOTH states.
"""
from __future__ import annotations

import json

from app.services.frontend_tools import (
    UI_OPEN_STUDIO_PANEL_TOOL,
    _studio_panel_tool,
    frontend_tool_defs,
)


def _panel_prop(td: dict) -> dict:
    return td["function"]["parameters"]["properties"]["panel_id"]


class TestCompactStudioPanelDesc:
    """`compact_studio_panel_desc` — compact the PROSE, never the closed set.

    CLAUDE.md states this explicitly: "while KEEPING the full panel_id enum
    (Frontend-Tool Contract: the closed set is correctness, never trimmed — only the
    prose guidance is compacted)". That invariant had no test in either state, on a
    tool whose enum-less predecessor shipped the original silent-no-op bug
    (gemma sent panel:"editor" → nothing happened → hallucinated success).
    """

    def test_enum_is_identical_in_both_states(self):
        full = _panel_prop(_studio_panel_tool(compact=False))
        compact = _panel_prop(_studio_panel_tool(compact=True))
        assert full.get("enum"), "panel_id must declare a closed set at all"
        assert compact["enum"] == full["enum"], (
            "compacting the description must NOT trim the panel_id enum — the closed set "
            "is correctness (Frontend-Tool Contract), only the prose is compacted"
        )

    def test_compact_actually_shortens_the_prose(self):
        full = _panel_prop(_studio_panel_tool(compact=False))["description"]
        compact = _panel_prop(_studio_panel_tool(compact=True))["description"]
        assert compact != full, "the lever must actually change something when ON"
        assert len(compact) < len(full), "compact must be shorter than full"

    def test_off_is_byte_identical_to_the_shared_constant(self):
        # config.py promises "Off ⇒ byte-identical to pre-F7c." Prove it, and prove the
        # compact path does not MUTATE the shared constant (it deepcopies).
        before = json.dumps(UI_OPEN_STUDIO_PANEL_TOOL, sort_keys=True)
        assert _studio_panel_tool(compact=False) is UI_OPEN_STUDIO_PANEL_TOOL
        _studio_panel_tool(compact=True)
        assert json.dumps(UI_OPEN_STUDIO_PANEL_TOOL, sort_keys=True) == before, (
            "the compact variant must deepcopy — mutating the module-level constant would "
            "leak the compact description into every later turn, including OFF ones"
        )

    # DEPRECATED 2026-07-25 — the `compact_studio_panel_desc` + `studio_panel_intent_gated`
    # config flags and the F7c nav-intent gate were REMOVED with the ui_open_studio_panel
    # advertisement they gated (GUI control is user/logic-driven; nothing advertises the studio
    # nav tools now). The _studio_panel_tool schema tests above stay as the compact-variant
    # contract guard (the wire schema is ai-gateway-owned). No config flag lives here anymore.


# ── The gate: a NEW lever may not ship untested ──────────────────────────────
#
# The audit above found 8 flags with zero test coverage in either state. Writing
# eight one-off tests fixes today; it does not stop the ninth. So enforce the rule
# mechanically, with an explicit debt allowlist that must SHRINK.
#
# Adding a boolean flag to config.py now forces a choice: cover both of its states,
# or add it here with a reason. Both are visible in review; silently shipping an
# untested kill-switch is not an option. Same shape as the repo's other
# rule + SoT + gate + allowlist mechanisms (scripts/ai-provider-gate.py).

# Flags that are STILL uncovered — tracked debt, not permission. Delete a row when you
# cover it; never add one without a reason.
# PAID 2026-07-23: the four compact_* levers now have both-state coverage in
# test_compact_flag_kill_switches.py ("needs a heavier fixture" was unbuilt work, not a
# blocker — the fixtures were built). The breadcrumb case is mutation-proven.
# PAID 2026-07-23: `rail_driver_enabled` — the row that was sharpened rather than paid on
# the first attempt ("needs the rail's own fixture, not a general stream one") now HAS that
# fixture, in test_rail_flag_kill_switch.py: all five preconditions are supplied, the ON case
# is asserted FIRST so the OFF assertions cannot be vacuous, and deleting the flag check from
# stream_service.py reds two of them (mutation-verified).
_UNCOVERED_DEBT: dict[str, str] = {
    "minio_use_ssl": "infra transport toggle, not an agent-behaviour lever — no chat-service path to assert",
}


def _boolean_flags() -> list[str]:
    import re
    from pathlib import Path

    cfg = Path(__file__).resolve().parents[1] / "app" / "config.py"
    return [m.group(1) for m in
            re.finditer(r"^\s{4}(\w+):\s*bool\s*=\s*(?:True|False)", cfg.read_text(encoding="utf-8"), re.M)]


def _flag_is_mentioned_in_tests(flag: str) -> bool:
    from pathlib import Path

    tests_dir = Path(__file__).resolve().parent
    # Deliberately EXCLUDES this file: its own docstring and debt table name every flag,
    # so counting them here would make the gate report its own debt as covered — a
    # self-referential false negative (the first draft did exactly that).
    return any(
        flag in p.read_text(encoding="utf-8", errors="ignore")
        for p in tests_dir.rglob("test_*.py")
        if p.name != Path(__file__).name
    )


def test_every_boolean_flag_is_covered_or_explicitly_tracked():
    """A new lever must be tested in both states, or listed as debt with a reason."""
    covered_here: set[str] = set()  # the 2 studio-panel flags were removed 2026-07-25
    missing = [
        f for f in _boolean_flags()
        if f not in covered_here
        and f not in _UNCOVERED_DEBT
        and not _flag_is_mentioned_in_tests(f)
    ]
    assert not missing, (
        "these config flags have NO test in either state and are not tracked as debt: "
        f"{missing}. A kill-switch whose OFF path is never exercised is an untested "
        "branch you would first run during an incident. Cover both states, or add a row "
        "to _UNCOVERED_DEBT with the reason."
    )


def test_the_debt_allowlist_does_not_rot():
    """Every debt row must name a flag that still exists — a stale row hides a real gap."""
    flags = set(_boolean_flags())
    stale = [f for f in _UNCOVERED_DEBT if f not in flags]
    assert not stale, f"_UNCOVERED_DEBT names flags that no longer exist: {stale}"
    # And a row must not linger once the flag IS covered elsewhere.
    now_covered = [f for f in _UNCOVERED_DEBT
                   if f != "minio_use_ssl" and _flag_is_mentioned_in_tests(f)]
    assert not now_covered, (
        f"these are tracked as debt but now have tests: {now_covered} — delete their rows"
    )
