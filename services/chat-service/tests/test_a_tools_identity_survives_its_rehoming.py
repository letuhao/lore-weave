"""Moving a tool's HOME must not change the NAME it suspends under.

🔴 THE REGRESSION THIS PINS. When the three KIND-C tools moved to ai-gateway (v1 retirement,
2026-09-03), `glossary_confirm_action` was given the SAME directive marker as `confirm_action`.
chat-service maps marker -> suspend name, so every glossary confirm began suspending as
`confirm_action`. Nothing failed:

  * the main chat UI accepts either name (`FRONTEND_TOOLS` lists both), so it kept working;
  * `cms-frontend/src/features/admin-chat/components/MessageList.tsx` gates on exactly
    `tc.tool === 'glossary_confirm_action'` and has NO auto-confirm fallback, so its
    AdminConfirmCard stopped rendering and the confirm degraded to a 10px grey text line;
  * TypeScript cannot see it — the name crosses the wire as a string;
  * every unit test on both sides stayed green, because each asserted its own half.

The plan predicted this exact line as "highest risk in the whole plan" and it shipped anyway,
because the risk was recorded in prose and not in an assertion. This is the assertion.
"""
from __future__ import annotations

from app.services import task_detect as td


def test_each_gated_marker_maps_to_its_own_distinct_tool_name():
    names = list(td._GATED_DIRECTIVES.values())
    assert len(names) == len(set(names)), (
        f"two markers share one suspend name {names} — the tool that loses its name loses "
        "every consumer that gates on it by string"
    )


def test_the_glossary_confirm_suspends_under_its_own_name():
    got = td.gated_directive_suspend_args({
        "type": td.GLOSSARY_CONFIRM_DIRECTIVE_TYPE,
        "confirm_token": "t", "descriptor": "d", "title": "x", "domain": "glossary",
    })
    assert got is not None, "the glossary confirm marker is not recognised at all"
    name, args = got
    assert name == "glossary_confirm_action", (
        f"suspended as {name!r}; cms-frontend MessageList.tsx renders AdminConfirmCard only for "
        "'glossary_confirm_action' and has no fallback"
    )
    assert "type" not in args


def test_the_plain_confirm_still_suspends_as_confirm_action():
    got = td.gated_directive_suspend_args({
        "type": td.CONFIRM_DIRECTIVE_TYPE,
        "confirm_token": "t", "descriptor": "d", "title": "x", "domain": "book",
    })
    assert got is not None and got[0] == "confirm_action"
