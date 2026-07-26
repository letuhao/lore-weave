#!/usr/bin/env python
"""KG unification discoverability smoke: given ONLY the 26 default-visible KG tools,
does gemma-4-12b pick the RIGHT unified tool + discriminator for a natural request?
Covers all 5 merges: kg_graph_query(scope) / kg_build(target) / kg_ontology_propose(op)
/ kg_view_edit(op) / kg_add_nodes(mode)."""
import json, urllib.request

MCP   = "http://localhost:8216/mcp/"
LM    = "http://localhost:1234/v1/chat/completions"
MODEL = "google/gemma-4-12b-qat"
USER  = "019d5e3c-7cc5-7e6a-8b27-1344e148bf7c"
PROJ  = "019f8064-d213-72e7-b763-338da572ad68"  # a knowledge project (ambient)
TOKEN = "dev_internal_token"

def sse(raw):
    raw = raw.decode() if isinstance(raw, bytes) else raw
    for ln in raw.splitlines():
        ln = ln.strip()
        if ln.startswith("data:"): ln = ln[5:].strip()
        if ln.startswith("{"):
            try: return json.loads(ln)
            except: pass
    return json.loads(raw)

req = urllib.request.Request(MCP, data=json.dumps({"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}).encode(),
    headers={"Content-Type":"application/json","Accept":"application/json, text/event-stream",
             "X-Internal-Token":TOKEN,"X-User-Id":USER,"X-Project-Id":PROJ})
tl = sse(urllib.request.urlopen(req, timeout=30).read())["result"]["tools"]
tools = []
for t in tl:
    if (t.get("_meta") or {}).get("visibility") == "legacy": continue
    p = dict(t.get("inputSchema") or {}); p.setdefault("type","object"); p.setdefault("properties",{})
    tools.append({"type":"function","function":{"name":t["name"],"description":t.get("description",""),"parameters":p}})
print(f"catalog fed to gemma: {len(tools)} tools (default-visible)\n")

SYS = ("You are a knowledge-graph assistant working INSIDE the current book's project. "
       "The current project is already known from context — never ask for or invent a project_id. "
       "When the user asks for something, call the single most appropriate tool.")

SC = [
 ("graph-project", "Show me the knowledge graph for the current project — who relates to whom.",
    "kg_graph_query", lambda a: a.get("scope") in (None, "project")),
 ("graph-world", "Roll up the knowledge graph across the whole world, unifying entities by name.",
    "kg_graph_query", lambda a: a.get("scope") == "world"),
 ("graph-multi", "Union the graphs across these two specific projects: P1 and P2.",
    "kg_graph_query", lambda a: a.get("scope") == "multi"),
 ("build-graph", "Build the knowledge graph by extracting it from the book's chapters.",
    "kg_build", lambda a: a.get("target") == "graph"),
 ("build-wiki", "Generate wiki articles for all the book's entities.",
    "kg_build", lambda a: a.get("target") == "wiki"),
 ("onto-schema", "Add a new edge type WORSHIPS to this project's ontology.",
    "kg_ontology_propose", lambda a: a.get("op") == "schema_edit"),
 ("onto-adopt", "Adopt the xianxia ontology template into this project.",
    "kg_ontology_propose", lambda a: a.get("op") == "adopt_template"),
 ("view-upsert", "Save a view called 'politics' showing the alliance and rivalry edge types.",
    "kg_view_edit", lambda a: a.get("op") == "upsert"),
 ("view-delete", "Delete my saved view with code 'politics'.",
    "kg_view_edit", lambda a: a.get("op") == "delete"),
 ("node-manual", "Create a character node named Kai in the graph.",
    "kg_add_nodes", lambda a: a.get("mode") == "manual"),
 ("node-glossary", "Seed the graph from my book's glossary entities.",
    "kg_add_nodes", lambda a: a.get("mode") == "from_glossary"),
]

def ask(prompt):
    body = json.dumps({"model":MODEL,"temperature":0,"tools":tools,"tool_choice":"auto",
        "messages":[{"role":"system","content":SYS},{"role":"user","content":prompt}]}).encode()
    d = json.loads(urllib.request.urlopen(urllib.request.Request(LM, data=body, headers={"Content-Type":"application/json"}), timeout=120).read())
    tc = (d["choices"][0]["message"].get("tool_calls") or [])
    if not tc: return None, {}
    f = tc[0]["function"]
    try: return f["name"], json.loads(f.get("arguments") or "{}")
    except: return f["name"], {}

passes = 0
for label, prompt, exp, chk in SC:
    try: name, args = ask(prompt)
    except Exception as e: print(f"[{label:14}] ERROR {e}"); continue
    ok = (name == exp) and chk(args)
    passes += 1 if ok else 0
    disc = {k: args.get(k) for k in ("scope","target","op","mode") if k in args}
    verdict = "PASS" if ok else ("TOOL-OK/ARG" if name == exp else "WRONG-TOOL")
    print(f"[{label:14}] {verdict:12} picked={name} disc={disc}  (want {exp})")
print(f"\n>> KG discoverability: {passes}/{len(SC)} picked the right unified tool + discriminator")
