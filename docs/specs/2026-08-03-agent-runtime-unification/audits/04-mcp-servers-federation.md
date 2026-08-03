# Audit 04 — MCP servers + federation (the product's own MCP layer)

Scope: the services that **define** MCP tools and the gateway that **federates** them.
Read-only audit, 2026-08-03, branch `feat/frontend-tools-mcp-migration`, HEAD `24dd7bdac`.
Everything below is evidence-backed with `file:line`. Counts are derived mechanically from the
registration sites (script re-run against the tree, not from docs).

---

## 0. Executive summary

The federation *plumbing* is genuinely good: one pure `computeCatalog`, per-call envelope
isolation, PARTIAL degradation with outage-aware notes, a shared `_meta` contract that
**panics/raises at registration** in both languages, and a boolean-subschema gate that already
killed the whole-provider de-federation bug class.

The **catalog layer** is not architecture, it is four hand-maintained, mutually-unaware tables
plus a name-prefix convention:

| Table | Home | Size | Maintained by |
|---|---|---|---|
| `DEFAULT_PREFIX_MAP` + `EXTRA_PREFIX_MAP` (what survives federation) | `ai-gateway/src/config/config.ts:90-135` | 9 + 4 | hand |
| `GROUP_DIRECTORY` + `DOMAIN_ALIASES` (what is discoverable, TS copy) | `ai-gateway/src/federation/find-tools.ts:27-61,239-249` | 14 + 7 | hand |
| `GROUP_DIRECTORY` + `_DOMAIN_ALIASES` (Python copy) | `chat-service/app/services/tool_discovery.py:65-…` | 14 + 7 | hand, "keep in lockstep" |
| `TOOL_POLICY` (what a public key may call) | `mcp-public-gateway/src/scope/tool-policy.ts:87-338` | 170 | hand |

**312 tools are federated. 153 of them (49%) have no `TOOL_POLICY` row and are default-denied at
the public edge. 63 of the 170 rows that DO exist point at tools that are now `visibility:"legacy"`.**
Adding a namespace requires edits in five files across three languages, and each of the five
namespaces added so far (`kg_`, `story_`, `lore_`, `web_`, `world_`, `plan_`) was added *after* an
incident in which the gateway silently dropped it — the comments in `config.ts:102-135` say so
in their own words.

---

## 1. TOOL CATALOG — the complete inventory

### 1.1 By owner service and surface

| # | Owner service | Language | MCP surface | Namespaces | Tools |
|---|---|---|---|---|---|
| 1 | composition-service | Python/FastMCP | `/mcp` | `composition_` (105), `plan_` (17), `composition_task_provide_input` | **123** |
| 2 | glossary-service | Go/go-sdk | `/mcp` | `glossary_` (incl. `glossary_task_provide_input`, `glossary_web_search`) | **54** |
| 3 | book-service | Go/go-sdk | `/mcp` | `book_` (33), `world_` (19), `book_task_provide_input` | **52** |
| 4 | knowledge-service | Python/FastMCP | `/mcp` | `kg_` (28), `memory_` (5), `lore_` (4), `story_` (1), others (3) | **41** |
| 5 | provider-registry-service (`settings`) | Go | `/mcp` | `settings_` (12), `web_search` (1) | **13** |
| 6 | translation-service | Python/FastMCP | `/mcp` | `translation_` | **12** |
| 7 | agent-registry-service (`registry`) | Go | `/mcp` | `registry_` | **9** |
| 8 | jobs-service | Python/FastMCP | `/mcp` | `jobs_` | **5** |
| 9 | catalog-service | Go | `/mcp` | `catalog_` | **2** |
| 10 | lore-enrichment-service | Python/FastMCP | `/mcp` | `lore_enrichment_` | **1** |
| | **FEDERATED SUBTOTAL (`/mcp`)** | | | | **312** |
| 11 | glossary-service | Go | `/mcp/admin` | `glossary_admin_` | 5 |
| 12 | knowledge-service | Python | `/mcp/admin` | `kg_admin_` | 2 |
| | **ADMIN SUBTOTAL (`/mcp/admin`)** | | | | **7** |
| 13 | ai-gateway (consumer-local, no provider) | TS | `/mcp` | `tool_list`, `tool_load`, `find_tools`, `propose_edit`, 7 × `ui_*` | 11 *(only 3 advertised)* |
| 14 | mcp-public-gateway (synthetic, edge-only) | TS | public `/mcp` | `invoke_tool`, `confirm_action` | 2 |
| 15 | chat-service (frontend tools, never federated) | Python | LLM surface only | `glossary_propose_entity_edit`, `glossary_confirm_action` (+ duplicate `confirm_action`, `propose_edit`) | 2 unique |
| | **GRAND TOTAL, distinct names** | | | | **≈334** |

