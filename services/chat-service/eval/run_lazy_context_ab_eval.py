"""F7c (2026-07-19) — capability-first A/B eval for the lazy-context enforcement levers.
docs/plans/2026-07-19-lazy-context-enforcement.md · methodology: docs/eval/context-budget/
OPTIMIZATION-EVAL-METHODOLOGY.md ("cutting context to save tokens can make the agent DUMBER").

Two halves:
  1. TOKEN SAVINGS (deterministic, no model) — measures the three levers' real production
     blocks baseline (flags off) vs optimized (flags on) with the REAL block builders.
  2. CAPABILITY PARITY (live gemma-4-26b) — the ship gate. For the two levers where lazy
     loading could degrade comprehension on a MEDIUM model:
       · panel selection (M2): does the COMPACT ui_open_studio_panel description still let
         the model pick the right panel_id?  (full vs compact, same prompts)
       · skill usage (M1): with the OPTIMIZED surface (L1 index + load_skill + hot tools,
         NO L2 body), does the model still accomplish a glossary/KG task — either by calling
         the hot tool directly, or by load_skill'ing the guidance first?  (baseline L2 vs optimized)

Run inside the chat-service container (has loreweave_llm + app.* + a real gemma-4-26b via
provider-registry):
    docker cp services/chat-service/eval/run_lazy_context_ab_eval.py infra-chat-service-1:/tmp/f7c_ab.py
    docker exec infra-chat-service-1 python /tmp/f7c_ab.py
"""
from __future__ import annotations

import asyncio
import json
import sys
from dataclasses import dataclass

from app.services.frontend_tools import _studio_panel_tool
from app.services.skill_registry import (
    LOAD_SKILL_TOOL,
    load_skill_result,
    skill_metadata_block,
    skill_prompts,
)
from app.services.token_budget import estimate_tokens
from app.services.tool_discovery import TOOL_LIST_TOOL, TOOL_LOAD_TOOL, FIND_TOOLS_TOOL

from loreweave_llm.client import Client
from loreweave_llm.models import DoneEvent, ErrorEvent, StreamRequest, ToolCallEvent, TokenEvent

PROVIDER_REGISTRY_URL = "http://provider-registry-service:8085"
INTERNAL_TOKEN = "dev_internal_token"
TEST_USER_ID = "019d5e3c-7cc5-7e6a-8b27-1344e148bf7c"
MODEL_REF = "019ebb72-27a2-72f3-a42d-d2d0e0ded179"  # Gemma-4 26B-A4B QAT (200K), tool_calling:true
BOOK_ID = "b_demo_0001"


def _toks(obj) -> int:
    return estimate_tokens(obj if isinstance(obj, str) else json.dumps(obj, ensure_ascii=False))


# ── Half 1: deterministic token savings ──────────────────────────────────────

def measure_tokens() -> None:
    print("\n=== HALF 1 · TOKEN SAVINGS (deterministic, real production blocks) ===\n")

    # M1 — skills on a STUDIO book WRITE turn (the co-writer surface F7c measured).
    # Baseline auto-inject: glossary+composition+knowledge (surface defaults) + co_write
    # (write binding) as full L2 bodies, PLUS the always-on L1 index.
    baseline_codes = ["glossary", "composition", "knowledge", "co_write"]
    baseline_bodies = sum(_toks(b) for b in skill_prompts(baseline_codes).values())
    l1_baseline = _toks(skill_metadata_block(editor=False, book_scoped=True, admin=False, studio=True, lazy=False) or "")
    baseline_skilltotal = baseline_bodies + l1_baseline

    # Optimized (lazy): only co_write (write binding) keeps its body; the surface defaults
    # go lazy → L1 index (lazy variant) + the load_skill control tool.
    opt_bodies = sum(_toks(b) for b in skill_prompts(["co_write"]).values())
    l1_lazy = _toks(skill_metadata_block(editor=False, book_scoped=True, admin=False, studio=True, lazy=True) or "")
    load_skill_tool = _toks(LOAD_SKILL_TOOL)
    opt_skilltotal = opt_bodies + l1_lazy + load_skill_tool

    print("M1 skills (studio book write turn):")
    print(f"  baseline: bodies {baseline_bodies} + L1 {l1_baseline} = {baseline_skilltotal}")
    print(f"  optimized: co_write {opt_bodies} + L1-lazy {l1_lazy} + load_skill {load_skill_tool} = {opt_skilltotal}")
    print(f"  >>> saved {baseline_skilltotal - opt_skilltotal} tokens/turn\n")

    # M2 — ui_open_studio_panel description.
    full_panel = _toks(_studio_panel_tool(compact=False))
    compact_panel = _toks(_studio_panel_tool(compact=True))
    print("M2 ui_open_studio_panel:")
    print(f"  baseline {full_panel} → compact {compact_panel}  >>> saved {full_panel - compact_panel} tokens/turn\n")

    # M3 — workflow directive (representative book workflows).
    sample_wfs = [
        {"slug": "world-setup", "title": "Set up your world",
         "description": "Create the book's glossary kinds and seed its first characters, places, and items from a source doc, then adopt naming standards — the full first-run world-building recipe."},
        {"slug": "plan-novel", "title": "Plan the novel",
         "description": "Draft a PlanForge spec from a premise, refine it with the user, then compile it into the linked arc/chapter/scene structure the drafts hang on."},
        {"slug": "translate-book", "title": "Translate the book",
         "description": "Run the chapter translation pipeline for a target language, review coverage, and publish a version."},
    ]
    full_dir = "\n".join(f"- {w['slug']}: {w['description']}" for w in sample_wfs)
    lazy_dir = "\n".join(f"- {w['slug']}: {w['title']}" for w in sample_wfs)
    print("M3 workflow directive (3 sample workflows):")
    print(f"  baseline {_toks(full_dir)} → lazy {_toks(lazy_dir)}  >>> saved {_toks(full_dir) - _toks(lazy_dir)} tokens/turn\n")


