"""Live-smoke for the agent-journey-gaps batch (M1/M3/M4) THROUGH THE GATEWAY.

Run inside a container that has the `mcp` client + httpx + the internal token and
network to ai-gateway (e.g. infra-knowledge-service-1). Proves:

  M1 (D-GW-XPROJECT-NOT-FORWARDED): kg_build_graph + kg_build_wiki MINT through the
     gateway with X-Project-Id set → a confirm_token comes back, NOT the old
     "no project in scope" refusal. (M2's entity-resolution is proven separately by
     the direct known-entities min_frequency probe.)
  M3 (D-ENRICH-MCP-OWNER-GATE): lore_enrichment_auto_enrich through the gateway with
     a FOREIGN (random) book_id → 404 (the grant gate denies; never an existence
     oracle). Proven end-to-end through the gateway envelope identity.
  M4 (D-COMPOSE-GENERATE-WORKER-POLL): composition_get_generation_job appears in the
     federated catalogue through the gateway.
"""
import asyncio
import json
import os
import uuid

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

TOKEN = os.environ["INTERNAL_SERVICE_TOKEN"]
USER = "019d5e3c-7cc5-7e6a-8b27-1344e148bf7c"
PROJECT = "019eef5d-c599-77ef-a340-d43ad439d877"
BOOK = "019eef55-c87f-7f29-8540-52a6280e7938"
GEN = "51ea9fd7-4a25-4801-af67-d88c2d161dac"  # gemma
EMB = "019e7f71-0271-722f-9c9c-3f049c0b26f4"  # bge-m3
GW = "http://ai-gateway:8210/mcp"
# The gateway lifts identity + project scope off these headers (M1 forwards X-Project-Id).
H = {"X-Internal-Token": TOKEN, "X-User-Id": USER, "X-Session-Id": "gaps-batch",
     "X-Project-Id": PROJECT}


def _txt(res):
    return res.content[0].text if res.content else ""


def _json(res):
    return json.loads(_txt(res))


async def main():
    failures = []
    async with streamablehttp_client(GW, headers=H) as (r, w, _):
        async with ClientSession(r, w) as s:
            await s.initialize()
            listing = await s.list_tools()
            names = {t.name for t in listing.tools}

            # ── M4: the new poll tool is federated ──────────────────────────
            ok = "composition_get_generation_job" in names
            print(f"[M4] composition_get_generation_job federated: {ok} "
                  f"({len(names)} tools total)")
            if not ok:
                failures.append("M4: poll tool missing from federated catalogue")

            # ── M1: kg tools MINT through the gateway (X-Project-Id resolves) ─
            for tool, payload in (
                ("kg_build_graph", {"llm_model": GEN}),
                ("kg_build_wiki", {"model_ref": GEN}),
            ):
                res = await s.call_tool(tool, payload)
                if getattr(res, "isError", False):
                    print(f"[M1] {tool} -> ERROR: {_txt(res)[:160]}")
                    failures.append(f"M1: {tool} errored through gateway: {_txt(res)[:80]}")
                    continue
                body = _json(res)
                got_token = bool(body.get("confirm_token"))
                no_scope = "no project in scope" in json.dumps(body).lower()
                print(f"[M1] {tool} -> confirm_token={got_token} "
                      f"descriptor={body.get('descriptor')} no_project_in_scope={no_scope}")
                if not got_token or no_scope:
                    failures.append(f"M1: {tool} did not mint through gateway: {body}")

            # ── M3: enrich gate denies a foreign book through the gateway ────
            foreign = str(uuid.uuid4())
            res = await s.call_tool("lore_enrichment_auto_enrich", {
                "project_id": PROJECT,
                "args": {"book_id": foreign, "embedding_model_ref": EMB,
                         "generation_model_ref": GEN, "max_gaps": 1},
            })
            body = _json(res) if not getattr(res, "isError", False) else {"raw": _txt(res)}
            denied = (body.get("status") == 404) or ("404" in json.dumps(body))
            print(f"[M3] auto_enrich(foreign book) -> {body}")
            if not denied:
                failures.append(f"M3: foreign book NOT denied (expected 404): {body}")

    print("\n" + ("FAILURES:\n - " + "\n - ".join(failures) if failures else "RESULT: PASS"))
    if failures:
        raise SystemExit(1)


asyncio.run(main())
