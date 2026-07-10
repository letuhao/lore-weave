"""Deterministic CAPABILITY sweep over the federated catalog (Track D · WS-D3 / ND3).

The insight that makes this cheap: **the CD4 ship gate blocks on `executes`, and `executes`
does not need a model.** `proven` (G1–G4 under a real LLM) does. So we can answer the
question the gate actually asks — *"does this tool work when called correctly?"* — for the
whole catalog, deterministically, with zero LLM turns and zero spend.

    NL probes  → `proven`   (expensive; one model turn each; F5 selection signal)
    THIS sweep → `executes` (cheap; MCP-direct; finds BROKEN tools)

── Safety (why this is allowed to call ~113 real tools) ─────────────────────────────
  Tier R  reads. Safe.
  Tier W  mints a `confirm_token` and writes NOTHING at call time. We never redeem it.
  Tier A  AUTO-COMMITS a write. NOT swept: `settings_update_profile` would mutate the
          real test account, `memory_forget` would delete real rows. Tier-A capability
          needs authored, fixture-scoped args — the P1 grind, not a heuristic.
  paid    never swept. A capability probe must not spend the user's money.
  ABSENT  swept as R, and reported: an untiered tool is a CD1 violation.

── Classification (conservative, and that is the point) ─────────────────────────────
A wrong verdict here is worse than no verdict: `executes: false` BLOCKS the tool from
every workflow and hides it from `tool_list`. So a call that fails for a reason that is
plausibly OUR fault — bad args, missing fixture, no permission, not found — is scored
`null` (unknown), never `false`. Only a failure the caller cannot have caused counts as
broken. `null` never blocks, by construction (see manifest.py / liveness.go).

Usage:
    python -m scripts.eval.tool_liveness.sweep            # dry-run: plan only, no calls
    python -m scripts.eval.tool_liveness.sweep --execute  # call the R+W tools
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from pathlib import Path
from typing import Any

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

from . import config
from .mcp_direct import _flatten

OUT_DIR = Path("docs/eval/tool-liveness")

_HEADERS = {
    "X-Internal-Token": config.INTERNAL_TOKEN,
    "X-User-Id": config.USER_ID,
    "X-Session-Id": "tle-sweep",
}

# Failures that are plausibly the PROBE's fault, not the tool's. Scored `null`, never
# `false` — an `executes: false` BLOCKS the tool from every workflow and hides it from
# `tool_list`, so a wrong verdict here is far worse than no verdict.
#
# Every alternative below was OBSERVED in the first sweep, where a narrower regex scored
# 10 healthy tools as broken: we handed `code="tle-sweep"` to a tool expecting a real kind
# code, and a placeholder string to a tool expecting a UUID. Those are our bugs, not
# theirs. Widen this list rather than let a false positive through.
_CALLER_FAULT = re.compile(
    r"required|must be|invalid|validation|missing|not found|no such|does not exist|"
    r"not configured|forbidden|permission|denied|unauthor|no project in scope|"
    r"only the .* owner|grant|expected|malformed|cannot be empty|at least one|"
    r"badly formed|is not a valid|unknown |no live |pass .* or |not a valid id|"
    r"must provide|provide (a|an|one)|out of range|too (long|short|many)",
    re.I,
)

# A required arg we cannot meaningfully supply. Calling anyway produces a lookup/parse
# failure that says nothing about whether the TOOL works.
_ID_KEY = re.compile(r"(^|_)(id|ids|uuid)$", re.I)
_REFERENCE_KEY = frozenset({
    "code", "kind", "kind_code", "slug", "attr_code", "genre", "genre_code",
    "world_id", "motif_id", "run_id", "job_id", "revision_id", "template_id",
})


def classify(ok: bool, message: str) -> tuple[bool | None, str]:
    """(executes, why). Conservative: only an unambiguous tool failure returns False."""
    if ok:
        return True, "returned successfully"
    if _CALLER_FAULT.search(message or ""):
        return None, "rejected our arguments/context — inconclusive, not a tool failure"
    return False, "failed with an error we did not cause"


def fill_args(schema: dict, fx: dict) -> dict | None:
    """Args for a REQUIRED-only call, from the fixture. None ⇒ cannot build, so DO NOT CALL.

    Refusing to call is the safe move. A tool handed a placeholder where it wanted a real
    id or an existing kind-code fails on lookup, and that failure says nothing about the
    tool. The first sweep learned this the hard way: 10 healthy tools scored "broken"
    because they correctly rejected `"tle-sweep"` as a UUID or a kind code.
    """
    props = (schema or {}).get("properties") or {}
    out: dict[str, Any] = {}
    for key in (schema or {}).get("required") or []:
        spec = props.get(key) or {}
        if key in fx and fx[key]:
            out[key] = fx[key]
            continue
        if key.endswith("_ids") and fx.get(key[:-4] + "_id"):
            out[key] = [fx[key[:-4] + "_id"]]
            continue
        enum = spec.get("enum")
        if enum:
            out[key] = enum[0]
            continue
        # An id / uuid / reference-code we have no fixture value for is unguessable.
        if _ID_KEY.search(key) or key in _REFERENCE_KEY or spec.get("format") == "uuid":
            return None
        t = spec.get("type")
        if t == "string":
            out[key] = "tle-sweep"
        elif t in ("integer", "number"):
            out[key] = spec.get("minimum", 1)
        elif t == "boolean":
            out[key] = False
        else:
            return None  # arrays/objects of structured items need authored args
    return out


async def _list_tools() -> list[dict]:
    async with streamablehttp_client(config.AI_GATEWAY_MCP, headers=_HEADERS) as (r, w, _):
        async with ClientSession(r, w) as s:
            await s.initialize()
            res = await s.list_tools()
            return [
                {"name": t.name, "description": t.description or "",
                 "schema": t.inputSchema or {}, "meta": (getattr(t, "meta", None) or {})}
                for t in res.tools
            ]


async def _call(session: ClientSession, name: str, args: dict) -> tuple[bool, str]:
    res = await session.call_tool(name, args)
    if getattr(res, "isError", False):
        return False, (res.content[0].text if res.content else "?")
    return True, ""


async def _sweep(targets: list[dict], fx: dict) -> list[dict]:
    rows: list[dict] = []
    async with streamablehttp_client(config.AI_GATEWAY_MCP, headers=_HEADERS) as (r, w, _):
        async with ClientSession(r, w) as s:
            await s.initialize()
            for t in targets:
                args = fill_args(t["schema"], fx)
                if args is None:
                    rows.append({"tool": t["name"], "tier": t["meta"].get("tier") or "ABSENT",
                                 "capability": "SKIP-NO-ARGS", "executes": None,
                                 "why": "required arg needs authored/structured input"})
                    continue
                try:
                    ok, msg = await _call(s, t["name"], args)
                except BaseExceptionGroup as eg:  # transport blew up, not the tool
                    ok, msg = False, f"transport: {_flatten(eg)}"
                except Exception as e:
                    ok, msg = False, f"transport: {type(e).__name__}: {e}"
                executes, why = classify(ok, msg)
                rows.append({
                    "tool": t["name"], "tier": t["meta"].get("tier") or "ABSENT",
                    "capability": {True: "PASS", False: "RED", None: "SKIP-INCONCLUSIVE"}[executes],
                    "executes": executes, "why": why,
                    "error": (msg or "")[:300], "args": args,
                })
    return rows


def plan(tools: list[dict]) -> tuple[list[dict], dict[str, int]]:
    """Split the catalog into sweepable / skipped, with the reason for each skip."""
    targets, skipped = [], {"tier_A": 0, "paid": 0}
    for t in tools:
        m = t["meta"]
        if m.get("paid"):
            skipped["paid"] += 1
            continue
        tier = m.get("tier")
        if tier in ("A", "S"):
            skipped["tier_A"] += 1
            continue
        targets.append(t)  # R, W, or ABSENT (swept as R, and reported)
    return targets, skipped


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--execute", action="store_true", help="actually call the R+W tools")
    ap.add_argument("--date", default="sweep", help="output subdirectory name")
    args = ap.parse_args()

    tools = asyncio.run(_list_tools())
    targets, skipped = plan(tools)
    untiered = [t["name"] for t in tools if not t["meta"].get("tier")]

    print(f"catalog {len(tools)} tools · sweeping {len(targets)} (R+W) · "
          f"skipping {skipped['tier_A']} Tier-A/S (auto-commit) + {skipped['paid']} paid")
    if untiered:
        print(f"CD1 VIOLATION — untiered on the wire (silently default to R): {untiered}")
    if not args.execute:
        print("\ndry run. re-run with --execute to call them.")
        return 0

    # A throwaway fixture, torn down after. The sweep must never address an id it did not
    # create — a Tier-W tool mints a delete token against whatever book_id we hand it.
    from .fixtures import Fixture
    from .mcp_direct import MCPDirect

    fx = Fixture().build()
    ids = {"book_id": fx.book_id, "chapter_id": fx.chapter_id}
    if fx.entities:
        ids["entity_id"] = fx.entities[0]["entity_id"]
    try:
        proj = MCPDirect().call("kg_project_create", {
            "name": f"TLE-sweep-{fx.run_id}", "project_type": "book", "book_id": fx.book_id})
        ids["project_id"] = proj.get("project_id")
    except Exception as e:
        print(f"  (no kg project: {e}) — project-scoped tools will score inconclusive")
    print(f"fixture: {ids}")

    try:
        rows = asyncio.run(_sweep(targets, ids))
    finally:
        print(f"teardown: {fx.teardown()}")

    broke = [r for r in rows if r["executes"] is False]
    works = [r for r in rows if r["executes"] is True]
    unk = [r for r in rows if r["executes"] is None]
    print(f"\nexecutes=true  {len(works)}")
    print(f"executes=false {len(broke)}   ← these will be BLOCKED by the CD4 gate")
    print(f"executes=null  {len(unk)}   (inconclusive — never blocks)")
    for r in broke:
        print(f"  BROKEN {r['tool']:<38} {r['error'][:110]}")

    out = OUT_DIR / args.date
    out.mkdir(parents=True, exist_ok=True)
    (out / "sweep.json").write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nwrote {out / 'sweep.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
