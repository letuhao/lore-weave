# Spec — Agent Extensibility Registry (Plugins · MCP · Skills · Commands · Hooks)

- **Date:** 2026-07-02
- **Status:** **DESIGN SEALED 2026-07-02** — all open questions resolved in the Decision Register (`docs/plans/2026-07-02-agent-extensibility-registry/00_EVALUATION_AND_TASKS.md` §3); autonomous implementation authorized (plan §7), human gate at final release only
- **Size:** XL (new service + cross-service contract + ai-gateway federation re-arch + FE)
- **Track:** Agent platform / extensibility
- **Author checkpoint answers (PO):**
  1. Scope = **Full plugin registry** (MCP + Skills + slash commands + hooks + subagents, bundled under a versioned *plugin*).
  2. External MCP openness = **Arbitrary user-supplied MCP URL** (full security: OAuth 2.1+PKCE, egress control, sandbox, supply-chain scan).
  3. User-authored Skills = **Prompt-only** (SKILL.md + references; **no** executable `scripts/`).

---

## 1. Problem

Today every agent capability is **hardcoded in source** and **shared globally**:

- MCP providers are a fixed `AI_GATEWAY_PROVIDERS` env list, memoized per-process, one global catalog for all users (`services/ai-gateway/src/config/config.ts`, `src/federation/federation.service.ts`).
- "Skills" are 5 hardcoded prompt modules; users may only enable/disable them (`services/chat-service/app/services/skill_registry.py`).
- No user can register a third-party MCP server, author a Skill pack, or define a slash command / hook.

We are an **agent-centric** product. The agent is the protagonist; its capability surface must be **user-extensible and multi-tenant**, matching the market standard (MCP Registry federation, Agent Skills open standard, Claude-Code-style plugin bundles). See `docs/specs/2026-07-02-*` research notes / conversation log for the market survey.

## 2. Goals / Non-goals

