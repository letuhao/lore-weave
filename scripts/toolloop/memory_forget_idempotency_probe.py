import json,sys,subprocess,uuid
sys.path.insert(0,".")
from scripts.eval.tool_liveness.mcp_direct import MCPDirect, MCPToolError
from scripts.toolloop.provision import Throwaway
from scripts.eval.tool_liveness import oracle
def cypher(q):
    # ONE graph reader (D-SEED-ASSERT-CANNOT-ADDRESS-THE-GRAPH). This had its own
    # cypher-shell call with the password HARDCODED, which is both a second way to reach
    # the graph and a credential in the tree; oracle.cypher_query reads it from the
    # container that owns the connection.
    rows = oracle.cypher_query(q)
    return rows[0][0] if rows and rows[0] else ""
m=MCPDirect(); fx=Throwaway("memidem", mcp=m).build()
try:
    tok=f"Emberfall {uuid.uuid4().hex[:6]}"
    r=m.call("memory_remember",{"project_id":fx.project_id,"fact_text":f"{tok} is a keep.","fact_type":"statement"})
    fid=r.get("fact_id")
    print("fact_id:",fid)
    a=m.call("memory_forget",{"fact_id":fid}); print("forget #1:",json.dumps(a,ensure_ascii=False)[:100])
    v1=cypher(f"MATCH (f:Fact {{id:'{fid}'}}) RETURN f.valid_until")
    b=m.call("memory_forget",{"fact_id":fid}); print("forget #2:",json.dumps(b,ensure_ascii=False)[:100])
    v2=cypher(f"MATCH (f:Fact {{id:'{fid}'}}) RETURN f.valid_until")
    print("valid_until after #1:",v1.replace("\n"," | "))
    print("valid_until after #2:",v2.replace("\n"," | "))
    print("IDEMPOTENT:", v1==v2)
finally:
    fx.teardown()
