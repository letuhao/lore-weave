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
import uuid
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
    # Unique per process: some tools cap per-session (memory_remember allows 10/session), so
    # a fixed id accumulates state across runs and eventually trips the cap. A fresh session
    # each run keeps those tools reachable.
    "X-Session-Id": f"tle-sweep-{uuid.uuid4().hex[:8]}",
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
    # the tool's own OUTPUT violates the schema it advertises (settings_get_profile). Only
    # "validating tool output" — NOT a bare "validating root: validating", which also fires
    # on INPUT-arg validation (a caller-fault from OUR bad payload, e.g. a wrong array-item
    # shape). The real settings bug message contains "validating tool output" and is caught.
    r"validating tool output|"
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


# Sentinel: this required field cannot be honestly supplied, so the whole call is unbuildable.
_UNFILLABLE = object()


def _resolve_ref(spec: dict, root: dict) -> dict:
    """Follow a local `#/$defs/Name` (or `#/definitions/Name`) $ref to its definition.

    28 composition tools wrap their real args in a single required field:
        {"properties": {"args": {"$ref": "#/$defs/_MotifCreateArgs"}}, "$defs": {...}}
    The `$defs` FULLY describe the structure, so a `$ref` is *buildable* — it is not a
    reason to refuse. The earlier `fill_args` saw `type: None` on the `$ref` node and gave
    up, leaving 28 tools permanently `executes: null`. A model resolving the schema has the
    `$defs` in hand and can construct the object; so can we. `root` is the top-level schema
    (it carries `$defs`), threaded through every recursion unchanged.
    """
    seen: set[str] = set()
    while isinstance(spec, dict) and "$ref" in spec:
        ref = spec["$ref"]
        if not isinstance(ref, str) or not ref.startswith("#/") or ref in seen:
            return spec if isinstance(spec, dict) else {}
        seen.add(ref)
        node: Any = root
        for part in ref[2:].split("/"):
            if not isinstance(node, dict):
                return {}
            node = node.get(part, {})
        spec = node
    return spec if isinstance(spec, dict) else {}


def _fill_value(key: str, spec: dict, fx: dict, root: dict, depth: int) -> Any:
    """A value for one required field, or `_UNFILLABLE` if we cannot honestly supply it.

    Refusing is the safe move: a tool handed a placeholder where it wanted a real id or an
    existing kind-code fails on lookup, and that failure says nothing about the tool. The
    first sweep learned this the hard way — 10 healthy tools scored "broken" because they
    correctly rejected `"tle-sweep"` as a UUID or a kind code.
    """
    if key in fx and fx[key]:
        return fx[key]
    if key.endswith("_ids") and fx.get(key[:-4] + "_id"):
        return [fx[key[:-4] + "_id"]]
    if spec.get("enum"):
        return spec["enum"][0]
    # An id / uuid / reference-code we have no fixture value for is unguessable.
    if _ID_KEY.search(key) or key in _REFERENCE_KEY or spec.get("format") == "uuid":
        return _UNFILLABLE
    t = spec.get("type")
    # A nested object whose schema fully describes it IS buildable (the composition `args`
    # wrapper). Recurse — but if any of ITS required fields is an unguessable id, the whole
    # object is unbuildable, exactly as a model would find when it tried to construct it.
    if t == "object" or (t is None and spec.get("properties")):
        nested = _build_object(spec, fx, root, depth + 1)
        return _UNFILLABLE if nested is None else nested
    if t == "string":
        return "tle-sweep"
    if t in ("integer", "number"):
        return spec.get("minimum", 1)
    if t == "boolean":
        return False
    return _UNFILLABLE  # arrays of structured items need authored args


def _build_object(schema: dict, fx: dict, root: dict, depth: int = 0) -> dict | None:
    """Build a required-only object from `schema`. None ⇒ a required field is unfillable.

    A schema nested more than a handful deep is not something a mechanical required-only
    sweep should be inventing — bail to `null` (inconclusive), never guess.
    """
    if depth > 5:
        return None
    props = (schema or {}).get("properties") or {}
    required = (schema or {}).get("required") or []
    out: dict[str, Any] = {}

    # OPTIONAL scope keys the fixture can supply. 13 kg_* tools declare `project_id` as
    # OPTIONAL (it normally rides the X-Project-Id envelope) and then refuse with
    # "no project in scope" when neither is present. A required-args-only call therefore
    # never exercised them. Supplying an optional arg we hold is free and honest — it is the
    # same value the envelope would have carried. (Applied at every object level, since the
    # composition `args` wrapper carries the scope key INSIDE the nested object.)
    for key in ("project_id", "book_id"):
        if key in props and key not in required and fx.get(key):
            out[key] = fx[key]

    for key in required:
        spec = _resolve_ref(props.get(key) or {}, root)
        val = _fill_value(key, spec, fx, root, depth)
        if val is _UNFILLABLE:
            return None
        out[key] = val
    return out


