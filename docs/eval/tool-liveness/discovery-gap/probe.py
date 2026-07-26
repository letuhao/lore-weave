#!/usr/bin/env python
"""FOUNDATIONAL: does a weak model reach a LAZY tool via tool_list -> tool_load?
Faithfully replicates the chat-service discovery advertisement (tool_list/tool_load core +
the group directory) on a 'universal' surface (NO domain tools hot). A request needs a lazy
glossary tool; we drive the multi-turn loop and see whether gemma discovers + loads + calls it.
Responses to tool_list/tool_load come from the LIVE glossary catalog (:8211)."""
import json, os, urllib.request

EXPLICIT = os.environ.get("EXPLICIT", "0") == "1"  # tool_load returns an explicit "now call it" directive
LOOPBREAK = os.environ.get("LOOPBREAK", "0") == "1"  # inject an explicit steer on a repeated no-progress call
LM    = "http://localhost:1234/v1/chat/completions"
MODEL = "google/gemma-4-12b-qat"
GLOSS = "http://localhost:8211/mcp"
USER  = "019d5e3c-7cc5-7e6a-8b27-1344e148bf7c"
TOKEN = "dev_internal_token"


def sse(raw):
    raw = raw.decode() if isinstance(raw, bytes) else raw
    for ln in raw.splitlines():
        ln = ln.strip()
        if ln.startswith("data:"):
            ln = ln[5:].strip()
        if ln.startswith("{"):
            try:
                return json.loads(ln)
            except Exception:
                pass
    return json.loads(raw)


# live glossary catalog (name -> {desc, schema, legacy})
req = urllib.request.Request(
    GLOSS, data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}).encode(),
    headers={"Content-Type": "application/json", "Accept": "application/json, text/event-stream",
             "X-Internal-Token": TOKEN, "X-User-Id": USER})
CAT = {}
for t in sse(urllib.request.urlopen(req, timeout=30).read())["result"]["tools"]:
    CAT[t["name"]] = {"desc": t.get("description", "")[:160],
                      "legacy": (t.get("_meta") or {}).get("visibility") == "legacy",
                      "schema": t.get("inputSchema") or {"type": "object", "properties": {}}}

GROUP_DIR = ("Tool domains (call tool_list with category=<name> to see every tool in one):\n"
             "- glossary: Lore entities (characters/locations/items/kinds) — CRUD + wiki + standards ontology.\n"
             "- story: Manuscript search (story_search).\n"
             "- knowledge: Derived KG facts, passage retrieval, memory_search.\n"
             "- composition: Outline/scene/canon planning.\n"
             "- book: Book/chapter CRUD, publishing, chapter body reads.")

TOOL_LIST = {"type": "function", "function": {"name": "tool_list", "description":
    "List EVERY tool in a category (or \"all\"), complete and deterministic — the reliable way to see "
    "what you can do here. This is how you discover a tool that isn't already advertised: list the "
    "category, then call tool_load(name) to get a tool's exact arguments before using it.",
    "parameters": {"type": "object", "properties": {"category": {"type": "string",
    "enum": ["glossary", "story", "knowledge", "composition", "book", "all"], "description": "A tool domain, or all."}},
    "additionalProperties": False}}}
TOOL_LOAD = {"type": "function", "function": {"name": "tool_load", "description":
    "Load the exact input schema for one or more tools by `name` so you can call them correctly. "
    "Loading makes them callable; it does NOT run anything. Use it after tool_list to pick tools by name.",
    "parameters": {"type": "object", "properties": {"name": {"type": "string", "description": "A single tool name."}},
    "additionalProperties": False}}}

SYS = ("You are a co-writing assistant. Only tool_list and tool_load are advertised right now; every "
       "domain tool is LAZY. To do anything domain-specific you MUST discover it: call tool_list with "
       "the right category to see the tools, then tool_load(name) to make it callable, then call it. "
       "Never invent a tool name.\n\n" + GROUP_DIR)


def chat(messages, tools):
    body = json.dumps({"model": MODEL, "temperature": 0, "tools": tools, "tool_choice": "auto",
                       "messages": messages}).encode()
    d = json.loads(urllib.request.urlopen(
        urllib.request.Request(LM, data=body, headers={"Content-Type": "application/json"}), timeout=120).read())
    return d["choices"][0]["message"]