# ── Half 2: live capability probes ────────────────────────────────────────────

# Faithful hand-defined hot tools (mirror the ALWAYS_HOT_WRITES the lazy surface keeps hot).
GLOSSARY_PROPOSE = {
    "type": "function",
    "function": {
        "name": "glossary_propose_entities",
        "description": "Propose one or more new glossary entities (characters, places, items) for the book — surfaces a confirm card the user approves.",
        "parameters": {
            "type": "object",
            "properties": {
                "book_id": {"type": "string"},
                "entities": {"type": "array", "items": {"type": "object", "properties": {
                    "name": {"type": "string"}, "kind": {"type": "string"}, "description": {"type": "string"},
                }, "required": ["name", "kind"]}},
            },
            "required": ["book_id", "entities"],
        },
    },
}
MEMORY_REMEMBER = {
    "type": "function",
    "function": {
        "name": "memory_remember",
        "description": "Record a durable fact about an entity in the book's knowledge graph/memory.",
        "parameters": {"type": "object", "properties": {
            "book_id": {"type": "string"}, "text": {"type": "string"},
        }, "required": ["book_id", "text"]},
    },
}
DISCOVERY_META = [TOOL_LIST_TOOL, TOOL_LOAD_TOOL, FIND_TOOLS_TOOL]


@dataclass
class Probe:
    key: str
    prompt: str
    accept: tuple[str, ...]  # tool names that count as capability preserved


PANEL_PROBES = [
    Probe("panel_timeline", "Open the knowledge-graph timeline of in-story events.", ("ui_open_studio_panel",)),
    Probe("panel_critic", "Show me the per-chapter critic quality scores.", ("ui_open_studio_panel",)),
    Probe("panel_motif_graph", "Open the motif relationship graph canvas.", ("ui_open_studio_panel",)),
    Probe("panel_divergence", "I want to manage the what-if versions of this book.", ("ui_open_studio_panel",)),
    Probe("panel_translation", "Open the translation coverage matrix.", ("ui_open_studio_panel",)),
    Probe("panel_import", "Let me import chapters from a docx file.", ("ui_open_studio_panel",)),
]
PANEL_EXPECT = {
    "panel_timeline": "kg-timeline", "panel_critic": "quality-critic",
    "panel_motif_graph": "motif-graph", "panel_divergence": "divergence",
    "panel_translation": "translation", "panel_import": "book-import",
}

SKILL_PROBES = [
    Probe("skill_add_char", "Add a new character to this book: Kael, a fire mage and the protagonist's rival.",
          ("glossary_propose_entities", "load_skill")),
    Probe("skill_add_place", "Record a new location in the glossary: the Ashen Spire, a volcanic tower.",
          ("glossary_propose_entities", "load_skill")),
    Probe("skill_remember_fact", "Remember that Kael betrayed the protagonist in chapter 12.",
          ("memory_remember", "load_skill", "glossary_propose_entities")),
]

PANEL_SYS = (
    "You are the LoreWeave Writing Studio assistant. The user is in the studio for "
    f"book_id='{BOOK_ID}'. When the user asks to open/show/view a studio panel, call "
    "ui_open_studio_panel with the right panel_id. Otherwise answer in text."
)
SKILL_SYS_TMPL = (
    "You are the LoreWeave writing assistant for book_id='{book}'. Use the tools available "
    "to fulfil the user's request. {index}"
)


