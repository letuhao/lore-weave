import json,sys,uuid
sys.path.insert(0,".")
import httpx
from scripts.eval.tool_liveness import config as cfg
from scripts.eval.tool_liveness.mcp_direct import MCPDirect, MCPToolError
from scripts.toolloop.provision import Throwaway, _tle_auth
m=MCPDirect()
def build(label):
    fx=Throwaway(label,mcp=m).build()
    httpx.post(f"{cfg.DOMAIN_BASE['glossary']}/v1/glossary/books/{fx.book_id}/adopt",
               headers=_tle_auth().bearer_header(),
               json={"genres":["universal"],"kinds":["character"]},timeout=60)
    return fx
def call(book,ops,label):
    try:
        r=m.call("glossary_propose_batch",{"book_id":book,"ops":ops})
        return {"verdict":"SUCCEEDED","detail":json.dumps(r,ensure_ascii=False)[:200]}
    except MCPToolError as e:
        return {"verdict":"refused","detail":str(e)[:230]}
a=None; out={}
try:
    a=build("pbs-a")
    KIND=[{"type":"create_kinds","params":{"kinds":[{"code":"faction","name":"Faction"}]}}]
    out["empty"]=call(a.book_id,[],"empty"); out["empty"]["asked"]="ops present but EMPTY"
    out["absent_book"]=call(str(uuid.uuid4()),KIND,"absent"); out["absent_book"]["asked"]="a book that does not exist"
    out["gate"]=call(a.book_id,KIND,"gate"); out["gate"]["asked"]="a real batch — does it MINT a confirm token rather than applying?"
finally:
    if a:
        try: a.teardown()
        except Exception as e: print("teardown:",e,file=sys.stderr)
for k,v in out.items(): print(f"  {k:12s} {v['verdict']:10s} {v['detail'][:150]}")
import pathlib
pathlib.Path("docs/eval/toolloop/2026-08-14/pbatch-ship-probe.json").write_text(json.dumps(out,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
