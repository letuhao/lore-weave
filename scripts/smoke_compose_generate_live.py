"""Live step-11 proof — write a NEW chapter through the assistant (MCP), end to end.

Drives the grounded cowrite ENGINE via the new composition_generate tool on the
Dracula Work:
  1. create a NEW chapter in book-service (the shell the author would add),
  2. build its composition outline (chapter node + scene node) via MCP,
  3. propose generate (MCP, mints a composition.generate token),
  4. confirm (composition internal route) -> the confirm effect runs
     engine.generate_chapter(persist=True) in-process -> gemma drafts the whole
     chapter grounded in the Dracula canon -> persisted to the book draft.
Prints the generated prose.
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
BOOK = "019eeb09-a4aa-7acf-9281-e812d7975a6c"
KG_PROJECT = "019eeb0b-41a4-75b4-902b-09025dd8a381"
GEN = "51ea9fd7-4a25-4801-af67-d88c2d161dac"  # gemma
GW = "http://ai-gateway:8210/mcp"
H = {"X-Internal-Token": TOKEN, "X-User-Id": USER, "X-Session-Id": "gen-live"}


def _bearer() -> str:
    now = int(time.time())
    return jwt.encode({"sub": USER, "iat": now, "exp": now + 600}, SECRET, algorithm="HS256")


def _p(res):
    if getattr(res, "isError", False):
        raise RuntimeError(f"tool error: {res.content[0].text if res.content else '?'}")
    return json.loads(res.content[0].text)


async def main():
    bearer = _bearer()
    print("--- create NEW book chapter (book-service) ---")
    async with httpx.AsyncClient(timeout=60) as c:
        cr = await c.post(
            f"http://book-service:8082/v1/books/{BOOK}/chapters",
            headers={"Authorization": f"Bearer {bearer}", "Content-Type": "application/json"},
            json={"title": "Chapter V — The Escape", "original_language": "en",
                  "sort_order": 50, "body": ""},
        )
    cr.raise_for_status()
    chapter_id = cr.json()["chapter_id"]
    print("book chapter_id:", chapter_id)

    async with streamablehttp_client(GW, headers=H) as (r, w, _):
        async with ClientSession(r, w) as s:
            await s.initialize()
            await s.call_tool("composition_create_work", {"project_id": KG_PROJECT, "book_id": BOOK})
            print("--- chapter + scene outline nodes (MCP) ---")
            chap = _p(await s.call_tool("composition_outline_node_create", {"args": {
                "project_id": KG_PROJECT, "kind": "chapter", "chapter_id": chapter_id,
                "title": "Chapter V — The Escape", "goal": "Jonathan escapes Castle Dracula",
            }}))
            scene = _p(await s.call_tool("composition_outline_node_create", {"args": {
                "project_id": KG_PROJECT, "kind": "scene", "parent_id": chap["id"],
                "chapter_id": chapter_id, "status": "done",
                "title": "Harker's last night in the castle",
                "goal": "Jonathan resolves to climb down the castle wall as dawn nears",
                "synopsis": "Tense, gothic; the Count's threat closes in.",
            }}))
            print("chapter node:", chap["id"], "scene node:", scene["id"])

            print("--- propose generate (chapter) ---")
            gp = _p(await s.call_tool("composition_generate", {"args": {
                "project_id": KG_PROJECT, "chapter_id": chapter_id,
                "model_source": "user_model", "model_ref": GEN,
                "guide": "Write the chapter in Bram Stoker's gothic first-person voice.",
            }}))
            token = gp["confirm_token"]
            print("descriptor:", gp["descriptor"])

    print("--- confirm (runs the cowrite engine in-process; gemma drafts) ---")
    async with httpx.AsyncClient(timeout=600) as c:
        resp = await c.post(
            "http://composition-service:8093/v1/composition/actions/confirm",
            params={"token": token},
            headers={"X-Internal-Token": TOKEN, "X-User-Id": USER},
        )
    print("confirm status:", resp.status_code)
    body = resp.json()
    gen = body.get("generation", {})
    text = gen.get("text", "")
    print("job_id:", gen.get("job_id"), "status:", gen.get("status"),
          "persisted:", gen.get("persisted"), "draft_version:", gen.get("draft_version"),
          "grounding:", gen.get("grounding_available"), "canon:", (gen.get("canon") or {}).get("status"))
    print("=== GENERATED PROSE (first 900 chars) ===")
    print(text[:900])
    assert resp.status_code == 200, f"confirm failed: {body}"
    assert text and len(text) > 80, "no real prose generated"
    print("RESULT: PASS")


asyncio.run(main())
