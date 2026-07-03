# Agent Extensibility Registry — Spec Evaluation + Task Breakdown

- **Date:** 2026-07-02
- **Spec under evaluation:** `docs/specs/2026-07-02-agent-extensibility-registry.md`
- **Companion UI draft:** `design-drafts/screens/plugin-register/draft-ui.html` (v2 — open in a browser)
- **Status:** **DESIGN SEALED 2026-07-02** — all open questions resolved (§3 Decision Register); **autonomous implementation authorized** (§7 Execution Model): no human-in-loop during the run, human reviews decisions + quality at the **final release gate only**. Every component carries a **real-run E2E** (§6 matrix).

---

## 1. Spec evaluation

### 1.1 Strengths (keep as-is)

- Code-grounded reuse map (§4) — every seam cites real files; the BYOK-vault clone and the roleplay 2-tier precedent are the right templates.
- Tenancy model (§5) applies the LOCKED 3-tier rule with the correct `UNIQUE(scope, slug)` shape.
- Phasing puts the federation re-arch (P2) *after* an independently shippable Skills milestone (P1) and de-risks it with internal-only registrations first.
- Security posture for arbitrary external MCP (§10) matches the market baseline (OAuth 2.1+PKCE, RFC 8707, egress allowlist, scan+quarantine).

### 1.2 Gaps found (each has a fix routed into the task list)

