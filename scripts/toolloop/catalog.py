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


class SurfaceRegressed(RuntimeError):
    """The live catalogue declares LESS than the cache it is about to replace."""


def surface_regressions(old: dict, new: dict) -> dict[str, list[str]]:
    """{tool: what it lost}. Only ever reports losses — a tool GAINING synonyms is progress.

    A tool that vanishes entirely is deliberately NOT reported here: providers legitimately
    retire tools, and the deprecation sweep already owns that number. What this catches is a
    tool that is still advertised while having QUIETLY stopped declaring how to reach it.
    """
    lost: dict[str, list[str]] = {}
    for name, was in old.items():
        now = new.get(name)
        if now is None:
            continue
        gone = []
        if synonyms(name, old) and not synonyms(name, new):
            gone.append("synonyms")
        if (was.get("description") or "").strip() and not (now.get("description") or "").strip():
            gone.append("description")
        was_req = set(((was.get("inputSchema") or {}).get("properties") or {}))
        now_req = set(((now.get("inputSchema") or {}).get("properties") or {}))
        if was_req and not now_req:
            gone.append("inputSchema.properties")
        if gone:
            lost[name] = gone
    return lost


def _refresh_now(allow_regression: bool = False) -> dict:
    data = asyncio.run(_fetch())
    if CACHE.exists() and not allow_regression:
        try:
            previous = json.loads(CACHE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            previous = {}
        lost = surface_regressions(previous, data)
        if lost:
            raise SurfaceRegressed(_regression_report(lost))
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    # 🔴 THE FORMAT MUST MATCH THE COMMITTED FILE OR EVERY REFRESH IS AN UNREVIEWABLE DIFF.
    # This wrote `indent=1` with the default `ensure_ascii=True` while the checked-in cache is
    # `indent=2` with raw UTF-8, so a refresh that ADDED ONE TOOL produced 24788 insertions and
    # 24757 deletions — a diff in which a real change (a tool gained a required argument, a
    # description was reworded) cannot be seen at all. Measured 2026-08-25 after adding
    # composition_reference_list: semantically +1 tool and 4 server-side edits, buried in 49k
    # lines of reformatting.
    CACHE.write_text(
        json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8")
    return data


def _regression_report(lost: dict[str, list[str]]) -> str:
    by_provider: dict[str, int] = {}
    for name in lost:
        by_provider[name.split("_")[0]] = by_provider.get(name.split("_")[0], 0) + 1
    lines = [
        f"REFUSING to cache: {len(lost)} tool(s) declare LESS than the cached surface.",
        "",
        "A whole provider losing its synonyms at once is a DEPLOYMENT regression, not a code",
        "change — an image built from a stale context, serving tools whose declarations were",
        "committed weeks ago. Caching it would make the degraded surface this loop's ground",
        "truth, and every batch measured afterwards would be measuring the wrong platform.",
        "",
        "by provider prefix: " + ", ".join(f"{k}={v}" for k, v in sorted(by_provider.items())),
        "",
    ]
    lines += [f"  {n}: lost {', '.join(w)}" for n, w in sorted(lost.items())[:30]]
    if len(lost) > 30:
        lines.append(f"  ... and {len(lost) - 30} more")
    lines += [
        "",
        "CHECK THE DEPLOYED IMAGE AGAINST SOURCE before doing anything else, e.g.",
        "  docker exec <svc> md5sum /app/app/mcp/server.py   # vs the file in git",
        "",
        "MEASURED CAUSE, twice on 2026-08-21 (knowledge-service, the same 26 tools both times):",
        "a POISONED BUILD-CACHE LAYER. `docker compose build <svc>` reused a cached COPY layer",
        "holding an eleven-commit-old tree, so the rebuilt IMAGE TAG was stale while every health",
        "check stayed green. The second occurrence was triggered by `docker compose up -d",
        "--force-recreate <OTHER-service>`, which implicitly rebuilt this one and reused the same",
        "bad layer. `--no-cache` produced an image md5-matching source, and a normal cached build",
        "then stayed correct. So:",
        "  docker compose build --no-cache <svc> && docker compose up -d --force-recreate <svc>",
        "and verify by CONTENT (md5 per file), never by the symbol you just added.",
        "If the loss is genuinely intended, re-run with --allow-regression.",
    ]
    return chr(10).join(lines)


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
    ap.add_argument("--allow-regression", action="store_true",
                    help="cache even if tools lost synonyms/description (see the refusal text)")
    ap.add_argument("--show")
    ap.add_argument("--synonyms")
    ap.add_argument("--audit-synonyms", action="store_true",
                    help="how many tools declare synonyms, and where they keep them")
    a = ap.parse_args()

    if a.refresh:
        try:
            cat = _refresh_now(allow_regression=a.allow_regression)
        except SurfaceRegressed as exc:
            print(str(exc), file=sys.stderr)
            return 2
        print(f"cached {len(cat)} tools -> {CACHE}")
    else:
        cat = load()
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
