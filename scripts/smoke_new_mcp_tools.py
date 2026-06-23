"""Live MCP smoke — confirm the two new agent tools are present + mint cleanly.

Run INSIDE the docker network (e.g. `docker compose exec composition-service
python /app/smoke_new_mcp_tools.py`). Lists tools on both /mcp facades over the
real streamable-HTTP wire and asserts the new tools appear.
"""
import asyncio
import os
import sys

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

TOKEN = os.environ["INTERNAL_SERVICE_TOKEN"]
USER = "019d5e3c-7cc5-7e6a-8b27-1344e148bf7c"  # claude-test


async def list_tools(url: str) -> set[str]:
    headers = {"X-Internal-Token": TOKEN, "X-User-Id": USER, "X-Session-Id": "smoke-1"}
    async with streamablehttp_client(url, headers=headers) as (r, w, _):
        async with ClientSession(r, w) as s:
            await s.initialize()
            listing = await s.list_tools()
            return {t.name for t in listing.tools}


async def main() -> int:
    comp = await list_tools("http://composition-service:8093/mcp")
    lore = await list_tools("http://lore-enrichment-service:8093/mcp")
    print("composition tools:", sorted(comp))
    print("lore-enrichment tools:", sorted(lore))
    ok = True
    if "composition_generate" not in comp:
        print("FAIL: composition_generate missing"); ok = False
    if "lore_enrichment_auto_enrich" not in lore:
        print("FAIL: lore_enrichment_auto_enrich missing"); ok = False
    print("RESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


sys.exit(asyncio.run(main()))