def run(goal, want_tool, max_turns=6):
    loaded = set()
    msgs = [{"role": "system", "content": SYS}, {"role": "user", "content": goal}]
    tools = [TOOL_LIST, TOOL_LOAD]
    trace = []
    last_discovery = None  # (name, key) of the previous discovery call, for loop detection
    for _ in range(max_turns):
        m = chat(msgs, tools)
        tcs = m.get("tool_calls") or []
        if not tcs:
            trace.append(f"text:{(m.get('content') or '')[:40]!r}")
            return False, trace, "gave up (text, no tool call)"
        tc = tcs[0]; fn = tc["function"]; nm = fn["name"]
        try:
            args = json.loads(fn.get("arguments") or "{}")
        except Exception:
            args = {}
        msgs.append({"role": "assistant", "content": m.get("content") or "", "tool_calls": [tc]})
        # LOOP-BREAK (user hypothesis 2026-07-22): a repeated no-progress discovery call gets an
        # EXPLICIT steer naming the already-loaded tool, instead of servicing the redundant call.
        cur_key = (nm, json.dumps(args, sort_keys=True))
        if LOOPBREAK and nm in ("tool_list", "tool_load") and cur_key == last_discovery and loaded:
            already = sorted(loaded)[0]
            trace.append(f"LOOP-BREAK@{nm}")
            msgs.append({"role": "tool", "tool_call_id": tc["id"], "content": json.dumps({
                "stop": True,
                "message": f"You are repeating {nm} with no progress. The tool for this task, "
                           f"{already}, is ALREADY loaded and callable. Call {already} NOW with its "
                           f"arguments — do not list or load any more tools."})})
            last_discovery = cur_key
            continue
        if nm in ("tool_list", "tool_load"):
            last_discovery = cur_key
        if nm == want_tool:
            trace.append(f"CALLED {nm}")
            return True, trace, "reached the lazy tool"
        elif nm == "tool_list":
            cat = args.get("category", "all")
            items = [{"name": n, "description": v["desc"]}
                     for n, v in CAT.items()
                     if (cat == "all" or n.startswith(cat + "_") or n.startswith("glossary")) and not v["legacy"]][:25]
            trace.append(f"tool_list({cat})->{len(items)}")
            msgs.append({"role": "tool", "tool_call_id": tc["id"], "content": json.dumps({"tools": items})})
        elif nm == "tool_load":
            n = args.get("name", "")
            if n in CAT:
                loaded.add(n)
                trace.append(f"tool_load({n})")
                tools = [TOOL_LIST, TOOL_LOAD] + [
                    {"type": "function", "function": {"name": x, "description": CAT[x]["desc"], "parameters": CAT[x]["schema"]}}
                    for x in loaded]
                # EXPLICIT directive (user hypothesis 2026-07-22): tell the model the tool is now
                # callable and to CALL it — not just {ready:true}. Toggle via EXPLICIT below.
                if EXPLICIT:
                    body = {"loaded": n, "ready": True, "next_action":
                            f"{n} is now LOADED and CALLABLE. Call {n} now with its arguments to "
                            f"complete the user's request. Do NOT list or load more tools."}
                else:
                    body = {"loaded": n, "ready": True}
                msgs.append({"role": "tool", "tool_call_id": tc["id"], "content": json.dumps(body)})
            else:
                trace.append(f"tool_load(BAD:{n})")
                msgs.append({"role": "tool", "tool_call_id": tc["id"], "content": json.dumps({"error": f"no tool {n}"})})
        else:
            trace.append(f"HALLUCINATED {nm}")
            return False, trace, f"invented tool {nm}"
    return False, trace, "ran out of turns"


SCEN = [
    ("Search the glossary for what we already know about the character Kai.", "glossary_search"),
    ("Propose a new character entity named Mara for this book's glossary.", "glossary_propose_entities"),
    ("Show me the review inbox — the AI-suggested entities awaiting my review.", "glossary_curation_list"),
]
ok = 0
for goal, want in SCEN:
    reached, trace, why = run(goal, want)
    ok += 1 if reached else 0
    print(f"[{'REACH' if reached else 'FAIL ':5}] want={want}")
    print(f"        {why}")
    print(f"        trace: {' -> '.join(trace)}\n")
print(f">> discovery-reach: {ok}/{len(SCEN)} reached the lazy tool via tool_list->tool_load")