async def call_model(client: Client, system: str, prompt: str, tools: list[dict]) -> dict:
    request = StreamRequest(
        model_source="user_model", model_ref=MODEL_REF,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": prompt}],
        tools=tools, tool_choice="auto", temperature=0.0, reasoning_effort="none",
    )
    frags: dict[int, dict[str, str]] = {}
    text: list[str] = []
    error = None
    try:
        async for ev in client.stream(request, user_id=TEST_USER_ID):
            if isinstance(ev, ToolCallEvent):
                slot = frags.setdefault(ev.index, {"name": "", "arguments": ""})
                if ev.name:
                    slot["name"] = ev.name
                slot["arguments"] += ev.arguments_delta
            elif isinstance(ev, TokenEvent):
                text.append(ev.delta)
            elif isinstance(ev, ErrorEvent):
                error = f"{ev.code}: {ev.message}"
            elif isinstance(ev, DoneEvent):
                break
    except Exception as exc:  # noqa: BLE001
        error = f"exception: {exc!r}"
    calls = []
    for i in sorted(frags):
        f = frags[i]
        try:
            args = json.loads(f["arguments"]) if f["arguments"] else {}
        except json.JSONDecodeError:
            args = None
        calls.append({"name": f["name"], "arguments": args})
    return {"calls": calls, "text": "".join(text), "error": error}


async def run_panel_ab(client: Client) -> None:
    print("\n=== HALF 2A · PANEL SELECTION (live gemma) — full vs COMPACT description ===\n")
    for label, compact in (("FULL   ", False), ("COMPACT", True)):
        tool = _studio_panel_tool(compact=compact)
        ok = 0
        for p in PANEL_PROBES:
            out = await call_model(client, PANEL_SYS, p.prompt, [tool])
            call = out["calls"][0] if out["calls"] else None
            picked = (call or {}).get("arguments", {}).get("panel_id") if call else None
            want = PANEL_EXPECT[p.key]
            good = call and call["name"] == "ui_open_studio_panel" and picked == want
            ok += 1 if good else 0
            flag = "OK " if good else "XX "
            print(f"  [{label}] {flag}{p.key}: picked={picked!r} want={want!r}" + (f"  err={out['error']}" if out["error"] else ""))
        print(f"  >>> {label}: {ok}/{len(PANEL_PROBES)} correct\n")


async def run_skill_ab(client: Client) -> None:
    print("\n=== HALF 2B · SKILL USAGE (live gemma) — baseline L2 body vs OPTIMIZED L1+load_skill ===\n")

    # Baseline: full glossary + knowledge L2 bodies injected into the system prompt (no load_skill,
    # no L1 directive) — the pre-F7c surface.
    baseline_bodies = "\n\n".join(skill_prompts(["glossary", "knowledge"]).values())
    baseline_sys = SKILL_SYS_TMPL.format(book=BOOK_ID, index=baseline_bodies)
    baseline_tools = [GLOSSARY_PROPOSE, MEMORY_REMEMBER, *DISCOVERY_META]

    # Optimized: L1 index (lazy variant, names load_skill) — NO L2 body — + the load_skill control,
    # + the same hot tools (lazy mode keeps them hot).
    l1 = skill_metadata_block(editor=False, book_scoped=True, admin=False, studio=True, lazy=True)
    opt_sys = SKILL_SYS_TMPL.format(book=BOOK_ID, index=l1)
    opt_tools = [GLOSSARY_PROPOSE, MEMORY_REMEMBER, LOAD_SKILL_TOOL, *DISCOVERY_META]

    for label, sys_p, tools in (("BASELINE ", baseline_sys, baseline_tools), ("OPTIMIZED", opt_sys, opt_tools)):
        ok = 0
        for p in SKILL_PROBES:
            out = await call_model(client, sys_p, p.prompt, tools)
            names = [c["name"] for c in out["calls"]]
            good = any(n in p.accept for n in names)
            ok += 1 if good else 0
            flag = "OK " if good else "XX "
            print(f"  [{label}] {flag}{p.key}: called={names} accept={list(p.accept)}" + (f"  err={out['error']}" if out["error"] else ""))
        print(f"  >>> {label}: {ok}/{len(SKILL_PROBES)} task-capable\n")


async def main() -> int:
    measure_tokens()
    client = Client(
        base_url=PROVIDER_REGISTRY_URL, auth_mode="internal",
        internal_token=INTERNAL_TOKEN, user_id=TEST_USER_ID,
    )
    try:
        await run_panel_ab(client)
        await run_skill_ab(client)
    finally:
        close = getattr(client, "aclose", None) or getattr(client, "close", None)
        if close:
            res = close()
            if asyncio.iscoroutine(res):
                await res
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
