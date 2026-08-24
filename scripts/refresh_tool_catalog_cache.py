#!/usr/bin/env python
"""Regenerate `contracts/tool-catalog-cache.json` from the LIVE federated catalogue.

🔴 WHY THIS EXISTS. Five instruments read that cache — `lint_duplicate_synonyms.py`,
`lint_superseded_synonyms.py`, `lint_synonym_spelling_variants.py`,
`toolloop/answerability_probe.py` and `test_a_measured_turn_reaches_its_tool_gate.py` — and
**nothing regenerated it.** It carried no timestamp and named no generator, so every one of them
silently measured whatever the catalogue looked like the last time somebody made the file by hand.

Caught 2026-08-25: a duplicate synonym was de-duplicated in two services, deployed, and verified
gone from the live wire — and the lint still reported the tie, because it was reading the
snapshot. An instrument that measures the past reports a fixed defect as open and, worse, would
report a NEW one as absent.

Shape matters: the cache is MCP-shaped (`meta`), while `answerable_tools` reads the OpenAI shape
(`function._meta`). The readers convert. This writes the MCP shape the readers expect.

Usage:
    python scripts/refresh_tool_catalog_cache.py            # rewrite the cache
    python scripts/refresh_tool_catalog_cache.py --check    # exit 1 if it is STALE, write nothing
"""
from __future__ import annotations

import argparse
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
CACHE = ROOT / "contracts" / "tool-catalog-cache.json"
HARNESS_USER = "019d5e3c-7cc5-7e6a-8b27-1344e148bf7c"

FETCH = f'''
import asyncio, json
from app.client.knowledge_client import get_knowledge_client
async def main():
    live = await get_knowledge_client().get_tool_definitions(user_id="{HARNESS_USER}")
    out = {{}}
    for x in live:
        fn = x.get("function") or {{}}
        name = fn.get("name")
        if not name:
            continue
        out[name] = {{
            "description": fn.get("description") or "",
            "inputSchema": fn.get("parameters") or {{}},
            "meta": fn.get("_meta") or {{}},
        }}
    print(json.dumps(out, ensure_ascii=False, sort_keys=True))
asyncio.run(main())
'''


def fetch_live() -> dict:
    r = subprocess.run(["docker", "exec", "-i", "infra-chat-service-1", "python", "-c", FETCH],
                       capture_output=True, text=True)
    line = next((ln for ln in reversed(r.stdout.splitlines()) if ln.startswith("{")), None)
    if not line:
        raise SystemExit(f"could not read the live catalogue:\n{r.stderr[-600:]}")
    return json.loads(line)


def main() -> int:
    a = argparse.ArgumentParser()
    a.add_argument("--check", action="store_true",
                   help="report staleness and exit 1; do not write")
    args = a.parse_args()

    live = fetch_live()
    old = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}

    added = sorted(set(live) - set(old))
    removed = sorted(set(old) - set(live))
    changed = sorted(n for n in (set(live) & set(old)) if live[n] != old[n])

    print(f"live catalogue : {len(live)} tools")
    print(f"cache on disk  : {len(old)} tools")
    print(f"  added   : {len(added)} {added[:6]}")
    print(f"  removed : {len(removed)} {removed[:6]}")
    print(f"  changed : {len(changed)} {changed[:6]}")

    stale = bool(added or removed or changed)
    if args.check:
        print("\nSTALE" if stale else "\nup to date")
        return 1 if stale else 0

    CACHE.write_text(json.dumps(live, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
                     encoding="utf-8")
    print(f"\nwrote {CACHE.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
