# Plan — Public MCP edge scope filter (H-E / H-F / OD-5)

- **Date:** 2026-06-27 · branch `feat/public-mcp-gateway` · size **L** (security-critical → /review-impl at POST-REVIEW)
- **Spec:** [03 §PUB-3/H-E/H-F](../specs/2026-06-26-public-mcp/03-public-mcp-security-design.md) · [04 §P2](../specs/2026-06-26-public-mcp/04-implementation-plan.md) · [05 tool-scope-map §2](../specs/2026-06-26-public-mcp/05-tool-scope-map.md)
- **PO decisions (CLARIFY):** FULL slice (edge filter + FE domain pickers + OD-5 default); **fail-closed** when a key holds no `domain:*` scope (deny all).

## Goal
The public edge advertises (`tools/list`) and permits (`tools/call`) **only** tools whose **tier scope ∩ every domain it touches** are held by the key. Unknown tools **default-deny** (H-E). Domains classified by **tools-touched, not prefix** (H-F). A user can grant domain scopes from the Settings → MCP create dialog; new keys default to `read` on `book+glossary+knowledge` (OD-5).

## Scope model (LOCKED by spec D3)
`scopes[]` is a flat array mixing **tier scopes** (`read`,`paid_read`,`write_auto`,`write_confirm`) and **domain scopes** (`domain:book`,`domain:glossary`,…). A tool is callable iff key holds `policy.tier` **and** `domain:<d>` for every `d ∈ policy.domains`. `*` scope (dev key) bypasses. auth-service `scopes TEXT[]` already stores these verbatim — **no auth change**.

## Edge (`services/mcp-public-gateway`)
1. **`src/scope/tool-policy.ts`** — `Tier`,`Domain` types; `TOOL_POLICY: Record<name,{tier,domains[]}>` allowlist from scope-map §2 (read + paid_read + write_auto + write_confirm), with H-F cross-domain (`translation_start_extraction`→[translation,glossary]; `composition_generate`→[composition,glossary,knowledge]; `lore_enrichment_auto_enrich`→[lore_enrichment,glossary,knowledge]) and `jobs`/`settings` as their own explicit domain. Helpers: `isToolAllowed(name,scopes)` (default-deny + `*` bypass), `filterTools(tools,scopes)`, `knownTool(name)`. Ungrantable tools (admin/secret/delete/purge) are simply **absent** → denied.
2. **`src/scope/scope-filter.ts`** — `gateRequestBody(body,scopes)` returns a JSON-RPC error response (or `null`=allow) for any `tools/call` to a disallowed tool, handling single + batch; `filterListResponseText(text,scopes,log)` parses the JSON response, filters `result.tools` (single + batch array), logs ai-gateway tools absent from the policy table (drift signal), fail-closed on unparseable list responses.
3. **`public-mcp.controller.ts`** — after resolve: gate the request body (deny → return error, no relay, H-E); relay; if the request was `tools/list`, rewrite the response via the filter. `*` scope skips both.

## FE (`frontend/src/features/settings`)
4. **`api.ts`** — add `MCP_DOMAINS` (book,glossary,knowledge,translation,composition,jobs,settings,lore_enrichment) + `domainScope()` helper; create payload composes `[...tierScopes, ...domains.map(domain:)]`.
5. **`McpCreateKeyDialog.tsx`** — domain multiselect, default `book+glossary+knowledge`; compose into `scopes` on submit. Tier default stays `read` (Wave-A safe).
6. **`McpAccessTab.tsx`** — render tier vs domain scopes as separate chip groups.
7. **i18n ×4** (en/vi/ja/zh-TW) — domain labels + section heading.

## Tests
- Edge unit (vitest): `isToolAllowed` default-deny (unknown→false), `*` bypass, tier-miss, domain-miss, cross-domain (needs both), fail-closed no-domain; `filterTools` strips out-of-scope; `gateRequestBody` denies disallowed call + allows in-scope + batch; `filterListResponseText` filters + drift-log + fail-closed parse error.
- FE vitest: domain default selected; scopes composed `domain:*` on submit; chips render.

## DoD
- `read`-only key (no domain) → sees **no** tools (fail-closed) ✓; with `domain:knowledge` read → sees only knowledge reads, `tools/call book_get`→denied ✓.
- unknown tool name → denied (H-E) ✓.
- cross-domain tool needs both domain scopes ✓.

## Out of scope (deferred)
- Idempotency keys (H-G) — per-provider P2 fanout.
- Spend/`incurs_cost` gate (PUB-10/12) — P3.
- Live cross-tenant stack smoke — fold into `D-PMCP-P2-LIVE-SMOKE`.
