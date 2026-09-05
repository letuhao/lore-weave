#!/usr/bin/env python3
"""CP-5.3 · replay the REAL failed calls through the resolution mechanism.

`docs/specs/2026-08-09-v2-tool-contract/CP-5.md` §3a. The pilot (§3b) asked *"can these names be
resolved at all?"*. This asks the next question: **does the mechanism turn those exact calls into a
substitution or an ACTIONABLE refusal, and is every one of them recorded?**

Not a synthetic probe. Every row is a `(tool, args)` pair that actually failed in production with
`entity_id must be a UUID`, taken from the pilot's own population, re-dispatched through
`refresolve.resolve_call` against the live glossary selector.

    python scripts/cp5-resolution-pilot.py --json pop.json
    python scripts/cp5-resolution-replay.py --population pop.json

Read-only: the resolver is `lane=read` by contract, which `load_registry` enforces before any
dispatch happens.
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services" / "chat-service"))

from app.agentruntime.refresolve import (  # noqa: E402
    apply_resolutions, load_registry, refusal_message, resolve_call,
)

BASE = os.environ.get("CP5_GLOSSARY_BASE", "http://localhost:8211")
TOKEN = os.environ.get("CP5_INTERNAL_TOKEN", "dev_internal_token")
LANE_BY_TIER = {"R": "read", "A": "action", "W": "write", "S": "system"}


def catalogue() -> dict[str, dict]:
    doc = json.loads((ROOT / "contracts" / "agent-runtime-baseline" / "tools-list.snapshot.json")
                     .read_text(encoding="utf-8"))
    return {t.get("function", t).get("name"): t for t in doc["tools"]}


def lane_of(cat: dict[str, dict]):
    def _lane(tool: str) -> str | None:
        td = cat.get(tool)
        if td is None:
            return None
        return LANE_BY_TIER.get(((td.get("function", td)).get("_meta") or {}).get("tier"))
    return _lane


def dispatch(tool: str, args: dict):
    """The selector core `glossary_search` calls, exactly as 5.3-pilot used it."""
    if tool != "glossary_search":
        raise RuntimeError(f"this replay only knows glossary_search, not {tool}")
    body = json.dumps({"query": args["query"], "max_entities": 20}).encode()
    req = urllib.request.Request(
        f"{BASE}/internal/books/{args['book_id']}/select-for-context", data=body,
        headers={"Content-Type": "application/json", "X-Internal-Token": TOKEN}, method="POST")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--population", required=True,
                    help="the --json output of scripts/cp5-resolution-pilot.py")
    args = ap.parse_args()

    cat = catalogue()
    doc = json.loads((ROOT / "contracts" / "agent-runtime-ref-resolvers.json")
                     .read_text(encoding="utf-8"))
    resolvers, bindings = load_registry(doc, lane_of(cat))
    print(f"registry: {len(resolvers)} ref type(s), {len(bindings)} bound (tool, param) pair(s)\n")

    pop = json.loads(pathlib.Path(args.population).read_text(encoding="utf-8"))
    pairs = pop.get("rows") or []
    if not pairs:
        print("the population file has no rows — run cp5-resolution-pilot.py --json first")
        return 1
    tally: dict[str, int] = {}
    calls: dict[str, int] = {}
    for p in pairs:
        book = p.get("book_id")
        if not book:
            continue
        for tool in (p.get("tools") or []):
            call_args = {"book_id": book, p["arg"]: p["name"]}
            res = resolve_call(tool, dict(call_args), bindings, resolvers, dispatch)
            if not res:
                tally["unbound"] = tally.get("unbound", 0) + 1
                calls["unbound"] = calls.get("unbound", 0) + p["calls"]
                print(f"  UNBOUND      {tool}.{p['arg']} = {p['value']!r}")
                continue
            record = apply_resolutions(call_args, res)
            for r in res:
                tally[r.outcome] = tally.get(r.outcome, 0) + 1
                calls[r.outcome] = calls.get(r.outcome, 0) + p["calls"]
                if r.ok:
                    print(f"  RESOLVED     {p['calls']:>4}x {tool}.{r.param} "
                          f"{r.sent!r} -> {r.resolved}")
                    # The record must keep the NAME: without it a resolved argument and a
                    # model-typed one are the same row and nothing can be measured.
                    assert record["model_sent"][r.param] == r.sent
                    assert call_args[r.param] == r.resolved
                else:
                    print(f"  {r.outcome.upper():<12} {p['calls']:>4}x {tool}.{r.param} "
                          f"{r.sent!r} ({len(r.candidates)} candidate(s))")
                    print(f"       -> {refusal_message([r])[:160]}")
                    assert call_args[r.param] == r.sent, "a refusal must not substitute"

    print(f"\nby (tool,param): {tally}")
    print(f"by CALL volume : {calls}")
    served = sum(calls.values()) or 1
    actionable = calls.get("resolved", 0) + calls.get("ambiguous", 0) + calls.get("no_match", 0)
    print(f"\nevery call reaches a branch: {actionable}/{served} "
          f"({100 * actionable / served:.1f}%) — a substitution or an ACTIONABLE refusal. "
          f"Today every one of them gets `entity_id must be a UUID`.")
    print("🔴 A refusal is still a FAILURE and is recorded as one — the contract may remove a "
          "failure's COST, never its SIGNAL (§3).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
