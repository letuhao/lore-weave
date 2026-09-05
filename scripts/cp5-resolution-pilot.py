#!/usr/bin/env python3
"""CP-5 · 5.3-pilot — does a NAME the model sent resolve to exactly one entity id?

`docs/specs/2026-08-09-v2-tool-contract/CP-5.md` row 5.3-pilot: run the ACTUAL failing
names against THEIR OWN books and measure the exact-match rate on the population the
member SERVES. Its result is recorded in §3b.

Why this script exists rather than a number in a document: v3's evidence (11/18) was
measured on 9 sessions whose overlap with the 24 failing sessions was ONE — the model had
searched precisely where it did NOT send a bare name, so the rate described the cases that
already went right (finding W2). This derives its population FROM the failures, so the
overlap is 100% by construction, and every denominator is a query result.

Two phases:

  1. POPULATION — classify the offending argument VALUE of every UUID-type failure in
     `loreweave_chat`. Only a human NAME is this member's subject; a placeholder, a
     quantifier (`"all"` — W3), a mangled uuid or a garbled decode are different defects
     and are counted separately rather than folded in.
  2. RESOLUTION — for each distinct (book, name) pair, call the selector core that
     `glossary_search` itself calls and count `tier: exact` matches.

Reported STRATIFIED. In a book holding one entity, resolution cannot fail; an aggregate
dominated by those books repeats W2's error one level down.

    python scripts/cp5-resolution-pilot.py [--json OUT]

Read-only: two SELECTs and a read-lane HTTP call per pair. Nothing is written.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
import uuid
from collections import Counter, defaultdict

PG_CONTAINER = os.environ.get("CP5_PG_CONTAINER", "infra-postgres-1")
GLOSSARY_BASE = os.environ.get("CP5_GLOSSARY_BASE", "http://localhost:8211")
INTERNAL_TOKEN = os.environ.get("CP5_INTERNAL_TOKEN", "dev_internal_token")
# glossary_search's own default (searchToolDefaultLimit): the pilot must not use a bound
# the tool would never send.
TOOL_DEFAULT_LIMIT = 20

FAILURES_SQL = r"""
SELECT m.session_id::text, m.owner_user_id::text, tc->>'tool', tc->>'error',
       coalesce(tc->'args','{}'::jsonb)::text
FROM chat_messages m, LATERAL jsonb_array_elements(m.tool_calls) tc
WHERE (tc->>'ok') = 'false'
  AND tc->>'error' ~* '(must be a (real )?UUID|hexadecimal UUID)'
