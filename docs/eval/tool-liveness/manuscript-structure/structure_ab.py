#!/usr/bin/env python
"""A/B measurement: does a weak model (gemma-4) navigate + mutate the manuscript STRUCTURE graph?

Two tool surfaces on the SAME 6 scenarios, driving the REAL book-service MCP (cross-service to
composition), DB-verified after each scenario, state reset between them.

  UNIFIED    = book_structure_read + book_structure_edit (the new tools)
  FRAGMENTED = book_structure_read + book_chapter_set_part + book_chapter_reorder
               (the pre-existing surface — NO way to create/rename/reorder a part: the real gap)

Run:  python structure_ab.py <internal_token>
"""
import json, sys, subprocess, urllib.request

MCP = "http://localhost:8205/mcp"
LM = "http://localhost:1234/v1/chat/completions"
MODEL = "google/gemma-4-26b-a4b-qat"
USER = "019d5e3c-7cc5-7e6a-8b27-1344e148bf7c"
BOOK = "019f8027-294f-7106-b697-a68b7e8f1c66"  # "Bug4 Part Repro": 2 chapters
CH1 = "019f8027-2969-789b-9291-a0edd9e5a0dc"   # Chapter 1
CH2 = "019f8027-298d-7347-b21a-9043bb4853b2"   # Chapter 2
PART1 = "019f8027-29a6-75a6-a398-3eced8826299" # "Part 1"
TOKEN = sys.argv[1]


def psql(db, sql):
    out = subprocess.run(["docker", "exec", "infra-postgres-1", "psql", "-U", "loreweave", "-d", db,
                          "-t", "-A", "-F", "|", "-c", sql], capture_output=True, text=True)
    return [ln for ln in out.stdout.strip().splitlines() if ln.strip()]


def mcp_call(name, args):
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                       "params": {"name": name, "arguments": args}}).encode()
    req = urllib.request.Request(MCP, data=body, headers={
        "Content-Type": "application/json", "Accept": "application/json, text/event-stream",
        "X-Internal-Token": TOKEN, "X-User-Id": USER})
    try:
        d = json.loads(urllib.request.urlopen(req, timeout=60).read())
    except urllib.error.HTTPError as e:
        return {"error": f"http {e.code}: {e.read().decode()[:200]}"}
    if "error" in d:
        return {"error": d["error"].get("message", str(d["error"]))}
    res = d.get("result", {})
    if res.get("isError"):
        txt = " ".join(c.get("text", "") for c in res.get("content", []))
        return {"error": txt or "tool error"}
    return res.get("structuredContent", {"ok": True})


# ── tool schemas (OpenAI format) ─────────────────────────────────────────────
READ = {"type": "function", "function": {
    "name": "book_structure_read",
    "description": "Read the manuscript structure (part/chapter graph). With book_id alone: the overview "
                   "(every part + its chapter_count + unassigned_count). With part_id=<id> or "
                   "part_id=\"unassigned\": that group's chapters.",
    "parameters": {"type": "object", "properties": {
        "book_id": {"type": "string"}, "part_id": {"type": "string"}}, "required": ["book_id"]}}}
EDIT = {"type": "function", "function": {
    "name": "book_structure_edit",
    "description": "Reorganize the manuscript structure. op = create_part (title) | rename_part "
                   "(part_id,title) | reorder_parts (ordered_part_ids) | home_chapter (chapter_id, part_id "
                   "or \"unassigned\") | reorder_chapters (chapter_ids = full new order).",
    "parameters": {"type": "object", "properties": {
        "op": {"type": "string", "enum": ["create_part", "rename_part", "reorder_parts", "home_chapter", "reorder_chapters"]},
        "book_id": {"type": "string"}, "title": {"type": "string"}, "part_id": {"type": "string"},
        "chapter_id": {"type": "string"}, "ordered_part_ids": {"type": "array", "items": {"type": "string"}},
        "chapter_ids": {"type": "array", "items": {"type": "string"}}},
        "required": ["op", "book_id"]}}}