`tools/list` on `ai-gateway/mcp` with all providers up serves **315** tools
(312 federated + `tool_list` + `tool_load` + `propose_edit` — `handlers.ts:69-82`).
The K23 test header measured 299 on 2026-07-23 (`ai-gateway/test/discovery-covers-everything.spec.ts:9`).

### 1.2 Deprecation state

`scripts/deprecated-tool-scan.py --list` (derives the catalog from the owning services):

```
202 advertised · 114 retired
```

**114 of the 312 federated tools (37%) carry `_meta.visibility:"legacy"`.** They are still in
`tools/list` and still callable; they are dropped from `find_tools`/`enumerateGroup`
(`find-tools.ts:354,393`) and hidden from `tool_list` unless `include_deprecated:true`
(`handlers.ts:252` — default `false`).

Full per-service name lists were dumped to `scratchpad/inv.json` and `scratchpad/scan.json`
during this audit; the registration-site scan is reproducible from the regexes in §2.

### 1.3 Registration-site evidence (spot samples)

- `services/glossary-service/internal/api/mcp_server.go:51` — `lwmcp.RegisterTool(srv, &mcp.Tool{Name: "glossary_search", …})`
- `services/book-service/internal/api/mcp_server.go:114` — `addTool(srv, "book_get", …)`
- `services/catalog-service/internal/api/mcp_server.go:42` — `addTool(srv, "catalog_list_public_books", …)`
- `services/knowledge-service/app/mcp/server.py:1706` — `@mcp_server.tool(name="kg_build_graph", …)`
- `services/composition-service/app/mcp/server.py:2480` — `@mcp_server.tool(name="composition_write_prose", …)`
- `services/lore-enrichment-service/app/mcp/server.py:80` — `@mcp_server.tool(name="lore_enrichment_auto_enrich", …)`
- knowledge also serves **2 resources** (`knowledge://project/{id}/summary`, `…/entities` — `server.py:1983,2005`)
  and **2 prompts** (`recap_story_so_far`, `entity_dossier` — `server.py:2059,2084`). No other provider
  serves either; the whole C5 resources/prompts federation exists for four objects from one service.

---

## 2. REGISTRATION MECHANISM — one pattern? No: **five**

There is a shared kit in each language (`sdks/go/loreweave_mcp`, `sdks/python/loreweave_mcp`)
and a shared `_meta` contract — that part *is* unified. The **call shape** is not.

| Variant | Where | Shape |
|---|---|---|
| **A. Go — kit direct** | glossary-service, e.g. `mcp_server.go:51-58` | `lwmcp.RegisterTool(srv, &mcp.Tool{Name, Description, InputSchema?, Meta}, handler)` |
| **B. Go — per-service `addTool` wrapper** | book-service `mcp_server.go:57-66`, catalog-service `mcp_server.go:27-36` | `addTool(srv, name, description, meta, handler)` — positional strings; wraps `MustValidateToolMeta` + `RegisterTool`. **Duplicated verbatim in two services.** |
| **B'. Go — `addToolClosedSet`** | book-service `mcp_server.go:75-…` | same + `map[string][]any` enum injection |
| **C. Go — schema helper** | glossary `closedSetSchemaFor[T](map[string][]any)`, `relaxAdditionalProps(...)` (`mcp_server.go:71,176,244-252`) | hand-built `InputSchema` overriding reflection |
| **D. Python — FastMCP decorator** | all 5 Python providers, e.g. `jobs-service/app/mcp/server.py`, `knowledge-service/app/mcp/server.py:370` | `@mcp_server.tool(name=…, description=…, meta=require_meta(tier, scope, …))` |
| **E. Hand-written TS object literals** | `ai-gateway/src/mcp/ui-tools.ts:105-225`, `propose-edit-tool.ts:27-65`, `find-tools.ts:73,420,452`, `mcp-public-gateway/src/scope/confirm-action.ts:39`, `invoke-tool.ts:27` | plain object with `name/description/inputSchema/_meta`; **no registration-time validator at all** |

**Divergences that matter**

1. **Variant E has no gate.** `ui-tools.ts:86-102` documents this precisely: "every domain service
   is FORCED to declare a tier — Go panics (`MustValidateToolMeta`), Python raises (`require_meta`)
   — but ai-gateway's own tools are hand-written defs that no service gate covers… a federated
   tools/list showed 3 untiered tools… these 8 were missed". The fix was to make the TS *type*
   non-optional (`_meta: { tier: 'R'; scope: 'none' }`) — which is compile-time only and only for
   `UiToolDef`. `find-tools.ts`'s three defs and both mcp-public-gateway synthetic tools carry no
   type constraint. `confirm-action.ts:39-53` and `invoke-tool.ts:27-42` have **no `_meta` at all**.
