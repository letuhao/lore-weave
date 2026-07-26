#!/usr/bin/env python
"""Measure the ambient-book win (spec 2026-07-22 Q4). Two conditions on gemma-4, N runs each,
driving the REAL book-service /mcp, DB-verified:

  BASELINE  — prompt gives the book UUID; tool schema REQUIRES book_id; NO X-Book-Id header.
              The model must TRANSCRIBE the 36-char UUID into every call (the burden + error class).
  AMBIENT   — prompt says "the current book" (no UUID); X-Book-Id header set; book_id OPTIONAL.
              The model calls with NO book_id — the id never enters its context or output.

Metrics: DB-verified success rate, whether book_id was emitted, mistranscription count, tokens.
Run: python ambient_ab.py <internal_token>
"""
import json, sys, subprocess, urllib.request, statistics

MCP = "http://localhost:8205/mcp"
LM = "http://localhost:1234/v1/chat/completions"
MODEL = "google/gemma-4-26b-a4b-qat"
USER = "019d5e3c-7cc5-7e6a-8b27-1344e148bf7c"
BOOK = "019f82b6-c31b-72e9-bf2a-3f37f4c8a847"   # The Tidewright (no Work)
TOKEN = sys.argv[1]
N = 5


def psql(db, sql):
    r = subprocess.run(["docker", "exec", "infra-postgres-1", "psql", "-U", "loreweave", "-d", db,
                        "-t", "-A", "-c", sql], capture_output=True, text=True)
    return [x for x in r.stdout.strip().splitlines() if x.strip()]


def mcp_call(name, args, ambient):
    hdr = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream",
           "X-Internal-Token": TOKEN, "X-User-Id": USER}
    if ambient:
        hdr["X-Book-Id"] = BOOK  # the studio binding
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                       "params": {"name": name, "arguments": args}}).encode()
    req = urllib.request.Request(MCP, data=body, headers=hdr)
    try:
        d = json.loads(urllib.request.urlopen(req, timeout=60).read())
    except urllib.error.HTTPError as e:
        return {"error": f"http {e.code}"}
    r = d.get("result", {})
    if r.get("isError"):
        return {"error": " ".join(c.get("text", "") for c in r.get("content", []))}
    return r.get("structuredContent", {"ok": True})


def edit_tool(ambient):
    # book_id is required in BASELINE, absent from the schema in AMBIENT (the surface drop).
    props = {"op": {"type": "string", "enum": ["create_part"]}, "title": {"type": "string"}}
    required = ["op", "title"]
    if not ambient:
        props["book_id"] = {"type": "string", "description": "the book UUID"}
        required.append("book_id")
    return [{"type": "function", "function": {
        "name": "book_structure_edit",
        "description": "Create a manuscript part. op=create_part with a title" + ("" if ambient else ", and the book_id"),
        "parameters": {"type": "object", "properties": props, "required": required}}}]


def reset():
    psql("loreweave_composition", f"UPDATE structure_node SET is_archived=true WHERE book_id='{BOOK}' AND kind='part'")

def live_titles():
    return psql("loreweave_composition", f"SELECT title FROM structure_node WHERE book_id='{BOOK}' AND kind='part' AND NOT is_archived")


SYS = "You are a manuscript assistant. Use the tool to do what the user asks. Reply briefly when done."


def run_once(ambient, title):
    if ambient:
        user = f"Create a part called '{title}' in the current book."
    else:
        user = f"Create a part called '{title}' in book {BOOK}."
    tools = edit_tool(ambient)
    msgs = [{"role": "system", "content": SYS}, {"role": "user", "content": user}]
    tin = tout = 0
    emitted_book_id = None
    for _ in range(4):
        body = json.dumps({"model": MODEL, "messages": msgs, "tools": tools, "temperature": 0, "max_tokens": 700}).encode()
        d = json.loads(urllib.request.urlopen(urllib.request.Request(LM, data=body, headers={"Content-Type": "application/json"}), timeout=180).read())
        u = d.get("usage", {}); tin += u.get("prompt_tokens", 0); tout += u.get("completion_tokens", 0)
        m = d["choices"][0]["message"]; msgs.append(m)
        tcs = m.get("tool_calls") or []
        if not tcs:
            break
        for tc in tcs:
            a = json.loads(tc["function"]["arguments"] or "{}")
            if "book_id" in a:
                emitted_book_id = a["book_id"]
            res = mcp_call(tc["function"]["name"], a, ambient)
            msgs.append({"role": "tool", "tool_call_id": tc.get("id", "0"), "name": tc["function"]["name"], "content": json.dumps(res)[:800]})
    return {"tin": tin, "tout": tout, "emitted_book_id": emitted_book_id}


def main():
    report = {}
    for cond in ("baseline", "ambient"):
        ambient = cond == "ambient"
        ok = mis = emitted = 0
        tins, touts = [], []
        for i in range(N):
            reset()
            title = f"Act-{cond[:3]}-{i}"
            r = run_once(ambient, title)
            success = title.lower() in [t.lower() for t in live_titles()]
            ok += 1 if success else 0
            tins.append(r["tin"]); touts.append(r["tout"])
            eb = r["emitted_book_id"]
            if eb is not None:
                emitted += 1
                if eb != BOOK:
                    mis += 1
            print(f"[{cond:8}] run{i}: {'PASS' if success else 'FAIL'} emitted_book_id={eb!r} {'(MISTRANSCRIBED!)' if eb and eb!=BOOK else ''} tok={r['tin']}/{r['tout']}")
        report[cond] = {"pass": ok, "emitted_book_id": emitted, "mistranscribed": mis,
                        "mean_tok_in": int(statistics.mean(tins)), "mean_tok_out": int(statistics.mean(touts))}
        print(f"  >> {cond}: {ok}/{N} pass · book_id emitted {emitted}/{N} · mistranscribed {mis} · mean_tok in={report[cond]['mean_tok_in']} out={report[cond]['mean_tok_out']}\n")
    reset()
    print(json.dumps(report))


if __name__ == "__main__":
    main()
