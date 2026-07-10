"""Deterministic CAPABILITY sweep over the federated catalog (Track D · WS-D3 / ND3).

The insight that makes this cheap: **the CD4 ship gate blocks on `executes`, and `executes`
does not need a model.** `proven` (G1–G4 under a real LLM) does. So we can answer the
question the gate actually asks — *"does this tool work when called correctly?"* — for the
whole catalog, deterministically, with zero LLM turns and zero spend.

    NL probes  → `proven`   (expensive; one model turn each; F5 selection signal)
    THIS sweep → `executes` (cheap; MCP-direct; finds BROKEN tools)

── Safety: `_meta.scope` decides what may be called ─────────────────────────────────
  Tier R  reads. Always swept.
  Tier W  mints a `confirm_token` and writes NOTHING at call time. We never redeem it.
  Tier A  AUTO-COMMITS. Swept only with --include-writes, and only when scoped
          book/project — those can touch nothing but the throwaway fixture we hand them.
          A user/none-scoped write (`settings_update_profile`, `memory_forget`) is NEVER
          swept: it would rewrite the real account or delete real rows.
  paid    never swept. A capability probe must not spend the user's money.
  ABSENT  swept as R, and reported: an untiered tool is a CD1 violation.

── Classification: broken only on POSITIVE evidence ─────────────────────────────────
`executes: false` BLOCKS the tool from every workflow and hides it from `tool_list`; a
missed detection merely leaves it `null`, which blocks nothing. The costs are wildly
asymmetric, so the default is `null`.

We therefore enumerate the bounded, language-level vocabulary of *tool* failure —
exceptions, SQL errors, panics, output-schema violations — and attribute everything else
to ourselves. The inverse (a regex for *caller* fault, defaulting to broken) was tried and
is unbounded: it needed widening four times, and twice laundered a real bug. See
`classify`.

Usage:
    python -m scripts.eval.tool_liveness.sweep                        # dry run: the plan
    python -m scripts.eval.tool_liveness.sweep --execute              # R + W
    python -m scripts.eval.tool_liveness.sweep --execute --include-writes  # + fixture-scoped A
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

# POSITIVE evidence that the TOOL is broken — the only thing that scores `executes: false`.
#
# This is a bounded, language-level vocabulary: a tool that raises a Python TypeError, runs
# SQL against a column that does not exist, panics, or emits output its own declared schema
# rejects, is broken on ANY input. Contrast caller-fault prose ("no adopted ontology", "no
# fields to update", "unknown kind"), which is unbounded — every domain invents its own —
# and which no regex can enumerate. Enumerate the small set; default the rest to `null`.
#
# Every entry below is a real failure this sweep found:
#   run_read() missing 1 required positional argument: 'user_id'   Python TypeError
#   column ct.model_source does not exist                          SQL schema drift
#   validating tool output: ... want one of "null, array"          declared-schema violation
_INTERNAL_FAULT = re.compile(
    # Python
    r"missing \d+ required positional argument|"
    r"\b(TypeError|AttributeError|KeyError|IndexError|NameError)\b|ValueError: |"
    r"'NoneType' object|Traceback \(most recent call last\)|"
    # SQL / schema drift
    r"column .* does not exist|relation .* does not exist|"
    r"syntax error at or near|undefined column|"
    # Go
    r"panic:|nil pointer dereference|index out of range \[|"
    # the tool's own output violates the schema it advertises (settings_get_profile)
    r"validating tool output|validating root: validating|"
    # unhandled server-side failure
    r"internal server error|unhandled exception",
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
    """(executes, why). **Broken only on POSITIVE evidence. Never by exclusion.**

    The earlier design was "broken unless the message matches a caller-fault regex", and it
    was wrong in *shape*, not merely in content. I widened that regex four times:

      badly formed hexadecimal UUID string      ← our placeholder where a UUID was wanted
      unknown kind: tle-sweep                   ← our placeholder kind-code
      no fields to update                       ← our required-args-only call is a no-op
      this project has no embedding model configured   ← our fixture lacks setup

    Each widening killed a false positive and edged closer to swallowing a true one — and
    twice it did, laundering two real bugs into "inconclusive":

      run_read() missing 1 required positional argument: 'user_id'   (Python TypeError)
      column ct.model_source does not exist                          (SQL schema drift)

    The asymmetry is the point. *Caller*-fault prose is unbounded — every domain invents its
    own vocabulary for "you didn't set this up". *Tool*-fault has a small, recognizable,
    language-level vocabulary: exceptions, SQL errors, panics, output-schema violations. So
    enumerate the bounded set and default the rest to `null`.

    An `executes: false` BLOCKS the tool from every workflow and hides it from `tool_list`.
    A missed detection merely leaves it `null`, which blocks nothing. The costs are wildly
    asymmetric, so the default must be `null`.
    """
    if ok:
        return True, "returned successfully"
    msg = message or ""
    if _INTERNAL_FAULT.search(msg):
        return False, "leaked an internal error (exception / SQL / panic / bad output schema)"
    return None, "rejected the call for a reason we cannot attribute to the tool"


def fill_args(schema: dict, fx: dict) -> dict | None:
    """Args for a REQUIRED-only call, from the fixture. None ⇒ cannot build, so DO NOT CALL.

    Refusing to call is the safe move. A tool handed a placeholder where it wanted a real
    id or an existing kind-code fails on lookup, and that failure says nothing about the
    tool. The first sweep learned this the hard way: 10 healthy tools scored "broken"
    because they correctly rejected `"tle-sweep"` as a UUID or a kind code.
    """
    props = (schema or {}).get("properties") or {}
    out: dict[str, Any] = {}

    # OPTIONAL scope keys the fixture can supply. 13 kg_* tools declare `project_id` as
    # OPTIONAL (it normally rides the X-Project-Id envelope) and then refuse with
    # "no project in scope" when neither is present. A required-args-only call therefore
    # never exercised them at all. Supplying an optional arg we hold is free and honest —
    # it is the same value the envelope would have carried.
    for key in ("project_id", "book_id"):
        if key in props and key not in (schema.get("required") or []) and fx.get(key):
            out[key] = fx[key]

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


def plan(tools: list[dict], include_writes: bool = False) -> tuple[list[dict], dict[str, int]]:
    """Split the catalog into sweepable / skipped, with the reason for each skip.

    `_meta.scope` is what makes Tier-A probing possible at all, and it is the first time
    that field earns its keep — until now it was a validated declaration nobody consumed.

      scope book|project  the tool can only touch the THROWAWAY FIXTURE we hand it, which
                          is deleted afterwards. Safe to call, with --include-writes.
      scope user|none     the tool mutates the real account or global state
                          (settings_update_profile rewrites the profile; memory_forget
                          deletes rows). NEVER swept.

    This matters because the twin of the one bug this sweep found — settings_update_profile
    — is itself Tier A. Tier-A tools WRITE, they were never called by anything, and that is
    exactly where the next output-schema break hides.
    """
    targets, skipped = [], {"tier_A_unsafe_scope": 0, "tier_A_writes": 0, "paid": 0}
    for t in tools:
        m = t["meta"]
        if m.get("paid"):
            skipped["paid"] += 1
            continue
        tier, scope = m.get("tier"), m.get("scope")
        if tier in ("A", "S"):
            if scope not in ("book", "project"):
                skipped["tier_A_unsafe_scope"] += 1
                continue
            if not include_writes:
                skipped["tier_A_writes"] += 1
                continue
        targets.append(t)  # R, W, ABSENT (swept as R + reported), or fixture-scoped A
    return targets, skipped


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--execute", action="store_true", help="actually call the tools")
    ap.add_argument("--include-writes", action="store_true",
                    help="also call Tier-A tools scoped to book/project (fixture-only writes)")
    ap.add_argument("--date", default="sweep", help="output subdirectory name")
    args = ap.parse_args()

    tools = asyncio.run(_list_tools())
    targets, skipped = plan(tools, include_writes=args.include_writes)
    untiered = [t["name"] for t in tools if not t["meta"].get("tier")]

    kinds = "R+W+fixture-scoped A" if args.include_writes else "R+W"
    print(f"catalog {len(tools)} tools · sweeping {len(targets)} ({kinds}) · skipping "
          f"{skipped['tier_A_unsafe_scope']} Tier-A user/global-scoped (would mutate real data)"
          + (f" + {skipped['tier_A_writes']} Tier-A writes (pass --include-writes)"
             if skipped["tier_A_writes"] else "")
          + f" + {skipped['paid']} paid")
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
        # The kg project is created HERE, not by Fixture.build(), so Fixture.teardown()
        # knows nothing about it and would leak one row per sweep. Clean up what we made:
        # "no probe may touch an id it did not create" cuts both ways.
        if ids.get("project_id"):
            from . import oracle
            pid = str(ids["project_id"]).replace("'", "''")
            try:
                oracle.db_query(config.DOMAIN_DB["knowledge"],
                                f"DELETE FROM knowledge_projects WHERE project_id='{pid}'")
                print(f"teardown: kg project {ids['project_id']} deleted")
            except Exception as e:
                print(f"teardown: FAILED to delete kg project {ids['project_id']}: {e}")
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