2. **Two Go `addTool` helpers with identical bodies** in book-service and catalog-service — no
   shared kit function, so a fix to one does not reach the other.
3. **Boolean-subschema safety is enforced asymmetrically**: Go panics at registration
   (`sdks/python/loreweave_mcp/schema_federation.py:24-26` states this), Python only asserts in a
   per-service *test* (5 copies: `services/*/tests/test_mcp_schema_federation_safe.py`). TS
   (variant E) has neither.
4. **Task-gate tools are registered by a third path** — `lwmcp.RegisterTaskProvideInput(srv, store, "glossary", …)`
   (`glossary/mcp_server.go:276`) and `register_task_endpoints(mcp_server, store, tool_prefix="composition")`
   (`composition/app/mcp/server.py:334`). Produces three names for one concept (§4.3).

---

## 3. FEDERATION — discovery, caching, invalidation, degradation

### 3.1 Mechanism

- `FederationService.onModuleInit` (`federation.service.ts:118-124`) does one `refresh()` then
  `setInterval(refresh, cfg.catalogRefreshMs)`.
- `catalogRefreshMs` defaults to **30 000 ms** (`config.ts:304`) and is **not set in
  `infra/docker-compose.yml`** — so 30 s in dev and prod.
- `refresh()` (`federation.service.ts:270-299`) walks providers **sequentially** (`for…await`),
  opening a fresh MCP client per provider per refresh, for tools *and* for resources/prompts —
  **2 connects × 10 providers every 30 s**, serialized. A slow provider delays every provider
  behind it in the list.
- Listing uses only `X-Internal-Token` (`federation.service.ts:306`) — no user identity, so the
  catalog is global, not per-user.

### 3.2 What is cached, and when it invalidates

| State | Home | Invalidated by |
|---|---|---|
| `state: Catalog` (toolList, toolToProvider, version, partial) | `federation.service.ts:106` | **only** the 30 s timer |
| `auxState: AuxCatalog` (resources/prompts) | `:109` | same timer |
| per-user overlay | `overlay.ts:66` `cache` | 30 s TTL **or** an `agent-registry` `catalog_version` change (`overlay.ts:164-168`) |
| admin catalog | `admin-federation.service.ts:41` | **never cached for serving** — re-listed live per request with the caller's token (`:66-88`) |

There is **no push invalidation**: MCP `notifications/tools/list_changed` is not subscribed
anywhere (`grep ToolListChanged` → only the SDK). A downstream that adds a tool is invisible for
up to 30 s; nothing propagates the change upward to consumers.

`Catalog.version` is `sha256([name, inputSchema])` (`catalog.ts:85-88`) — **a description or
`_meta.synonyms` change does not bump the version.** No consumer currently reads
`catalogVersion()` (grep across chat/composition/bff: no hits), so this is latent rather than
live, but the H10 "catalog version" cannot detect the field that most affects model behaviour.

### 3.3 Downstream DOWN / PARTIAL — what a consumer sees

`computeCatalog` (`catalog.ts:55-60`): a provider that errors contributes **nothing**, sets
`partial=true`, and records `{name, available:false}`.

Consumers get:
- `tools/list` → `_meta: { unavailable_providers: [...], partial: true }` (`handlers.ts:81`)
- `tool_list` / `tool_load` → `stampIncomplete()` note (`find-tools.ts:510-524`) and, for an
  unresolvable name, `provider_unavailable` instead of `not_found` (`find-tools.ts:568-590`).
  Both were written after a real 2026-07-23 incident, documented in those comments.
- `GET /health/federation` → 503 once PARTIAL persists ≥ `AI_GATEWAY_FEDERATION_DEGRADED_AFTER`
  (default 3) refreshes (`health.controller.ts:39-46`).
- provider LOSS/RECOVERY logged as a transition, not per-refresh noise (`federation.service.ts:178-202`).

**Gap (see §6.1): the `tools/call` path never got this treatment.**

---

## 4. NAMING & SCHEMA DISCIPLINE

### 4.1 Prefix enforcement is the *only* namespacing rule, and it is a hand-maintained allowlist

`computeCatalog` drops any tool whose name does not start with the provider's `prefix` or one of
its `extraPrefixes` (`catalog.ts:65-77`), logging a WARN **server-side only**. The provider's
prefix comes from `DEFAULT_PREFIX_MAP` (9 entries), or `${name}_` derived
(`config.ts:225`). Extra namespaces come from `EXTRA_PREFIX_MAP` (`config.ts:116-135`).

The comments in that map are the incident log:

