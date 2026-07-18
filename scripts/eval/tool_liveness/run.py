"""TLE P0 orchestrator — run the 10-probe set through the four gates on a live stack.

Flow per probe: fresh chat session → black-box NL turn (context injected) →
  G1 SELECT  the model called the expected tool
  G2 SHAPE   the call's args carry every schema-required field (from the live inventory)
  G3 EXECUTE the call returned without error; Tier-W: the confirm_token round-trip 200s
  G4 EFFECT  the probe's oracle verifies the change via an INDEPENDENT DB read-back

Emits matrix.json + matrix.md + transcript.jsonl to docs/eval/tool-liveness/<date>/.

Usage (host, stack up):
  TLE_MODEL_REF=<gemma_uuid> python -m scripts.eval.tool_liveness.run
Env: see config.py. --allow-paid opts paid probes in (default: UNTESTED-PAID).
"""
from __future__ import annotations

import asyncio
import datetime as dt
import json
import sys
import time
from pathlib import Path

import httpx

from . import config, matrix, oracle, probes as probes_mod
from .auth import Auth
from .confirm import confirm as do_confirm, find_confirm_token
from .fixtures import Fixture
from .mcp_direct import MCPDirect
from .poller import find_job_id, poll_via_tool
from .sse import create_session, send_turn


def load_inventory() -> dict:
    """Map tool_name -> {required:[...], meta:{...}} from the live ai-gateway."""
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client
    H = {"X-Internal-Token": config.INTERNAL_TOKEN, "X-User-Id": config.USER_ID,
         "X-Session-Id": "tle-inv"}

    async def _go():
        out = {}
        async with streamablehttp_client(config.AI_GATEWAY_MCP, headers=H) as (r, w, _):
            async with ClientSession(r, w) as s:
                await s.initialize()
                tl = await s.list_tools()
                for t in tl.tools:
                    out[t.name] = {
                        "required": (t.inputSchema or {}).get("required", []),
                        "meta": getattr(t, "meta", None) or {},
                    }
        return out

    return asyncio.run(_go())


def service_of(tool: str) -> str:
    p = tool.split("_", 1)[0]
    return {"kg": "knowledge", "plan": "composition"}.get(p, p)


def _context_for(fx: Fixture, probe: dict) -> dict | None:
    if not probe.get("needs_context"):
        return None
    return {"book_context": {"book_id": fx.book_id}}


def _match_calls(tools: list[dict], tool: str) -> list[dict]:
    """Return the effective calls to `tool`. The agent uses a lazy tool-loading
    facade (`tool_list`/`tool_load` then the real tool as a direct call), so the
    real tool usually appears directly. Some paths wrap it as
    `invoke_tool({name, arguments})` — normalize that shape too so G1/G2 see the
    real args/result, not the wrapper's."""
    out = []
    for tc in tools:
        if tc["tool"] == tool:
            out.append(tc)
        elif tc["tool"] in ("invoke_tool", "tool_call") and isinstance(tc.get("args"), dict):
            a = tc["args"]
            if a.get("name") == tool or a.get("tool") == tool:
                out.append({"tool": tool,
                            "args": a.get("arguments") or a.get("args") or {},
                            "ok": tc.get("ok"), "result": tc.get("result"),
                            "error": tc.get("error")})
    return out


def probe_capability(fx: Fixture, probe: dict, harness: dict, row: dict) -> str:
    """After a G1 miss, call the tool DETERMINISTICALLY (MCP-direct, authored args) to
    answer the question the NL probe could not: *can this tool work at all?*

    Returns one of:
      "PASS"        — the tool works; the model simply didn't pick it (F5, a description
                      / discovery problem). The ship gate WARNS.
      "RED"         — the tool fails even when called correctly (F6, a product bug).
                      The ship gate BLOCKS. `capability_error` carries the server's
                      own message (mcp_direct now unwraps anyio's ExceptionGroup).
      "SKIP-PAID"   — never spend the user's money to score a matrix cell.
      "SKIP-NO-ARGS" — no authored `direct` builder, or its fixture inputs are missing.

    Safety: a Tier-W tool MINTS a confirm_token and writes nothing at call time — we
    never redeem it. A Tier-A tool writes only into the throwaway fixture. Nothing here
    addresses an id the fixture did not create.
    """
    if row.get("paid"):
        return "SKIP-PAID"
    builder = probe.get("direct")
    if builder is None:
        return "SKIP-NO-ARGS"
    try:
        args = builder(fx, harness)
    except Exception as e:  # a fixture field the build never populated
        row["capability_error"] = f"direct-args build failed: {type(e).__name__}: {e}"
        return "SKIP-NO-ARGS"
    if args is None:
        return "SKIP-NO-ARGS"

    mcp = MCPDirect()
    # Some tools have a precondition an agent would satisfy first (F6: kg_build_graph
    # needs a configured embedding model). Run it, and report a setup failure AS a
    # capability failure — an unreachable precondition IS the tool being unreachable.
    for setup_tool, setup_args in (probe.get("setup") or (lambda *_: []))(fx, harness):
        try:
            mcp.call(setup_tool, setup_args)
        except Exception as e:
            row["capability_error"] = f"setup {setup_tool} failed: {e}"
            return "RED"

    try:
        result = mcp.call(probe["tool"], args)
    except Exception as e:
        row["capability_error"] = str(e)[:400]
        return "RED"
    row["evidence"]["capability_call"] = {"args": args, "result": json.dumps(result)[:200]}
    return "PASS"


