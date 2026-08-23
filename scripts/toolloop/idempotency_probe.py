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

#: Tables whose "delete" is a SOFT archive, so a row COUNT cannot tell replacement from duplication.
#: Derived from the stores this loop has measured; add a table here the moment a probe reports a
#: bare DUPLICATED for a tool whose description says it archives.
_SOFT_ARCHIVING_TABLES = ("outline_node", "structure_node", "arc_template", "motif",
                          "composition_work", "glossary_entities")

import httpx  # noqa: E402 — used by _redeem_if_gated

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from eval.tool_liveness import config as _tlc  # noqa: E402
from eval.tool_liveness.confirm import domain_of as _domain_of  # noqa: E402
_DOMAIN_BASE = _tlc.DOMAIN_BASE
_INTERNAL_TOKEN = _tlc.INTERNAL_TOKEN
_USER_ID = _tlc.USER_ID

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


def _redeem_if_gated(result, out: dict, slot: str) -> None:
    """Redeem a confirm_token so a CONFIRM-GATED tool's write actually happens.

    🔴 WITHOUT THIS THE PROBE CANNOT ASK THE QUESTION AT ALL. A Tier-W tool's call only MINTS a
    token and writes NOTHING until it is redeemed, so both store diffs come back empty however the
    tool behaves and the guard below correctly reports "two no-ops ... proves nothing". Measured
    2026-08-23 on composition_decompile_arcs, whose own scenario asks "decompiling a book that
    ALREADY has an arc layer must not silently duplicate it" — a question that can only be asked
    AFTER a first confirmation.

    Same route the seeds already use: POST /v1/{domain}/actions/confirm?token=…, domain taken from
    the tool-name prefix. Best-effort and RECORDED either way: a redemption that fails is written
    into the result rather than swallowed, because a silent failure here would look exactly like a
    tool that wrote nothing.
    """
    if not isinstance(result, dict):
        return
    token = result.get("confirm_token")
    if not isinstance(token, str) or not token:
        return
    # 🔴 THE PREFIX IS NOT THE DOMAIN. `kg_*` lives in `knowledge` and `plan_*` in `composition`,
    # so a bare split would have looked up a base url for "kg" and found none. Reuse the mapping
    # the liveness kit already keeps, which is itself a mirror of the platform's own `_domain_of` —
    # a second copy here would be a third place for the same table to drift.
    domain = _domain_of(out["tool"])
    base = _DOMAIN_BASE.get(domain)
    if not base:
        out.setdefault("confirm", {})[slot] = f"no base url for domain {domain!r}"
        return
    # 🔴 TWO CONFIRM CONVENTIONS ON ONE PLATFORM, measured 2026-08-23:
    #   composition/book/translation : POST /v1/{domain}/actions/confirm?token=…   (query param)
    #   knowledge (kg_*)             : POST /v1/kg/actions/confirm {"confirm_token": …}  (body)
    # and note the PATH segment is `kg`, not the domain name `knowledge`. Redeeming a kg token at
    # /v1/knowledge/actions/confirm returns 404 — which is what this probe did until the recorded
    # status made it visible. `scripts/eval/tool_liveness/confirm.py` builds exactly that URL, so
    # the same 404 is waiting there for every kg_* tool.
    #
    # Both shapes are tried and the one that answered is recorded, so a future reader sees WHICH
    # convention a service actually uses rather than inferring it from a name.
    seg = "kg" if domain == "knowledge" else domain
    attempts = (
        (f"{base}/v1/{seg}/actions/confirm", {"params": {"token": token}}),
        (f"{base}/v1/{seg}/actions/confirm", {"json": {"confirm_token": token}}),
    )
    # 🔴 RECORD EVERY ATTEMPT, NOT THE LAST. Keeping only `last` hid the answer: the QUERY attempt
    # returned 400 with the real reason and the BODY attempt then returned a meaningless 422 (no
    # token where the route wants one), so the recorded value said "422 body" and I went looking for
    # a validation problem that did not exist. The failing shape a caller happens to try last is not
    # the diagnosis.
    hdr = {"X-Internal-Token": _INTERNAL_TOKEN, "X-User-Id": _USER_ID}
    tried = []
    for url, kw in attempts:
        shape = "query" if "params" in kw else "body"
        try:
            r = httpx.post(url, headers=hdr, timeout=180, **kw)
        except Exception as e:  # noqa: BLE001 — recorded, never swallowed
            tried.append(f"{shape}: {type(e).__name__}: {e}")
            continue
        body = ""
        if r.status_code not in (200, 201, 202, 204):
            body = f" {str(r.text)[:160]}"
        tried.append(f"{shape}: {r.status_code}{body}")
        if r.status_code in (200, 201, 202, 204):
            break
    out.setdefault("confirm", {})[slot] = tried


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
            _r1 = fx.mcp.call(tool, args)
            out["first"] = ["ok", _r1]
            _redeem_if_gated(_r1, out, "first")
        except MCPToolError as e:
            out["first"] = ["refused", str(e)[:200]]
        mid = snapshot(fx.book_id, fx.project_id, fx.world_id, fx.chapter_id, fx.user_model_id)

        try:
            _r2 = fx.mcp.call(tool, args)
            out["second"] = ["ok", _r2]
            _redeem_if_gated(_r2, out, "second")
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

        # 🔴 A GROWN TABLE IS NOT PROOF OF A DUPLICATE. Measured 2026-08-23 on
        # composition_motif_bind_edit: the second bind ARCHIVED the prior scenes and wrote
        # replacements, exactly as its description promises, and this verdict called it
        # "NOT IDEMPOTENT — the second call DUPLICATED: outline_node 3->5". The rows grew because
        # the archive is SOFT and deliberately preserves the author's prose. The count is the
        # SYMPTOM; the lifecycle column is the diagnosis, and it was already sitting in the store.
        #
        # So a growth on a table that carries a lifecycle column is now a QUESTION rather than a
        # verdict, and the check that would settle it is named in the output. It is deliberately
        # NOT auto-resolved: this probe reads counts, and teaching it to read `is_archived` per
        # table is a bigger change than the one instance justifies — but a reader must never again
        # see a bare "DUPLICATED" for a tool that archived correctly.
        dup = _rows_changed(out["diff_second"])
        soft = [d for d in dup if any(t in d for t in _SOFT_ARCHIVING_TABLES)]
        if dup and soft and len(soft) == len(dup):
            out["verdict"] = (
                f"⚠ INCONCLUSIVE — the second call GREW {', '.join(dup)}, and every one of those "
                "tables SOFT-ARCHIVES. Growth is what an archive-and-replace looks like from a row "
                "count. Settle it by counting ACTIVE rows only (the lifecycle column), not total: "
                "a correct tool leaves the same number of ACTIVE rows and more archived ones.")
        elif dup:
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
