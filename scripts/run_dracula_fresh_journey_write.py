"""Fresh Dracula journey phase 7 — enrichment + write a new chapter THROUGH THE GATEWAY.

Reads /app/scenario_state.json (book_id, project_id from earlier phases). Exercises
M3 (owner-gated lore_enrichment_auto_enrich) + composition_generate (the cowrite engine
reached in-process via propose->confirm).
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


async def main():
    st = load()
    book = st["book_id"]
    project = st["project_id"]
    H = {"X-Internal-Token": TOKEN, "X-User-Id": USER, "X-Session-Id": "fresh-write",
         "X-Project-Id": project}
    bj = bearer()

    # New chapter shell for the writing assistant to fill.
    print("== prep: create a NEW book chapter ==")
    async with httpx.AsyncClient(timeout=60) as c:
        cr = await c.post(
            f"http://book-service:8082/v1/books/{book}/chapters",
            headers={"Authorization": f"Bearer {bj}", "Content-Type": "application/json"},
            json={"title": "Chapter II — The Journey Onward", "original_language": "en",
                  "sort_order": 50, "body": ""})
    cr.raise_for_status()
    chapter_id = cr.json()["chapter_id"]
    print("  new chapter_id:", chapter_id)

    async with streamablehttp_client(GW, headers=H) as (r, w, _):
        async with ClientSession(r, w) as s:
            await s.initialize()

            # ── 7a — enrichment (M3 owner-gated) ──────────────────────────────
            print("== 7a: lore_enrichment_auto_enrich ==")
            en = _p(await s.call_tool("lore_enrichment_auto_enrich", {
                "project_id": project,
                "args": {"book_id": book, "embedding_model_ref": EMB,
                         "generation_model_ref": GEN, "max_gaps": 3}}))
            print("  enrich:", json.dumps(en)[:240])
            st["enrich_job"] = en.get("job_id")
            save(st)

            # ── 7b — write a new chapter (composition_generate) ───────────────
            print("== 7b: composition_generate ==")
            await s.call_tool("composition_create_work", {"project_id": project, "book_id": book})
            chap = _p(await s.call_tool("composition_outline_node_create", {"args": {
                "project_id": project, "kind": "chapter", "chapter_id": chapter_id,
                "title": "Chapter II — The Journey Onward",
                "goal": "Harker continues toward the Count's castle"}}))
            _p(await s.call_tool("composition_outline_node_create", {"args": {
                "project_id": project, "kind": "scene", "parent_id": chap["id"],
                "chapter_id": chapter_id, "status": "done",
                "title": "The road to the Borgo Pass",
                "goal": "Harker rides into the Carpathians as night falls",
                "synopsis": "Mounting gothic dread as the Count's land nears."}}))
            gp = _p(await s.call_tool("composition_generate", {"args": {
                "project_id": project, "chapter_id": chapter_id,
                "model_source": "user_model", "model_ref": GEN,
                "guide": "Write in Bram Stoker's gothic first-person voice."}}))
            token = gp["confirm_token"]
            print("  generate descriptor:", gp.get("descriptor"))

    print("  confirm (runs the cowrite engine in-process)...")
    async with httpx.AsyncClient(timeout=600) as c:
        resp = await c.post(
            "http://composition-service:8093/v1/composition/actions/confirm",
            params={"token": token},
            headers={"X-Internal-Token": TOKEN, "X-User-Id": USER})
    body = resp.json()
    gen = body.get("generation", {})
    text = gen.get("text", "")
    print("  confirm:", resp.status_code, "status:", gen.get("status"),
          "persisted:", gen.get("persisted"), "draft_version:", gen.get("draft_version"),
          "chars:", len(text))
    print("  --- generated prose (first 300 chars) ---")
    print("  " + text[:300].replace("\n", " "))
    st["wrote_chapter"] = chapter_id
    save(st)
    print("PHASE 7 STATE:", json.dumps(load()))


asyncio.run(main())