def run_probe(client: httpx.Client, auth: Auth, fx: Fixture, inv: dict,
              probe: dict, harness: dict, transcript: list) -> dict:
    tool = probe["tool"]
    meta = inv.get(tool, {}).get("meta", {})
    row = {
        "id": probe["id"], "tool": tool, "service": service_of(tool),
        "tier": meta.get("tier") or ("ABSENT→R" if tool in inv else "?"),
        "async": bool(meta.get("async")), "paid": bool(meta.get("paid")),
        "probe": probe["nl"], "G1": None, "G2": None, "G3": None, "G4": None,
        "evidence": {}, "status": "RED", "notes": "",
    }
    if probe.get("paid") and not config.ALLOW_PAID:
        row["status"] = "UNTESTED-PAID"
        row["notes"] = "paid tool; run with --allow-paid + budget cap"
        return row

    sid = create_session(client, auth, f"tle-{probe['id']}")
    ctx = _context_for(fx, probe)
    t0 = time.time()
    try:
        res = send_turn(client, auth, sid, probe["nl"],
                        permission_mode=probe.get("permission_mode", "write"), context=ctx)
    except Exception as e:
        row["notes"] = f"turn failed: {type(e).__name__}: {e}"
        return row
    dt_s = round(time.time() - t0, 1)
    transcript.append({"probe": probe["id"], "tool": tool, "sid": sid,
                       "assistant": res["assistant"][:2000], "tools": res["tools"],
                       "latency_s": dt_s})

    # G1 SELECT (see through the lazy tool-loading facade / invoke_tool wrapper)
    calls = _match_calls(res["tools"], tool)
    row["G1"] = "PASS" if calls else "RED"
    if not calls:
        called = sorted({tc["tool"] for tc in res["tools"]})
        row["notes"] = f"model did not call {tool}; called instead: {called}"
        # A G1 miss used to return here — so the tool was NEVER exercised, and a
        # *selection* failure looked identical to a *capability* failure. That collapse
        # hid F6 for a full cycle: kg_build_graph was scored "model did not call it"
        # while it also could not have succeeded. Re-probe deterministically to tell the
        # two apart; the ship gate (CD4) must block on the second, not the first.
        row["capability"] = probe_capability(fx, probe, harness, row)
        return row
    call = calls[-1]
    row["evidence"]["call"] = {"args": call.get("args"), "ok": call.get("ok"),
                               "error": call.get("error")}

    # G2 SHAPE — every schema-required arg present (non-empty)
    required = inv.get(tool, {}).get("required", [])
    args = call.get("args") or {}
    missing = [k for k in required if k not in args or args.get(k) in (None, "", [])]
    # book/chapter/project ids may be auto-injected by the context layer (not in the
    # visible args) — treat context-injected ids as satisfied when context was provided
    if ctx:
        missing = [k for k in missing if k not in ("book_id", "project_id")]
    row["G2"] = "PASS" if not missing else "RED"
    if missing:
        row["notes"] = f"missing required args: {missing}"
        # continue to G3 anyway to observe execution

    # G3 EXECUTE
    a = call.get("args") or {}
    suspended = (call.get("ok") is None and call.get("result") is None
                 and isinstance(a, dict) and a.get("kind") == "tool_approval")
    if probe.get("confirm"):
        # Tier-W: resolve the confirm_token round-trip (token may ride in the result
        # OR in a suspension descriptor). This is what makes a W tool executable.
        tok = find_confirm_token(call.get("result")) or find_confirm_token(a)
        if not tok:
            row["G3"] = "RED"
            row["notes"] += " | Tier-W but no confirm_token to resolve"
        else:
            ok, code, body = do_confirm(auth, tool, tok)
            row["evidence"]["confirm"] = {"status": code, "ok": ok, "body": str(body)[:300]}
            row["G3"] = "PASS" if ok else "RED"
            if not ok:
                row["notes"] += f" | confirm failed HTTP {code}"
    elif suspended:
        # tier-A approval card: the tool did NOT execute — it awaits approval.
        row["G3"] = "RED"
        row["notes"] = (row["notes"] + " | " if row["notes"] else "") + \
            "SUSPENDED on tool_approval card (tier-A not allowlisted / approval unresolved)"
    elif call.get("ok") is False:
        row["G3"] = "RED"
        row["notes"] = (row["notes"] + " | " if row["notes"] else "") + \
            f"call isError: {str(call.get('error'))[:160]}"
    else:
        row["G3"] = "PASS"

    # async: poll to terminal before G4
    if probe.get("cls") == "async" and row["G3"] == "PASS":
        job = find_job_id(call.get("result"))
        st_tool = probe.get("status_tool")
        if st_tool:
            poll = poll_via_tool(client, auth, sid, st_tool,
                                 {"project_id": harness.get("kg_project_id")},
                                 tries=int(probe.get("poll_timeout_s", 120) // 8) or 8,
                                 delay=8.0)
            row["evidence"]["poll"] = {"job_id": job, "terminal": poll["terminal"],
                                       "status": poll["status"]}

    # G4 EFFECT — independent oracle
    if row["G3"] == "PASS":
        try:
            passed, ev = probe["oracle"](fx, call, harness)
        except Exception as e:
            passed, ev = False, {"oracle_error": f"{type(e).__name__}: {e}"}
        row["G4"] = "PASS" if passed else "RED"
        row["evidence"]["readback"] = ev
        if not passed and not row["notes"]:
            row["notes"] = "SILENT-SUCCESS SUSPECT: call ok but effect not found in DB"
    else:
        row["G4"] = "SKIP"

    row["status"] = matrix.status_for(row)
    return row


def setup_async_prereq(fx: Fixture, harness: dict) -> None:
    """Create a KG project from the fixture book + push entities to nodes so the
    async kg_build probe has a target. Best-effort; records the reason on failure."""
    try:
        mcp = MCPDirect()
        proj = mcp.call("kg_project_create", {
            "name": f"TLE-kg-{fx.run_id}", "project_type": "book", "book_id": fx.book_id})
        pid = proj.get("project_id") or proj.get("id")
        harness["kg_project_id"] = pid
        if pid:
            eids = [e["entity_id"] for e in fx.entities]
            try:
                mcp.call("kg_project_entities_to_nodes",
                         {"project_id": pid, "entity_ids": eids})
            except Exception as e:
                harness["kg_nodes_note"] = f"entities_to_nodes failed: {e}"
    except Exception as e:
        harness["kg_project_note"] = f"kg_project_create failed: {e}"


def negative_control(fx: Fixture) -> dict:
    """Prove the effect oracle is NOT a no-op: run the write-oracles against state
    that was deliberately NOT written and assert they go RED. If any returns PASS,
    the oracle is broken (it would rubber-stamp silent-success)."""
    checks = []
    # 1) a book description that was never set
    row = oracle.book_row(fx.book_id) or {}
    desc = (row.get("description") or "")
    checks.append({"check": "phantom_description",
                   "oracle_says_present": "NEVER-WRITTEN-XYZZY" in desc,
                   "expect": False})
    # 2) an entity that was never added
    names = [n.lower() for n in oracle.glossary_entity_names(fx.book_id)]
    checks.append({"check": "phantom_entity",
                   "oracle_says_present": any("zzz_phantom_never_added" in n for n in names),
                   "expect": False})
    # 3) a kind that was never proposed
    checks.append({"check": "phantom_kind",
                   "oracle_says_present": oracle.book_kind_exists(fx.book_id, "zzz_never"),
                   "expect": False})
    ok = all(c["oracle_says_present"] is False for c in checks)
    return {"oracle_discriminates": ok, "checks": checks,
            "meaning": "PASS ⇒ the oracle returns False for effects that never happened "
                       "(so a real G4 PASS is meaningful, not a rubber stamp)."}


def main() -> int:
    config_allow_paid = "--allow-paid" in sys.argv
    if config_allow_paid:
        config.ALLOW_PAID = True
    auth = Auth()
    auth.token()  # force auth now (records mode)

    print(f"[tle] auth mode = {auth.mode}")
    print("[tle] loading live inventory from ai-gateway…")
    inv = load_inventory()
    print(f"[tle] inventory: {len(inv)} tools")

    print("[tle] building fixture (throwaway book + ontology + chapter + entities)…")
    fx = Fixture().build()
    print(f"[tle] fixture book_id={fx.book_id} chapter_id={fx.chapter_id} "
          f"entities={len(fx.entities)}")

    # Pre-allowlist the tier-A auto-write tools so they don't suspend on the
    # approval card (spec §4). Tier-W tools still mint a confirm_token (handled by
    # the confirm resolver) — allowlisting is orthogonal to the W confirm gate.
    fx.allowlist_tools([
        "book_create", "book_update_meta", "glossary_propose_entities",
        "glossary_propose_new_kind", "book_chapter_publish", "glossary_entity_delete",
    ])

    harness: dict = {}
    # delete target for W3 = the 'Ember Codex' fixture entity
    for e in fx.entities:
        if "codex" in (e["name"] or "").lower():
            harness["delete_target_entity_id"] = e["entity_id"]
    setup_async_prereq(fx, harness)
    print(f"[tle] async prereq: kg_project_id={harness.get('kg_project_id')} "
          f"{harness.get('kg_project_note','')}{harness.get('kg_nodes_note','')}")

    rows: list[dict] = []
    transcript: list[dict] = []
    with httpx.Client() as client:
        for probe in probes_mod.build_probes():
            print(f"[tle] probe {probe['id']} {probe['tool']} …", flush=True)
            try:
                row = run_probe(client, auth, fx, inv, probe, harness, transcript)
            except Exception as e:
                row = {"id": probe["id"], "tool": probe["tool"],
                       "service": service_of(probe["tool"]), "tier": "?",
                       "async": probe.get("cls") == "async", "paid": False,
                       "probe": probe["nl"], "G1": "RED", "G2": None, "G3": None,
                       "G4": None, "evidence": {}, "status": "RED",
                       "notes": f"probe crashed: {type(e).__name__}: {e}"}
            rows.append(row)
            print(f"       G1={row['G1']} G2={row['G2']} G3={row['G3']} G4={row['G4']} "
                  f"=> {row['status']}  {row['notes'][:80]}")

    negctrl = negative_control(fx)
    print(f"[tle] oracle negative-control discriminates = {negctrl['oracle_discriminates']}")

    # The kg project is created by THIS module (kg_project_create above), not by
    # Fixture.build(), so Fixture.teardown() knows nothing about it and leaked one row per
    # run — five orphans accumulated before anyone looked. "No probe may touch an id it did
    # not create" cuts both ways: it must also destroy what it did.
    if harness.get("kg_project_id"):
        pid = str(harness["kg_project_id"]).replace("'", "''")
        try:
            oracle.db_query(config.DOMAIN_DB["knowledge"],
                            f"DELETE FROM knowledge_projects WHERE project_id='{pid}'")
            print(f"[tle] teardown: kg project {harness['kg_project_id']} deleted")
        except Exception as e:
            print(f"[tle] teardown: FAILED to delete kg project: {e}")

    teardown = fx.teardown()
    print(f"[tle] teardown: {teardown}")

    # ── write reports ─────────────────────────────────────────────────────────
    date = dt.date.today().isoformat()
    model_short = (config.MODEL_REF or "model")[:8]
    out_dir = Path(__file__).resolve().parents[3] / "docs" / "eval" / "tool-liveness" / date
    out_dir.mkdir(parents=True, exist_ok=True)
    meta = {"label": "P0", "date": date, "gateway": config.GATEWAY,
            "model_ref": config.MODEL_REF, "auth_mode": auth.mode,
            "fixture_book_id": fx.book_id}
    matrix.write_matrix_json(rows, out_dir / "matrix.json")
    (out_dir / "matrix.md").write_text(matrix.render_md(rows, meta), encoding="utf-8")
    (out_dir / "transcript.jsonl").write_text(
        "\n".join(json.dumps(t, ensure_ascii=False) for t in transcript) + "\n",
        encoding="utf-8")
    (out_dir / "negative-control.json").write_text(
        json.dumps(negctrl, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "meta.json").write_text(
        json.dumps({**meta, "teardown": teardown, "harness": harness}, indent=2),
        encoding="utf-8")

    npass = sum(1 for r in rows if r["status"] == "PASS")
    nred = sum(1 for r in rows if r["status"] == "RED")
    print(f"\n[tle] DONE: {npass}/{len(rows)} PASS, {nred} RED → {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
