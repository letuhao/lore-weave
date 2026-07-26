"""9/9 payoff — steps 8 (enrich) + 9 (write a chapter) THROUGH THE GATEWAY.

Step 8: lore_enrichment_auto_enrich (Tier-A, owner identity from the envelope) → enqueues
   an async enrichment job → QUARANTINED proposals. M3's grant gate lets the owner through.
Step 9: composition_generate (Tier-W propose → composition confirm) → the cowrite engine
   drafts + persists a new chapter to the book draft, in-process.
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
H = {"X-Internal-Token": TOKEN, "X-User-Id": USER, "X-Session-Id": "run99",
     "X-Project-Id": PROJECT}


def bearer():
    n = int(time.time())
    return jwt.encode({"sub": USER, "iat": n, "exp": n + 3600}, SECRET, algorithm="HS256")


def _p(res):
    if getattr(res, "isError", False):
        raise RuntimeError(f"tool error: {res.content[0].text if res.content else '?'}")
    return json.loads(res.content[0].text)


async def main():
    bearer_jwt = bearer()
    # Step 9 needs a chapter shell first (the author would add the empty chapter).
    print("=== prep: create a NEW book chapter for step 9 ===")
    async with httpx.AsyncClient(timeout=60) as c:
        cr = await c.post(
            f"http://book-service:8082/v1/books/{BOOK}/chapters",
            headers={"Authorization": f"Bearer {bearer_jwt}", "Content-Type": "application/json"},
            json={"title": "Chapter II — The Pass", "original_language": "en",
                  "sort_order": 80, "body": ""},
        )
    cr.raise_for_status()
    chapter_id = cr.json()["chapter_id"]
    print("  book chapter_id:", chapter_id)

    async with streamablehttp_client(GW, headers=H) as (r, w, _):
        async with ClientSession(r, w) as s:
            await s.initialize()

            print("=== STEP 8: lore_enrichment_auto_enrich (owner, via gateway) ===")
            en = _p(await s.call_tool("lore_enrichment_auto_enrich", {
                "project_id": PROJECT,
                "args": {"book_id": BOOK, "embedding_model_ref": EMB,
                         "generation_model_ref": GEN, "max_gaps": 3},
            }))
            print("  enrich:", json.dumps(en)[:240])

            print("=== STEP 9: composition_generate (via gateway) ===")
            await s.call_tool("composition_create_work", {"project_id": PROJECT, "book_id": BOOK})
            chap = _p(await s.call_tool("composition_outline_node_create", {"args": {
                "project_id": PROJECT, "kind": "chapter", "chapter_id": chapter_id,
                "title": "Chapter II — The Pass", "goal": "Harker journeys to the Borgo Pass",
            }}))
            _p(await s.call_tool("composition_outline_node_create", {"args": {
                "project_id": PROJECT, "kind": "scene", "parent_id": chap["id"],
                "chapter_id": chapter_id, "status": "done",
                "title": "The coach to the pass",
                "goal": "Harker rides toward the Borgo Pass as dusk falls",
                "synopsis": "Gothic dread builds as the Count's land nears.",
            }}))
            gp = _p(await s.call_tool("composition_generate", {"args": {
                "project_id": PROJECT, "chapter_id": chapter_id,
                "model_source": "user_model", "model_ref": GEN,
                "guide": "Write in Bram Stoker's gothic first-person voice.",
            }}))
            token = gp["confirm_token"]
            print("  generate descriptor:", gp.get("descriptor"), "token:", bool(token))

    print("  confirm (runs the cowrite engine in-process; gemma drafts)...")
    async with httpx.AsyncClient(timeout=600) as c:
        resp = await c.post(
            "http://composition-service:8093/v1/composition/actions/confirm",
            params={"token": token},
            headers={"X-Internal-Token": TOKEN, "X-User-Id": USER},
        )
    body = resp.json()
    gen = body.get("generation", {})
    text = gen.get("text", "")
    print("  confirm:", resp.status_code, "status:", gen.get("status"),
          "persisted:", gen.get("persisted"), "draft_version:", gen.get("draft_version"),
          "chars:", len(text))
    print("  --- generated prose (first 320 chars) ---")
    print("  " + text[:320].replace("\n", " "))


asyncio.run(main())