> `services/ai-gateway/src/config/config.ts:109-114` — "Without `story_` here the C-GW gate
> silently dropped `story_search` (proven: ai-gateway logged "dropping tool 'story_search' …
> does not match any allowed prefix [memory_, kg_]"), leaving the agent with no keyword/full-text
> search over the manuscript"

> `config.ts:117-120` — "`lore_` … Without it the C-GW gate silently drops all four, exactly as it
> once dropped `story_search`"

> `config.ts:131-134` — "`world_` … without this the C-GW gate silently drops the whole
> agent-native worldbuilding surface (same drop class as story_search / kg_)"

Five namespaces, five identical incidents, five hand-patches. Nothing prevents the sixth.

**Collision policy:** first-provider-wins, silently (`catalog.ts:78` `if (map.has(t.name)) continue;`).
Providers are de-duped by name *and* prefix at parse time (`config.ts:231-237`), which makes a
cross-provider collision unlikely but not impossible (a provider can serve a name under an
`extraPrefix` another provider also claims — `extraPrefixes` are **not** in `seenPrefix`).

### 4.2 De-federation risk (`any`-typed field) — **already defended, well**

The known kill-shot is documented at `sdks/python/loreweave_mcp/schema_federation.py:1-31`:
`glossary_curation_list` typed `Items any`, the Go reflector emitted a boolean subschema, and
**all 54 glossary tools vanished** from a 245-tool catalog. Defences now:
- Go: panics at `lwmcp.RegisterTool`.
- Python: `assert_no_boolean_subschemas` in 5 per-service tests.
- **TS (ai-gateway + mcp-public-gateway hand-written defs): no check.** `ui_show_panel.args`
  uses `{ type: 'object', additionalProperties: true }` (`ui-tools.ts:172`), which is safe, but
  nothing enforces that for the next one.

### 4.3 Closed-set / enum discipline

Enforced where it was audited:
- Go: `addToolClosedSet` + `TestEveryEnumeratedClosedSetHasAnEnum` (`book-service/internal/api/mcp_closed_set_contract_test.go:48`), glossary `closedSetSchemaFor`.
- Python: `sdks/python/loreweave_mcp/closed_set_gate.py` (prose-enumeration detector, mirrors the Go one).
- ai-gateway consumer-local: `validateUiToolArgs` (`ui-tools.ts:258-286`) + `validateProposeEditArgs`.

**Not enforced, live violation:**

```ts
// services/mcp-public-gateway/src/scope/confirm-action.ts:49
domain: { type: 'string', description: 'The action domain from the propose result (e.g. composition, book).' },
```

`domain` is the discriminator that selects **which service commits a Tier-W write**. It is a free
string with an "e.g." in the description. The *same* tool name in chat-service declares it as a
real enum:

```py
# services/chat-service/app/services/frontend_tools.py:573-574
"domain": {"type": "string", "enum": ["glossary","book","composition","translation","settings"], …}
```

`confirm-action.ts:45-52` also omits `additionalProperties: false` and requires only
`[confirm_token, domain]`, whereas the chat-service copy requires
`[confirm_token, descriptor, title, domain]`. **One name, two incompatible schemas, on two
surfaces the same model may see.** This is the exact `panel_id` bug class named in
`docs/standards/mcp-tool-io.md` and in `ui-tools.ts:9-12`.

`invoke_tool.arguments` is also `{ type: 'object' }` with no schema (`invoke-tool.ts:37`) — that
one is defensible (it is a generic envelope), but it means the edge relays *unvalidated* args.

---

## 5. WHO CAN SEE WHAT

| Surface | AuthN | Tool-list filtering |
|---|---|---|
| `ai-gateway POST /mcp` | `X-Internal-Token`, constant-time (`mcp.controller.ts:25-33`) | **none per user.** Every internal caller sees all 315. Identity (`X-User-Id`, `X-Book-Id`, `X-Project-Id`, `X-Mcp-Key-Id`) is lifted from headers (`handlers.ts:29-39`) and forwarded, but only affects *dispatch*, never the list. |
| `ai-gateway POST /internal/tools/execute` | `X-Internal-Token`, **non-constant-time** `!==` (`tools.controller.ts:32`) | n/a (single tool) |
| `ai-gateway POST /mcp/admin` | internal token (constant-time) **+ presence of `X-Admin-Token`** (`admin-mcp.controller.ts:37-58`); RS256 `admin:write` verified at the upstream (`glossary/admin_mcp_server.go:40-64`) | separate catalog object; admin names can never blend into `/mcp` (`admin-federation.service.ts:19-27`) |
| `mcp-public-gateway` public `/mcp` | API key / OAuth → scopes | `filterTools` → `TOOL_POLICY` tier ∩ domain, default-deny (`tool-policy.ts:353-365`), then collapsed to `{tool_list, tool_load, find_tools} ∪ activated` (`scope-filter.ts:190-197`) |
| overlay (user-registered MCP servers) | flag `REGISTRY_OVERLAY_ENABLED`, **default `false`** (`config.ts:309`, `docker-compose.yml:1086`) | per-`(userId, projectId)` merge under a mandatory `u_/b_/s_` prefix (`overlay.ts:61,182`) |

### Is a tool ever hidden for a reason the agent cannot discover? **Yes, four ways.**

1. **C-GW prefix drop** (`catalog.ts:71-77`) — the tool is gone from the catalog entirely. The only
   trace is a server WARN. No `_meta`, no note, nothing an agent could ever see. This is the
   mechanism behind all five §4.1 incidents.
2. **`visibility:"legacy"`** — 114 tools. Dropped from `find_tools`/`enumerateGroup`
   (`find-tools.ts:354,393`); hidden from `tool_list` by the `include_deprecated=false` default
   (`handlers.ts:252`). Recoverable via `tool_load(name)` **only if the agent already knows the name**.
3. **Public-edge scope filtering** — deliberately anti-oracle (`scope-filter.ts:33-43`), softened by
   `scope_note` (`:261-262`) only when a non-empty set collapses to empty. A tool with **no**
   `TOOL_POLICY` row is indistinguishable from a nonexistent one (§6.2).
4. **`consumerLocalTools()` excludes `ui_*`** (`handlers.ts:236-240`), so `tool_load('ui_open_book')`
   answers `not_found` — and the very test that locks this in
   (`test/discovery-covers-everything.spec.ts:67`) sits under a header stating
   *"`not_found` … tells the model the tool DOES NOT EXIST"* (`:14-16`). The handler is still
   dispatchable (`handlers.ts:318-320`). The K23 principle is knowingly inverted for these 7.

---

## 6. DEFECTS & INCOHERENCES

### 6.1 🔴 `tools/call` on a down provider says "unknown tool — it is not in the tool catalog"

`federation.executeTool` throws `unknown tool '<n>'` when `toolToProvider` has no entry
(`federation.service.ts:368-370`) — which is exactly what happens when the owning provider is
down, because `computeCatalog` removes its tools. `classifyCallToolError` then returns:

```ts
// services/ai-gateway/src/mcp/handlers.ts:399-401
if (/^unknown tool /.test(msg)) {
  return `unknown tool — it is not in the tool catalog; call tool_list to see valid tool names, …`;
}
```

with code `NOT_DISCOVERED` (`:486`). **It never consults `federation.isPartial()`.** This is the
same false-premise defect that `toolLoadResult` fixed with a long comment about the 2026-07-23
incident (`find-tools.ts:568-580`: *"Asserting `not_found` there is a LIE, and it cost us a real
incident"*) — fixed on the discovery path, left in place on the **execution** path, which is where
a real run actually lands. `handleCallTool` has the `federation` handle; it just doesn't use it.

### 6.2 🔴 The public edge default-denies **half** the catalog, and prefers deprecated tools

Measured against the registration sites:

- 312 federated tools; **170** `TOOL_POLICY` rows; **153 federated tools have no row** → denied by
  absence (`tool-policy.ts:359 `if (!pol) return false;`), each emitting a WARN on every
  `tools/list` (`scope-filter.ts:180`).
- Entire namespaces are unreachable from the public edge: all 19 `world_*`, all 4 `lore_*`,
  all 13 `composition_authoring_run_*`, `plan_bootstrap_*`, `registry_*_workflow`,
  `glossary_propose_batch`, `glossary_propose_entities`, `glossary_curation_list`,
  `glossary_extract_entities_from_doc`, `kg_build`, `kg_multi_query`, `story_search`'s siblings, …
- **63 of the 170 rows point at `visibility:"legacy"` tools.** The clearest case: the edge grants
  `book_get`, `book_get_chapter`, `book_list_chapters`, `book_list_revisions` — all four tagged
  legacy at `book-service/internal/api/mcp_server.go:118,126,134,142` with
  *"DEPRECATED: use book_read / book_list"* — and grants **neither** `book_read` (`:183`) nor
  `book_search` (`:170`). A public key is steered into deprecated tools and denied their
  replacements.
- Two rows exist purely to paper over a rename: `web_search` (`domain:research`) **and**
  `glossary_web_search` (`domain:glossary`) — "Its row MUST stay — existing public keys are scoped
  to `domain:glossary`" (`tool-policy.ts:174-179`). Same handler, two names, two domains, forever.

There is **no gate** asserting the policy table covers the catalog — `test/tool-policy.spec.ts`
tests the *function*, not the *coverage*.

### 6.3 🔴 `find_tools` is de-advertised upstream, but the whole public edge is still built on it

`handleListTools` no longer emits `FIND_TOOLS_TOOL` (`handlers.ts:69-80`; F17 rationale at `:61-63`).
`consumerLocalTools()` also omits it (`:239`). So `find_tools` never appears in any `tools/list`.

Everything downstream still assumes it does:

- `invoke-tool.ts:30-32` — `invoke_tool`'s description, injected into **every** public `tools/list`:
  *"REQUIRED to actually run a tool a **find_tools** match returned … Pass the exact `name` from a
  **find_tools** match"*. The model is told to use a tool it cannot see.
- `invoke-tool.ts:124` — `notActivatedError`: *"call **find_tools** with what you want to do first"*.
- `invoke-tool.ts:139-143,168-169` — `EDGE_FIND_TOOLS_DESCRIPTION` and the `if (tool.name === 'find_tools')`
  rewrite: **dead code**, the branch can never match.
- `proxy-server.factory.ts:40-47` — the MCP `instructions` string served to every connecting
  client: *"call `find_tools` with a short description of what you want to do … to discover the
  right tool"*. Written to fix a "ZERO self-description" bug report (`:30-33`); now it points the
  client at the one tool that was removed. `tool_list`/`tool_load` are not mentioned.
- `scope-filter.ts:187-196`, `tool-policy.ts:357`, `public-mcp.controller.ts:393-405` — the entire
  lazy-activation state machine still keys off `find_tools`.

### 6.4 🟠 Defined but never federated / two homes for one schema

| Tool | Home A | Home B | Effect |
|---|---|---|---|
| `propose_edit` | `ai-gateway/src/mcp/propose-edit-tool.ts:27` (federated) | `chat-service/app/services/frontend_tools.py:80` (advertised on the editor branch, `:672`) | Two schemas; the Python copy carries the comment *"K10 — MUST stay byte-identical to ai-gateway's copy … The move never finished, and the leftover copy **had already drifted**"* (`frontend_tools.py:84-90`) |
| `confirm_action` | `mcp-public-gateway/src/scope/confirm-action.ts:39` | `chat-service/.../frontend_tools.py:541` | Incompatible required-args + enum (§4.3) |
| `glossary_confirm_action` | chat-service only (`frontend_tools.py:255`) | — | Named in **9+ federated glossary tool descriptions** (`glossary/internal/api/mcp_server.go:164,173,192,208,234,261`, `book_tools.go:43,81,93`, `sync_tools.go:40`, `curation_propose_tools.go:34`) and in agent-registry **workflow steps** (`migrate.go:507,602`) — but it is not in ai-gateway's catalog, so a public-edge or non-chat client is told to call a tool that does not exist there |
| `glossary_propose_entity_edit` | chat-service only (`frontend_tools.py:146`) | — | Same class |
| `ui_*` (7) | `ai-gateway/src/mcp/ui-tools.ts:105` | 2 of them also in `chat-service/.../frontend_tools.py:313,513` | Neither advertises them any more; both keep the defs "as a fallback" |

### 6.5 🟠 Runtime description-rewriting layers

Two of them, both patching over the drift in §6.4:

```ts
// services/mcp-public-gateway/src/scope/invoke-tool.ts:156-160
function rewriteStaleConfirmActionMention(description: string): string {
  return description.includes('glossary_confirm_action')
    ? description.replaceAll('glossary_confirm_action', 'confirm_action') : description;
}
```

Applied to **every** outgoing tool description on every `tools/list` (`:170-172`). The comment
(`:145-155`) is candid: *"Rather than a hardcoded per-tool-name list, this is a generic string
replace … so any tool (these 9 today, or a future one) whose federated description mentions the
stale name gets corrected automatically."* A `String.replaceAll` on the LLM-facing prose of nine
Go source files, at request time.

The second is `EDGE_FIND_TOOLS_DESCRIPTION` (`invoke-tool.ts:139-143`), now unreachable (§6.3).

### 6.6 🟠 `/internal/tools/execute` cannot reach any consumer-local tool

```ts
// services/ai-gateway/src/tools/tools.controller.ts:51-54
if (!this.federation.providerFor(tool)) { res.status(404).json({ error: `unknown tool '${tool}'` }); return; }
```

`providerFor` only knows federated tools, so `tool_list`, `tool_load`, `find_tools`,
`propose_edit` and all `ui_*` 404 on this path even though `/mcp` dispatches them fine. The
endpoint also bypasses `normalizeToolResult` (`:59`), so its callers see the raw provider shape
while `/mcp` callers see the C4 envelope — two result contracts for one execution.

### 6.7 🟡 A load-bearing design rationale that the repo contradicts

`federation.service.ts:163-166` and `health.controller.ts:11-19` justify keeping `/health` free of
federation state:

> "`glossary-service` itself declares `depends_on: ai-gateway: condition: service_healthy`
> (infra/docker-compose.yml), so failing the gateway's health on a partial catalog would DEADLOCK"

`grep -n "ai-gateway" infra/docker-compose.yml` → the only `depends_on: ai-gateway` blocks are
**chat-service (:1049)** and **mcp-public-gateway (:1135)**. `glossary-service` has none; in fact
**ai-gateway depends_on glossary-service `service_healthy`** (`docker-compose.yml:1088-1092`). The
conclusion (keep `/health` a pure liveness probe) is still right — the cycle it would create runs
through chat-service — but the cited fact is false, which makes the rule unverifiable by the next
reader.

### 6.8 🟡 Smaller items

- `AdminFederationService.catalogFor` writes shared mutable `this.state` on every request
  (`admin-federation.service.ts:86`) while claiming race-freedom; only the *returned* value is used
  for routing, so `this.state` is a write-only field that serves no purpose and invites misuse.
- `handleAdminCallTool` leaks raw `String(e)` to the caller (`admin-handlers.ts:73`) — the user
  path deliberately sanitizes URLs/hosts (`handlers.ts:369-379`); the admin path does not.
- `ToolsController` compares the internal token with `!==` (`tools.controller.ts:32`) while both MCP
  controllers use `constantTimeEquals`.
- `refresh()` is sequential and unbounded — no per-provider timeout. A hung provider stalls the
  whole 30 s cycle (the overlay path *does* bound its calls: `overlay.ts:72-73`).
- `GROUP_DIRECTORY.book` advertises *"chapter body reads (incl. book_get_chapter)"*
  (`find-tools.ts:36`) — `book_get_chapter` is legacy and hidden from the default `tool_list`.
  Same for `story: 'Manuscript search (story_search).'` being the only member of its group.

---

## 7. PATCHWORK TELLS (quoted)

1. **The prefix map as an incident log** — `config.ts:109-134`, three near-identical paragraphs each
   ending *"same drop class as story_search"*.
2. **Hand-synced constants across two languages, "verified" by a third hardcoded copy**:
   ```ts
   // services/ai-gateway/test/find-tools.spec.ts:203-207
   it('mirrors chat-service GROUP_DIRECTORY verbatim (same keys)', () => {
     // Keep this list in sync BY HAND with tool_discovery.py's GROUP_DIRECTORY —
     expect(Object.keys(GROUP_DIRECTORY).sort()).toEqual([ …literal list… ]);
   ```
   The "lockstep" test never reads the Python file. Three hand-maintained copies of one list.
3. **A deprecated mechanism kept dispatchable "for a legacy caller"** — `find_tools` (§6.3),
   `handleUiTool` (`handlers.ts:72-76`: *"handleUiTool stays wired, so a directive still resolves if
   one arrives — the model just never sees these tools"*), `AppConfig.adminProvider` marked
   `@deprecated` but still constructed (`config.ts:52-56,292-296`).
4. **A runtime `String.replaceAll` over LLM-facing prose** — `invoke-tool.ts:156-160` (§6.5).
5. **A hardcoded "these are real, trust me" list** inside the catalog scanner:
   ```py
   # scripts/deprecated-tool-scan.py:57-63
   _CORE_EXTRA = { "tool_list","tool_load","find_tools","confirm_action","web_search",
                   "load_skill","run_subagent","workflow_list","workflow_load",
                   "glossary_propose_entity_edit","glossary_confirm_action","propose_edit" }
   ```
   The scanner that exists *because* hand-maintained lists go blind (`:12-15`) opens with one.
   It also only globs `services/*/app/mcp/server.py` and `services/*/internal/api/*.go`
   (`:124-133`) — `knowledge-service/app/mcp/admin_server.py` is invisible to it.
6. **A ratcheted debt counter as a gate** — `DEAD_TO_DEAD_BASELINE = 9` (`deprecated-tool-scan.py:53-55`).
7. **A test that codifies the bug its own header condemns** —
   `test/discovery-covers-everything.spec.ts:14-16` vs `:67`.
8. **Domain-union members added retroactively with an apology** — `tool-policy.ts:30-49` (`story`,
   `registry`): *"Confirmed an incomplete rollout, not intentional tier-gating: no key, however
   privileged short of the wildcard dev key, could ever reach it"* … *"the exact same
   incomplete-rollout shape as the `story` gap above."*
9. **Three names for one concept because routing is by name**:
   `glossary_task_provide_input` / `book_task_provide_input` / `composition_task_provide_input`
   — *"a bare `task_provide_input` would collide with book's"* (`glossary/mcp_server.go:273`).
10. `dist/` is **not** checked in — `git ls-files | grep -c /dist/` → `0`, and `.gitignore:13`
    has `dist/`. No staleness risk from build output. (Reported as requested.)

---

## 8. WHAT A UNIFIED ARCHITECTURE NEEDS

### 8.1 Can the catalog become a machine-checkable SSOT? Yes — most of the parts already exist.

**Already built, already machine-readable:**

| Asset | What it already carries |
|---|---|
| `_meta` on every tool (`sdks/*/loreweave_mcp/meta.{py,go}`) | `tier`, `scope`, `synonyms`, `visibility`, `superseded_by`, `paid`, `async`, `ambient_book`, `ambient_project` — **validated at registration; Go panics, Python raises**. This is a real per-tool manifest, and it federates. |
| `scripts/deprecated-tool-scan.py::build_catalog()` | Derives `{advertised, legacy→replacement}` **from the owning services**, cross-language. Already used as a gate by `chat-service/tests/test_skill_registry.py:549` |
| `contracts/tool-liveness.json` | Generated per-tool `{status, executes, proven, waived}` |
| `contracts/frontend-tools.contract.json` | FE↔BE arg/enum mirror for the frontend tools, with a drift test on each side |
| agent-registry workflow rows (`migrate.go:505-554`) | `{"id":…, "tool":…, "gate":…, "inputs_map":…}` — **the workflow→tool edge already exists as data** |
| `chat-service` `SYSTEM_SKILLS[*].hot_domains` + `TestSkillClaimsLint` | **the skill→group edge already exists as data**, and is already cross-checked against the derived catalog |
| `ai-gateway GET /health/catalog` | live `{version, tools, providers, partial}` |

**Missing — and it is the whole problem:**

1. **`_meta` has no `group`.** Group membership is *inferred from the name prefix* plus two
   hand-maintained alias maps duplicated in TS and Python (`find-tools.ts:226-254`,
   `tool_discovery.py`). That single inference is why adding a namespace costs five edits in three
   languages, and why every one of those five was discovered by an outage.
   → **Add `group` (and optionally `workflows: [...]`) to `require_meta` / `NewToolMeta`.** The
   registration chokepoint that already panics on a missing tier can panic on a missing group. The
   prefix maps then become *derived*, not authored.
2. **No generated catalog artifact.** `build_catalog()` produces the data in-process and throws it
   away. → Emit `contracts/mcp-tool-catalog.json`: one row per tool with
   `{name, owner_service, surface (user|admin), group, tier, scope, visibility, superseded_by,
   paid, async, public_policy: {tier, domains} | "denied", synonyms}`. Generate it from a live
   `tools/list` in CI (truthful about federation) with the static scanner as the offline fallback.
3. **No coverage gates.** Three one-liners over that artifact would have caught every §6 finding:
   - every federated tool has a `group` in `GROUP_DIRECTORY` → kills the §4.1 silent-drop class;
   - every federated tool has a `TOOL_POLICY` row **or** an explicit `public: denied` declaration →
     kills §6.2 (153 silent denials);
   - no `TOOL_POLICY` row points at a `visibility:"legacy"` tool whose `superseded_by` has no row →
     kills the `book_get`-granted/`book_read`-denied inversion.
4. **No one-name-one-schema check.** `confirm_action` and `propose_edit` exist twice with different
   schemas. The `frontend-tools.contract.json` drift-test pattern already solves exactly this for
   FE tools; extend it to any name defined in more than one place, or delete the duplicates.
5. **No push invalidation and no description-sensitive version.** `Catalog.version` should hash
   `(name, description, inputSchema, _meta)`; subscribing to `notifications/tools/list_changed`
   would make the 30 s poll a fallback rather than the mechanism.
6. **`instructions` and every "call X first" string should be generated from the artifact**, not
   typed. `proxy-server.factory.ts:40-47` and `invoke-tool.ts:30,124,139` all name `find_tools`
   because a human typed it once and nothing re-checks it.

### 8.2 Minimal ordering

1. Fix §6.1 (one `isPartial()` check in `handleCallTool`) and §6.3 (three strings + delete the dead
   branch). Both are single-file, and both are actively lying to the model today.
2. Add `_meta.group`, backfill it from the current prefix inference, then make
   `GROUP_DIRECTORY`/`DOMAIN_ALIASES`/`EXTRA_PREFIX_MAP` derived.
3. Generate `contracts/mcp-tool-catalog.json` + the three coverage gates.
4. Reconcile `TOOL_POLICY` against the artifact (153 rows to classify, 63 to retarget).
5. Finish the frontend-tools migration (delete the chat-service duplicates) so the
   `rewriteStaleConfirmActionMention` string-replace can be deleted with it.
