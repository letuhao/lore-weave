"""Agent-driven Dracula MCP scenario — phase 9: write a NEW chapter on the FRESH
book via composition_generate (run inside the docker net). Reads scenario_state.json.
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
GEN = "51ea9fd7-4a25-4801-af67-d88c2d161dac"
GW = "http://ai-gateway:8210/mcp"
H = {"X-Internal-Token": TOKEN, "X-User-Id": USER, "X-Session-Id": "scenario3"}
STATE = "/app/scenario_state.json"
BOOK_SVC = "http://book-service:8082"
COMP = "http://composition-service:8093"


def bearer():
    n = int(time.time()); return jwt.encode({"sub": USER, "iat": n, "exp": n + 600}, SECRET, algorithm="HS256")


def _p(res):
    if getattr(res, "isError", False):
        raise RuntimeError(f"tool error: {res.content[0].text if res.content else '?'}")
    return json.loads(res.content[0].text)


async def main():
    st = json.load(open(STATE))
    book, proj = st["book_id"], st["kg_project"]
    print("book", book, "project", proj)

    async with httpx.AsyncClient(timeout=60) as c:
        cr = await c.post(f"{BOOK_SVC}/v1/books/{book}/chapters",
                          headers={"Authorization": f"Bearer {bearer()}", "Content-Type": "application/json"},
                          json={"title": "Chapter II — The Escape", "original_language": "en",
                                "sort_order": 10, "body": ""})
    cr.raise_for_status()
    chapter_id = cr.json()["chapter_id"]
    print("new chapter_id:", chapter_id)

    async with streamablehttp_client(GW, headers=H) as (r, w, _):
        async with ClientSession(r, w) as s:
            await s.initialize()
            await s.call_tool("composition_create_work", {"project_id": proj, "book_id": book})
            chap = _p(await s.call_tool("composition_outline_node_create", {"args": {
                "project_id": proj, "kind": "chapter", "chapter_id": chapter_id,
                "title": "Chapter II — The Escape", "goal": "Jonathan plots his escape from the castle"}}))
            scene = _p(await s.call_tool("composition_outline_node_create", {"args": {
                "project_id": proj, "kind": "scene", "parent_id": chap["id"], "chapter_id": chapter_id,
                "status": "done", "title": "The locked door",
                "goal": "Jonathan realises he is a prisoner and resolves to escape",
                "synopsis": "Gothic dread; the Count's true nature dawns."}}))
            print("chapter node:", chap["id"], "scene node:", scene["id"])
            gp = _p(await s.call_tool("composition_generate", {"args": {
                "project_id": proj, "chapter_id": chapter_id,
                "model_source": "user_model", "model_ref": GEN,
                "guide": "Write in Bram Stoker's gothic first-person voice."}}))
            token = gp["confirm_token"]
            print("propose descriptor:", gp["descriptor"])

    async with httpx.AsyncClient(timeout=600) as c:
        resp = await c.post(f"{COMP}/v1/composition/actions/confirm",
                            params={"token": token},
                            headers={"X-Internal-Token": TOKEN, "X-User-Id": USER})
    body = resp.json()
    gen = body.get("generation", {})
    text = gen.get("text", "")
    print("confirm:", resp.status_code, "persisted:", gen.get("persisted"),
          "draft_version:", gen.get("draft_version"), "status:", gen.get("status"))
    print("=== PROSE (first 700) ===")
    print(text[:700])
    assert resp.status_code == 200 and len(text) > 80, f"generate failed: {body}"
    json.dump({**st, "wrote_chapter": chapter_id}, open(STATE, "w"), indent=1)
    print("RESULT: PASS")


asyncio.run(main())