SET_PART = {"type": "function", "function": {
    "name": "book_chapter_set_part",
    "description": "Move a chapter into/out of a manuscript part. part_id = target part, or null to un-home.",
    "parameters": {"type": "object", "properties": {
        "book_id": {"type": "string"}, "chapter_id": {"type": "string"}, "part_id": {"type": "string"}},
        "required": ["book_id", "chapter_id"]}}}
REORDER = {"type": "function", "function": {
    "name": "book_chapter_reorder",
    "description": "Set the reading order of a book's chapters. chapter_ids = the complete new order.",
    "parameters": {"type": "object", "properties": {
        "book_id": {"type": "string"}, "chapter_ids": {"type": "array", "items": {"type": "string"}}},
        "required": ["book_id", "chapter_ids"]}}}

SURFACES = {
    "unified": [READ, EDIT],
    "fragmented": [READ, SET_PART, REORDER],
}


def reset():
    """Deterministic baseline: 2 chapters both in Part 1 (sort 1,2); archive any other live part.
    Park sorts at negatives FIRST to dodge the partial UNIQUE(book_id,sort_order,language)."""
    psql("loreweave_book", f"UPDATE chapters SET sort_order=-1 WHERE id='{CH1}'")
    psql("loreweave_book", f"UPDATE chapters SET sort_order=-2 WHERE id='{CH2}'")
    psql("loreweave_book", f"UPDATE chapters SET structure_node_id='{PART1}', sort_order=1 WHERE id='{CH1}'")
    psql("loreweave_book", f"UPDATE chapters SET structure_node_id='{PART1}', sort_order=2 WHERE id='{CH2}'")
    psql("loreweave_composition",
         f"UPDATE structure_node SET is_archived=true WHERE book_id='{BOOK}' AND kind='part' AND id<>'{PART1}'")
    psql("loreweave_composition",
         f"UPDATE structure_node SET is_archived=false, title='Part 1' WHERE id='{PART1}'")


def ch_part(ch):
    r = psql("loreweave_book", f"SELECT structure_node_id FROM chapters WHERE id='{ch}'")
    return r[0] if r else None

def ch_sort(ch):
    r = psql("loreweave_book", f"SELECT sort_order FROM chapters WHERE id='{ch}'")
    return int(r[0]) if r else None

def live_parts():
    return psql("loreweave_composition",
                f"SELECT id,title FROM structure_node WHERE book_id='{BOOK}' AND kind='part' AND NOT is_archived ORDER BY rank")


# ── scenarios: (name, prompt, verify_fn(final_text) -> (ok, detail)) ─────────
def v_navigate(txt):
    # Ch2 is in Part 1 after reset. Correct answer must say "Part 1".
    return ("part 1" in txt.lower(), "answer must name 'Part 1'")

def v_create_move(_):
    parts = live_parts()
    act2 = [p for p in parts if "act" in p.split("|")[1].lower() or "two" in p.split("|")[1].lower() or len(parts) == 2]
    if len(parts) < 2:
        return (False, f"no new part created (parts={[p.split('|')[1] for p in parts]})")
    newp = [p for p in parts if p.split("|")[0] != PART1]
    if not newp:
        return (False, "no non-Part1 part")
    npid = newp[0].split("|")[0]
    return (ch_part(CH2) == npid, f"Ch2 home={ch_part(CH2)} newpart={npid}")

def v_reorder(_):
    return (ch_sort(CH2) < ch_sort(CH1), f"Ch2 sort={ch_sort(CH2)} Ch1 sort={ch_sort(CH1)} (want Ch2<Ch1)")

def v_traversal(txt):
    return ("0" in txt or "zero" in txt.lower() or "none" in txt.lower(), "unassigned should be 0")

def v_trap(txt):
    # No op can nest a part inside a chapter. Success = model does NOT claim it did it; it declines/explains.
    bad = any(w in txt.lower() for w in ["done", "moved", "successfully", "i have put", "nested"])
    declines = any(w in txt.lower() for w in ["can't", "cannot", "not possible", "no ", "isn't", "unable", "doesn't", "not support"])
    return (declines and not bad, "should decline the impossible nesting, not fabricate success")

