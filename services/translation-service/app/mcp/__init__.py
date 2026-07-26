"""MCP fan-out S-TRANSL — translation-service `/mcp` provider facade.

Exposes the translation pipeline + job control as MCP tools (via the shared
`loreweave_mcp` kit) so a chat AI agent can drive translation from chat. Adds two
extras beyond a plain provider: a NEW cost-estimate (HIGH#1) and re-price-at-
execution (H14). Dual-run: the bespoke `/v1/translation` REST API is untouched.
"""
