#!/usr/bin/env python3
"""P7-FALSE-ABSENCE's memory instance, reproduced on demand.

    python scripts/toolloop/memory_false_absence_probe.py

Stores a fact with a nonce, searches for that exact nonce twice (immediately and after 3s), then
forgets it by the id the write returned. The invariant under test is P7's: "a store that accepts a
write must have a read that can find it, or the write must refuse."

Measured 2026-08-23: remember confirms with a fact_id, both searches return hits: [] with
degraded: {"semantic": "not_indexed"}, and forget BY ID works. So the store is sound and the
retrieval path is not - which matters because memory_remember's id is gone by the next turn, making
search the only route a later turn has to a stored fact.

SAFETY: one throwaway project of this module's own making, torn down in a finally.
"""
import json,sys,uuid,time
sys.path.insert(0,".")
from scripts.eval.tool_liveness.mcp_direct import MCPDirect, MCPToolError
from scripts.toolloop.provision import Throwaway
m=MCPDirect()
fx=Throwaway("p7-false-absence", mcp=m).build()
out={}
try:
    token=f"Emberfall {uuid.uuid4().hex[:6]}"
    r=m.call("memory_remember",{"project_id":fx.project_id,
        "fact_text":f"{token} is the name of the harness throwaway keep.","fact_type":"statement"})
    out["remember"]=json.dumps(r,ensure_ascii=False)[:200]
    fid=r.get("fact_id") or (r.get("result") or {}).get("fact_id")
    out["fact_id"]=fid
    for label,delay in (("immediate",0),("after_3s",3)):
        if delay: time.sleep(delay)
        try:
            s=m.call("memory_search",{"project_id":fx.project_id,"query":token})
            blob=json.dumps(s,ensure_ascii=False)
            out[f"search_{label}"]={"finds_token": token in blob,
                                    "degraded": "not_indexed" in blob or "degraded" in blob,
                                    "detail": blob[:220]}
        except MCPToolError as e:
            out[f"search_{label}"]={"error":str(e)[:200]}
    if fid:
        try:
            f1=m.call("memory_forget",{"fact_id":fid}); out["forget_1"]=json.dumps(f1,ensure_ascii=False)[:160]
        except MCPToolError as e: out["forget_1"]=f"refused: {e}"[:160]
finally:
    try: fx.teardown()
    except Exception as e: print("teardown failed:",e,file=sys.stderr)
print(json.dumps(out,indent=2,ensure_ascii=False)[:1500])
