"""Federation prefix-drop guard (Track A gap closed from Track D · WS-D5-followups).

THE BUG THIS CATCHES. `ai-gateway`'s `computeCatalog` (services/ai-gateway/src/federation/
catalog.ts:71) DROPS any tool whose name doesn't start with one of its provider's allowed
prefixes (`provider.prefix` + `EXTRA_PREFIX_MAP`). It once silently dropped `world_*`, `lore_*`,
and `story_search` — each present in its service's own `/mcp` tools/list but ABSENT from the
federated catalog, so no agent could ever see them, with no error anywhere.

`providers.spec.ts` guards the static config MAP and book-service has an in-process test for its
OWN advertisement (book_/world_), but NOTHING checked the *general* invariant across every
federated provider. This does: it compares each provider's raw `/mcp` tools/list against the
assembled federated catalog and fails if any (non-legacy) provider tool was dropped — the exact
"served-but-not-federated" signature, without hard-coding the prefix map.

LIVE test — skips if the stack isn't reachable (same discipline as the sweep).
"""
from __future__ import annotations

import asyncio

import pytest

try:
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client

    from tool_liveness import config
    from tool_liveness.sweep import _HEADERS
    _IMPORTS_OK = True
except Exception:  # pragma: no cover - environment without the MCP SDK
    _IMPORTS_OK = False


async def _tools_at(url: str) -> list[dict]:
    async with streamablehttp_client(url, headers=_HEADERS) as (r, w, _):
        async with ClientSession(r, w) as s:
            await s.initialize()
            res = await s.list_tools()
            return [{"name": t.name, "meta": (getattr(t, "meta", None) or {})} for t in res.tools]


async def _gather() -> tuple[set[str], dict[str, list[dict]]]:
    federated = {t["name"] for t in await _tools_at(config.AI_GATEWAY_MCP)}
    per_provider: dict[str, list[dict]] = {}
    for name, base in config.DOMAIN_BASE.items():
        per_provider[name] = await _tools_at(f"{base}/mcp")
    return federated, per_provider


@pytest.mark.skipif(not _IMPORTS_OK, reason="MCP SDK / harness not importable")
def test_no_provider_tool_is_silently_dropped_by_the_gateway():
    """Every tool a provider SERVES must appear in the federated catalog — else the gateway's
    prefix filter dropped it silently (the world_*/lore_*/story_search class). Legacy tools are
    exempt (they may be hidden by design)."""
    try:
        federated, per_provider = asyncio.run(asyncio.wait_for(_gather(), timeout=30))
    except Exception as e:  # stack down / unreachable → not this test's failure to report
        pytest.skip(f"live stack unreachable: {type(e).__name__}: {e}")

    dropped: dict[str, list[str]] = {}
    for provider, tools in per_provider.items():
        missing = [
            t["name"] for t in tools
            if t["name"] not in federated
            and (t.get("meta") or {}).get("visibility") != "legacy"
        ]
        if missing:
            dropped[provider] = sorted(missing)

    assert not dropped, (
        "gateway silently DROPPED provider tools (served on the provider's /mcp but absent from "
        f"the federated catalog): {dropped}. A provider serves a tool whose prefix isn't in its "
        "ai-gateway allowed set (config.ts DEFAULT_PREFIX_MAP + EXTRA_PREFIX_MAP) — add the prefix, "
        "or the agent can never see the tool. This is the world_*/lore_*/story_search bug class."
    )
