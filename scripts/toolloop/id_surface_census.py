#!/usr/bin/env python3
"""DQ-T76 (f) census: every LIVE tool taking an *_id / *_ref argument, and what supplies it.

THE RULING (owner 2026-09-01) requires the plan to contain "a CENSUS: every LIVE tool taking an
*_id/*_ref argument, split by whether a name-equivalent entry point already exists" -- and to be
derived rather than typed, because a hand-listed census of 199 tools goes stale the first time
anyone adds a tool.

WHAT COUNTS AS A SUPPLIER is measured from what results actually RETURN, not from what tools
declare: a declared output field is a promise, and the question is what came back. Same rule the
2026-09-01 supply census used.

DEPRECATED TOOLS ARE EXCLUDED. They are dropped from every wire whatever they declare, so
migrating them is effort on dead code.
"""
from __future__ import annotations

import argparse
import collections
import glob
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
CATALOG = ROOT / "contracts" / "tool-catalog-cache.json"
UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
                     r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")

#: Ids the RUNTIME injects from the turn envelope. Not the model's to supply, so not this
#: migration's subject -- `_inject_context_ids` already owns them.
CONTEXT_IDS = frozenset({"book_id", "chapter_id", "project_id"})


def live_tools() -> dict:
    cat = json.loads(CATALOG.read_text(encoding="utf-8"))
    return {k: v for k, v in cat.items()
            if isinstance(v, dict) and (v.get("meta") or {}).get("visibility") != "legacy"}


def id_args(tool: dict) -> list[tuple[str, bool]]:
    """(argument name, is_required) for every *_id / *_ref property."""
    schema = tool.get("inputSchema") or {}
    req = set(schema.get("required") or [])
    return [(k, k in req) for k in (schema.get("properties") or {})
            if k.endswith("_id") or k.endswith("_ref")]


def observed_suppliers() -> dict[str, collections.Counter]:
    """arg name -> Counter(tool that RETURNED a value under that key, in an ok result)."""
    out: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)

    def walk(node, tool, depth=0):
        if depth > 6:
            return
        if isinstance(node, dict):
            for k, v in node.items():
                if isinstance(v, str) and (k.endswith("_id") or k.endswith("_ref")) \
                        and UUID_RE.match(v):
                    out[k][tool] += 1
                elif isinstance(v, (dict, list)):
                    walk(v, tool, depth + 1)
        elif isinstance(node, list):
            for v in node:
                walk(v, tool, depth + 1)

    for path in glob.glob(str(ROOT / "docs" / "eval" / "toolloop" / "*" / "*-raw.json")):
        try:
            recs = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(recs, list):
            continue
        for r in recs:
            if not isinstance(r, dict):
                continue
            names = {c.get("toolCallId"): c.get("toolCallName")
                     for c in (r.get("tool_calls") or [])
                     if isinstance(c, dict) and c.get("type") == "TOOL_CALL_START"}
            for res in (r.get("results") or []):
                content = res.get("content") or ""
                if '"ok": true' not in content and '"ok":true' not in content:
                    continue
                try:
                    payload = json.loads(content)
                except Exception:
                    continue
                walk(payload, names.get(res.get("id")) or "?")
    return out


def name_entry_points(tools: dict) -> set[str]:
    """Arguments for which a NAME-based entry point plausibly exists already.

    Judged from declared synonyms and descriptions mentioning a name/title lookup -- a lead for
    the plan, deliberately NOT presented as a finding: whether a given resolver truly covers an
    argument is a per-tool question the migration answers, not a regex.
    """
    hits = set()
    for name, t in tools.items():
        blob = (t.get("description") or "").lower()
        if "by name" in blob or "name or alias" in blob or "resolve" in blob and "name" in blob:
            for a, _ in id_args(t):
                hits.add(a)
    return hits


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    tools = live_tools()
    sup = observed_suppliers()
    named = name_entry_points(tools)

    per_arg: dict[str, dict] = collections.defaultdict(
        lambda: {"tools": set(), "required_in": set()})
    for tname, t in tools.items():
        for arg, req in id_args(t):
            per_arg[arg]["tools"].add(tname)
            if req:
                per_arg[arg]["required_in"].add(tname)

    rows = []
    for arg, info in per_arg.items():
        rows.append({
            "arg": arg,
            "context_id": arg in CONTEXT_IDS,
            "consumers": len(info["tools"]),
            "required_in": len(info["required_in"]),
            "observed_suppliers": len(sup.get(arg) or {}),
            "supplier_names": sorted((sup.get(arg) or {}).keys())[:4],
            "name_entry_hint": arg in named,
        })
    rows.sort(key=lambda r: (r["context_id"], -r["required_in"], -r["consumers"]))

    if a.json:
        print(json.dumps(rows, indent=1))
        return 0

    tools_with = {t for t in tools if id_args(tools[t])}
    print(f"LIVE tools: {len(tools)}   taking at least one *_id/*_ref: {len(tools_with)}")
    print(f"distinct id arguments: {len(rows)}\n")
    print(f"{'argument':<26}{'used by':>8}{'required':>9}{'suppliers':>10}  name?")
    for r in rows:
        if r["context_id"]:
            continue
        print(f"{r['arg']:<26}{r['consumers']:>8}{r['required_in']:>9}"
              f"{r['observed_suppliers']:>10}  {'yes' if r['name_entry_hint'] else '-'}")
    print("\nCONTEXT IDS (runtime-injected, NOT this migration's subject):")
    for r in rows:
        if r["context_id"]:
            print(f"   {r['arg']:<20} used by {r['consumers']}, required in {r['required_in']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
