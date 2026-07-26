#!/usr/bin/env python
"""Discoverability smoke: given ONLY the 25 default-visible glossary tools (the shrunk catalog),
does a weak model (gemma-4-12b) pick the RIGHT unified tool for a natural request?
Tests curation_list / propose_curation / set_genres / get_entity.include."""
import json, urllib.request

MCP   = "http://localhost:8211/mcp"
LM    = "http://localhost:1234/v1/chat/completions"
MODEL = "google/gemma-4-12b-qat"
USER  = "019d5e3c-7cc5-7e6a-8b27-1344e148bf7c"
BOOK  = "019f82b6-c31b-72e9-bf2a-3f37f4c8a847"
TOKEN = "dev_internal_token"
EID   = "019f8027-2969-789b-9291-a0edd9e5a0dc"  # a placeholder entity id (pick-only test)

def sse_json(raw):
    if isinstance(raw, bytes): raw = raw.decode("utf-8", "replace")
    for ln in raw.splitlines():
        ln = ln.strip()
        if ln.startswith("data:"): ln = ln[5:].strip()
        if ln.startswith("{"):
            try: return json.loads(ln)
            except: pass
    return json.loads(raw)

# 1) fetch the default-visible (non-legacy) glossary tools, to OpenAI tool format
req = urllib.request.Request(MCP, data=json.dumps({"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}).encode(),
    headers={"Content-Type":"application/json","Accept":"application/json, text/event-stream",
             "X-Internal-Token":TOKEN,"X-User-Id":USER})
tl = sse_json(urllib.request.urlopen(req, timeout=30).read())["result"]["tools"]
tools, names = [], []
for t in tl:
    if (t.get("_meta") or {}).get("visibility") == "legacy": continue
    names.append(t["name"])
    tools.append({"type":"function","function":{
        "name": t["name"], "description": t.get("description",""),
        "parameters": (lambda p: (p.setdefault("type","object"), p.setdefault("properties",{}), p)[2])(dict(t.get("inputSchema") or {}))}})
print(f"catalog fed to gemma: {len(tools)} tools (default-visible)\n")

SYS = ("You are a glossary co-writing assistant working INSIDE the current book's studio. "
       "The current book is already known from context — never ask for or invent a book_id. "
       "When the user asks for something, call the single most appropriate tool.")

# scenario: (label, user request, expected tool, checker(args)->bool, why)
SC = [
 ("merge-review", "This book may have duplicate entities. Show me the merge candidates so I can review them.",
    "glossary_curation_list", lambda a: a.get("view")=="merge_candidates"),
 ("ai-inbox", "What entities has the extractor suggested that still need my review?",
    "glossary_curation_list", lambda a: a.get("view")=="ai_suggestions"),
 ("unknown-triage", "List the entities whose kind couldn't be determined, so I can fix their type.",
    "glossary_curation_list", lambda a: a.get("view")=="unknowns"),
 ("approve", f"Approve these two draft entities as active: {EID} and 019f8027-298d-7347-b21a-9043bb4853b2.",
    "glossary_propose_curation", lambda a: a.get("op")=="status_change"),
 ("merge-do", f"Merge the duplicate entity 019f8027-298d-7347-b21a-9043bb4853b2 into {EID} (keep {EID}).",
    "glossary_propose_curation", lambda a: a.get("op")=="merge"),
 ("reassign", f"Entity {EID} is the wrong type — reassign it to the 'character' kind.",
    "glossary_propose_curation", lambda a: a.get("op")=="reassign_kind"),
 ("activate-genre", "Turn on the 'xianxia' genre for this book.",
    "glossary_set_genres", lambda a: a.get("target")=="book_active"),
 ("entity-detail", f"Show me entity {EID} together with its revision history and the evidence behind its attributes.",
    "glossary_get_entity", lambda a: bool(set(a.get("include") or []) & {"revisions","evidence"})),
]

def ask(prompt):
    body = json.dumps({"model":MODEL,"temperature":0,"tools":tools,"tool_choice":"auto",
        "messages":[{"role":"system","content":SYS},{"role":"user","content":prompt}]}).encode()
    r = urllib.request.Request(LM, data=body, headers={"Content-Type":"application/json"})
    d = json.loads(urllib.request.urlopen(r, timeout=120).read())
    msg = d["choices"][0]["message"]
    tc = (msg.get("tool_calls") or [])
    if not tc: return None, None
    f = tc[0]["function"]
    try: args = json.loads(f.get("arguments") or "{}")
    except: args = {}
    return f["name"], args

passes = 0
for label, prompt, exp_tool, chk in SC:
    try:
        name, args = ask(prompt)
    except Exception as e:
        print(f"[{label:14}] ERROR {e}"); continue
    tool_ok = (name == exp_tool)
    arg_ok = tool_ok and chk(args)
    ok = tool_ok and arg_ok
    passes += 1 if ok else 0
    disc = {k:args.get(k) for k in ("view","op","target","include","status") if k in args}
    verdict = "PASS" if ok else ("TOOL-OK/ARG-MISS" if tool_ok else "WRONG-TOOL")
    print(f"[{label:14}] {verdict:16} picked={name} disc={disc}  (want {exp_tool})")
print(f"\n>> discoverability: {passes}/{len(SC)} picked the right unified tool + discriminator")