"""

# A PLACEHOLDER is a token the model invented to stand in for an id it did not hold.
# It names nothing, so no resolver can serve it.
PLACEHOLDER = re.compile(
    r"^(0|null|none|nil|undefined|n/?a|tbd|unknown|\?+|-+)$|placeholder|^current_|^<.*>$"
    r"|^\[.*\]$|^\{\{.*\}\}$|^\$\{.*\}$"
    r"|^(the_)?(current|target|new|existing)_[a-z_]*id$|^[a-z_]*id_\d+$|^id_?\d*$",
    re.I,
)
# CASE-SENSITIVE on purpose. An ALL-CAPS token is a template slot, but under re.I
# `[A-Z][A-Z0-9_]{3,}` matches ANY word — it silently ate `Dracula`, a real name, and
# would have shrunk the denominator by exactly the cases the pilot exists to measure.
PLACEHOLDER_CS = re.compile(r"^[A-Z][A-Z0-9_]{3,}$|_HERE$")
# A MANGLED id is a uuid the model corrupted (a dropped nibble, a colon for a dash).
# A resolver has nothing to look up — it is a different defect.
MANGLED = re.compile(r"^[0-9a-fA-F][0-9a-fA-F:\-]{20,}$")
# A SYMBOLIC value names something in the SYSTEM (a tool, a field), not an entity.
SYMBOLIC = re.compile(r"^[a-z]+(_[a-z]+)+$")
# A GARBLED value is a decode failure — the model's own framing bled into the argument.
GARBLED = re.compile(r"[\n{}\"]|<\|?tool_call")
# A QUANTIFIER asks for something the parameter cannot express (W3).
QUANTIFIER = {"all", "*", "any", "every", "everything", "each"}

ERROR_NAMES_KEY = re.compile(r"\b([a-z_]*_id)\b\s+must be a")


def psql(db: str, sql: str) -> str:
    cmd = ["docker", "exec", PG_CONTAINER, "psql", "-U", "loreweave", "-d", db,
           "-At", "-R", "\x1e", "-F", "\x1f", "-c", sql]
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    if proc.returncode != 0:
        raise RuntimeError(f"psql {db} failed: {proc.stderr.strip()}")
    return proc.stdout


def is_uuid(v) -> bool:
    try:
        uuid.UUID(str(v))
        return True
    except (ValueError, AttributeError, TypeError):
        return False


def classify(value) -> str:
    v = str(value).strip()
    if not v:
        return "empty"
    if v.lower() in QUANTIFIER:
        return "quantifier"
    if GARBLED.search(v) or len(v) > 80:
        return "garbled"
    if MANGLED.match(v):
        return "mangled_uuid"
    if PLACEHOLDER.search(v) or PLACEHOLDER_CS.search(v):
        return "placeholder"
    if SYMBOLIC.match(v):
        return "symbolic"
    return "name"


def population() -> dict:
    total_calls, sessions = 0, set()
    buckets: dict[str, Counter] = defaultdict(Counter)
    bucket_sessions: dict[str, set] = defaultdict(set)
    pairs: dict[tuple, dict] = {}

    for rec in psql("loreweave_chat", FAILURES_SQL).split("\x1e"):
        parts = rec.strip("\n").split("\x1f")
        if len(parts) != 5:
            continue
        sid, uid, tool, err, raw = parts
        try:
            args = json.loads(raw)
        except json.JSONDecodeError:
            args = {}
        total_calls += 1
        sessions.add(sid)
        # Blame the field the TOOL blamed; fall back to any non-uuid `*_id` argument.
        keys = set(ERROR_NAMES_KEY.findall(err or ""))
        if not keys:
            keys = {k for k, v in args.items() if k.endswith("_id") and not is_uuid(v)}
        offending = {k: args[k] for k in keys if k in args and not is_uuid(args[k])}
        if not offending:
            buckets["no_offending_arg_recorded"][tool] += 1
            bucket_sessions["no_offending_arg_recorded"].add(sid)
            continue
        for k, v in offending.items():
            cls = classify(v)
            buckets[cls][f"{tool}.{k}"] += 1
            bucket_sessions[cls].add(sid)
            if cls != "name":
                continue
            book = args.get("book_id") if is_uuid(args.get("book_id")) else None
            slot = pairs.setdefault(
                (book, k, str(v)),
                {"calls": 0, "sessions": set(), "tools": Counter(), "users": Counter()})
            slot["calls"] += 1
            slot["sessions"].add(sid)
            slot["tools"][tool] += 1
            slot["users"][uid] += 1

    served = [
        {"book_id": b, "arg": k, "value": v, "calls": s["calls"],
         "sessions": sorted(s["sessions"]), "tools": dict(s["tools"]),
         "user_id": s["users"].most_common(1)[0][0]}
        for (b, k, v), s in sorted(pairs.items(), key=lambda kv: -kv[1]["calls"])
    ]
    return {
        "uuid_failures_calls": total_calls,
        "uuid_failures_sessions": len(sessions),
        "buckets": {c: {"calls": sum(cnt.values()), "sessions": len(bucket_sessions[c]),
                        "top": cnt.most_common(6)}
                    for c, cnt in sorted(buckets.items(), key=lambda kv: -sum(kv[1].values()))},
        "served": {"calls": sum(p["calls"] for p in served),
                   "sessions": len({s for p in served for s in p["sessions"]}),
                   "pairs": len(served)},
        "rows": served,
    }


def ground_truth(book_ids: list[str]) -> dict[str, list[dict]]:
    """Every entity per book from the SSOT, so 'no match' stays decomposable into
    'the resolver missed it' and 'there was nothing to resolve'."""
    if not book_ids:
        return {}
    ids = ",".join(f"'{b}'" for b in book_ids)
    out = psql("loreweave_glossary",
               "SELECT book_id::text, entity_id::text, coalesce(cached_name,''), "
               "coalesce(array_to_string(cached_aliases,'~'),'') "
               f"FROM glossary_entities WHERE deleted_at IS NULL AND book_id::text IN ({ids})")
    truth: dict[str, list[dict]] = {}
    for rec in out.split("\x1e"):
        parts = rec.strip("\n").split("\x1f")
        if len(parts) != 4:
            continue
        book, eid, name, aliases = parts
        truth.setdefault(book, []).append(
            {"entity_id": eid, "name": name,
             "aliases": [a for a in aliases.split("~") if a]})
    return truth


def search(book_id: str, query: str) -> list[dict]:
    """The selector core `glossary_search` calls (mcp_server.go → selectGlossaryForContext),
    same bounds. It differs only in the grant check, which is not what this measures — and
    these books are deleted from loreweave_book, so the grant-checked MCP path cannot run."""
    req = urllib.request.Request(
        f"{GLOSSARY_BASE}/internal/books/{book_id}/select-for-context",
        data=json.dumps({"query": query, "max_entities": TOOL_DEFAULT_LIMIT}).encode(),
        headers={"Content-Type": "application/json", "X-Internal-Token": INTERNAL_TOKEN},
        method="POST")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())["entities"]


def tally(rows, weight):
    total = sum(weight(r) for r in rows) or 1
    return {o: (sum(weight(r) for r in rows if r["outcome"] == o),
                round(100 * sum(weight(r) for r in rows if r["outcome"] == o) / total, 1))
            for o in ("EXACTLY_ONE", "ZERO_EXACT", "AMBIGUOUS")}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", help="write the full report here")
    args = ap.parse_args()

    pop = population()
    truth = ground_truth(sorted({p["book_id"] for p in pop["rows"] if p["book_id"]}))

    results = []
    for p in pop["rows"]:
        book, name = p["book_id"], p["value"]
        # `tools` rides along so the report is self-sufficient: `cp5-resolution-replay.py` needs
        # the CALLING tool to look up its binding, and a population that names the argument but not
        # the tool cannot be replayed against the mechanism.
        row = {"book_id": book, "name": name, "arg": p["arg"], "calls": p["calls"],
               "sessions": len(p["sessions"]), "tools": sorted(p["tools"])}
        in_book = truth.get(book or "", [])
        row["entities_in_book"] = len(in_book)
        low = name.strip().lower()
        row["ground_truth_present"] = any(
            e["name"].strip().lower() == low
            or low in [a.strip().lower() for a in e["aliases"]] for e in in_book)
        if not book or not in_book:
            row["outcome"] = "NO_SUBSTRATE"
            row["note"] = "no surviving glossary entity for this book — UNMEASURABLE"
            results.append(row)
            continue
        try:
            ents = search(book, name)
        except (urllib.error.HTTPError, urllib.error.URLError, OSError) as exc:
            row["outcome"], row["note"] = "SEARCH_ERROR", repr(exc)
            results.append(row)
            continue
        exact = [e for e in ents if e.get("tier") == "exact"]
        row.update(returned=len(ents), exact=len(exact),
                   exact_names=[e.get("cached_name") for e in exact][:6],
                   top=[(e.get("cached_name"), e.get("tier"), round(e.get("rank_score", 0), 3))
                        for e in ents[:3]])
        row["outcome"] = ("EXACTLY_ONE" if len(exact) == 1
                          else "ZERO_EXACT" if not exact else "AMBIGUOUS")
        if len(exact) == 1:
            row["resolved_to"] = exact[0].get("entity_id")
        results.append(row)

    measurable = [r for r in results
                  if r["outcome"] in ("EXACTLY_ONE", "ZERO_EXACT", "AMBIGUOUS")]
    # A book holding one entity cannot fail this task. Stratify, or the aggregate measures
    # the cases that were never hard — W2's error one level down.
    trivial = [r for r in measurable if r["entities_in_book"] <= 1]
    contested = [r for r in measurable if r["entities_in_book"] > 1]
    unmeasurable = [r for r in results if r not in measurable]

    report = {
        "instrument": "POST /internal/books/{book_id}/select-for-context "
                      "— selectGlossaryForContext, the core glossary_search calls",
        "population": pop["served"],
        "buckets": pop["buckets"],
        "strata": {
            "single_entity_book": {
                "pairs": len(trivial), "calls": sum(r["calls"] for r in trivial),
                "by_pair": tally(trivial, lambda r: 1),
                "note": "resolution cannot fail here — excluded from the informative rate"},
            "contested_book": {
                "pairs": len(contested), "calls": sum(r["calls"] for r in contested),
                "entities_range": [min((r["entities_in_book"] for r in contested), default=0),
                                   max((r["entities_in_book"] for r in contested), default=0)],
                "by_pair": tally(contested, lambda r: 1),
                "by_call": tally(contested, lambda r: r["calls"])},
            "aggregate_misleading": {
                "pairs": len(measurable), "calls": sum(r["calls"] for r in measurable),
                "by_pair": tally(measurable, lambda r: 1),
                "by_call": tally(measurable, lambda r: r["calls"])},
        },
        "unmeasurable": [{"book_id": r["book_id"], "name": r["name"], "calls": r["calls"],
                          "outcome": r["outcome"], "note": r.get("note")}
                         for r in unmeasurable],
        "rows": results,
    }

    print(f"UUID-type failures: {pop['uuid_failures_calls']} calls / "
          f"{pop['uuid_failures_sessions']} sessions")
    for c, d in pop["buckets"].items():
        print(f"  {c:<26} {d['calls']:>5} calls {d['sessions']:>3} sessions  {d['top'][:3]}")
    print(f"\nSERVED (a NAME in an id field): {pop['served']['calls']} calls / "
          f"{pop['served']['sessions']} sessions / {pop['served']['pairs']} pairs\n")
    for r in results:
        gt = "gt+" if r.get("ground_truth_present") else "gt-"
        print(f"  {r['outcome']:<13} {gt} {r['calls']:>4}x {r['name']!r:<16} "
              f"book={(r['book_id'] or '-')[:8]} n={r['entities_in_book']:>3} "
              f"exact={r.get('exact')} top={r.get('top')}")
    st = report["strata"]
    print(f"\n  single-entity book  {st['single_entity_book']['pairs']} pairs / "
          f"{st['single_entity_book']['calls']} calls  {st['single_entity_book']['by_pair']}")
    print(f"  CONTESTED book      {st['contested_book']['pairs']} pairs / "
          f"{st['contested_book']['calls']} calls, entities "
          f"{st['contested_book']['entities_range']}\n"
          f"      by pair {st['contested_book']['by_pair']}\n"
          f"      by call {st['contested_book']['by_call']}   <-- THE INFORMATIVE RATE")
    print(f"  aggregate (do not quote alone) {st['aggregate_misleading']['by_call']}")
    unm = sum(r["calls"] for r in unmeasurable)
    served = pop["served"]["calls"] or 1
    print(f"\n  UNMEASURABLE: {unm} of {served} calls "
          f"({round(100 * unm / served, 1)}%) — substrate deleted")

    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump(report, fh, ensure_ascii=False, indent=2)
        print(f"\nwritten: {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
