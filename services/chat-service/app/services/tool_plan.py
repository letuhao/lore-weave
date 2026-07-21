"""Dynamic planner-executor POC (D-WEAK-MODEL-PLANNER).

The problem (dogfood 2026-07-21): weak local models can't drive an open-ended
ReAct tool loop — they lack an ANCHOR for "what next / when to stop", so they loop
or mis-route (e.g. pick book_chapter_create for "update the description"). But the
SAME models route correctly in a ONE-SHOT call with the catalog present
(benchmark: Qwen3.6 6/6, Gemma 5/6). This module exploits that asymmetry.

Approach (Planner-Executor, the dynamic form of a state-machine — the plan is a
throwaway state-machine generated PER TURN, so it fits open-ended chat where a
fixed pipeline can't):
  1. PLAN — one clean structured call: given the request + the tool catalog,
     emit an ORDERED list of tool names. This is the anchor. It is a one-shot
     classification (the shape weak models handle), NOT an agentic loop.
  2. EXECUTE — the orchestrator drives the model through the plan: each step it
     offers ONLY the planned tool(s) (+ the always-on core), so the weak model
     CANNOT pick a wrong sibling or wander. Hard controls (step budget /
     loop-break) still backstop it.

This module holds the PURE, testable pieces (prompt, parse, tool-restriction);
the async plan call + the stream wiring live in stream_service.
"""
from __future__ import annotations

import json
import re

# Tools the executor ALWAYS keeps available regardless of the plan — the gate/UI
# primitives a step legitimately needs (confirm a Tier-W card, apply a proposed
# edit, load a tool's exact schema). Without these a planned write can't complete.
_EXECUTOR_KEEP_CORE: frozenset[str] = frozenset(
    # propose_record_edit removed (auto-gate M5) — the generic record diff card is retired.
    {"confirm_action", "propose_edit", "tool_load"}
)


def build_plan_prompt(catalog_text: str, user_message: str) -> str:
    """The planner prompt — a ONE-SHOT tool-sequence classification (the reliable
    shape), catalog present as distractors. Returns names only, ordered."""
    return (
        "You are a tool-use PLANNER. Below is the catalog of available tools, one "
        "per line as `name: description`.\n\n"
        f"{catalog_text}\n\n"
        f'The user says: "{user_message}"\n\n'
        "Output ONLY a JSON array of the exact tool NAMES to call, in the order "
        "they should run, to fulfil the request — e.g. "
        '["book_list", "book_update_details"]. Include a read tool first only if '
        "you need an id you don't have. No prose, no explanation, JSON array only. "
        "If NO tool is needed (a plain conversational reply), output []."
    )


def parse_plan(raw: str, known_names: set[str]) -> list[str]:
    """Extract the ordered tool-name list from the planner output, tolerating a
    ```json fence / trailing prose, and KEEP ONLY real tool names (a hallucinated
    name is dropped, never executed). De-duplicates preserving order."""
    if not raw:
        return []
    s = raw.strip()
    fence = re.search(r"```(?:json)?\s*(.+?)```", s, re.DOTALL)
    if fence:
        s = fence.group(1).strip()
    m = re.search(r"\[.*?\]", s, re.DOTALL)
    if not m:
        return []
    try:
        arr = json.loads(m.group(0))
    except (json.JSONDecodeError, TypeError):
        return []
    if not isinstance(arr, list):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for item in arr:
        name = item.strip() if isinstance(item, str) else ""
        if name in known_names and name not in seen:
            out.append(name)
            seen.add(name)
    return out


def restrict_tools_to_plan(
    advertised: list[dict], plan: list[str], core_names: set[str] | None = None
) -> list[dict]:
    """The EXECUTOR's tool-availability constraint: keep only tools whose name is
    in the plan OR in the always-keep core. This is what stops a weak model from
    picking a wrong sibling — the wrong tool is simply not offered. Order follows
    the plan (planned tools first, in plan order), then any kept core.

    `advertised` is the list of tool defs (OpenAI function shape:
    {"type":"function","function":{"name":...}}). A plan tool absent from the
    advertised set is skipped here (the caller is responsible for having loaded
    the planned tools' schemas — see stream_service wiring)."""
    keep = _EXECUTOR_KEEP_CORE | (core_names or set())
    plan_set = set(plan)

    def _name(td: dict) -> str:
        fn = td.get("function") if isinstance(td, dict) else None
        return fn.get("name", "") if isinstance(fn, dict) else ""

    by_name = {_name(td): td for td in advertised if _name(td)}
    ordered: list[dict] = []
    used: set[str] = set()
    for pname in plan:  # planned tools first, in plan order
        td = by_name.get(pname)
        if td is not None and pname not in used:
            ordered.append(td)
            used.add(pname)
    for td in advertised:  # then the kept core (stable order)
        n = _name(td)
        if n and n not in used and n in keep and n not in plan_set:
            ordered.append(td)
            used.add(n)
    return ordered


def plan_directive(plan: list[str], user_message: str) -> str:
    """The system directive injected for the executor so the model knows its plan
    and executes ONE step at a time (belt-and-suspenders with the tool-restriction)."""
    steps = "\n".join(f"  {i+1}. {t}" for i, t in enumerate(plan))
    return (
        "[PLAN] For this request you will execute this exact tool sequence, one "
        "step at a time, in order — do NOT deliberate about which tool to use, the "
        "plan is fixed:\n"
        f"{steps}\n"
        "Call the next un-done step now with the arguments it needs. When the last "
        "step's result is in, briefly tell the user it's done. Only the planned "
        "tools (plus confirm/apply) are available."
    )