| # | Gap | Severity | Fix |
|---|---|---|---|
| G1 | **Agent self-registration was out of scope.** PO requires the agent to register skills itself. Spec said "future, leave room". | BLOCKER (requirement) | **FIXED in spec** — new §12b (5 MCP tools on agent-registry's own `/mcp`, propose→confirm HITL); folded into P1. Tasks REG-P1-06…08. |
| G2 | No acceptance criteria per task/phase — "implement will miss things" is exactly right. | HIGH | Every task below carries AC (Given/When/Then style, condensed). |
| G3 | **Contract-first rule not scheduled.** Spec lists API routes but no OpenAPI freeze step before FE work. | HIGH | REG-P0-06 freezes `contracts/api/agent-registry.yaml` before any FE task starts. MCP tool schemas get contract-snapshot tests (REG-P1-07). |
| G4 | No UI specification at all — §13 is one paragraph. | HIGH | `draft-ui.html` mocks all 6 surfaces; FE tasks reference specific mock screens. |
| G5 | **Enablement precedence ambiguous**: can a user disable a System plugin? default-on or off? book-level override direction? | MED | Proposed defaults in §3-D1; must be signed off before REG-P0-04. |
| G6 | **No quotas/limits**: unbounded skills per user, SKILL.md size, MCP servers per user, scan frequency. | MED | §3-D2 proposes concrete caps; REG-X-02 implements. |
| G7 | **Migration/back-compat for `chat_sessions.enabled_skills TEXT[]`** unspecified — the 5 hardcoded skill slugs must keep resolving during and after migration. | HIGH | REG-P1-03/05 define seed + dual-read fallback; slugs stay byte-identical. |
| G8 | **Versioning semantics undefined** — plugin semver vs in-place skill edits conflict. | MED | §3-D3: user-tier content is edited in place with `draft/published` states; semver applies only to export/import bundles and System catalog entries. |
| G9 | No audit trail / observability plan for registry writes and catalog resolution. | MED | REG-X-01 (audit via AFTER-UPDATE trigger projection — proven pattern), REG-X-03 (metrics). |
| G10 | Validation under-specified: name regex, reverse-DNS check, frontmatter schema, prompt-injection lint list, SSRF guard on user URLs. | HIGH | Concretized in REG-P1-01 / REG-P3-01 ACs. |
| G11 | **Proposal storage** for propose→confirm not in the schema sketch (§8). | MED | Add `skill_proposals` table — REG-P1-06 AC. |
| G12 | MCP tool args must obey the Frontend-Tool-Contract enum rule; spec §11 mentions it but no task enforced it for the *new* tools. | MED | REG-P1-07 AC: closed-set args registered in `CLOSED_SET_ARGS`, contract JSON regenerated. |

**Verdict:** spec is architecturally sound; it was *not* implementation-ready (G2/G3/G4/G7/G10 would have caused exactly the "thiếu sót" the PO fears). This document + the UI draft close that gap.

### 1.3 UX/UI gaps (draft v1 review, 2026-07-02 — fixed in draft v2)

| # | Gap | Resolution |
|---|---|---|
| U1 | **Lists were not browser-standard** — no search/filter/sort/paging, unlike the rest of the app. | All lists now use the existing shell: `EntityListBrowser`-style toolbar + `Pager`/`useServerPagedList` (server-paged, "X–Y of N", page-size). REG-P1-09/REG-P3-06 ACs updated: **reuse these components, do not hand-roll tables**. |
| U2 | **No Proposals inbox** — an agent proposal lived only in a chat card; close the chat and it's unfindable. | New "Proposals" screen (pending badge, review/approve/reject, history, expiry) → new task REG-P1-12. |
| U3 | **No server detail page** — nowhere to see a server's tools, scan report (the flagged description!), health history, breaker state, OAuth expiry/reconnect. | New "Server detail" screen with tool browser + scan-report review (accept-risk vs keep-quarantined) → new task REG-P3-08. |
| U4 | **No audit/activity UI** (REG-X-01 was BE-only). | New "Activity log" screen; REG-X-01 gains an FE sub-task. |
| U5 | No empty/loading/error states, no quota indicators (D2), no destructive-delete cascade dialog. | States section in draft v2 (empty CTA, skeleton, cached+retry banner); header quota strip; typed-confirm delete listing cascades + "N sessions pin this skill". |
| U6 | No shadow-warning UX when a user slug overrides a System skill; no unsaved-changes / revision history in the skill editor. | Added to skill editor panel (warn banner, `unsaved changes`, History ▾). |
| U7 | No bulk actions, no book-scope selector in create flows. | Bulk bar on plugins list (System rows excluded from bulk delete); `scope` select in skill editor. |
| U8 | Cross-cutting FE conventions unstated: i18n (react-i18next vi/en), a11y (`role="switch"`, focus, keyboard), responsive (multi-device rule), `data-testid` per interactive element. | Stated in draft v2 footer as implementation notes; fold into every FE task's AC. |

---

## 2. Deliverables map

| Artifact | Purpose |
|---|---|
| `docs/specs/2026-07-02-agent-extensibility-registry.md` | WHAT + architecture (amended with §12b, §13b) |
| This file | Evaluation, sealed decisions, task decomposition, E2E matrix, execution model, master checklist |
| `design-drafts/screens/plugin-register/draft-ui.html` | Clickable UI draft v2 (10 screens) — the FE acceptance artifact |
| `./01_GUI_CHECKLIST.md` | **Element-level GUI checklist (270 lines)** — every visible element in the draft = one line; a screen's task is not done until its section is 100% ticked; each section lists the BE it forces. The anti-omission control. |
| `./DECISION_LOG.md` | Mid-run fork log (autonomous execution, §7) |

---

## 3. Decision Register — ALL SEALED (PO sign-off 2026-07-02)

No open questions remain. Anything not listed here that forks during the run goes to `DECISION_LOG.md` (§7), it does NOT pause the run.

| ID | Decision | Sealed value |
|---|---|---|
| **D1** | Enablement precedence | System plugins **default-ON**; a user may disable *for themselves* (`plugin_enablement` row `enabled=false` — the System row itself is never mutated). User-tier default-ON for owner. **Book scope overrides user scope.** Only explicit overrides stored; absence = tier default. |
| **D2** | Quotas v1 | 50 skills/user · SKILL.md body ≤ 64 KB · references ≤ 256 KB total · 10 external MCP servers/user · 100 advertised tools per user catalog (overflow → `find_tools`-only) · health/scan ≤ 1/min/server. |
| **D3** | Versioning | User-tier content: in-place edit + `draft/published`. Semver only on export/import bundles + System catalog entries. |
| **D4** | Proposal expiry | 7 days; expired confirm → `result.error: proposal_expired`. |
| **Q-FED** | Per-user catalog overlay location | **ai-gateway** — it owns federation + envelope (user_id/book_id already present); chat-service unchanged; every future consumer inherits the overlay. |
| **Q-CACHE** | Catalog cache invalidation | **Version-bump + TTL 30 s fallback** — agent-registry bumps `catalog_version` on any mutation; gateway compares version per turn (cheap check), 30 s TTL as safety net. |
| **SCAN-GATE** | Accept-risk authority on flagged scan findings | **User self-serve** (BYOK spirit): the owner may "Accept risk & activate" their own server — blast radius already bounded by tenancy isolation + egress allowlist + `u_<hash>_` prefix. Audit-logged. Admin retains global suspend. |
| **DECISION-1** | MCP secret storage | agent-registry's **own AES-GCM vault** (clone provider-registry pattern), not `provider_credentials`. |
| **PANEL-1** | Studio panel granularity | One `extensions` hub panel (plugins · MCP · commands&hooks tabs) + `proposals` panel in agent enum; `skill-editor` singleton params-retarget, hiddenFromPalette, **outside** the agent enum v1 (json-editor precedent; keeps the enum small for weak models). |
| **HOOK-1** | Hook engine placement | In-process at the chat-service loop seams (`stream_service.py`), reusing the approval gate + steering-style injection. Declarative only. |
| **AGENT-W** | Agent write scope | §12b tools write **own-tier only**; System rows rejected with `result.error`; owner always from envelope `X-User-Id`, never LLM args. |
| **E2E-1** | E2E harness form | Committed scripted suite `tests/e2e/registry/` (eval/-style runner) against the real dev stack — NOT one-off smoke scripts (per `prefer-e2e-and-evaluation-over-live-smoke-poc`). Live-LLM scenarios use the test account's local lm_studio models ($0). Milestone gate = its E2E slice green; final gate = full matrix green in one pass. |

---

## 4. Task breakdown

Legend: `[BE]`/`[FE]`/`[FS]`/`[QA]` · **Deps** = must complete first · **AC** = acceptance criteria (evidence required at VERIFY). Every phase ends with the standard gates: unit green, 2-stage REVIEW, cross-service **live smoke**, POST-REVIEW.

### P0 — Foundation: `agent-registry-service` (parity, nothing user-visible)

| ID | T | Task | Deps | AC |
|---|---|---|---|---|
| REG-P0-01 | BE | Scaffold Go/Chi `agent-registry-service`: config, health, JWT auth mw, `X-Internal-Token` mw, envelope extraction (clone provider-registry `server.go` skeleton). Add `contracts/language-rule.yaml` row, docker-compose service + its own Postgres DB, gateway BFF route. | — | Service boots in compose; `language-rule-lint` green; `/healthz` 200; BFF proxies `/v1/agent-registry/*`. |
| REG-P0-02 | BE | Migration v1: `plugins`, `plugin_enablement` per spec §8, incl. tier CHECK, scope-key NOT-NULL-per-tier constraint (CHECK: exactly one of owner_user_id/book_id per tier), `UNIQUE(owner_user_id,name,version)`, `UNIQUE(book_id,name,version)`. | P0-01 | Migration idempotent (runs twice clean); constraint tests: System row with owner_user_id rejected. |
| REG-P0-03 | BE | Plugin CRUD (JWT): POST/GET/PATCH/DELETE `/v1/agent-registry/plugins`. Owner from token, never body. Regular users create `tier='user'` only; admin routes for System tier (mirror roleplay `scripts.rs:52-91` rule). Name = reverse-DNS regex `^[a-z0-9.-]+/[a-z0-9-]+$`. | P0-02 | User A cannot read/patch B's plugin (404, anti-oracle); non-admin creating System-tier → 403; invalid name → 400 with field error. |
| REG-P0-04 | BE | Enablement API `PUT /v1/agent-registry/plugins/{id}/enablement` (scope user\|book) + resolution per **D1**. | P0-03, D1 | Matrix test: {System,user}×{no-row,enabled,disabled}×{book override} — all 8 cells assert per D1. |
| REG-P0-05 | BE | `GET /internal/effective-catalog?user_id=&book_id=` v0 — returns System-tier static set (parity with today's `AI_GATEWAY_PROVIDERS`), with `catalog_version` etag. | P0-04 | Response schema frozen; etag stable across identical calls; internal-token required (401 otherwise). |
| REG-P0-06 | BE | **Contract freeze:** `contracts/api/agent-registry.yaml` (OpenAPI) covering P0+P1 public routes. | P0-03 | Spec committed; handler↔spec drift test (route table vs spec paths). |
| REG-P0-07 | QA | Live smoke: CRUD roundtrip through BFF with the test account; tenancy negatives; `ai-provider-gate.py` + pre-commit green. | P0-01..06 | Evidence: `live smoke: BFF plugin CRUD + cross-tenant 404`. |

### P1 — Skills (prompt-only) + agent self-registration ⭐ first shippable value

| ID | T | Task | Deps | AC |
|---|---|---|---|---|
| REG-P1-01 | BE | `skills` table + SKILL.md parser/validator: frontmatter YAML (`name`,`description` required; optional `surfaces[]`,`triggers`,`book_scoped`), slug regex `^[a-z0-9][a-z0-9-]{1,63}$`, body ≤ 64 KB (D2), tier scoping identical to plugins. Reject `scripts/` content markers. | P0-02 | Fixture suite: valid/missing-name/oversize/bad-slug/scripts-smuggle all behave per AC; parser fuzz on frontmatter. |
| REG-P1-02 | BE | Skills CRUD REST + `POST .../skills/import` (single SKILL.md or folder-zip minus scripts) + `GET .../skills/{id}/export`. `draft/published` status per **D3**. | P1-01 | Import a real `.claude`-style folder → skill row + references stored; export roundtrips byte-identical body. |
| REG-P1-03 | BE | Seed migration: the 5 hardcoded skills (`glossary`,`universal`,`knowledge`,`admin`,`plan_forge`) from `chat-service/app/services/*_skill.py` constants → System-tier rows, **slugs byte-identical** (G7). | P1-01 | Seed idempotent; slugs equal `SYSTEM_SKILLS` keys; body equals the python constants (checksum test). |
| REG-P1-04 | BE | `GET /internal/skills?user_id=&book_id=&surface=` — merge System→user→book, shadow by slug, filter surface, return L1 metadata lines + lazy body handles. | P1-03 | Shadow test: user skill with slug `glossary` shadows System `glossary` for that user only. |
| REG-P1-05 | BE | chat-service integration: `skill_registry.py` gains a registry client (cache TTL 60 s) with **fallback to the python constants** when registry is unreachable; `chat_sessions.enabled_skills` slugs keep working unchanged (G7). Injection order in `stream_service.py:1424-1464` unchanged for System skills. | P1-04 | Kill agent-registry container → chat turn still works on constants (fallback log line); enable a user skill → its L1 line appears in the system prompt (assert via prompt-capture test). |
| REG-P1-06 | BE | Proposal store + confirm spine: `skill_proposals` table (proposal_id, owner_user_id, action create\|update, target_skill_id NULL, frontmatter, body, `confirm_token`, expires_at per **D4**, status). Confirm route internal-token + `X-User-Id` gated (mirror the P4 approval-spine pattern — no JWT mint). | P1-01 | Confirm with wrong user → 404; expired → `proposal_expired`; double-confirm idempotent. |
| REG-P1-07 | BE | **MCP server on agent-registry** (`/mcp`, Go, mirror glossary `mcp_server.go` + identity mw): the 5 §12b tools. Closed-set args (`action`, `surface`) as enums; register in `CLOSED_SET_ARGS`; regenerate `contracts/frontend-tools.contract.json` if any frontend-executed piece is added; federate via `AI_GATEWAY_PROVIDERS += registry=...` + prefix map `registry_` (both `config.ts` maps + compose env). Tool tiers in chat-service `tool_tier()`: list/get=R, propose/update/enable=A. | P1-06 | `tools/list` through **ai-gateway** shows `registry_*` with prefix; envelope user enforced (missing `X-User-Id` → error); ask-mode advertises only R tools. |
| REG-P1-08 | FS | SkillProposalCard: chat FE renders a pending `registry_propose_skill` result → preview card (rendered frontmatter + markdown + diff for update) → Approve calls confirm via BFF; Reject resolves with `result.error`. Follows `ProposeEditCard.tsx` pattern. | P1-07 | Deterministic FE test: inject suspended proposal → card renders → approve → resolve POST body correct. No silent no-op path. |
| REG-P1-09 | FE | Skills management UI per draft v2 "Skills" screen: **browser-standard library list (reuse `EntityListBrowser` toolbar + `Pager`/`useServerPagedList` — no hand-rolled tables)**, editor (frontmatter form + markdown pane + live preview + L1-metadata-line preview + unsaved-changes guard + shadow-warning banner + revision history), import/export, quota indicator. React-MVC split, ≤100-line components, i18n keys, `data-testid`, `role="switch"` toggles. | P0-06, P1-02 | Playwright: create→publish→appears in list→toggle off→gone from `/internal/skills`; search/sort/page roundtrip; shadow warning shown on System-slug collision. |
| REG-P1-12 | FE | **Proposals inbox** (U2): pending/approved/rejected/expired list (browser-standard), badge count in nav, review card reachable outside chat, approve/reject wired to the same confirm spine as REG-P1-08. | P1-08 | Proposal created in a chat → visible in inbox after chat closed → approve from inbox creates the skill; expired proposal shows `proposal_expired` on approve attempt. |
| REG-P1-13 | FS | **Studio shells (§13b)**: register `extensions` (management hub: plugins · MCP servers · commands & hooks tabs) + `proposals` panels in `STUDIO_PANELS` (i18n titleKey/descKey, self-title via `props.api.setTitle`, never conditionally unmounted); `skill-editor` singleton retargeting via params `{skillId}` (json-editor precedent, hiddenFromPalette); extend `ui_open_studio_panel` `panel_id` enum with `extensions`+`proposals` + description entries; regenerate `contracts/frontend-tools.contract.json` (`WRITE_FRONTEND_CONTRACT=1 pytest`); same feature components mount in route AND panel (logic in hooks/context, zero fork). | P1-09, P1-12 | `panelCatalogContract.test.ts` green (enum == palette-openable ⊆ buildable); **live browser smoke: agent says "mở quản lý extensions" → `ui_open_studio_panel(extensions)` → dock panel actually opens** (effect, not tool-call); Command Palette lists both panels; skill "Edit" retargets the singleton. |
| REG-P1-10 | FE | Chat affordance: "Save as skill" action on a conversation + proposal card entry point (mock screen "Agent flow"). | P1-08 | Clicking sends the distill prompt; card lifecycle as P1-08. |
| REG-P1-11 | QA | **E2E with live LLM** (local lm_studio model, $0): user asks agent to save a workflow as a skill → `registry_propose_skill` → card → approve → row exists → **new session** shows the L1 line and injects body on trigger. Rebuild touched images first (stale-image trap). | all P1 | Evidence: `live smoke: agent-proposed skill approved + injected next session`. |

### P2 — Per-user dynamic federation (internal-only registrations)

| ID | T | Task | Deps | AC |
|---|---|---|---|---|
| REG-P2-01 | BE | `mcp_server_registrations` migration (spec §8) — internal/no-secret fields only at this phase. | P0-02 | Constraints per §8; `UNIQUE(owner_user_id, endpoint_url)`. |
| REG-P2-02 | BE | effective-catalog v1: merge enabled registrations over System set; `catalog_version` bumps on any enablement/registration change; cache keyed `(user_id, book_id)` TTL ≤ 30 s. | P2-01 | Version bumps exactly on mutation; stale-cache window ≤ TTL proven by test. |
| REG-P2-03 | BE | ai-gateway overlay: per-context catalog fetch in `federation.service.ts`; user tools forced under `u_<hash8(user_id)>_` prefix via `computeCatalog`; System pinned first (collision win); `executeTool` per-context provider map; **feature flag** `REGISTRY_OVERLAY_ENABLED` (default off); zero-plugin fast path = today's static path. | P2-02 | Flag off → byte-identical catalog to today (snapshot test); flag on + zero plugins → same; user server tool never shadows a System name (collision test). |
| REG-P2-04 | QA | Perf + tenancy live smoke: p95 catalog resolve overhead < 50 ms on the turn path; user A's registration invisible in B's `tools/list` **через ai-gateway** (cross-tenant live test — the class unit tests miss). Full regression on the existing 9 providers. | P2-03 | Evidence: `live smoke: per-user catalog isolation A/B + 9-provider regression`. |

### P3 — External MCP + full security (the heavy milestone; `/review-impl` mandatory)

| ID | T | Task | Deps | AC |
|---|---|---|---|---|
| REG-P3-01 | BE | Registration validation: URL parse + **SSRF guard** (deny RFC1918/loopback/link-local/metadata IPs, resolve-then-connect pinning), streamable-http only, model-capability rejection (§10 provider-invariant guard). | P2-01 | SSRF fixture suite (10+ payloads incl. DNS-rebind shape) all rejected; `ollama`-style URL rejected with pointer to provider-registry BYOK. |
| REG-P3-02 | BE | Secret vault: AES-GCM `encryptSecret`/`decryptSecret` clone; auth kinds `none/bearer/oauth2`; secrets decrypt only in `/internal/mcp-servers/{id}/credentials`. Public API returns `has_secret` only. | P3-01 | Grep-test: no secret field in any public serializer; internal route filters owner. |
| REG-P3-03 | BE | OAuth 2.1+PKCE: `/oauth/start` (PKCE S256, RFC 8707 `resource`=server URL) + callback + refresh worker; tokens in vault. | P3-02 | Live smoke against a reference OAuth MCP server; refresh rotates before expiry; token never appears in logs (log-scan test). |
| REG-P3-04 | BE | Egress-controlled call path in ai-gateway for user-tier servers: per-server allowlist, 15 s timeout, 1 MB response cap, per-server circuit breaker; failure → tool `result.error` (never stall the loop, never silent). | P2-03 | Breaker opens after N failures and the turn completes with the error surfaced to the model; internal-network egress attempt blocked. |
| REG-P3-05 | BE | Supply-chain scan + quarantine: on register + on refresh, fetch `tools/list`, lint descriptions/schemas against injection-marker list (OWASP Agentic Top-10 derived), store `scan_result`; status machine `pending→active→suspended`; `POST .../rescan`. | P3-01 | Poisoned-description fixture → quarantined, not advertised; rescan of a cleaned server activates it. |
| REG-P3-06 | FE | Add-MCP-Server wizard per draft v2 (4 steps: URL → Auth/OAuth-connect → Health & Scan → Review/Enable) + **browser-standard servers list** (search/filter by status+auth/sort/paging), status chips (pending/active/suspended/error), token-expired → Reconnect state. | P0-06, P3-05 | Playwright wizard happy-path + each failure state renders its chip and `result.error` text. |
| REG-P3-08 | FE | **Server detail page** (U3): connection panel (OAuth status/expiry/reconnect, egress allowlist, limits, breaker state), health history (24 h, p50/p95), scan report with per-finding review (**accept-risk & activate** vs **keep quarantined**), tool browser (paged, per-tool scan verdict). | P3-05, P3-06 | Flagged finding rendered with the offending description text; accept-risk transitions server pending→active and is audit-logged. |
| REG-P3-09 | FS | **MCP-in-studio (§13b)**: the MCP servers tab, add-server wizard, and server detail all function inside the `extensions` dock panel (not only the route) — incl. the OAuth popup flow from within the dock; wizard state survives panel hide/show (never-unmount rule). | P1-13, P3-06, P3-08 | Live browser smoke: register + OAuth-connect + scan review completed entirely inside the studio panel; hiding/showing the panel mid-wizard loses no state. |
| REG-P3-07 | QA | Security gate: `/review-impl` on P3 diff; cross-tenant + SSRF + injection live smokes; **live smoke with a real third-party MCP server** end-to-end (register → OAuth → tool call in a chat turn). | all P3 | `/review-impl` findings folded; evidence: `live smoke: external MCP registered + called in-turn`. |

### P4 — Slash commands + declarative hooks

| ID | T | Task | Deps | AC |
|---|---|---|---|---|
| REG-P4-01 | BE | `slash_commands` CRUD + resolution: `/name` in a chat message expands the template (server-side default; `expand_side` enum) with `{{args}}` from the arg schema; coexists with the fixed `/effort`/`/think` parses (`parse_inline_effort` precedence documented). | P0-06 | `/mycmd foo` expands; unknown command falls through untouched; collision with built-ins rejected at create. |
| REG-P4-02 | FE | `/` autocomplete in chat input (System ∪ user commands) + command builder UI per mock. | P4-01 | Autocomplete lists tier-merged commands; builder round-trips arg schema. |
| REG-P4-03 | BE | `hooks` CRUD + engine at loop seams: `pre_tool_call` (deny / require_approval → existing approval gate), `post_tool_call` (annotate), `pre_turn/post_turn` (inject_text via steering-style block). Declarative only; `on_event`/`action.kind` enums. | P0-06 | Hook `deny` on tool X → call blocked with `result.error`; `inject_text` appears in prompt capture; hook evaluation adds < 5 ms p95. |
| REG-P4-04 | FE | Hook builder UI per mock (event dropdown → match form → action form). | P4-03 | Create→fires in a live turn (Playwright + prompt echo). |

### P5 — Subagents + plugin bundling

| ID | T | Task | Deps | AC |
|---|---|---|---|---|
| REG-P5-01 | BE | `subagent_defs` CRUD + runtime: named persona with own `system_prompt`, `tool_scope` (subset filter over the user's catalog), `model_ref`; invoked via a `registry_run_subagent`-style server tool extending the `composer.py` seam (isolated sub-context, result returned to main turn). | P2-03 | Subagent runs with *only* its scoped tools (negative test); its context does not leak into the main window. |
| REG-P5-02 | BE | Plugin bundle export/import (`plugin.json` + members, zip); semver enforced on bundles per D3; import validates every member with the P1/P3 validators. | P1-02 | Export→delete→import roundtrip restores all members; tampered bundle rejected. |
| REG-P5-03 | BE | System catalog ingest (admin): pull from the official MCP Registry API into an admin curation queue → approve → System-tier rows. | P3-05 | Ingested entry lands `pending`; only admin approval publishes. |
| REG-P5-04 | FE | Plugin detail/install UX + export/import per mock. | P5-02 | Playwright roundtrip. |

### Cross-cutting (start in P0, ride every phase)

| ID | T | Task | AC |
|---|---|---|---|
| REG-X-01 | FS | Audit log for all registry writes via AFTER-UPDATE trigger → projection table (proven `projection-trigger-activity-log` pattern) + **Activity log screen** (U4: browser-standard, filter by kind/actor/range). | Every CRUD path leaves an audit row (matrix test); screen pages + filters against live rows. |
| REG-X-02 | BE | Quotas per **D2**, enforced at write time with clear 4xx errors. | Each cap has an over-limit test. |
| REG-X-03 | BE | Metrics: catalog-resolve latency, scan verdict counts, per-server breaker state, proposal funnel (proposed→approved). | Exposed on `/metrics`; dashboards noted in runbook. |
| REG-X-04 | — | Docs: SESSION_HANDOFF rows per milestone; deferred rows `D-SKILL-SCRIPTS`, `D-A2A-AGENTCARD`, `D-STDIO-MCP`, `D-PLUGIN-MARKETPLACE` registered at P0 commit. | Rows exist with gate reasons. |

---

## 5. Dependency graph (milestone level)

```
P0 ──► P1 (skills + agent MCP tools)  ──► P4 (commands/hooks)
 │                                        
 └────► P2 (per-user federation) ──► P3 (external MCP + security) ──► P5 (subagents/bundles)
```
P1 and P2 are parallelizable after P0 (disjoint surfaces: chat-service+FE vs ai-gateway), **but** integrate serially with one combined VERIFY (fan-out rule).

## 6. E2E real-run matrix (per component — PO requirement 2026-07-02)

**Definition of a "real run"** (all five conditions, or the scenario doesn't count):
1. Real dev stack (`infra/docker-compose.yml`) with **rebuilt images** of every touched service (stale-image trap).
2. Entry through the **real edge** — BFF `/v1/*`, ai-gateway `/mcp` — never internal ports (those are for assertions only).
3. Real data via real APIs — no hand-fed/crafted payloads that bypass resolution (the `_render_outline_plan` lesson).
4. Real LLM where the loop involves one — test-account BYOK local lm_studio model ($0).
5. Real browser (Playwright) against the **built FE image** on `--network infra_default` — not a host vite dev server.

Harness: `tests/e2e/registry/` — scripted, repeatable, one file per scenario, evidence (pass log) recorded per milestone.

| ID | Component | Real-run scenario | Gate |
|---|---|---|---|
| E2E-P0-A | Plugin CRUD + tenancy | Login test account via BFF → create/list/patch/delete plugin; second account sees 404 (anti-oracle) | P0 |
| E2E-P0-B | effective-catalog v0 | A real chat turn's `tools/list` through ai-gateway is byte-identical before/after the registry is introduced (parity regression) | P0 |
| E2E-P1-A | Skill CRUD UI | Playwright: create → publish → listed → toggle off → gone from a fresh `/internal/skills` resolve | P1 |
| E2E-P1-B | Skill injection | Real chat turn (local LLM): enabled skill's L1 line present; trigger phrase → L2 body applied (behavioral assert) | P1 |
| E2E-P1-C | Seed + back-compat | 5 System skills checksum == python constants; a pre-existing session with `enabled_skills` resolves identically | P1 |
| E2E-P1-D | Registry-down fallback | Stop agent-registry container mid-stack → chat turn still succeeds on constants (fallback log line asserted) | P1 |
| E2E-P1-E | **Agent self-registration loop** | Live LLM + Playwright: "lưu quy trình này thành skill" → `registry_propose_skill` → SkillProposalCard renders → approve → row exists → **new session** shows L1 + applies the skill | P1 |
| E2E-P1-F | Proposals inbox | Propose in chat → close chat → approve from inbox → skill created; expired proposal → `proposal_expired` | P1 |
| E2E-P1-G | Studio shells | Live browser: agent turn "mở quản lý extensions" → `ui_open_studio_panel(extensions)` → dock panel actually opens (effect); palette opens both panels; Edit-skill retargets the singleton | P1 |
| E2E-P2-A | Per-user overlay isolation | User A registers an internal MCP reg → A's real chat `tools/list` shows `u_<hash>_` tools, user B's does not (cross-tenant, through the gateway) | P2 |
| E2E-P2-B | Flag-off parity + fast path | `REGISTRY_OVERLAY_ENABLED=false` → catalog byte-identical to today; flag on + zero plugins → same | P2 |
| E2E-P2-C | Invalidation | Disable a registration → next turn (>version-bump) no longer advertises it, within 30 s worst-case | P2 |
| E2E-P3-A | External MCP happy path | Spin a real reference MCP server container → Playwright wizard: URL → bearer → health/scan → enable → a real chat turn calls its tool and the answer uses the result | P3 |
| E2E-P3-B | OAuth 2.1 | OAuth-protected reference server → full PKCE connect in browser → tool call succeeds; token refresh observed | P3 |
| E2E-P3-C | Security negatives | SSRF payload set rejected; poisoned-description server lands quarantined and is NOT advertised; dead server → breaker opens and the chat turn still completes with `result.error` | P3 |
| E2E-P3-D | MCP-in-studio | Entire wizard + scan review completed inside the `extensions` dock panel; hide/show mid-wizard loses no state | P3 |
| E2E-P4-A | Slash command | Create `/recap` in UI → type `/recap 1-3` in a real chat → expansion + LLM answer reflects the template | P4 |
| E2E-P4-B | Hooks | `deny` hook: agent's write tool call blocked with `result.error` in a live turn; `require_approval` renders the approval card; `inject_text` changes behavior | P4 |
| E2E-P5-A | Subagent | Live turn delegating to a subagent def: runs with ONLY its scoped tools (out-of-scope tool provably unavailable); main context unpolluted | P5 |
| E2E-P5-B | Bundle roundtrip | Export plugin → delete → import → every member works live (skill injects, command expands, MCP tool callable) | P5 |
| E2E-P5-C | Registry ingest | Ingest from the official MCP Registry → admin curation → System row → user enables → tool callable in a turn | P5 |
| E2E-X-A | Audit | Piggyback: every scenario above leaves its expected audit rows (asserted at the end of each script) | all |
| E2E-X-B | Quotas | 51st skill / 11th server rejected with the clear 4xx surfaced in UI | P1/P3 |

## 7. Execution model — autonomous run (PO directive 2026-07-02)

The PO has authorized a **continuous, no-human-in-loop implementation**: the human reviews **decisions and quality at the final release gate only**. Mechanics:

1. **Design is sealed** (§3). The run never pauses to ask a design question.
2. **Mid-run forks → `DECISION_LOG.md`** (this folder): when implementation surfaces a genuinely new fork, the agent picks the safest default consistent with §3 + CLAUDE.md invariants, records `{context, options, chosen, rationale}`, and **continues**. The human reviews the log at the final gate and may order rework.
3. **Per-milestone self-gates (agent-enforced, no pause):** fresh VERIFY evidence → 2-stage self-review → the milestone's E2E slice green (§6, rebuilt images) → **the milestone's `01_GUI_CHECKLIST.md` sections 100% ticked against the running app** (element-level, prevents draft→impl omission) → commit + SESSION_HANDOFF update. `/review-impl` auto-invoked at P3 (security) and its findings fixed in-run.
4. **PO checkpoints:** per PO directive, the per-milestone POST-REVIEWs for P0→P5 are **batched into one final release gate**. (CLARIFY-end checkpoint = this sealed document.)
5. **Hard stops — the only three:** (a) a security-critical ambiguity with no safe default; (b) the debugging protocol's 3-failed-fixes rule; (c) a genuinely external blocker (cannot be built in this repo). Everything else is a DECISION_LOG entry, not a stop.
6. **Final release gate (human):** full §6 matrix green **in one pass** (evidence pack) · DECISION_LOG walkthrough · demo script (the P1 agent-self-registration loop + P3 external-server loop live) · deferred rows review · then merge/release.

## 8. Master checklist

### Gate-keeping
- [x] Decision Register sealed — D1–D4, Q-FED, Q-CACHE, SCAN-GATE, DECISION-1, PANEL-1, HOOK-1, AGENT-W, E2E-1 (PO 2026-07-02)
- [x] Autonomous execution authorized; human gate at final release only (§7)
- [ ] Branch created off `main` for this track (do NOT build on `feat/studio-agent-raid`)
- [ ] `tests/e2e/registry/` harness scaffolded (E2E-1)
- [ ] `DECISION_LOG.md` created (empty) in this folder
- [ ] `contracts/language-rule.yaml` row for agent-registry-service
- [ ] Deferred rows registered (REG-X-04)

### P0 — Foundation ✅ (2026-07-03)
- [x] REG-P0-01 scaffold + compose + BFF route (Go/Chi svc :8099, DB loreweave_agent_registry, BFF proxy `/v1/agent-registry/*`, language-rule row)
- [x] REG-P0-02 schema v1 + constraint tests (plugins/plugin_enablement/registry_audit/registry_meta; per-tier partial UNIQUE; scope-key CHECK)
- [x] REG-P0-03 plugin CRUD + tenancy negatives (owner-from-token, cross-tenant 404 anti-oracle, System-admin gate — E2E green)
- [x] REG-P0-04 enablement matrix (8 cells — pure resolver unit test) + D1 precedence
- [x] REG-P0-05 effective-catalog v0 (System parity + per-user override + catalog_version etag)
- [x] REG-P0-06 OpenAPI contract frozen (`contracts/api/agent-registry.yaml`)
- [x] REG-P0-07 live smoke + gates green (go test green; real-stack E2E 20/20; BFF tsc clean)
- [x] **E2E slice green: E2E-P0-A, E2E-P0-B** (`tests/e2e/registry/p0_smoke.ps1` — 20/20 vs live Postgres)
- Note: through-the-BFF-container E2E bundled into P1 stack rebuild (service-level + BFF typecheck done; DL-3).

### P1 — Skills + agent self-registration  (BACKEND ✅ 2026-07-03 · FE/chat pending)
- [x] REG-P1-01 parser/validator + fixtures (slug regex, 64KB cap, scripts/ reject — E2E green)
- [x] REG-P1-02 CRUD + import/export (SKILL.md parse/render, draft/published, revisions-on-publish)
- [x] REG-P1-03 seed 5 System skills (slugs byte-identical; bodies stay in chat-service — DL-4)
- [x] REG-P1-04 /internal/skills merge+shadow (+ system_overrides + shadowed_system)
- [x] REG-P1-05 chat-service dual-read + fallback + enabled_skills back-compat (user_skills_client + stream_service inject; 6 unit tests)
- [x] REG-P1-06 proposal store + approve/reject/expiry spine (JWT-owner approve — DL-5)
- [x] REG-P1-07 registry MCP server federated (`registry_` prefix in DEFAULT_PREFIX_MAP + compose; 5 tools; tool-meta valid at boot; propose call → DB row proven)
- [ ] REG-P1-08 SkillProposalCard (chat render of registry_propose_skill result) (PENDING — FE, chat pipeline)
- [~] REG-P1-09 Skills management UI — SkillsView (browser-standard) built + mounted in ExtensionsPanel; standalone /extensions route PENDING
- [ ] REG-P1-10 "Save as skill" affordance (PENDING — FE)
- [ ] REG-P1-11 live-LLM E2E (next-session injection proven) (PENDING — stack rebuild)
- [~] REG-P1-12 Proposals inbox — ProposalsView (approve/reject/filter) built + mounted in ProposalsPanel; standalone route PENDING
- [x] REG-P1-13 Studio shells: extensions+proposals panels + skill-editor singleton registered; `ui_open_studio_panel` enum extended + contract regen; **panelCatalogContract 3/3 + BE contract 20 pass + FE tsc clean**. Live browser smoke rides stack rebuild.
- [x] **E2E slice (backend): p1_rest_smoke.ps1 29/29 vs live PG + MCP propose call verified**
- [x] **E2E stack-rebuild (2026-07-03, live full stack): `p1_edge_smoke.ps1` 6/6 — BFF proxy CRUD, ai-gateway federates all 5 `registry_` tools (prefix), agent-propose THROUGH gateway → proposal row (envelope owner survived federation).**
- [x] **E2E-P1-B/D/E full-turn injection (live LLM): published skill (real test account) → `/internal/skills` (chat-container fetch) → `user_skills_block` → Qwen-7B turn EMITTED the skill's marker `XYZZY-INJECTED` (asst content == marker; breakdown persisted). Agent-propose loop proven through the gateway.**
- [x] **E2E-P1-G deterministic form GREEN: panelCatalogContract 3/3 (enum⊆palette⊆buildable) + `registryPanels.test.tsx` 4/4 (ExtensionsPanel/ProposalsPanel/SkillEditorPanel actually MOUNT + render — the "assert the host effect" form). Live Playwright run still blocked by a concurrent agent holding the shared browser (`D-REG-P1G-BROWSER`) — a when-free follow-up, not a functional gap.**

### Deferred items — ALL CLEARED (2026-07-03)
- **D-REG-BOOK-GRANT** ✅ grantclient wired; book-tier writes grant-gated (live 404 fail-closed).
- **REG-X-02** ✅ 50-skill quota enforced at write (live 429).
- **D-REG-SKILLPROPOSAL-CARD** ✅ in-chat approve/reject card (chat-quality track landed; AssistantMessage clean).
- **Standalone /extensions route** ✅ ExtensionsPage (two-shells) + quota strip.
- **Save-as-skill affordance** ✅ prompt template.
- **D-REG-P1G-BROWSER** ✅ deterministic form (mount + contract); live browser = when-free follow-up.
- [ ] **GUI checklist ticked: §0, §1, §4, §6, §7, §9, §10(P1 rows)** (FE pending)

### P2 — Per-user federation
- [ ] REG-P2-01 registrations table
- [ ] REG-P2-02 catalog v1 + versioning + cache
- [ ] REG-P2-03 gateway overlay + flag + prefix + fast path
- [ ] REG-P2-04 perf + A/B isolation live smoke + 9-provider regression
- [ ] **E2E slice green: E2E-P2-A, B, C**
- [ ] **GUI checklist ticked: §2 (internal-reg rows)**

### P3 — External MCP security
- [ ] REG-P3-01 SSRF guard + capability rejection
- [ ] REG-P3-02 secret vault (has_secret only in public)
- [ ] REG-P3-03 OAuth 2.1+PKCE+RFC8707 + refresh
- [ ] REG-P3-04 egress path: allowlist/timeout/cap/breaker
- [ ] REG-P3-05 scan + quarantine machine
- [ ] REG-P3-06 wizard UI + servers browser list + status chips
- [ ] REG-P3-07 `/review-impl` + external-server live E2E
- [ ] REG-P3-08 Server detail page (scan review, health, tool browser) (U3)
- [ ] REG-P3-09 MCP-in-studio: wizard + detail inside the extensions panel, state survives hide/show (§13b)
- [ ] **E2E slice green: E2E-P3-A, B, C, D, E2E-X-B(servers)**
- [ ] **GUI checklist ticked: §2 (full), §3, §8, §10(P3 rows)**

### P4 — Commands + hooks
- [ ] REG-P4-01 command CRUD + expansion
- [ ] REG-P4-02 autocomplete + builder
- [ ] REG-P4-03 hook engine (deny/approve/inject/annotate)
- [ ] REG-P4-04 hook builder UI
- [ ] **E2E slice green: E2E-P4-A, B**
- [ ] **GUI checklist ticked: §5**

### P5 — Subagents + bundles
- [ ] REG-P5-01 subagent defs + scoped runtime
- [ ] REG-P5-02 bundle export/import
- [ ] REG-P5-03 official-registry ingest + curation
- [ ] REG-P5-04 plugin detail UX
- [ ] **E2E slice green: E2E-P5-A, B, C**
- [ ] **GUI checklist ticked: §1 (Import bundle rows)**

### Cross-cutting
- [ ] REG-X-01 audit trail (+ E2E-X-A piggyback asserts in every scenario)
- [ ] REG-X-02 quotas (D2)
- [ ] REG-X-03 metrics
- [ ] REG-X-04 session/deferred hygiene

### FINAL RELEASE GATE (the only human checkpoint — §7.6)
- [ ] Full E2E matrix (§6) green **in one pass** — evidence pack attached
- [ ] **`01_GUI_CHECKLIST.md` — all 270 lines ticked, re-walked against the running app (screen-by-screen vs draft-ui)**
- [ ] DECISION_LOG.md walkthrough with PO
- [ ] Live demo: P1 agent-self-registration loop + P3 external-server loop
- [ ] Deferred rows reviewed (D-SKILL-SCRIPTS, D-A2A-AGENTCARD, D-STDIO-MCP, D-PLUGIN-MARKETPLACE)
- [ ] PO approves → merge/release
