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
    m.call("glossary_propose_entities",{"book_id":fx.book_id,
        "items":[{"kind":"character","name":f"Aldric {label}","attributes":{"occupation":"soldier"}}]})
    s=m.call("glossary_search",{"book_id":fx.book_id,"query":"Aldric"})
    blob=json.dumps(s); i=blob.find('"entity_id": "')
    eid=blob[i+14:].split('"')[0] if i>=0 else None
    r=m.call("composition_create_derivative",{"project_id":fx.project_id,"name":f"what-if {label}"})
    resp=httpx.post(f"{cfg.DOMAIN_BASE['composition']}/v1/composition/actions/confirm?token={r['confirm_token']}",
                    headers=_tle_auth().bearer_header(),timeout=60)
    dpid=(resp.json().get("derivative") or {}).get("project_id")
    return fx,eid,dpid
def call(pid,eid,label,fields=None,op="add"):
    a={"op":op,"project_id":pid,"target_entity_id":eid,"overridden_fields":fields if fields is not None else {"occupation":"cartographer"}}
    try:
        r=m.call("composition_entity_override_edit",a); return {"verdict":"SUCCEEDED","detail":json.dumps(r,ensure_ascii=False)[:200]}
    except MCPToolError as e: return {"verdict":"refused","detail":str(e)[:220]}
a=b=None; out={}
try:
    a,a_ent,a_pid=build("ovs-a"); b,b_ent,b_pid=build("ovs-b")
    out["_fixture"]={"a_derivative":a_pid,"b_derivative":b_pid}
    out["absent"]=call(a_pid,str(uuid.uuid4()),"absent"); out["absent"]["asked"]="an entity that does not exist"
    out["tenancy"]=call(a_pid,b_ent,"tenancy"); out["tenancy"]["asked"]="book B's entity offered to book A's derivative"
    out["empty"]=call(a_pid,a_ent,"empty",fields={}); out["empty"]["asked"]="overridden_fields present but EMPTY"
    out["canonical"]=call(a.project_id,a_ent,"canonical"); out["canonical"]["asked"]="the CANONICAL project instead of the derivative"
    first=call(a_pid,a_ent,"first"); out["idem_first"]=first
    out["idem_repeat"]=call(a_pid,a_ent,"repeat"); out["idem_repeat"]["asked"]="the same add, twice"
finally:
    for fx in (a,b):
        if fx:
            try: fx.teardown()
            except Exception as e: print("teardown:",e,file=sys.stderr)
for k,v in out.items():
    print(f"  {k:12s} {v.get('verdict','?'):10s} {str(v.get('detail',''))[:120]}")
import pathlib
pathlib.Path("docs/eval/toolloop/2026-08-14/override-ship-probe.json").write_text(json.dumps(out,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