**Goals**
- G1. A user can **register, configure, enable/disable, and delete** their own extensions.
- G2. Extensions are packaged as **Plugins** — a versioned bundle that may contain: MCP-server refs, Skills, slash commands, hooks (declarative), and subagent definitions.
- G3. **Per-user, dynamic** capability resolution — the agent's tool/skill surface is composed from {System tier} ∪ {this user's enabled plugins} ∪ {this book's plugins}, not a global static list.
- G4. **Arbitrary external MCP servers** with production-grade security (OAuth 2.1+PKCE, per-tenant secret vault, egress allowlist, sandboxed execution path, supply-chain scanning).
- G5. Reuse existing seams: BYOK `provider-registry` secret pattern, `ai-gateway` federation, roleplay `session_templates` 2-tier tenancy, chat-service skill/tool advertising.
- G6. Follow the two open standards on the wire: `server.json` (MCP) and `SKILL.md` (Agent Skills), plus a `plugin.json` manifest.

**Non-goals (this effort)**
- N1. Executable skill `scripts/` (prompt-only by decision #3). Deferred behind a sandbox track.
- N2. A2A / Agent Card agent↔agent protocol (future track; leave manifest room).
- N3. A public plugin *marketplace* with monetization/ratings. We build the **private subregistry + per-user management**; a curated System catalog stands in for a marketplace at v1.
- N4. Memory as an MCP primitive (knowledge-service already owns memory; watch `memorywire` standard).

## 3. Market alignment (why this shape)

- **Federation / subregistry.** The official MCP Registry is a *meta-registry* + an OpenAPI spec that private subregistries implement. We are a **private subregistry**: ingest curated public servers (System tier) + host user/internal ones (per-user/per-book tiers). We do **not** fork the official registry codebase (it is explicitly not self-hostable).
- **Plugin as the unit.** Claude Code / the ecosystem distribute a *plugin bundle* (skills + commands + hooks + MCP + subagents), not loose primitives. Our unit of install = **Plugin**.
- **Two wire standards.** `server.json` for MCP entries; `SKILL.md` (YAML frontmatter `name`+`description` required, progressive disclosure) for Skills.
- **Security is first-class.** OWASP Agentic Skills Top 10 + the "26% of skills carry a vuln" finding drive: prompt-only skills at v1, sandbox + egress control + supply-chain scan for external MCP, OAuth 2.1+PKCE with per-server resource-scoped tokens (RFC 8707).

## 4. Current architecture we reuse (code-grounded)

| Seam | File(s) | How we use it |
|---|---|---|
| BYOK secret vault + resolver | `services/provider-registry-service/internal/migrate/migrate.go`, `internal/api/server.go` (`createProviderCredential`, `getInternalCredentials`, `encryptSecret`/`decryptSecret`, `requireInternalToken`) | **Mirror** the AES-GCM secret pattern + `/internal/*` resolver for MCP-server credentials. |
| MCP federation | `services/ai-gateway/src/federation/federation.service.ts` (`refresh`, `executeTool`, `providerFor`), `src/federation/catalog.ts` (`computeCatalog`), `src/config/config.ts` (`parseProviders`) | **Re-arch** from global-static provider list → per-user dynamic catalog (§9). |
| Tool advertising | `services/chat-service/app/client/knowledge_client.py` (`get_tool_definitions`), `app/services/stream_service.py` (`_stream_with_tools`, discovery, tiers) | Consumes the (now per-user) federated catalog; add skill-pack injection alongside `skill_registry`. |
| 2-tier tenancy precedent | `services/roleplay-service/src/handlers/scripts.rs`, `session_templates` (`tier ∈ {system,user}`, `owner_user_id NULL ⇒ system`) | **Copy** the System∪own resolution + create-only-own-tier rule. |
| Hardcoded skills | `services/chat-service/app/services/skill_registry.py` (`SYSTEM_SKILLS`, `enabled_skills`) | System-tier skills become the seed rows of the new Skills catalog; enable/disable UX generalizes. |
| Hook-like injection precedent | `services/chat-service/app/services/steering.py` (per-book rule-based prompt injection) | Model for **declarative hooks** (event → inject/deny), no arbitrary code. |
| Public MCP edge (reference only) | `services/mcp-public-gateway/*` | The *outbound* direction; not reused, but its OAuth/scope-gate code informs the inbound OAuth design. |

**Note:** the `gateway-drops-xprojectid-envelope` memory is **STALE** — `ai-gateway` now forwards `X-Project-Id` (`federation.service.ts` `buildEnvelopeHeaders`; confirmed in `docs/specs/2026-06-30-editor-compose-overhaul/00_INVESTIGATION.md`). Per-book plugin scoping can rely on the envelope.

## 5. Tenancy model (LOCKED — applies the CLAUDE.md 3-tier rule)

Every registry row declares its tier. Resolution merges **System → Per-user → Per-book**, higher shadows lower by stable key (mirrors the entity-kinds fix).

| Tier | Owner | Who writes | Visible to | Example |
|---|---|---|---|---|
| **System** | platform | **admin only** | everyone (read-only) | the 9 internal MCP providers; curated public MCP servers; the 5 seed skills |
| **Per-user** | `owner_user_id` | that user | that user (+ grantees) | user's registered external MCP; user's authored Skill pack; user's plugin |
| **Per-book/project** | `book_id`/`project_id` | owner + E0 grantees | owner + grantees | a plugin enabled only for one manuscript |

**Hard rules carried over:** every table has a scope key; `UNIQUE(owner_user_id, slug)` / `UNIQUE(book_id, slug)` never a bare global `UNIQUE(slug)`; cross-tenant access only via E0 grants; a regular user never mutates a System row (they *clone/override* into their tier).

## 6. Domain model — the Plugin and its sub-primitives

```
Plugin (versioned bundle, the unit of install)
├── plugin.json           # manifest: name (reverse-DNS), version, tier, capabilities[]
├── mcp_servers[]         # → McpServerRegistration (server.json-shaped)
├── skills[]              # → Skill (SKILL.md-shaped, prompt-only)
├── commands[]            # → SlashCommand (prompt template + arg schema)
├── hooks[]               # → Hook (declarative event → action; NO arbitrary code at v1)
└── subagents[]           # → SubagentDef (system_prompt + tool-scope + model_ref)
```

- **Plugin** — install/enable unit. Reverse-DNS name (`io.github.user/pack`), semver, tier. Enabling a plugin enables all its members (member-level override allowed later).
- **McpServerRegistration** — a `server.json` entry + connection: `transport` (streamable-http/stdio-not-at-v1), `endpoint_url`, `auth` (oauth2 | bearer | none), secret ref, `egress_allowlist`, `status`, health.
- **Skill** — `SKILL.md`: YAML frontmatter (`name`, `description` required; optional `surfaces`, `triggers`, `book_scoped`) + markdown body + optional `references/`. **No `scripts/`.** Loaded via progressive disclosure exactly like `skill_registry` already does (metadata line always, body on trigger).
- **SlashCommand** — generalizes today's fixed `/think`/`/effort=`; a named prompt template with an arg schema, expands client- or server-side into a message. Closed-set args → enum (Frontend-Tool-Contract rule).
- **Hook** — declarative only: `on: {pre_tool_call | post_tool_call | pre_turn | post_turn | tool_result}`, `match: {...}`, `action: {inject_text | deny | require_approval | annotate}`. Reuses the steering-style injection machinery. Arbitrary-code hooks are N1 (deferred to sandbox track).
- **SubagentDef** — a named persona with its own tool-scope + model, generalizing `roleplay_scripts` + the existing `composer_model_ref` sub-model routing; runs in an isolated sub-context (extends `services/composer.py` seam).

## 7. Service decision

**New service: `agent-registry-service` (Go / Chi)** — per language rule (domain/meta service ⇒ Go), owner of plugins + all sub-primitive definitions + registrations + enablement state.

- **Secrets:** MCP-server credentials (OAuth client secret, bearer token, refresh token) are stored **in agent-registry's own AES-GCM vault**, cloning the `provider-registry` `encryptSecret`/`decryptSecret` pattern — *not* in `provider_credentials`, because that table is model-capability shaped (`capability_flags`, `pricing`, `user_models` join) and an MCP tool server is not a model. Rationale is recorded as **DECISION-1** below; revisit if a unified secret vault emerges.
- **Provider-gateway invariant is untouched:** external MCP servers are *tool* endpoints, not LLM/embedding/rerank/image/audio/STT providers, so they do not fall under the provider-registry-only rule. (If a registered "MCP server" is actually a model backend, it must go through provider-registry as BYOK — enforced by validation, see §10.)
- **MCP-first invariant:** human-driven registry CRUD is plain domain REST (not agentic). **Agent-driven self-registration is IN scope (PO decision 2026-07-02):** the agent must be able to list/read/propose skills itself. Per the invariant, these are **MCP tools hosted on agent-registry-service's own `/mcp`** (domain owns its tools; ai-gateway federates them) — see §12b.

## 8. Data model (agent-registry-service, sketch)

All tables carry a scope key + `tier`; secrets never echoed (expose `has_secret` only).

```sql
plugins (
  plugin_id UUID PK, tier TEXT CHECK(tier IN('system','user','book')),
  owner_user_id UUID NULL, book_id UUID NULL,        -- one non-null per tier
  name TEXT NOT NULL,                                 -- reverse-DNS
  version TEXT NOT NULL, manifest JSONB NOT NULL,
  status TEXT DEFAULT 'active', created_at, updated_at,
  UNIQUE(owner_user_id, name, version), UNIQUE(book_id, name, version)
)
mcp_server_registrations (
  mcp_server_id UUID PK, plugin_id UUID FK ON DELETE CASCADE,
  tier, owner_user_id, book_id,
  server_json JSONB NOT NULL,                         -- server.json-shaped
  transport TEXT CHECK(transport IN('streamable_http')),  -- stdio deferred
  endpoint_url TEXT NOT NULL,
  auth_kind TEXT CHECK(auth_kind IN('none','bearer','oauth2')),
  secret_ciphertext TEXT, secret_key_ref TEXT,        -- AES-GCM (mirror provider-registry)
  oauth_meta JSONB,                                   -- issuer, scopes, resource(RFC8707), PKCE
  egress_allowlist JSONB DEFAULT '[]',
  tool_name_prefix TEXT,                              -- collision/prefix enforcement (catalog.ts)
  status TEXT DEFAULT 'pending', last_health JSONB, scan_result JSONB,
  UNIQUE(owner_user_id, endpoint_url), UNIQUE(book_id, endpoint_url)
)
skills (
  skill_id UUID PK, plugin_id UUID FK ON DELETE CASCADE,
  tier, owner_user_id, book_id,
  slug TEXT NOT NULL, frontmatter JSONB NOT NULL, body_md TEXT NOT NULL,
  surfaces TEXT[], triggers JSONB, book_scoped BOOL DEFAULT false,
  UNIQUE(owner_user_id, slug), UNIQUE(book_id, slug)
)
slash_commands ( command_id PK, plugin_id FK, tier, owner_user_id, book_id,
  name TEXT, arg_schema JSONB, template_md TEXT, expand_side TEXT, UNIQUE(owner_user_id,name) )
hooks ( hook_id PK, plugin_id FK, tier, owner_user_id, book_id,
  on_event TEXT, match JSONB, action JSONB, UNIQUE(owner_user_id,hook_id) )   -- declarative only
subagent_defs ( subagent_id PK, plugin_id FK, tier, owner_user_id, book_id,
  name TEXT, system_prompt TEXT, tool_scope JSONB, model_ref TEXT, UNIQUE(owner_user_id,name) )
plugin_enablement (                                   -- per-user / per-book on/off, incl. of System plugins
  enablement_id PK, plugin_id FK, scope TEXT CHECK(scope IN('user','book')),
  owner_user_id UUID, book_id UUID, enabled BOOL DEFAULT true,
  UNIQUE(plugin_id, owner_user_id), UNIQUE(plugin_id, book_id)
)
```

## 9. The crux — per-user dynamic federation (ai-gateway re-arch)

Today `ai-gateway` builds **one global catalog** memoized per process. We must make the catalog **per-resolution-context** = f(user_id, book_id/project_id).

Design:
1. **System providers stay static** (the 9 internal MCP servers) — cached as now.
2. **Add a per-user overlay.** On a tool-loop turn, `ai-gateway` (or chat-service, at the `get_tool_definitions` call) asks agent-registry: `GET /internal/effective-catalog?user_id=&book_id=` → resolved list of enabled MCP-server registrations (with per-server secret/endpoint from the vault) merged over the System set.
3. **Federate the overlay** through the same `computeCatalog` collision/prefix logic (`catalog.ts`) — user servers get a mandatory namespace prefix (`u_<hash>_`) so they can never shadow System tools.
4. **`executeTool` routing** gains a per-user provider map; connection per-call already (INV-7), so no shared-connection tenancy leak — but **cache catalogs keyed by (user_id, book_id, catalog_version)** with short TTL, not process-global.
5. **External call path is sandboxed** (§10): user-server calls egress through a controlled fetch (allowlist + timeout + size cap), separate from trusted internal providers.

Open architectural question **Q-FED** (§15): does the overlay resolve in `ai-gateway` (keeps chat-service thin) or in chat-service `knowledge_client` (keeps gateway stateless)? Lean: **ai-gateway**, because it already owns federation + envelope; chat-service just passes `user_id`/`book_id` (already in the envelope).

## 10. Security

**External MCP (arbitrary URL) — the heavy part:**
- **OAuth 2.1 + PKCE (S256).** Per-server token scoped via Resource Indicators (RFC 8707); short-lived access token (15–60 min) + refresh token in the AES-GCM vault; never surfaced to the LLM. Reuse the OAuth patterns proven in `mcp-public-gateway`.
- **Egress control.** Per-server `egress_allowlist`; all user-server traffic exits through a controlled sandboxed HTTP path (timeout, response-size cap, no access to internal network / metadata endpoints). Consider a Firecracker/seccomp-isolated egress worker for stdio/binary MCP later; v1 is streamable-http only so a hardened fetch proxy suffices.
- **Supply-chain scan.** On registration + refresh: fetch the server's `tools/list`, scan tool descriptions/schemas for injection markers, store `scan_result`; quarantine (`status='pending'`) until it passes; re-scan on catalog refresh. Track against OWASP Agentic Skills Top 10.
- **Namespacing / anti-shadow.** Reverse-DNS names; user tools forced under `u_<hash>_` prefix; System tools always win a collision (`computeCatalog` first-provider-wins already, we pin System first).
- **Secrets never in prompt/logs/cache** (tenancy rule); every registration write derives `owner_user_id` from JWT; `/internal` resolve gated by `X-Internal-Token`, filters `owner_user_id`.
- **Validation guard:** reject an MCP registration whose declared purpose is a model capability (chat/embedding/rerank/…); those must go through provider-registry BYOK (upholds the provider gateway invariant).

**Skills (prompt-only)** — dramatically smaller surface: no code execution, so the 26%-vuln / reverse-shell threat class is designed out. Residual risk = **prompt injection via skill body**. Mitigations: skills are content, injected into the system prompt under clear delimiters; a user's own skill runs only in that user's sessions (no cross-tenant); System-tier skills are admin-authored; optional lint on frontmatter.

## 11. Manifest formats (on the wire)

- **`plugin.json`** — `{ name (reverse-DNS), version (semver), tier, description, capabilities: {mcp_servers, skills, commands, hooks, subagents} }`. Extensible (leave A2A / memory slots).
- **`server.json`** — conform to the MCP Registry draft schema so a registration can be imported from / exported to the official registry and other subregistries (federation win). We *store* `server_json` verbatim + our connection/security columns alongside.
- **`SKILL.md`** — YAML frontmatter (`name`, `description` required) + markdown; progressive disclosure identical to `skill_registry`'s L1/L2 loading. Importable from `.claude`-style skill folders (minus `scripts/`).
- **Contract tests** (Frontend-Tool-Contract rule): closed-set args (transport, auth_kind, on_event, expand_side, tier) are enums; a committed JSON contract snapshot both sides.

## 12. API surface (agent-registry-service)

- Public (JWT, owner from token): `POST/GET/PATCH/DELETE /v1/agent-registry/plugins`, `.../mcp-servers`, `.../skills`, `.../commands`, `.../hooks`, `.../subagents`; `PUT .../enablement`; `POST .../mcp-servers/{id}/health`, `.../{id}/oauth/start` + callback, `.../{id}/rescan`.
- Internal (`X-Internal-Token`): `GET /internal/effective-catalog?user_id=&book_id=` (for ai-gateway), `GET /internal/mcp-servers/{id}/credentials?user_id=` (resolve secret, decrypt only here), `GET /internal/skills?user_id=&book_id=&surface=` (for chat-service injection).
- Never echo secrets; expose `has_secret`, `oauth_connected`.

### 12b. Agent-facing MCP tools (self-registration — PO decision 2026-07-02)

agent-registry-service hosts its own `/mcp` (Go, mirror `glossary-service/internal/api/mcp_server.go`), federated through ai-gateway with prefix `registry_`. Identity always from the envelope (`X-User-Id`), never from LLM args.

| Tool | Tier | Behavior |
|---|---|---|
| `registry_list_skills` | R | List skills visible to the envelope user (System ∪ own ∪ book), slugs + metadata lines only |
| `registry_get_skill` | R | Full SKILL.md body of one visible skill |
| `registry_propose_skill` | A | **Propose-pattern** (never direct write): agent submits frontmatter+body, server validates + stores a proposal with `confirm_token`; FE renders a SkillProposalCard; human approves → confirm route (internal-token gated, mirror the P4 approval spine) creates the row in the user's tier |
| `registry_update_skill` | A | Same propose→confirm, diff against existing (own-tier only; System rows rejected with `result.error`) |
| `registry_set_skill_enabled` | A | Toggle enablement for the envelope user (prompt-once approval gate) |

Key flow this unlocks: **"save this workflow as a skill"** — the agent distills the current conversation's procedure into a SKILL.md and proposes it; the human reviews the rendered preview and approves. Every reject path returns `result.error` (no silent no-op — Frontend-Tool-Contract rule).

## 13. Frontend

New management surface under `frontend/src/features/` (React-MVC rules): `plugins/` feature — list/install/enable, per-tier badges, MCP-server add wizard (URL → OAuth connect → health/scan → enable), Skill editor (SKILL.md frontmatter form + markdown body + preview), command/hook builders. Reuse `AgentContextRack`/`ToolSkillAddModal` patterns already in `features/chat/components`. Per-device UI state in localStorage; all registry data server-side (persistence rules). Lists follow the browser standard (`EntityListBrowser` toolbar + `Pager`/`useServerPagedList`). UI reference: `design-drafts/screens/plugin-register/draft-ui.html` (v2).

### 13b. Writing Studio standard (PO requirement 2026-07-02 — studio-first, not route-only)

Every registry surface must be openable **inside the Writing Studio dock**, not only as a traditional page — and the MCP management surface follows the same standard. The studio standard in this repo is a concrete contract chain; each item below is mandatory for the new surfaces:

1. **Two shells, one controller.** Each feature ships as shell-agnostic components whose logic lives in hooks/context (MVC rule); the same component mounts in (a) the standalone route page and (b) a studio dock panel. No logic forked per shell.
2. **Dock catalog registration** (`frontend/src/features/studio/panels/catalog.ts`): new `STUDIO_PANELS` entries with `id` === dockview component id, i18n `titleKey`/`descKey` (studio namespace), palette-openable unless `hiddenFromPalette`. Panels self-title via `props.api.setTitle` and are **never conditionally unmounted** (CSS hidden / internal branching only).
3. **New panel ids (v1):**
   - `extensions` — the management hub (plugins · MCP servers · commands & hooks as internal tabs), palette-openable, in the agent enum.
   - `proposals` — the agent-proposal inbox, palette-openable, in the agent enum (the natural reply to "duyệt skill tôi vừa nhờ bạn lưu").
   - `skill-editor` — **singleton, retargets via params `{skillId?}`** (the `json-editor` precedent, `catalog.ts:39-41`); opened by "Edit skill" affordances; `hiddenFromPalette`, outside the agent enum at v1.
4. **Agent-openable (the "MCP applies the studio standard" half):** extend the `ui_open_studio_panel` `panel_id` enum (`frontend_tools.py:402`) with `extensions` and `proposals` + enum-description entries. Per the LOCKED Frontend-Tool Contract: regenerate `contracts/frontend-tools.contract.json` (`WRITE_FRONTEND_CONTRACT=1 pytest …`), keep `panelCatalogContract.test.ts` green (advertised set == palette-openable set ⊆ buildable dock set), resolver rejects with `result.error` — never a silent no-op.
5. **Registry MCP tools compose with studio tools in one turn:** e.g. `registry_propose_skill` → SkillProposalCard → after approve the agent may call `ui_open_studio_panel(panel_id='extensions')` or retarget `skill-editor` to show the result. The §12b tools are surface-gated like the rest of the universal set and remain available in the studio Compose surface (`studio_context`).
6. **Verified by EFFECT:** each new panel + enum entry gets the live-browser smoke (or its deterministic injected-suspend form) proving the GUI actually reacted — a raw-stream smoke is insufficient (LOCKED rule).

## 14. Phased roadmap

The XL effort ships as milestones at risk boundaries (budget-driven cadence), each with its own VERIFY + 2-stage REVIEW + POST-REVIEW + cross-service live-smoke.

- **P0 — Foundation.** New `agent-registry-service` (Go), schema, tenancy, plugin + enablement CRUD, `/internal/effective-catalog` returning **System tier only** (parity with today). Language-rule + provider-gate green. *Ships nothing user-visible new; proves the seam.*
- **P1 — Skills (prompt-only) + agent self-registration.** Skills table + SKILL.md import + FE editor; migrate the 5 hardcoded skills to System-tier seed rows; chat-service reads user/book skills from `/internal/skills` alongside `skill_registry`; **the §12b MCP tools + SkillProposalCard confirm loop** (agent can propose skills from chat, human approves); **studio-first shells** — `extensions` + `proposals` dock panels, `skill-editor` singleton, `ui_open_studio_panel` enum extension + contract regen (§13b). **Lowest risk, highest immediate value.**
- **P2 — Per-user federation re-arch.** ai-gateway overlay: `/internal/effective-catalog` merges enabled MCP registrations; catalog cache keyed by (user, book); namespace prefixing; **internal-only MCP registrations first** (no external URL yet) to de-risk the federation change in isolation.
- **P3 — External MCP + security.** Arbitrary URL registration, OAuth 2.1+PKCE, egress-controlled call path, supply-chain scan, quarantine. MCP management ships in both shells (route + `extensions` studio panel, §13b). The heavy security milestone; `/review-impl` mandatory.
- **P4 — Commands + declarative Hooks.** Generalize inline `/effort` into user slash commands; steering-style declarative hooks.
- **P5 — Subagents + Plugin bundling UX.** SubagentDef (extends composer/roleplay seams); plugin export/import; optional System catalog ingest from the official MCP Registry.

Reorder P1/P2 by appetite; P1 is independently shippable and the natural first cut.

## 15. Open questions (ALL RESOLVED) / risks / deferred

**All design questions are SEALED** — see the Decision Register (plan §3): D1–D4, **Q-FED = ai-gateway**, **Q-CACHE = version-bump + 30 s TTL fallback**, **SCAN-GATE = user self-serve accept-risk (audit-logged)**, DECISION-1 = own vault, PANEL-1, HOOK-1, AGENT-W, E2E-1. New forks discovered during the run go to `DECISION_LOG.md` with a chosen default and do not pause implementation (plan §7).
- **Risk — federation blast radius:** making the global catalog per-user touches the hot path for every turn. Mitigate: P2 does internal-only first; feature-flag; keep System-only fast path when a user has zero plugins.
- **Risk — external latency/failure:** a slow user MCP server must not stall the loop. Per-call timeout + circuit-breaker + drop-with-`result.error` (never silent no-op — Frontend-Tool-Contract rule).
- **Deferred (gate-passing rows to add to SESSION_HANDOFF):**
  - `D-SKILL-SCRIPTS` — executable skill `scripts/` behind a Firecracker/seccomp sandbox (gate #2 structural; N1).
  - `D-A2A-AGENTCARD` — agent↔agent protocol / Agent Card layer (gate #1 out-of-scope; N2).
  - `D-STDIO-MCP` — stdio-transport MCP servers (needs the sandboxed egress worker; gate #2).
  - `D-PLUGIN-MARKETPLACE` — public marketplace + ratings/monetization (gate #1; N3).

## 16. Invariant compliance check

- **Gateway invariant** — external traffic still via `api-gateway-bff`; registry is a normal domain service behind it. ✓
- **MCP-first** — registry CRUD is non-agentic REST; future agentic install exposed as MCP tool on the owning service. ✓ (noted)
- **Provider gateway invariant** — external MCP = tool endpoints, not model providers; a model-capability registration is rejected and routed to provider-registry BYOK. ✓
- **No hardcoded model names / secrets** — unchanged; new secrets via AES-GCM vault + env key. ✓
- **Language rule** — new service is Go (domain/meta). Must add a `contracts/language-rule.yaml` row. ✓ (action)
- **Tenancy (LOCKED)** — every table scope-keyed, System read-only/admin-write, resolution merges tiers, `UNIQUE(scope, slug)`. ✓
- **Frontend MVC + persistence** — management GUI follows hooks/context/components split; registry data server-side. ✓
- **Frontend-Tool Contract (LOCKED) + studio standard** — new panel ids ride the `ui_open_studio_panel` enum → contract JSON regen → `panelCatalogContract` lockstep; never-silent-no-op; effect-verified by live browser smoke (§13b). ✓

---

### Immediate next step
CLARIFY is effectively done (scope locked by PO). Recommended next action: **DESIGN + PLAN for P0+P1** (foundation service + prompt-only Skills) as the first shippable milestone, since it is independently valuable and de-risks the schema/tenancy before the federation re-arch. On approval, scaffold `agent-registry-service` and add its `contracts/language-rule.yaml` row.
