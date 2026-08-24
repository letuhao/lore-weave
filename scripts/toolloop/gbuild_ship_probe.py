"""SHIP audit for composition_glossary_build — a tool that has NEVER completed a call.

Tier A/W multi-stage and it SPENDS at every stage. Every call here is a PROPOSE where the tool
gates; no confirm token is ever redeemed. Two throwaway books, provisioned and torn down.
"""
import json, sys, uuid
sys.path.insert(0, ".")
import httpx
from scripts.eval.tool_liveness import config as cfg
from scripts.eval.tool_liveness.mcp_direct import MCPDirect, MCPToolError
from scripts.toolloop.provision import Throwaway, _tle_auth

m = MCPDirect()
REAL_MODEL = "019ebb72-27a2-72f3-a42d-d2d0e0ded179"
STORY = ("Aldric Vane climbs the black stair of Hollow Keep as the storm breaks; "
         "Mira Solene waits at the waterline where the Obsidian Trench is walkable only at low tide.")


def build(label):
    fx = Throwaway(label, mcp=m).build()
    # The ontology precondition the scenario seeds: without it the tool has no kinds to build into.
    httpx.post(f"{cfg.DOMAIN_BASE['glossary']}/v1/glossary/books/{fx.book_id}/adopt",
               headers=_tle_auth().bearer_header(),
               json={"genres": ["universal"], "kinds": ["character"]}, timeout=60)
    return fx


def call(**args):
    try:
        r = m.call("composition_glossary_build", args)
        return {"verdict": "SUCCEEDED", "detail": json.dumps(r, ensure_ascii=False)[:220], "_raw": r}
    except MCPToolError as e:
        return {"verdict": "refused", "detail": str(e)[:260]}


a = b = None
out = {}
try:
    a, b = build("gb-ship-a"), build("gb-ship-b")
    out["_fixture"] = {"book_a": a.book_id, "book_b": b.book_id}

    out["absent_status"] = call(op="status", book_id=a.book_id, run_id=str(uuid.uuid4()))
    out["absent_status"]["asked"] = "op=status with a run_id that does not exist"

    out["absent_approve_plan"] = call(op="approve_plan", book_id=a.book_id, run_id=str(uuid.uuid4()),
                                      worklist=[])
    out["absent_approve_plan"]["asked"] = "op=approve_plan with a run_id that does not exist"

    out["empty_source_text"] = call(op="start", book_id=a.book_id, source_text="",
                                    model_ref=REAL_MODEL, model_source="user_model")
    out["empty_source_text"]["asked"] = "op=start with source_text present but EMPTY"

    out["omitted_model_ref"] = call(op="start", book_id=a.book_id, source_text=STORY)
    out["omitted_model_ref"]["asked"] = "op=start with model_ref omitted"

    out["invented_model_ref"] = call(op="start", book_id=a.book_id, source_text=STORY,
                                     model_ref="default", model_source="user_model")
    out["invented_model_ref"]["asked"] = "op=start with model_ref='default'"

    g = call(op="start", book_id=a.book_id, source_text=STORY, model_ref=REAL_MODEL,
             model_source="user_model")
    g["asked"] = "a VALID op=start — the first call this tool has ever completed"
    out["gate"] = g

    g2 = call(op="start", book_id=a.book_id, source_text=STORY, model_ref=REAL_MODEL,
              model_source="user_model")
    g2["asked"] = "op=start a SECOND time on the same book"
    out["idempotency"] = g2
finally:
    for fx in (a, b):
        if fx:
            try:
                fx.teardown()
            except Exception as e:  # noqa: BLE001
                out.setdefault("_teardown_errors", []).append(str(e)[:120])
for v in out.values():
    if isinstance(v, dict):
        v.pop("_raw", None)
print(json.dumps(out, indent=2, ensure_ascii=False))
