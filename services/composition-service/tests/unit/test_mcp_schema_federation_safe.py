"""Federation-safety guard for composition-service's advertised MCP schemas.

A boolean subschema (JSON Schema's `true`/`false`-as-a-whole-schema) is legal JSON
Schema that ai-gateway's federation validator REJECTS — and the blast radius is the
PROVIDER, not the tool: the whole `tools/list` response fails, so every sibling tool
disappears from the catalog. It shipped for real on 2026-07-23 (`glossary_curation_list`
typed a union payload as `any`) and erased all 54 glossary tools; nothing caught it,
because the schema is valid in isolation and only breaks at the cross-service,
cross-language boundary.

Go enforces this at registration (loreweave_mcp.RegisterTool panics). FastMCP has no
equivalent shared chokepoint, so each Python provider asserts it here.
"""

from __future__ import annotations

from loreweave_mcp.schema_federation import assert_no_boolean_subschemas


async def test_advertised_schemas_are_federation_safe():
    from app.mcp.server import mcp_server

    tools = await mcp_server.list_tools()
    assert tools, "tools/list returned an empty catalog"
    assert_no_boolean_subschemas(tools)
