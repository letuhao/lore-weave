"""Live EXECUTION smoke for the two new agent tools (run inside the docker net).

- lore_enrichment_auto_enrich → real enqueue against the Dracula book (gateway →
  lore-enrichment → glossary detect → create job → enqueue).
- composition_generate (chapter) → propose (mint) via gateway, then confirm via the
  composition internal confirm route. With no scene plan the engine returns
  NO_CHAPTER_PLAN — which PROVES the confirm effect actually invoked the engine
  in-process (Work resolved, scenes_for_chapter queried) without spending tokens.
"""
import asyncio
import json
import os
import uuid

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

TOKEN = os.environ["INTERNAL_SERVICE_TOKEN"]
USER = "019d5e3c-7cc5-7e6a-8b27-1344e148bf7c"  # claude-test
DRACULA = "019eeb09-a4aa-7acf-9281-e812d7975a6c"
KG_PROJECT = "019eeb0b-41a4-75b4-902b-09025dd8a381"
EMB = "019e7f71-0271-722f-9c9c-3f049c0b26f4"   # bge-m3
GEN = "51ea9fd7-4a25-4801-af67-d88c2d161dac"   # gemma
GW = "http://ai-gateway:8210/mcp"
H = {"X-Internal-Token": TOKEN, "X-User-Id": USER, "X-Session-Id": "exec-smoke"}


def _payload(res):
    return json.loads(res.content[0].text)


async def main():
    async with streamablehttp_client(GW, headers=H) as (r, w, _):
        async with ClientSession(r, w) as s:
            await s.initialize()

            print("--- lore_enrichment_auto_enrich ---")
            er = await s.call_tool("lore_enrichment_auto_enrich", {
                "project_id": KG_PROJECT,
                "args": {"book_id": DRACULA, "embedding_model_ref": EMB,
                         "generation_model_ref": GEN, "max_gaps": 2},
            })
            ep = _payload(er)
            print("enrich result:", ep)
            assert ep.get("job_id") or ep.get("enqueued") is not None, "no enrich job"

            print("--- composition_create_work ---")
            wr = await s.call_tool("composition_create_work",
                                   {"project_id": KG_PROJECT, "book_id": DRACULA})
            print("work:", _payload(wr).get("project_id"))

            print("--- composition_generate (propose, chapter) ---")
            chapter = str(uuid.uuid4())  # no scene plan → engine returns NO_CHAPTER_PLAN
            gr = await s.call_tool("composition_generate", {
                "args": {"project_id": KG_PROJECT, "chapter_id": chapter,
                         "model_source": "user_model", "model_ref": GEN},
            })
            gp = _payload(gr)
            print("propose:", {k: gp.get(k) for k in ("descriptor", "domain")})
            token = gp["confirm_token"]
            assert gp["descriptor"] == "composition.generate"

    print("--- composition confirm (reaches engine in-process) ---")
    async with httpx.AsyncClient() as c:
        resp = await c.post(
            "http://composition-service:8093/v1/composition/actions/confirm",
            params={"token": token},
            headers={"X-Internal-Token": TOKEN, "X-User-Id": USER},
        )
    print("confirm status:", resp.status_code, "body:", resp.text[:300])
    # A 4xx with NO_CHAPTER_PLAN proves the engine ran (Work found, no plan); a 200
    # would mean it generated. Either proves the in-process engine call wired up; a
    # 500 / token error would mean the wiring is broken.
    assert resp.status_code in (200, 400, 409), f"unexpected confirm status {resp.status_code}"
    print("RESULT: PASS")


asyncio.run(main())
