#!/usr/bin/env python
"""The federated tool catalogue, as the model actually receives it — dumped and cached.

Two things in this loop need it, and both were being done by hand:

  1. **Argument shapes.** "Read the tool schema before the first call" is an anti-drift rule
     because five argument names guessed from the tool's NAME were wrong in a single session,
     and each wrong guess produced a scenario failure that looked exactly like a defect. The
     schema is the only authority; the name is a hint at best.

  2. **Scenario prompts.** A tool's `_meta.synonyms` is the tool's OWN claim about what a user
     would say to reach it. Generating the prompt from that claim is what turns "the model
     didn't call it" from an argument into a defect: the tool declared it answers this phrasing.
     A prompt I invent proves only that I can phrase things the model likes.

Cached to `contracts/tool-catalog-cache.json` because tools/list is a federation round trip
across ten providers and the batch loop reads it constantly. `--refresh` re-fetches.

Usage:
    python scripts/toolloop/catalog.py --refresh
    python scripts/toolloop/catalog.py --show composition_list_outline
    python scripts/toolloop/catalog.py --synonyms composition_list_outline
"""
from __future__ import annotations

import argparse
import asyncio
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from mcp import ClientSession  # noqa: E402
from mcp.client.streamable_http import streamablehttp_client  # noqa: E402

from scripts.eval.tool_liveness import config  # noqa: E402

CACHE = ROOT / "contracts" / "tool-catalog-cache.json"

_HEADERS = {
    "X-Internal-Token": config.INTERNAL_TOKEN,
    "X-User-Id": config.USER_ID,
    "X-Session-Id": "toolloop-catalog",
}


async def _fetch() -> dict:
    out: dict = {}
    async with streamablehttp_client(config.AI_GATEWAY_MCP, headers=_HEADERS) as (r, w, _):
        async with ClientSession(r, w) as s:
            await s.initialize()
            listing = await s.list_tools()
            for t in listing.tools:
                out[t.name] = {
                    "description": t.description or "",
                    "inputSchema": t.inputSchema or {},
                    # `_meta` is where the surfacing layer keeps synonyms/domain/tier. It rides
                    # on the tool object rather than the schema, and is dropped by anything that
                    # only reads inputSchema — which is how "the tool declares no synonyms" got
                    # believed about tools that declare plenty.
                    "meta": getattr(t, "meta", None) or {},
                }
    return out


def load(refresh: bool = False) -> dict:
    if CACHE.exists() and not refresh:
        return json.loads(CACHE.read_text(encoding="utf-8"))
    data = _refresh_now()
    return data


def _refresh_now() -> dict:
    data = asyncio.run(_fetch())
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(data, indent=1, sort_keys=True), encoding="utf-8")
    return data


def required_args(name: str, cat: dict | None = None) -> list[str]:
    cat = cat if cat is not None else load()
    return list((cat.get(name, {}).get("inputSchema") or {}).get("required") or [])


def synonyms(name: str, cat: dict | None = None) -> list[str]:
    """What the tool itself says a user would ask to reach it.

    Looked up in several places because the key has moved: the surfacing layer reads
    `_meta.synonyms`, some providers nest it under `_meta.loreweave`, and a few tools carry it
    on the schema. Returning [] silently for a tool that DOES declare them is the failure this
    guards against — R1's answerability pass is blind to a tool whose synonyms it cannot see,
    and "87 of 315 declare none" was measured with a lookup that only checked one of these.
    """
    cat = cat if cat is not None else load()
    entry = cat.get(name) or {}
    meta = entry.get("meta") or {}
    for holder in (meta, meta.get("loreweave") or {}, entry.get("inputSchema") or {}):
        if isinstance(holder, dict):
            v = holder.get("synonyms")
            if isinstance(v, list) and v:
                return [str(x) for x in v]
    return []


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--show")
    ap.add_argument("--synonyms")
    ap.add_argument("--audit-synonyms", action="store_true",
                    help="how many tools declare synonyms, and where they keep them")
    a = ap.parse_args()

    cat = load(refresh=a.refresh)
    if a.refresh:
        print(f"cached {len(cat)} tools -> {CACHE}")
    if a.show:
        print(json.dumps(cat.get(a.show, {"__missing__": a.show}), indent=1))
    if a.synonyms:
        print(json.dumps(synonyms(a.synonyms, cat), indent=1))
    if a.audit_synonyms:
        have = [n for n in cat if synonyms(n, cat)]
        print(f"{len(have)} of {len(cat)} tools declare synonyms; "
              f"{len(cat) - len(have)} declare none")
        keys = {}
        for n, e in cat.items():
            for k in (e.get("meta") or {}):
                keys[k] = keys.get(k, 0) + 1
        print("meta keys seen:", json.dumps(keys, indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