def fill_args(schema: dict, fx: dict) -> dict | None:
    """Args for a REQUIRED-only call, from the fixture. None ⇒ cannot build, so DO NOT CALL.

    The top-level schema is also the `$ref` resolution root (it carries `$defs`), so it is
    threaded through the recursion unchanged.
    """
    return _build_object(schema or {}, fx, schema or {}, 0)


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


async def _call_json(session: ClientSession, name: str, args: dict) -> tuple[bool, str, dict]:
    res = await session.call_tool(name, args)
    if getattr(res, "isError", False):
        return False, (res.content[0].text if res.content else "?"), {}
    sc = getattr(res, "structuredContent", None)
    if isinstance(sc, dict):
        return True, "", sc
    if res.content:
        try:
            return True, "", json.loads(res.content[0].text)
        except Exception:
            pass
    return True, "", {}


async def _sweep(targets: list[dict], fx: dict, headers: dict | None = None,
                 authored_fn=None) -> list[dict]:
    """`authored_fn(tool, fx, state) -> dict | None` overrides fill_args per tool.

    `state` accumulates the RESULT of every successful call, so a later tool can consume
    what an earlier one created: `glossary_user_create` mints a kind `code`, and
    `glossary_user_patch` / `_delete` / `_restore` need exactly that code. Without chaining
    those three can never be reached — a fixture cannot invent a row the tool itself is
    supposed to make. Targets are swept in the order given, so a chain must be ordered.
    """
    rows: list[dict] = []
    state: dict[str, Any] = {}
    async with streamablehttp_client(config.AI_GATEWAY_MCP, headers=headers or _HEADERS) as (r, w, _):
        async with ClientSession(r, w) as s:
            await s.initialize()
            for t in targets:
                args = None
                if authored_fn is not None:
                    args = authored_fn(t["name"], fx, state)
                if args is None:
                    args = fill_args(t["schema"], fx)
                if args is None:
                    rows.append({"tool": t["name"], "tier": t["meta"].get("tier") or "ABSENT",
                                 "capability": "SKIP-NO-ARGS", "executes": None,
                                 "why": "required arg needs authored/structured input"})
                    continue
                result: dict = {}
                try:
                    ok, msg, result = await _call_json(s, t["name"], args)
                except BaseExceptionGroup as eg:  # transport blew up, not the tool
                    ok, msg = False, f"transport: {_flatten(eg)}"
                except Exception as e:
                    ok, msg = False, f"transport: {type(e).__name__}: {e}"
                if ok:
                    state[t["name"]] = result
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
    ap.add_argument("--include-user-writes", action="store_true",
                    help="also call user/none-scoped Tier-A tools AS A THROWAWAY USER "
                         "(registers one, sweeps as them, deletes them)")
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
    if len(fx.entities) > 1:
        ids["entity_id2"] = fx.entities[1]["entity_id"]  # a distinct loser for propose_merge
    try:
        proj = MCPDirect().call("kg_project_create", {
            "name": f"TLE-sweep-{fx.run_id}", "project_type": "book", "book_id": fx.book_id})
        ids["project_id"] = proj.get("project_id")
    except Exception as e:
        print(f"  (no kg project: {e}) — project-scoped tools will score inconclusive")
    # Seed a throwaway authoring run so its get/gate/close consumers are reachable at $0.
    from .project_chain import seed_authoring_run, seed_db_fixtures, seed_chain_extras
    seed_authoring_run(ids)
    # Seed rows no $0 MCP creator can mint (a world, a scene, a completed translation) so
    # kg_world_query / book_scene_get / the 5 translation-version tools reach on owned targets.
    seed_db_fixtures(ids)
    # Mint the 2nd-of-a-pair targets (2 KG nodes, a 2nd project with 2 nodes + an archived
    # node + a motif) so the kg node-chain / scene-link / motif-bind / node-restore reach.
    seed_chain_extras(ids)
    print(f"fixture: {ids}")

    # Order the book/project creators before their consumers so a later tool can read the
    # id an earlier one minted (composition_create_work → project_id, plan_propose_spec →
    # run_id, …). Anything not in the chain keeps catalog order and falls back to fill_args.
    from .project_chain import (
        PROJECT_SWEEP_ORDER,
        authored_project_args,
        teardown_composition,
    )
    prank = {name: i for i, name in enumerate(PROJECT_SWEEP_ORDER)}
    targets.sort(key=lambda t: (prank.get(t["name"], len(prank)), t["name"]))

    try:
        rows = asyncio.run(_sweep(
            targets, ids,
            authored_fn=lambda tool, _ids, state: authored_project_args(tool, ids, state)))
        # Phase 3 (WS-D4): hold the WORKFLOW-CRITICAL set to executes ∧ effect on the SAME
        # fixture, before teardown. A critical tool that returns ok but whose effect does
        # not land is scored executes:false (silent success) — the CD4 gate then rejects any
        # workflow referencing it. Appended last so the merge prefers this stronger verdict.
        from .critical import verify as verify_critical
        crit_rows = asyncio.run(verify_critical(ids))
        if crit_rows:
            print("workflow-critical (executes ∧ effect): " + ", ".join(
                f"{r['tool']}={'PASS' if r['effect_verified'] else r['executes']}" for r in crit_rows))
            rows.extend(crit_rows)
    finally:
        # Everything created HERE (outside Fixture.build) must be cleaned HERE — Fixture
        # knows nothing about the kg project or the composition rows, and would leak one of
        # each per sweep. "no probe may touch an id it did not create" cuts both ways.
        from . import oracle
        if ids.get("project_id"):
            pid = str(ids["project_id"]).replace("'", "''")
            try:
                oracle.db_query(config.DOMAIN_DB["knowledge"],
                                f"DELETE FROM knowledge_projects WHERE project_id='{pid}'")
                print(f"teardown: kg project {ids['project_id']} deleted")
            except Exception as e:
                print(f"teardown: FAILED to delete kg project {ids['project_id']}: {e}")
        print(f"teardown: composition {teardown_composition(fx.book_id)}")
        from .project_chain import teardown_db_fixtures
        print(f"teardown: db-fixtures {teardown_db_fixtures(ids)}")
        print(f"teardown: {fx.teardown()}")

    # ── Phase 2: the user/none-scoped Tier-A writes ────────────────────────────────
    # These mutate THE CALLER, so there is no book to hand them — only a throwaway user.
    # That is exactly where `settings_update_profile` hid its output-schema break: the
    # only reason nothing called it is that calling it would have rewritten the real
    # account. Register a user, sweep as them, delete them.
    if args.include_user_writes:
        from .user_fixture import USER_SWEEP_ORDER, UserFixture, authored_user_args

        user_targets = [t for t in tools
                        if t["meta"].get("tier") in ("A", "S")
                        and t["meta"].get("scope") in ("user", "none")
                        and not t["meta"].get("paid")]
        # Some tools consume state minted in PHASE 2 (the throwaway user's credential/model,
        # or a motif) but are Tier R/W, so the A/S filter above excludes them — they would
        # otherwise be swept in phase 1 against the real account, where that state does not
        # exist (SKIP-NO-ARGS → null). Pulling them into phase 2 as the throwaway user is
        # safe (a read returns the user's own rows; a Tier-W mint writes nothing) and their
        # phase-2 result supersedes the phase-1 null in the manifest merge (null → conclusive,
        # never the reverse — no regression).
        by_name = {t["name"]: t for t in tools}
        already = {t["name"] for t in user_targets}
        _PHASE2_EXTRAS = (
            "settings_provider_inventory", "settings_model_delete",          # credential-gated
            "composition_motif_get", "composition_motif_link_list",          # motif reads
            "composition_motif_adopt",                                       # motif token-mint
            "registry_get_skill", "registry_get_workflow",                   # seeded-slug reads
        )
        for extra in _PHASE2_EXTRAS:
            if extra in by_name and extra not in already:
                user_targets.append(by_name[extra])
        # Chains must run in order: create mints the code that patch/delete/restore need.
        rank = {name: i for i, name in enumerate(USER_SWEEP_ORDER)}
        user_targets.sort(key=lambda t: (rank.get(t["name"], len(rank)), t["name"]))

        ufx = UserFixture().build()
        print(f"\nphase 2 — {len(user_targets)} user-scoped writes as throwaway user {ufx.user_id}")
        try:
            user_rows = asyncio.run(_sweep(
                user_targets, {}, headers=ufx.headers(),
                authored_fn=lambda tool, _fx, state: authored_user_args(tool, ufx, state)))
        finally:
            print(f"  teardown: {ufx.teardown()}")
        for r in user_rows:
            r["as_throwaway_user"] = True
        rows.extend(user_rows)

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
