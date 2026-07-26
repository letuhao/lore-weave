"""Fresh Dracula journey phase 6 — KG build + wiki THROUGH THE GATEWAY.

Exercises M1 (X-Project-Id forwarded so kg tools resolve the project), the benchmark-UX
fix (kg_run_benchmark on a hidden sandbox), and M2 (wiki resolves entities at
min_frequency=1 → articles on a 1-chapter book). Reads /app/scenario_state.json from
phases 1-5; persists project_id.
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
GEN = "51ea9fd7-4a25-4801-af67-d88c2d161dac"   # gemma
EMB = "019e7f71-0271-722f-9c9c-3f049c0b26f4"   # bge-m3
GW = "http://ai-gateway:8210/mcp"
KNOW = "http://knowledge-service:8092"
STATE = "/app/scenario_state.json"


def bearer():
    n = int(time.time())
    return jwt.encode({"sub": USER, "iat": n, "exp": n + 3600}, SECRET, algorithm="HS256")


def load():
    with open(STATE) as f:
        return json.load(f)


def save(st):
    with open(STATE, "w") as f:
        json.dump(st, f, indent=1)


def _p(res):
    if getattr(res, "isError", False):
        raise RuntimeError(f"tool error: {res.content[0].text if res.content else '?'}")
    return json.loads(res.content[0].text)


def _err(res):
    return res.content[0].text if getattr(res, "content", None) else "?"


def hdrs(project_id=None):
    h = {"X-Internal-Token": TOKEN, "X-User-Id": USER, "X-Session-Id": "fresh-kg"}
    if project_id:
        h["X-Project-Id"] = project_id  # M1 — the gateway forwards this downstream
    return h


async def kg_confirm(token):
    async with httpx.AsyncClient(timeout=180) as c:
        r = await c.post(f"{KNOW}/v1/kg/actions/confirm",
                         headers={"Authorization": f"Bearer {bearer()}"},
                         json={"confirm_token": token})
    ct = r.headers.get("content-type", "")
    return r.status_code, (r.json() if ct.startswith("application/json") else r.text)


async def main():
    st = load()
    book = st["book_id"]

    # ── 6a — create the KG project bound to the book (no X-Project-Id needed) ──
    if not st.get("project_id"):
        print("== 6a: create KG project ==")
        async with streamablehttp_client(GW, headers=hdrs()) as (r, w, _):
            async with ClientSession(r, w) as s:
                await s.initialize()
                res = _p(await s.call_tool("kg_project_create", {
                    "name": "Dracula KG (fresh journey)", "book_id": book,
                    "project_type": "book", "description": "agent-driven KG", "genre": "gothic"}))
        st["project_id"] = res.get("project_id") or res.get("id")
        save(st)
    project = st["project_id"]
    print("project_id:", project)

    # ── 6b — set the project's embedding model (bge-m3), confirm=true ──────────
    if not st.get("embed_set"):
        print("== 6b: set embedding model (bge-m3) ==")
        async with httpx.AsyncClient(timeout=60) as c:
            rr = await c.put(f"{KNOW}/v1/knowledge/projects/{project}/embedding-model?confirm=true",
                             headers={"Authorization": f"Bearer {bearer()}"},
                             json={"embedding_model": EMB})
        print("  embedding-model PUT:", rr.status_code, json.dumps(rr.json())[:160])
        st["embed_set"] = True
        save(st)

    async with streamablehttp_client(GW, headers=hdrs(project)) as (r, w, _):
        async with ClientSession(r, w) as s:
            await s.initialize()

            # ── 6c — run the benchmark via the NEW MCP tool (hidden sandbox) ───
            if not st.get("benchmark_passed"):
                print("== 6c: kg_run_benchmark (sandbox) ==")
                res = await s.call_tool("kg_run_benchmark", {})
                if getattr(res, "isError", False):
                    print("  benchmark ERROR:", _err(res)[:200])
                else:
                    bm = json.loads(res.content[0].text)
                    print("  benchmark:", json.dumps(bm)[:240])
                    if bm.get("passed"):
                        st["benchmark_passed"] = True; save(st)

            # ── 6d — kg_build_graph through the gateway ───────────────────────
            if not st.get("kg_built"):
                print("== 6d: kg_build_graph ==")
                # Only MINT a new build if one hasn't already run (idempotent resume).
                if not st.get("kg_job"):
                    g = _p(await s.call_tool("kg_build_graph", {"llm_model": GEN}))
                    print("  build_graph mint:", "token" if g.get("confirm_token") else json.dumps(g)[:200])
                    if g.get("confirm_token"):
                        code, body = await kg_confirm(g["confirm_token"])
                        print("  build_graph confirm:", code, json.dumps(body)[:200])
                        st["kg_job"] = (body or {}).get("job_id") if isinstance(body, dict) else None
                        save(st)
                # poll: extraction_status=ready is the done signal (stat_entity_count is a
                # separate projection that lags / stays null — the actual graph lands in Neo4j).
                for i in range(60):
                    async with httpx.AsyncClient(timeout=30) as c:
                        rr = await c.get(
                            f"{KNOW}/v1/knowledge/projects/{project}",
                            headers={"Authorization": f"Bearer {bearer()}"})
                    statu = rr.json().get("extraction_status") if rr.status_code == 200 else "?"
                    print(f"  [kg] {i}: extraction_status={statu}")
                    if statu == "ready":
                        st["kg_built"] = True; save(st); break
                    if statu in ("failed", "disabled"):
                        print("  kg stopped at", statu); break
                    await asyncio.sleep(10)

            # ── 6e — kg_build_wiki through the gateway (M2 payoff) ─────────────
            if st.get("kg_built") and not st.get("wiki_started"):
                print("== 6e: kg_build_wiki (M2) ==")
                wk = _p(await s.call_tool("kg_build_wiki", {"model_ref": GEN}))
                print("  build_wiki mint:", "token" if wk.get("confirm_token") else json.dumps(wk)[:200])
                if wk.get("confirm_token"):
                    code, body = await kg_confirm(wk["confirm_token"])
                    print("  build_wiki confirm:", code, "->", json.dumps(body)[:240])
                    if isinstance(body, dict):
                        st["wiki_job"] = body.get("job_id")
                        st["wiki_entity_count"] = body.get("entity_count")
                    st["wiki_started"] = True
                    save(st)

    print("PHASE 6 STATE:", json.dumps(load()))


asyncio.run(main())
