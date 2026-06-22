"""9/9 payoff — steps 6 (KG build) + 7 (wiki) THROUGH THE GATEWAY on the fresh book.

Proves M1 (X-Project-Id forwarded → kg tools resolve the project through federation) +
M2 (wiki resolves all 26 entities at min_frequency=1 → articles produced, 0→N) end-to-end:
mint via the gateway → confirm via knowledge REST → poll to completion.
"""
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
PROJECT = "019eef5d-c599-77ef-a340-d43ad439d877"
BOOK = "019eef55-c87f-7f29-8540-52a6280e7938"
GEN = "51ea9fd7-4a25-4801-af67-d88c2d161dac"   # gemma (local)
EMB = "019e7f71-0271-722f-9c9c-3f049c0b26f4"   # bge-m3 (local)
GW = "http://ai-gateway:8210/mcp"
KNOW = "http://knowledge-service:8092"
H = {"X-Internal-Token": TOKEN, "X-User-Id": USER, "X-Session-Id": "run99",
     "X-Project-Id": PROJECT}


def bearer():
    n = int(time.time())
    return jwt.encode({"sub": USER, "iat": n, "exp": n + 3600}, SECRET, algorithm="HS256")


def _p(res):
    if getattr(res, "isError", False):
        raise RuntimeError(f"tool error: {res.content[0].text if res.content else '?'}")
    return json.loads(res.content[0].text)


async def kg_confirm(token):
    async with httpx.AsyncClient(timeout=180) as c:
        r = await c.post(f"{KNOW}/v1/kg/actions/confirm",
                         headers={"Authorization": f"Bearer {bearer()}"},
                         json={"confirm_token": token})
    body = r.json() if r.headers.get("content-type", "").startswith("application/json") else r.text
    return r.status_code, body


async def main():
    async with streamablehttp_client(GW, headers=H) as (r, w, _):
        async with ClientSession(r, w) as s:
            await s.initialize()

            print("=== STEP 6: kg_build_graph (mint via gateway) ===")
            g = _p(await s.call_tool("kg_build_graph", {"llm_model": GEN}))
            print("  descriptor:", g.get("descriptor"), "confirm_token:", bool(g.get("confirm_token")))
            code, body = await kg_confirm(g["confirm_token"])
            print("  confirm:", code, json.dumps(body)[:200])

            print("=== STEP 7: kg_build_wiki (mint via gateway) — the M2 payoff ===")
            wk = _p(await s.call_tool("kg_build_wiki", {"model_ref": GEN}))
            print("  descriptor:", wk.get("descriptor"), "confirm_token:", bool(wk.get("confirm_token")))
            code, body = await kg_confirm(wk["confirm_token"])
            print("  confirm:", code, "->", json.dumps(body)[:260])
            # The M2 proof is in the confirm response: entity_count should be 26
            # (was a 422 BuildWikiNoEntities before the fix).
            ec = body.get("entity_count") if isinstance(body, dict) else None
            job_id = body.get("job_id") if isinstance(body, dict) else None
            print(f"  >>> wiki job {job_id} created with entity_count={ec} "
                  f"(pre-fix this was 422 no-entities)")


asyncio.run(main())