def v_rename(_):
    parts = [p.split("|")[1].lower() for p in live_parts()]
    return (any("two" in t or "second" in t for t in parts), f"parts={parts} (want one renamed to 'Part Two')")

SCENARIOS = [
    ("navigate", f"In book {BOOK}, which part is chapter {CH2} in? Answer with the part's title.", v_navigate, None),
    ("create+move", f"In book {BOOK}: create a new part titled 'Act II', then move chapter {CH2} into it.", v_create_move, None),
    ("reorder_chapters", f"In book {BOOK}, reorder the chapters so chapter {CH2} comes BEFORE chapter {CH1}.", v_reorder, None),
    ("traversal", f"In book {BOOK}, how many chapters are NOT in any part (unassigned)? Answer with just the number.", v_traversal, None),
    ("trap_nest", f"In book {BOOK}, put Part 1 (id {PART1}) INSIDE chapter {CH1} — make the part a child of the chapter.", v_trap, None),
    ("rename_part", f"In book {BOOK}: first create a part 'Act II', then rename that part to 'Part Two'.", v_rename, "needs_create"),
]

SYS = ("You are a manuscript-structure assistant. Use the provided tools to inspect and modify the book's "
       "part/chapter structure. Call tools to gather ids you don't have. When the task is done (or cannot "
       "be done), reply with a short final sentence. Do not invent ids — read them from tool results.")


def run_scenario(surface, prompt):
    tools = SURFACES[surface]
    msgs = [{"role": "system", "content": SYS}, {"role": "user", "content": prompt}]
    calls, tok_in, tok_out = [], 0, 0
    for _ in range(8):
        body = json.dumps({"model": MODEL, "messages": msgs, "tools": tools,
                           "temperature": 0, "max_tokens": 1300}).encode()
        req = urllib.request.Request(LM, data=body, headers={"Content-Type": "application/json"})
        d = json.loads(urllib.request.urlopen(req, timeout=180).read())
        u = d.get("usage", {})
        tok_in += u.get("prompt_tokens", 0); tok_out += u.get("completion_tokens", 0)
        m = d["choices"][0]["message"]
        msgs.append(m)
        tcs = m.get("tool_calls") or []
        if not tcs:
            return {"final": m.get("content", "") or "", "calls": calls, "tok_in": tok_in, "tok_out": tok_out}
        for tc in tcs:
            fn = tc["function"]["name"]
            try:
                a = json.loads(tc["function"]["arguments"] or "{}")
            except Exception:
                a = {}
            result = mcp_call(fn, a)
            calls.append({"tool": fn, "args": a, "err": result.get("error")})
            msgs.append({"role": "tool", "tool_call_id": tc.get("id", "0"), "name": fn,
                         "content": json.dumps(result)[:1200]})
    return {"final": "(max turns)", "calls": calls, "tok_in": tok_in, "tok_out": tok_out}


def main():
    report = {"model": MODEL, "surfaces": {}}
    for surface in ("fragmented", "unified"):
        rows = []
        for name, prompt, verify, flag in SCENARIOS:
            reset()
            r = run_scenario(surface, prompt)
            ok, detail = verify(r["final"])
            wrong_tool = any(c["tool"] not in [t["function"]["name"] for t in SURFACES[surface]] for c in r["calls"])
            errs = [c["err"] for c in r["calls"] if c["err"]]
            rows.append({"scenario": name, "ok": ok, "detail": detail, "final": r["final"][:160],
                         "tool_calls": [c["tool"] for c in r["calls"]], "errors": errs,
                         "tok_in": r["tok_in"], "tok_out": r["tok_out"]})
            print(f"[{surface:10}] {name:18} {'PASS' if ok else 'FAIL'}  calls={[c['tool'] for c in r['calls']]}  tok={r['tok_in']}/{r['tok_out']}  {detail}")
        report["surfaces"][surface] = rows
        passed = sum(1 for x in rows if x["ok"])
        ti = sum(x["tok_in"] for x in rows); to = sum(x["tok_out"] for x in rows)
        print(f"  >> {surface}: {passed}/{len(rows)} pass, tokens in={ti} out={to}\n")
    reset()
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
