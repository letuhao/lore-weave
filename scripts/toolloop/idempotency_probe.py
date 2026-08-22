#!/usr/bin/env python3
"""Call a tool TWICE with identical arguments against one fixture, and read the store between.

    python scripts/toolloop/idempotency_probe.py --scenarios scripts/toolloop/scenarios-c1-rerun.json \
        --tool world_map_update_region --args '{"region_id": "{step:2:region.region_id}", "name": "Renamed"}'
    python scripts/toolloop/idempotency_probe.py --spec docs/eval/toolloop/2026-08-14/c1-idem-spec.json

🔴 WHY THIS CANNOT BE MEASURED FROM THE CHAT ARM. Every repeat there gets its OWN fixture — that is
deliberate, and it is what makes a store diff attributable to the run that caused it. But it also
means the second call never sees the first one's result, so idempotency is structurally
unobservable through the runner. Fifteen of cycle 1's twenty outstanding SHIP cases are exactly
this, and no number of repeats would have closed one of them.

WHAT IT ASSERTS, and the interesting answer is not always "identical":

    first call    must succeed and MOVE the store
    second call   must be a clear NO-OP — it may succeed idempotently or refuse, but it must not
                  DOUBLE the effect (two regions where the author asked for one rename) and it
                  must not corrupt what the first call wrote

So the verdict comes from the STORE, not from the tool's own two responses. A tool that returns
`{"ok": true}` twice while writing twice is the failure this exists to catch, and its responses
look identical in both the good and the bad case.

THE FIXTURE IS THE SCENARIO'S OWN. The seed steps are reused verbatim from the scenario file, so
the substrate is the one the tool was measured against — no second definition to drift. Provisioned
and torn down per probe, like every other fixture in this loop.

SAFETY: throwaway only, by construction — `Throwaway` refuses to delete a book it did not name, and
the world sweep is scoped to the id its own `world_create` returned.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "toolloop"))

from provision import Throwaway  # noqa: E402
from store_snapshot import diff as store_diff, snapshot  # noqa: E402
from scripts.eval.tool_liveness.mcp_direct import MCPToolError  # noqa: E402


def _resolve_sql(args: dict, fx) -> dict:
    """Resolve `{sql:<db>:<query>}` to a single scalar, AFTER the fixture is built.

    🔴 A SQL SEED RETURNS NOTHING THE PROBE CAN ADDRESS. `{step:N:key}` reads a value an MCP seed
    step RETURNED — but several fixtures are seeded by raw INSERT (translation, for one, because
    the tool path SPENDS), and an INSERT hands back no id. So the ids those tools need to be
    called twice simply do not exist in the substitution namespace.

    This closes that with one lookup against the fixture's own rows, scoped by the book the
    fixture just created. It is deliberately a SCALAR: anything richer would be a second seeding
    language, and the seeds are already the one definition of the substrate.
    """
    from scripts.eval.tool_liveness import oracle
    out = {}
    for k, v in args.items():
        if isinstance(v, str) and v.startswith("{sql:") and v.endswith("}"):
            _, db, q = v[1:-1].split(":", 2)
            q = q.replace("{book_id}", fx.book_id or "").replace(
                "{chapter_id}", fx.chapter_id or "")
            rows = oracle.db_query(db, q)
            if not rows or not rows[0] or not rows[0][0]:
                raise SystemExit(f"the lookup for {k!r} returned no row: {q}")
            out[k] = rows[0][0]
        else:
            out[k] = v
    return out


def _resolve_pre(args: dict, pre_results: list, fx) -> dict:
    """Resolve `{pre:N:key}` against the Nth PRE-CALL's result.

    🔴 SOME IDS ONLY EXIST ONCE YOU ASK FOR THEM. `kg_triage_resolve` needs a `signature`, and the
    only place a signature comes from is `kg_triage_list` — a READ, run against the fixture the
    seeds have already built. It is not a seed (it creates nothing) and it is not a SQL lookup (the
    signature is computed, not stored under that name), so neither existing resolver reaches it.

    A pre-call is a READ ONLY convenience and is recorded in the result, so a probe can never
    quietly acquire its target by writing one. `{pre:N:key}` also digs one level into a list — the
    triage queue is `{"items": [{"signature": ...}]}` — via `key` paths like `items.0.signature`.
    """
    def dig(obj, path: str):
        for part in path.split("."):
            if isinstance(obj, list):
                obj = obj[int(part)]
            elif isinstance(obj, dict):
                obj = obj.get(part)
            else:
                return None
            if obj is None:
                return None
        return obj

    out = {}
    for k, v in args.items():
        if isinstance(v, str) and v.startswith("{pre:") and v.endswith("}"):
            _, idx, path = v[1:-1].split(":", 2)
            got = dig(pre_results[int(idx)], path)
            if got is None:
                raise SystemExit(
                    f"the pre-call lookup for {k!r} found nothing at {path!r}. "
                    f"pre-call {idx} returned: {json.dumps(pre_results[int(idx)])[:300]}")
            out[k] = got
        else:
            out[k] = v
    return out


def run_one(scenarios: dict, tool: str, args_tpl: dict, pre: list | None = None) -> dict:
    scen = next((s for s in scenarios["scenarios"] if s.get("tool_under_test") == tool), None)
    if scen is None:
        raise SystemExit(f"{tool} is not in that scenarios file")

    fx = Throwaway(f"idem-{tool}")
    out: dict = {"tool": tool}
    try:
        fx.build(scen.get("seed") or [], chapter=True)
        pre_results = []
        for p in (pre or []):
            pre_results.append(fx.mcp.call(p["tool"], fx._substitute(p.get("args") or {})))
        out["pre"] = [{"tool": p["tool"]} for p in (pre or [])]
        args = fx._substitute(args_tpl)          # the same substitution the seeds use
        args = _resolve_sql(args, fx)            # …plus one lookup the seeds cannot provide
        args = _resolve_pre(args, pre_results, fx)
        out["args"] = args

        before = snapshot(fx.book_id, fx.project_id, fx.world_id, fx.chapter_id, fx.user_model_id)
        try:
            out["first"] = ["ok", fx.mcp.call(tool, args)]
        except MCPToolError as e:
            out["first"] = ["refused", str(e)[:200]]
        mid = snapshot(fx.book_id, fx.project_id, fx.world_id, fx.chapter_id, fx.user_model_id)

        try:
            out["second"] = ["ok", fx.mcp.call(tool, args)]
        except MCPToolError as e:
            out["second"] = ["refused", str(e)[:200]]
        after = snapshot(fx.book_id, fx.project_id, fx.world_id, fx.chapter_id, fx.user_model_id)

        out["diff_first"] = store_diff(before, mid)
        out["diff_second"] = store_diff(mid, after)

        # 🔴 THE FIRST VERSION OF THIS VERDICT WAS TOO STRONG AND WOULD HAVE MIS-REPORTED A CLEAN
        # TOOL. world_map_update_region renamed to the same name twice: the row COUNT held at
        # 2 -> 2 and only `latest` (max updated_at) moved. "The second call moved the store again"
        # reads as duplication; what actually happened is the row was re-written in place with
        # identical content. Those are different findings and only one of them is a defect —
        # duplicating what the author asked for once is damage, bumping a timestamp is not.
        #
        # So the verdict reads the two apart. `rows` is the duplication signal; `latest` alone is
        # a touched row, which is worth recording and is not a failure.
        def _rows_changed(d: dict) -> list[str]:
            out_ = []
            for k, v in (d or {}).items():
                b, a2 = (v or {}).get("before") or {}, (v or {}).get("after") or {}
                if isinstance(b, dict) and isinstance(a2, dict) and b.get("rows") != a2.get("rows"):
                    out_.append(f"{k} {b.get('rows')}->{a2.get('rows')}")
            return out_

        dup = _rows_changed(out["diff_second"])
        if dup:
            out["verdict"] = f"🔴 NOT IDEMPOTENT — the second call DUPLICATED: {', '.join(dup)}"
        elif out["diff_second"]:
            out["verdict"] = ("IDEMPOTENT IN EFFECT — no row was added or removed by the second "
                              "call; it re-wrote the same row in place (updated_at moved). Worth "
                              "recording, not a defect.")
        else:
            out["verdict"] = "STRICTLY IDEMPOTENT — the second call touched nothing at all"

        out["first_had_effect"] = bool(out["diff_first"])
        if not out["first_had_effect"]:
            out["verdict"] += ("  ⚠ BUT THE FIRST CALL CHANGED NOTHING EITHER, so this probe "
                               "measured two no-ops and proves nothing about idempotency.")
    finally:
        try:
            out["teardown"] = fx.teardown()
        except Exception as e:  # noqa: BLE001
            out["teardown_error"] = f"{type(e).__name__}: {e}"
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenarios", default="scripts/toolloop/scenarios-c1-rerun.json")
    ap.add_argument("--tool")
    ap.add_argument("--args", help="JSON args, may use {step:N:path} / {book_id} placeholders")
    ap.add_argument("--spec", help="JSON file: [{tool, args}, ...] — many in one pass")
    ap.add_argument("--out")
    a = ap.parse_args()

    scen = json.loads(pathlib.Path(a.scenarios).read_text(encoding="utf-8"))
    if a.spec:
        jobs = json.loads(pathlib.Path(a.spec).read_text(encoding="utf-8"))
    elif a.tool and a.args:
        jobs = [{"tool": a.tool, "args": json.loads(a.args)}]
    else:
        ap.print_help()
        return 2

    results = []
    for j in jobs:
        print(f"\n=== {j['tool']} ===")
        try:
            r = run_one(scen, j["tool"], j["args"], j.get("pre"))
        except Exception as e:  # noqa: BLE001 — one tool's failure must not abort the pass
            r = {"tool": j["tool"], "error": f"{type(e).__name__}: {e}"[:300]}
        results.append(r)
        if "error" in r:
            print("  ERROR:", r["error"])
            continue
        print(f"  args     {json.dumps(r['args'], ensure_ascii=False)[:150]}")
        print(f"  first    {r['first'][0]}: {json.dumps(r['first'][1], ensure_ascii=False)[:150]}")
        print(f"  second   {r['second'][0]}: {json.dumps(r['second'][1], ensure_ascii=False)[:150]}")
        print(f"  diff 1   {json.dumps(r['diff_first'], ensure_ascii=False)[:170]}")
        print(f"  diff 2   {json.dumps(r['diff_second'], ensure_ascii=False)[:170]}")
        print(f"  {r['verdict']}")
    if a.out:
        pathlib.Path(a.out).write_text(json.dumps(results, indent=1, ensure_ascii=False) + "\n",
                                       encoding="utf-8")
        print(f"\nwrote {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
