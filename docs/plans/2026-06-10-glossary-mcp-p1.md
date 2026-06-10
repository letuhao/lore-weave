# glossary MCP read tools — P1 design + plan

- **Date:** 2026-06-10 · **Phase:** P1 of `2026-06-10-glossary-assistant-architecture.md` · **Size:** L
- **Goal:** glossary-service hosts a Go MCP server (official `modelcontextprotocol/go-sdk`, OD-1a) exposing Tier-R **read tools** with the ownership guard (INV-8); add glossary as ai-gateway **provider #2** → ship a read-only assistant.
- **PO (CLARIFY):** default v2.2 (no /amaw); suggest /review-impl at POST-REVIEW (ownership = security boundary).

## Verified building blocks (reuse, don't reinvent)
- `s.verifyBookOwner(w, ctx, bookID, userID)` — HTTP-coupled (writes to w). Fetches book-service projection, 403 on non-owner. → extract a non-HTTP core.
- `s.loadEntityDetail(ctx, bookID, entityID) (*entityDetailResp, error)` — already clean → `glossary_get_entity`.
- `s.internalSelectForContext` tier logic (pinned/exact/fts/recent, budgets) → extract `s.selectGlossaryForContext(...)` core → `glossary_search`.
- `s.listKinds` — kinds + attr defs are **GLOBAL** (no book_id) → extract `s.loadKinds(ctx)` → `glossary_list_kinds` (no ownership needed).
- `cfg.InternalServiceToken`, `cfg.BookServiceURL`; glossary listens `:8088`; Chi `srv.Router()`.

## Design

1. **MCP mount (`internal/api/mcp_server.go`)** — go-sdk `mcp.Server` with 3 `mcp.AddTool` handlers; `mcp.NewStreamableHTTPHandler(getServer, {Stateless:true, JSONResponse:true})`. An **identity middleware** validates `X-Internal-Token` (constant-time) → 401; lifts `X-User-Id` (+`X-Trace-Id`) into `ctx` (the proven §20 pattern — header→ctx works with go-sdk stateless). Mounted on Chi at `/mcp` in `server.go Router()`.

2. **Ownership guard (INV-8)** — new non-HTTP `s.checkBookOwnership(ctx, bookID, userID) error` returning sentinels:
   - `errNotAccessible` for **both** not-found and non-owner (uniform `GLOSS_NOT_ACCESSIBLE`, H13 — no enumeration oracle),
   - `errBookUnavailable` when book-service is down → **fail-closed** (deny).
   Backed by a **60s TTL cache** keyed `user:book → owned bool` (`sync.Map` + expiry). Only successes are cached; failures/unavailable are not. Reuses `fetchBookProjection`.

3. **Tools** (each: read `userID` from ctx; parse `book_id` arg; ownership; core):
   | Tool | Args | Core | Ownership |
   |---|---|---|---|
   | `glossary_search` | `book_id`, `query`, `limit?` (def 20, max 50 — SO-3) | `selectGlossaryForContext` | yes |
   | `glossary_get_entity` | `book_id`, `entity_id` | `loadEntityDetail` | yes |
   | `glossary_list_kinds` | — | `loadKinds` | no (global catalog) |

4. **ai-gateway provider #2** — `config.ts` providers += `{name:'glossary', mcpUrl: GLOSSARY_MCP_URL ?? 'http://glossary-service:8088/mcp'}`. Tool names already `glossary_*` (H7, no collision with `memory_*`). docker-compose: ai-gateway env `GLOSSARY_MCP_URL` + depends_on glossary-service.

5. **SEC-1:** `user_id` from the envelope header (set by chat from the JWT, forwarded by the gateway) — never from the LLM. `book_id` IS an LLM arg (OD-3) — safe because every tool ownership-checks it.

## Build steps (→ TodoWrite)
1. glossary go.mod: add `github.com/modelcontextprotocol/go-sdk`.
2. Refactor: extract `selectGlossaryForContext` + `loadKinds` cores (HTTP handlers call them — behavior unchanged).
3. `checkBookOwnership` + 60s cache (+ unit test: owned / not-owner→NotAccessible / not-found→NotAccessible / book-down→Unavailable / cache-hit).
4. `mcp_server.go`: 3 tools + identity middleware; mount on Chi `/mcp`.
5. ai-gateway config + docker-compose provider #2.
6. VERIFY: glossary `go build`/`go test`; ai-gateway jest (unchanged green); **live-smoke** gateway↔glossary read tool (extend smoke harness or a Go test). Cross-service (glossary+gateway+book) → live-smoke token.

## Acceptance criteria (§18 DoD)
AC1 MCP server on glossary `/mcp` (stateless + identity middleware) · AC2 3 read tools · AC3 ownership INV-8 (cache, fail-closed, uniform NotAccessible) · AC4 book_id=LLM arg, user_id=envelope · AC5 caps 20/50 · AC6 gateway provider #2 (`glossary_` prefix) · AC7 live-smoke · AC8 existing glossary endpoints/tests unchanged.

## Risks / watch
- Extract-method refactor must keep the existing select-for-context + listKinds HTTP behavior byte-identical (existing tests guard this).
- go-sdk header→ctx threading proven in the H3 spike; replicate the stateless + own-middleware pattern exactly.
- Ownership cache: cache only positive results; never cache a book-service-down (fail-closed must re-check).
