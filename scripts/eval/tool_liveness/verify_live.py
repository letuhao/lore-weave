"""Component-level LIVE proofs for the two headline components the model-driven
matrix could not exercise (the agent under-selects Tier-W / async tools, a real G1
finding — see the matrix). These prove the HARNESS components work end-to-end on a
live stack, independent of whether a given model happens to select the tool.

  1. CONFIRM RESOLVER (the biggest gap): Tier-W `glossary_propose_new_kind` mints a
     confirm_token (writes nothing) → the resolver POSTs the domain confirm route →
     the kind then exists, read back via an INDEPENDENT DB path (CD3 anti-oracle).
  2. ASYNC POLLER (best-effort): drive `kg_build_graph` (declared `_meta.async`) via
     MCP-direct on the fixture project, poll the produced artifact (graph nodes) to a
     terminal/present state, assert the artifact — not the job id.

Run: TLE_MODEL_REF=<gemma> TLE_JWT_SECRET=<secret> \
     python -m scripts.eval.tool_liveness.verify_live
Writes docs/eval/tool-liveness/<date>/verify-live.json.
"""
from __future__ import annotations

import datetime as dt
import json
import time
from pathlib import Path

from . import config, oracle
from .auth import Auth
from .confirm import confirm as do_confirm, find_confirm_token
from .fixtures import Fixture
from .mcp_direct import MCPDirect


def prove_confirm_resolver(fx: Fixture, mcp: MCPDirect, auth: Auth) -> dict:
    before = oracle.book_kind_exists(fx.book_id, "faction")
    r = mcp.call("glossary_propose_new_kind", {
        "book_id": fx.book_id, "code": "faction", "name": "Faction",
        "description": "A political faction."})
    token = find_confirm_token(r)
    ok, code, body = (False, 0, None)
    if token:
        ok, code, body = do_confirm(auth, "glossary_propose_new_kind", token)
    after = oracle.book_kind_exists(fx.book_id, "faction")
    return {
        "component": "confirm_resolver",
        "token_minted": bool(token),
        "wrote_nothing_at_call_time": before is False,  # W writes nothing until confirm
        "confirm_http": code, "confirm_ok": ok,
        "effect_after_confirm": after,
        "PASS": bool(token) and (before is False) and ok and (after is True),
    }


def prove_async_poller(fx: Fixture, mcp: MCPDirect, kg_project_id: str | None,
                       timeout_s: int = 120) -> dict:
    out = {"component": "async_poller", "kg_project_id": kg_project_id}
    if not kg_project_id:
        out["PASS"] = False
        out["note"] = "no kg project (setup failed)"
        return out

    # F6: kg_build_graph requires the project to have an embedding model. A freshly
    # created project has none, and until `kg_project_set_embedding_model` existed this
    # step was reachable ONLY through the REST route behind the Build-KG dialog — so the
    # async poller could never be live-proven. Configure it the way an agent now would.
    if config.EMBEDDING_MODEL_REF:
        try:
            r = mcp.call("kg_project_set_embedding_model", {
                "project_id": kg_project_id,
                "embedding_model": config.EMBEDDING_MODEL_REF})
            out["embedding_model_configured"] = r.get("embedding_dimension")
        except Exception as e:
            out["embedding_model_configured"] = False
            out["note"] = f"kg_project_set_embedding_model failed: {e}"
            out["PASS"] = False
            return out
    else:
        out["note"] = ("set TLE_EMBEDDING_MODEL_REF to an embedding user_model uuid — "
                       "kg_build_graph cannot run without a configured embedding model")

    try:
        r = mcp.call("kg_build_graph", {
            "llm_model": config.MODEL_REF, "project_id": kg_project_id,
            "scope": "glossary_sync"})
        out["build_accepted"] = True
        out["build_result"] = json.dumps(r)[:200]
    except Exception as e:
        out["build_accepted"] = False
        # MCPToolError now carries the SERVER's message; it used to be swallowed into
        # "unhandled errors in a TaskGroup (1 sub-exception)" by anyio's group wrapper.
        out["note"] = f"kg_build_graph call failed: {e}"
        out["PASS"] = False
        return out
    # poll the produced artifact (independent path) until nodes present or timeout
    db = config.DOMAIN_DB["knowledge"]
    deadline = time.time() + timeout_s
    nodes = 0
    node_table = None
    for cand in ("kg_nodes", "nodes", "graph_nodes", "kg_entity_nodes"):
        try:
            oracle.count(db, f"{cand} WHERE project_id='{kg_project_id}'")
            node_table = cand
            break
        except Exception:
            continue
    if not node_table:
        out["PASS"] = False
        out["note"] = "could not locate a kg node table for the artifact read-back"
        return out
    while time.time() < deadline:
        nodes = oracle.count(db, f"{node_table} WHERE project_id='{kg_project_id}'")
        if nodes > 0:
            break
        time.sleep(6)
    out["node_table"] = node_table
    out["artifact_node_count"] = nodes
    out["terminal_reached"] = nodes > 0
    out["PASS"] = nodes > 0
    if nodes == 0:
        out["note"] = f"no graph artifact within {timeout_s}s (build slow or errored)"
    return out


def main() -> int:
    auth = Auth()
    auth.token()
    mcp = MCPDirect()
    fx = Fixture().build()
    kg_pid = None
    try:
        proj = mcp.call("kg_project_create", {
            "name": f"TLE-verify-{fx.run_id}", "project_type": "book",
            "book_id": fx.book_id})
        kg_pid = proj.get("project_id") or proj.get("id")
        if kg_pid:
            mcp.call("kg_project_entities_to_nodes",
                     {"project_id": kg_pid, "entity_ids": [e["entity_id"] for e in fx.entities]})
    except Exception as e:
        print("kg setup:", e)

    results = {
        "date": dt.date.today().isoformat(),
        "stack": config.GATEWAY, "model_ref": config.MODEL_REF,
        "auth_mode": auth.mode, "fixture_book_id": fx.book_id,
        "confirm_resolver": prove_confirm_resolver(fx, mcp, auth),
        "async_poller": prove_async_poller(fx, mcp, kg_pid),
    }
    fx.teardown()

    for k in ("confirm_resolver", "async_poller"):
        print(f"[verify] {k}: PASS={results[k].get('PASS')}  "
              f"{ {x: results[k][x] for x in results[k] if x != 'component'} }")

    out_dir = (Path(__file__).resolve().parents[3] / "docs" / "eval"
               / "tool-liveness" / results["date"])
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "verify-live.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[verify] wrote {out_dir / 'verify-live.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
