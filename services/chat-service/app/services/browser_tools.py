"""Which tools the BROWSER executes — the one question that outlived architecture v1.

🔴 THIS IS NOT "WHICH TOOLS DOES CHAT-SERVICE INTERCEPT". The old `frontend_tools.py` answered
both questions and its own docstring recorded a bug from conflating them. V7 (2026-09-03) settled
it by deleting the interception question entirely: the three KIND-C tools moved to ai-gateway as
directive tools, `FRONTEND_TOOL_NAMES` emptied, and `is_frontend_tool` went with the module.

The execution question did NOT go away, and forgetting that cost a real defect. `is_browser_executed`
had answered True for those three only VIA `FRONTEND_TOOL_NAMES`; emptying that set flipped them to
False and two consumers changed behaviour with nothing failing loudly:

  * `subagent_runtime.resolve_scoped_tools` stopped excluding them — a HEADLESS sub-run was being
    offered a human-gate tool with no human to gate on. It can only hang or be answered dishonestly.
  * `agent_surface` stopped routing them to the "ui" server bucket.

**Moving a tool's HOME must not change WHO EXECUTES it.** Caught by a NEGATIVE assertion
(`test_subagent_runtime.py:69`, `not in`) — the shape that usually goes vacuous rather than red;
here it reddened because the tools appeared somewhere they must never appear.

Membership is EXPLICIT, not a prefix rule. `ui_` is the one pattern, because that family is closed
and its members are generated; everything else is named. A prefix over `glossary_` would have swept
the real glossary-service tools, and this repo has paid repeatedly for a name used as an identity.
"""
from __future__ import annotations

#: Browser-executed tools named one by one.
#:
#: `propose_edit` and the three KIND-C tools are all ai-gateway consumer-local DIRECTIVE tools:
#: the gateway validates and returns a directive, chat-service suspends on it, and the BROWSER
#: performs the effect (apply the edit / POST the confirm / PATCH the record). None of them has a
#: server executor, which is exactly why they could not become domain MCP tools — see
#: docs/plans/2026-09-03-retire-v1-BUILD.md DQ-V9.
BROWSER_EXECUTED_NAMES: frozenset[str] = frozenset({
    "propose_edit",
    "confirm_action",
    "glossary_confirm_action",
    "glossary_propose_entity_edit",
})

#: The studio/nav family. De-advertised since 2026-07-25 (GUI control is user- and logic-driven),
#: but still DISPATCHABLE if a cached directive arrives — so it is still browser-executed, and a
#: headless sub-run must still never be offered one.
_UI_PREFIX = "ui_"


def is_browser_executed(name: str) -> bool:
    """True when the BROWSER performs this tool's effect, not a server.

    Two consumers depend on it and both are safety-relevant:
      * `subagent_runtime` — a headless run must never be offered one of these.
      * `agent_surface` — they route to the `ui` server bucket, not a domain's.
    """
    return bool(name) and (name in BROWSER_EXECUTED_NAMES or name.startswith(_UI_PREFIX))
