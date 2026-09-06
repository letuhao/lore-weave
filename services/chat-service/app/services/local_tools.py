"""The tools **chat-service serves itself** — one enumeration, for everything that needs the set.

🔴 **CP-5 · THIS MODULE EXISTS BECAUSE THE ANSWER TO *"WHICH TOOLS ARE THERE"* DEPENDED ON WHO WAS
ASKING, AND THE CHEAPEST ANSWER WAS ALWAYS WRONG IN THE SAME DIRECTION.**

The federated snapshot (`contracts/agent-runtime-baseline/tools-list.snapshot.json`) holds 315
tools. It is the frozen control group and must not change. But chat-service puts four more on the
wire itself, and every measurement that reached for the snapshot alone silently excluded them:

* the essential-set derivation reported the co-writer's `compose_prose` role as **never used** —
  it had 2 sessions and 100% success, and was simply not in the file;
* the 5.10 phantom-name measurement reported **17 invented tools**, of which `workflow_load`
  (100% ok), `chat_search_sessions` and `run_subagent` are real;
* `declared_lane`'s docstring says *"measured on the live catalogue: 315/315 tools declare a
  tier"* — measured on the population that excludes the only four that did not.

Three separate false findings from one missing union, so the union gets a name and a single home.

**Why a module and not a second frozen file.** A frozen copy of these definitions would need a
freeze step, a drift check and a reason to trust it; these tools are defined in this repository, in
Python, and are not going to disagree with themselves. The snapshot exists because the federated
catalogue lives in *other* services and changes without us.
"""
from __future__ import annotations

from app.services.composer import COMPOSE_PROSE_TOOL


def local_tool_defs() -> list[dict]:
    """Every tool definition chat-service serves without federating it.

    Returned in the WRAPPED (`{"type": "function", "function": {...}}`) shape they are authored in,
    which is what the wire uses; `derive._fn` accepts both that and the snapshot's flat shape.
    """
    # V7 (2026-09-03) — the frontend-tool dicts are GONE. They were unioned in here so the
    # agent-runtime admission could see the tools chat-service served itself; all three moved
    # to ai-gateway and now reach the admission through the federated baseline instead.
    # `compose_prose` is the only tool chat-service still serves on its own.
    return [COMPOSE_PROSE_TOOL]


def local_tool_names() -> frozenset[str]:
    return frozenset(
        d.get("function", d).get("name")
        for d in local_tool_defs()
        if (d.get("function", d) or {}).get("name")
    )
