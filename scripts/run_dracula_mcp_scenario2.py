"""Scenario phases 6-7 via knowledge /mcp DIRECT (the gateway drops X-Project-Id,
so project-scoped KG tools can't be driven through federation today — a pre-existing
gateway gap). Still MCP tool-calls. build_graph + build_wiki propose->confirm->poll."""
import asyncio
import json
import os
import time

import httpx
import jwt
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

TOKEN = os.environ["INTERNAL_SERVICE_TOKEN"]
SECRET = os.environ["JWT_SECRET"]
USER = "019d5e3c-7cc5-7e6a-8b27-1344e148bf7c"
GEN = "51ea9fd7-4a25-4801-af67-d88c2d161dac"
KG_MCP = "http://knowledge-service:8092/mcp"
KNOW = "http://knowledge-service:8092"
STATE = "/app/scenario_state.json"


def bearer():
    n = int(time.time()); return jwt.encode({"sub": USER, "iat": n, "exp": n + 3600}, SECRET, algorithm="HS256")


def load(): return json.load(open(STATE))
def save(st): json.dump(st, open(STATE, "w"), indent=1)


def _p(res):
    if getattr(res, "isError", False):
        raise RuntimeError(f"tool error: {res.content[0].text if res.content else '?'}")
    return json.loads(res.content[0].text)


async def kg_confirm(token):
    async with httpx.AsyncClient(timeout=180) as c:
        r = await c.post(f"{KNOW}/v1/kg/actions/confirm",
                         headers={"Authorization": f"Bearer {bearer()}"},
                         json={"confirm_token": token})
    return r.status_code, (r.json() if r.headers.get("content-type", "").startswith("application/json") else r.text)


async def main():
    st = load(); proj = st["kg_project"]
    H = {"X-Internal-Token": TOKEN, "X-User-Id": USER, "X-Session-Id": "s2c", "X-Project-Id": proj}
    async with streamablehttp_client(KG_MCP, headers=H) as (r, w, _):
        async with ClientSession(r, w) as s:
            await s.initialize()
            if not st.get("kg_done"):
                gp = _p(await s.call_tool("kg_build_graph", {"llm_model": GEN, "scope": "all"}))
                print("build_graph propose:", json.dumps(gp)[:160])
                code, body = await kg_confirm(gp["confirm_token"])
                print("build_graph confirm:", code, json.dumps(body)[:240])
                for i in range(90):
                    async with httpx.AsyncClient(timeout=30) as c:
                        gg = await c.get(f"{KNOW}/v1/knowledge/projects/{proj}",
                                         headers={"Authorization": f"Bearer {bearer()}"})
                    pj = gg.json() if gg.status_code == 200 else {}
                    ec = pj.get("entity_count") or pj.get("graph_entity_count")
                    print(f"  [kg] {i}: status={pj.get('extraction_status')} entities={ec}")
                    if ec and ec > 0:
                        st["kg_done"] = True; st["kg_entities"] = ec; save(st); break
                    await asyncio.sleep(10)
            if st.get("kg_done") and not st.get("wiki_done"):
                wp = _p(await s.call_tool("kg_build_wiki", {"model_ref": GEN, "model_source": "user_model"}))
                print("build_wiki propose:", json.dumps(wp)[:160])
                code, body = await kg_confirm(wp["confirm_token"])
                print("build_wiki confirm:", code, json.dumps(body)[:240])
                st["wiki_done"] = (code == 200); save(st)
    print("STATE:", json.dumps(load()))


asyncio.run(main())
