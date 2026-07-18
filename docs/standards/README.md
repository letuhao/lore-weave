# LoreWeave Standards Index — the one place

**This file is the single entry point to every cross-cutting rule, law, invariant, and machine contract in the repo.** It does **not** copy their content (that would create a second source of truth that drifts) — each row **links to the authoritative source** and records: *what it governs · where it lives · how it's enforced · status*.

> **Maintenance rule (read before adding a standard):** a new cross-cutting rule is not "done" until it has a row here. When you add/promote/retire a standard, update the matching row. An unlisted standard is invisible to the next agent/human — the exact failure this index exists to prevent.

Audited & assembled 2026-07-04. Status tokens are quoted from each doc's own header where present.

---

## How standards are enforced here (the meta-pattern)

Almost every standard in this repo is defended against **silent drift** (a schema/enum/language/contract that diverges across services or languages, passes isolated unit tests, and breaks the live cross-service loop) by one of two shapes:

- **Machine contract** → a **YAML/JSON/Go SoT file** + a **typed loader** + a **CI lint / pre-commit gate** + a **drift/snapshot test**. The SoT is authoritative; a lint rejects anything defined outside it.
- **Code invariant** → an **`INV-<id>`** cited *at its enforcement site* **and** *in its proving test*, so removing the guard turns a test red.

When you build something new, the question is not "is there a rule?" but "**which SoT + which gate + which test** does my change touch?"

---

## Quick-nav by concern

| I'm working on… | Read these (in order) |
|---|---|
| **A new MCP tool (input args + return shape)** | **[MCP Tool I/O Standard](./mcp-tool-io.md)** — the consolidated input+output discipline (enum-lock, self-correcting errors, 4-source drift, reference-first, concise-wire, verify-by-effect) |
| **An MCP tool's return shape (no context bloat)** | [MCP Tool I/O Standard §2](./mcp-tool-io.md) (OUT-1..6) → design authority [Context Budget Law §6](../specs/2026-07-03-context-budget-law.md) |
| **Chat-agent ↔ MCP wiring** | [MCP-first invariant](#a-platform-build-standards) · [Studio Agent Standard (07S)](../specs/2026-07-01-writing-studio/07S_studio_agent_standard.md) · [Agent GUI Reconciliation (09)](../specs/2026-07-01-writing-studio/09_agent_gui_reconciliation.md) |
| **An agent-RUNTIME / consuming the control layer (drive, executive, checkpoint, effect-probes)** | **[Agent Control Plane Standard](./agent-control-plane.md)** — the consumable boundary (contracts + per-language SDK); no forking chat-service, no god-service, contract machine-checked every side, verdict-only harness, per-mode enforcement |
| **Context budget / prompt assembly** | [Context Budget Law + Session Compiler](../specs/2026-07-03-context-budget-law.md) |
| **A dockable studio panel / GUI** | **[Dockable Panel Standard](./dockable-gui.md)** (the consolidated checklist DOCK-1..11) → [JSON Document Standard (12)](../specs/2026-07-01-writing-studio/12_json_document_standard.md) · [Studio State Architecture (08)](../specs/2026-07-01-writing-studio/08_studio_state_architecture.md) · `panelCatalogContract.test.ts` |
| **A new agent capability (skill/command/hook/subagent)** | [Agent Extensibility Standard](./agent-extensibility.md) |
| **A single-shot LLM generate feature** | [AI-Task Standard](../specs/2026-07-03-ai-task-standard.md) |
| **Any LLM/embed/rerank/image/audio call** | [Provider-gateway invariant](#a-platform-build-standards) — **ENFORCED** by `ai-provider-gate.py` |
| **A new table / any user data** | [User Boundaries & Tenancy](#a-platform-build-standards) (3-tier scope) · [User Data Scope & Protection](./user-data-scope.md) (C1–C6 classes) · [Data Persistence Rules](#a-platform-build-standards) |
| **A user setting / toggle / mode / threshold / any configurable behavior** | **[Settings & Configuration Boundary](./settings-and-config.md)** (SET-1..8) — is this a user setting or platform config? env = ceiling not a per-user knob; no silent fallback; must be consumed (not write-only); closed-set ⇒ enum |
| **Anything language-dependent** | [Multilingual / Anti-Language-Bias](./multilingual.md) — no English-only rule logic, Unicode-correct, CJK-aware |
| **Reusable logic / a shared utility** | [SDK-First](./sdk-first.md) — ≥2 users ⇒ SDK, never copy-paste |
| **Module/service boundaries** | [Data & Logic Scope Separation](./scope-separation.md) — one owner per concept |
| **Reading/writing entity or KG knowledge** | [INV-KAL](#c-code-level-invariants) — only through knowledge-gateway |
| **An LLM/provider call (logging its I/O)** | [LLM Call Logging Standard](./llm-call-logging.md) — one chokepoint, encrypted (dedicated key), trace-correlated |
| **Any logging / trace-id / redaction** | [Logging Standard](./logging.md) |
| **Anything security-sensitive** | [Security Standard](./security.md) — secrets/authN/authZ/injection/PII/encryption/SSRF/rate-limit |
| **Any perf-sensitive path** | [Performance Standard](./performance.md) — timeouts, pagination, no-blocking-async, SLOs |
| **Sending a user notification** | [Notification Standard](./notification.md) |
| **A stat / correction / feedback event** | [Analytics & Learning Standard](./analytics-and-learning.md) |
| **Any task, start to finish** | [Task Workflow v2.2](../../agentic-workflow/WORKFLOW.md) (+ opt-in [AMAW](../amaw-workflow.md)) |

---

## A. Platform build standards

The rules you read **before building** on the main LoreWeave product. Many are stated in **[`CLAUDE.md`](../../CLAUDE.md)** (always loaded into every agent session — the de-facto hub); this table points to the *authoritative detail* for each.

| Standard | Governs | Authoritative source | Status | Enforcement |
|---|---|---|---|---|
| **Agent Extensibility Standard** | storage→resolver→degrade-safe-consumer→live-E2E shape for any user/agent-authorable capability; 3-tier tenancy; 404 anti-oracle; enum closed-set args; quarantine+scan+SSRF for external sources | [docs/standards/agent-extensibility.md](./agent-extensibility.md) | ACTIVE | rule-IDs + `CLOSED_SET_ARGS` registration + mandatory consumer live-E2E + `/review-impl` |
| **Dockable Panel Standard** | authoring/migrating any Writing-Studio dock panel: DOCK-1..7/10/11 consolidate the 08/11/12 checklists; DOCK-8 bans internal page-replacement view-switches; DOCK-9 bans hand-rolled `fixed inset-0` overlays — mandates adopting the existing `components/shared/{FormDialog,ConfirmDialog}` (Radix-portal-based, now with a `size` prop for wizard-width content) instead of a per-panel one-off | [docs/standards/dockable-gui.md](./dockable-gui.md) | ACTIVE | `panelCatalogContract.test.ts` (DOCK-6) + `dockablePanelHygiene.test.ts` (DOCK-7/9, new) + review (rest) |
| **MCP Tool I/O Standard** | how every LLM-callable tool defines inputs (enum-lock, scope-from-envelope, self-correcting errors, 4-source drift, one-name-one-concept) + shapes outputs (reference-first, detail/limit, concise-wire, success-discrimination, no-silent-truncate); verify-by-effect; **catalog hygiene** (CAT-1..4: merge-by-discriminator not action-enum, explicit branching for divergent-safety merges, `items[]` batch with per-item results, `_meta.visibility` legacy-tag instead of deletion) | [docs/standards/mcp-tool-io.md](./mcp-tool-io.md) | ACTIVE (consolidation) | contract/drift-lock tests + `context-budget-l3-lint.py` (see doc §Enforcement for tracked gaps) |
| **MCP Tool `_meta` Completeness Law + Tool Liveness** | every tool declares `tier`+`scope`; a job-starter declares `async`; a money-spender declares `paid` and is **never tier R** (an absent tier silently defaults to `R`/inert ⇒ an untiered write runs in read-only *ask* mode and skips the approval card — found + fixed in knowledge `f191cb858`, still open in glossary). Plus `propose_*` semantics (token vs draft) and the **G1–G4 liveness gates**: an LLM-driven NL probe must prove each tool is selected, arg-shaped, executed, and **effectful** | [Track D contracts CD1–CD4](../specs/2026-07-09-mcp-tool-liveness-eval/contracts.md) | **PROPOSED** (Track D · WS-D0/D1) | per-service `tools/list` wire gate (reference: `knowledge-service/tests/test_mcp_server.py`) + `propose ⇒ tier ∈ {A,W}` lint + generated `matrix.json` ship gate |
| **LLM Call Logging Standard** | every provider call (streaming + sync) logs request+response through one chokepoint, encrypted with a dedicated key (not JWT_SECRET), trace-correlated, redacted, retention-decoupled | [docs/standards/llm-call-logging.md](./llm-call-logging.md) | ACTIVE (rules; enforcement P1) | round-trip decrypt test + `ai-provider-gate.py` chokepoint rule (to build) — see [audit](../plans/2026-07-04-enterprise-hardening-audit.md) |
| **Logging Standard** | one structured-JSON idiom per language, OTel trace-id auto-injected, typed source-side redaction, audit-vs-operational split | [docs/standards/logging.md](./logging.md) | ACTIVE (rules; enforcement P1) | revive+flip+wire `logging-discipline-lint.sh` (to build) |
| **Security Standard** | secrets/authN/authZ/injection/PII/encryption/SSRF/rate-limit/input-validation/audit for the main platform | [docs/standards/security.md](./security.md) | ACTIVE (rules; parts enforced) | gitleaks + SSRF + adminjwt + 404-oracle (today); dep-vuln-scan, raw-SQL/injection/pii lints, edge rate-limit (to build) |
| **Performance Standard** | timeouts all-languages, resilience matrix on product deps, bounded results, no-blocking-in-async, latency SLOs, caching | [docs/standards/performance.md](./performance.md) | ACTIVE (rules; parts enforced) | `timeout-discipline-lint` (Go/Rust) + `pagination-cap`/`blocking-in-async` (Python) + **platform latency SLO** `contracts/slo/latency.yaml` guarded by `slo-latency-lint.py` (P2·D; perf-nightly p95 assertion is the infra-gated tail `D-D-PERF-NIGHTLY`) |
| **Notification Standard** | one versioned envelope, category enum on every ingress, outbox+dedup delivery, user opt-out, PII on bodies | [docs/standards/notification.md](./notification.md) | ACTIVE (rules; enforcement P1) | `contracts/notifications/envelope` + consumer contract/no-silent-drop tests (to build) |
| **Analytics & Learning Standard** | statistics = one owner + frozen event contract; learning = one correction-event contract + no-silent-drop wiring; two-loop boundary | [docs/standards/analytics-and-learning.md](./analytics-and-learning.md) | ACTIVE (rules; enforcement P1) | event-contract + handler-coverage wiring tests (to build) |
| **Multilingual / Anti-Language-Bias** | language a first-class param; Unicode-correct normalization (NFKC+CJK, no naive lower); script-agnostic segmentation (no `[A-Z][a-z]`/space-split); no English-only rule logic; `ensure_ascii=False`; per-locale i18n from the Registry SoT (`languages.ts`); **ML-7 one authored `en` locale — every other locale is GAP-FILLED by `scripts/i18n_translate.py` (whole-repo auto-scan, reasoning-off, verify+self-heal+resumable, no silent blanks), never hand-edited, never a one-off translator** | [docs/standards/multilingual.md](./multilingual.md) | ACTIVE | `language-bias-gate.py` (ML-2/3/5) + golden fixtures (ML-1/4) + **`i18n-completeness-gate.py --staged` (ML-7, pre-commit)** + registry⇄`TARGETS` parity (to build) |
| **SDK-First** | reusable logic (used by ≥2 services) lives in `sdks/`/`contracts/`, never copy-pasted; adopt-don't-orphan; polyglot mirrors move together | [docs/standards/sdk-first.md](./sdk-first.md) | ACTIVE (rules; enforcement P1) | near-duplicate detector + symbol-level grep-gate + adoption check (to build) |
| **Data & Logic Scope Separation** | one data owner + one logic owner per concept; cross-service via contract not shared table; SSOT-vs-derived explicit; declare boundary at design time | [docs/standards/scope-separation.md](./scope-separation.md) | ACTIVE | DB-per-service + INV-FACTS (today); no-cross-service-DB + one-owner lints (to build) |
| **User Data Scope & Protection** | classify user data C1–C6; each class → scope key + protection profile (encryption, PII tags, retention, erasure, redaction) | [docs/standards/user-data-scope.md](./user-data-scope.md) | ACTIVE | pii-classify (MMO today) → extend to platform; tenancy tests; crypto-shred wiring (to build) |
| **Settings & Configuration Boundary** | when a configurable behavior is a **user setting** (tiered/resolved/consumed) vs **platform config** (global/env/deploy-owned); SET-1 don't abuse env for per-user behavior · SET-3 env = deploy ceiling not a per-user knob · SET-4 no silent fallback (effective value+source observable) · SET-5 must be consumed, prove by effect (no write-only store) · SET-6 closed-set ⇒ enum · SET-7 server-SSOT · SET-8 one home/one name, inherit don't re-store | [docs/standards/settings-and-config.md](./settings-and-config.md) | ACTIVE (rules; enforcement via review + linked gates) | `/review-impl` gate (env-abuse/silent-fallback/write-only) + tenancy tests (SET-2/7) + Frontend-Tool-Contract enum pattern (SET-6); candidate `settings-boundary-lint` (SET-1) to build |
| **AI-Task Standard** | every *non-agentic single-shot* LLM generate routes through shared `structured_generate`/`extract_json_object` + FE `EffortSelect`/`SpendCapField` | [docs/specs/2026-07-03-ai-task-standard.md](../specs/2026-07-03-ai-task-standard.md) | ACTIVE (boundary LOCKED) | SDK helper + acceptance tests + per-milestone live-smoke |
| **Agent Control Plane** | any *multi-step AGENTIC* runtime consumes control/governance (drive verdict, executive, checkpoint, effect-probes) through ONE surface — contracts + per-language SDK — never by forking chat-service: no god-service (extract to libs/contracts/existing services), contract machine-checked EVERY side, producer-stays-a-producer, verdict-only harness (consumer owns the loop), per-runtime-mode enforcement (interactive holds / autonomous parks), invariants pass through (owner-scoped checkpoints, per-user models, `/internal` probes), framework-agnostic port not a dependency | [docs/standards/agent-control-plane.md](./agent-control-plane.md) · design [ACP spec](../specs/2026-07-16-agent-control-plane-sdk.md) | ACTIVE (A0–A4 built 2026-07-16) | 3-side contract tests (chat/knowledge jsonschema + roleplay real-`freeze()`) + SDK goldens + real-DB owner-scope/lock test + `/review-impl` standards gate |
| **Context Budget Law + Session Compiler** | repo-wide MCP tool-return shape (L1/L2/L3) + Planner/Compiler budget; never silent-truncate | [docs/specs/2026-07-03-context-budget-law.md](../specs/2026-07-03-context-budget-law.md) | **DRAFT** (T0–T2 shipped) | L3 lint `scripts/context-budget-l3-lint.py` (live); per-tool contract-snapshot tests (planned) |
| **Studio Agent Standard (07S)** | how the Writing-Studio chat-agent is built: 7-bucket context, hybrid compaction, HITL permission modes, plan-mode, autonomy dial | [docs/specs/2026-07-01-writing-studio/07S_studio_agent_standard.md](../specs/2026-07-01-writing-studio/07S_studio_agent_standard.md) | DESIGN (decisions locked 2026-07-02) | convention + unit/live smoke |
| **JSON Document Standard (12)** | studio's 4th registry (`registerJsonDocumentProvider`), model–view split, save-wraps-domain-API (MCP-first), one-tool-per-cycle LIVE gate | [docs/specs/2026-07-01-writing-studio/12_json_document_standard.md](../specs/2026-07-01-writing-studio/12_json_document_standard.md) | specced 2026-07-02 | LIVE browser-smoke gate + `panelCatalogContract.test.ts` |
| **Studio State Architecture (08)** | cross-panel state contract: 5-tier model, read-only snapshot bus, one owner per domain hoist | [docs/specs/2026-07-01-writing-studio/08_studio_state_architecture.md](../specs/2026-07-01-writing-studio/08_studio_state_architecture.md) | specced (design) | panel-author checklist + bus/registry unit tests |
| **Agent GUI Reconciliation (09)** | how the agent affects the GUI: 3-lane model, **no data-bearing frontend tools**, reconciler reloads SSOT | [docs/specs/2026-07-01-writing-studio/09_agent_gui_reconciliation.md](../specs/2026-07-01-writing-studio/09_agent_gui_reconciliation.md) | specced (design) | `consumer_capabilities.frontend_tools` advertise filter + effect-registry tests |
| **Frontend-Tool Contract** <a id="frontend-tool-contract"></a> | agent→GUI tools span 2 services/2 langs: closed-set arg⇒enum, resolver never silently no-ops, one-name-one-concept, machine-checked both sides, verify-by-effect | [`CLAUDE.md`](../../CLAUDE.md) §Frontend-Tool Contract · SoT [contracts/frontend-tools.contract.json](../../contracts/frontend-tools.contract.json) | **LOCKED** | 4 tests (see [§D](#d-enforcement-mechanisms)) |
| **MCP-first invariant** | any AI *agent* capability MUST be an MCP tool-call through `ai-gateway` (never bespoke HTTP/raw-prompt); domain owns its tools | [`CLAUDE.md`](../../CLAUDE.md) · [docs/specs/2026-06-10-glossary-assistant-architecture.md](../specs/2026-06-10-glossary-assistant-architecture.md) | ENFORCED (convention) | review; new agentic HTTP tracked in Deferred |
| **Provider-gateway invariant** | no service imports a provider SDK / calls a provider API directly; all LLM/embed/**rerank**/image/audio/STT via `provider-registry-service`; local backends only as BYOK creds | [`CLAUDE.md`](../../CLAUDE.md) | **ENFORCED** | `scripts/ai-provider-gate.py` (pre-commit + CI) |
| **No hardcoded model names** | model names + pricing resolve from provider-registry, never literal in runtime code | [`CLAUDE.md`](../../CLAUDE.md) | **ENFORCED** | `scripts/ai-provider-gate.py` |
| **Language rule (I3)** | Rust=kernel-derived · Go=domain/meta · Python=AI/LLM · TS=gateway/realtime | SoT [contracts/language-rule.yaml](../../contracts/language-rule.yaml) · [I3 amendment](../plans/2026-05-29-foundation-mega-task/I3_INVARIANT_AMENDMENT.md) | **LOCKED 2026-05-29** | `scripts/language-rule-lint.sh` (CI) |
| **User Boundaries & Tenancy** | 3 scope tiers (System/Per-user/Per-book); no regular-user write to shared rows; every table carries a scope key; grant-gated cross-tenant; tier-merged resolution | [`CLAUDE.md`](../../CLAUDE.md) §User Boundaries | **LOCKED** | review + partial-UNIQUE(scope,name) schema pattern |
| **Data Persistence Rules** | server-is-SSOT; no localStorage for user data; multi-device; persist UI state to DB; prefs write-through | [`CLAUDE.md`](../../CLAUDE.md) · [docs/DATA_ARCHITECTURE.md](../DATA_ARCHITECTURE.md) | ACTIVE ("enforced") | review |
| **Frontend Architecture (React MVC)** | hooks=controllers · context=services · components=views; no `useEffect` for events; split context by update freq; ~100/200-line limits | [`CLAUDE.md`](../../CLAUDE.md) §Frontend Architecture Rules | ACTIVE | review |
| **Gateway invariant (I1)** | all external traffic through `api-gateway-bff` (one sanctioned exception: PRR-20 game-server WS) | [`CLAUDE.md`](../../CLAUDE.md) · [docs/ARCHITECTURE.md](../ARCHITECTURE.md) | ACTIVE | review |
| **Per-service DB ownership / no cross-DB FK** | each microservice owns its Postgres DB; integrate via HTTP/outbox, never shared tables | [docs/DATA_ARCHITECTURE.md](../DATA_ARCHITECTURE.md) · [`CLAUDE.md`](../../CLAUDE.md) | ACTIVE ("enforced") | review |
| **Two-layer glossary↔knowledge** | glossary = authored SSOT; knowledge adds fuzzy/semantic layer anchored via `glossary_entity_id` FK | [docs/03_planning/KNOWLEDGE_SERVICE_ARCHITECTURE.md](../03_planning/KNOWLEDGE_SERVICE_ARCHITECTURE.md) | ACTIVE | review |
| **Task Workflow v2.2** (+ opt-in **AMAW v3.0**) | mandatory 12-phase per-task flow; size-by-complexity/risk; anti-skip; POST-REVIEW never skippable; VERIFY evidence gate | [agentic-workflow/WORKFLOW.md](../../agentic-workflow/WORKFLOW.md) · [docs/amaw-workflow.md](../amaw-workflow.md) | ACTIVE (v2.2 default; AMAW opt-in) | `scripts/workflow-gate.py` state machine + commit-blocking gate |
| **No-Defer-Drift** | FIX-NOW default; a deferral must earn a row via the 5-point gate; "missing infra" ≠ "blocked" | [`CLAUDE.md`](../../CLAUDE.md) §No Deadline · [docs/deferred/DEFERRED.md](../deferred/DEFERRED.md) | ACTIVE | review at each PLAN |
| **A11y Policy** | all user-facing FE ships WCAG 2.2 AA | [docs/02_governance/A11Y_POLICY.md](../02_governance/A11Y_POLICY.md) | Policy — **enforced** | axe-core CI (serious/critical **block merge**) |
| **UI Copy Style Guide** | terminology map + progressive disclosure; no internal terms in default UI; i18n EN+VI min | [docs/02_governance/UI_COPY_STYLEGUIDE.md](../02_governance/UI_COPY_STYLEGUIDE.md) | Policy — enforced at review | PR checkbox (manual) |
| **Debugging Protocol** | no fixes without root cause; INVEST→PATTERN→HYPOTHE→FIX; 3-strike hard-stop | [`CLAUDE.md`](../../CLAUDE.md) §Debugging Protocol | ACTIVE | convention |
| **Test Parallelization** | pytest-xdist `-n auto --dist loadgroup`; DB-touching tests carry `xdist_group("pg")` | [`CLAUDE.md`](../../CLAUDE.md) §Test Parallelization | ACTIVE | convention (a missing mark → interleaved counts) |
| **Lean Context Architecture** | token-efficient docs convention (single-SoT, tiered, Module Briefs) | [docs/02_governance/LEAN_CONTEXT_ARCHITECTURE.md](../02_governance/LEAN_CONTEXT_ARCHITECTURE.md) | **Proposal** (DA review pending) | convention |

---

## B. Cross-cutting machine contracts

Shared, machine-readable interop SoT files (excluding per-service OpenAPI feature specs under `contracts/api/*/v1/`). Pattern: **YAML/JSON SoT + typed loader + CI-lint + drift-test**.

| SoT file | Standardizes | Consumed by / gate |
|---|---|---|
| [contracts/language-rule.yaml](../../contracts/language-rule.yaml) | `services/<name>/` → required language | `scripts/language-rule-lint.sh` (FAIL on mismatch / declared-missing-but-present / present-but-unmapped) |
| [contracts/frontend-tools.contract.json](../../contracts/frontend-tools.contract.json) | agent→GUI frontend-tool arg schemas + enum rule (cross-language SoT) | BE `frontend_tools.py` + FE resolvers; regen `WRITE_FRONTEND_CONTRACT=1 pytest` |
| `contracts/api/knowledge-gateway/kal.v1.yaml` | the **KAL** versioned read/write boundary over glossary EAV + Neo4j KG | knowledge-gateway + all KAL consumers; backs **INV-KAL** |
| `contracts/dependencies/matrix.yaml` | every external dependency (timeout, breaker, retry, bulkhead, fallback, runbook) | `dependency-registry-lint.sh` + `client_factory.go` (wrapped clients) |
| `contracts/events/_registry.yaml` | authoritative `event_type` registry (versions, upcasters) | `make eventgen` → polyglot outputs; CI `eventgen-validate.sh` (drift-fail) |
| `contracts/errors/canonical.go` | 4 canonical error classes (`user`/`system`/`transient`/`permanent`) | Go services; exhaustiveness tests |
| `contracts/cache/keys.yaml` | cache-key namespace registry (kind, TTL, invalidation, sensitivity) | Go `KeyRegistry` (rejects unregistered kinds at runtime) |
| `contracts/slo/latency.yaml` | platform user-HTTP p95 latency SLO per top-level endpoint (P2·D; complements the MMO `slo_targets.yaml`) | `scripts/slo-latency-lint.py` (shape/presence) + planned perf-nightly p95 assertion |
| `contracts/canon/guardrail_rules.yaml` | L1 axiomatic canon-guardrail predicates | roleplay-service pre-prompt `check_proposed_write` |
| `contracts/entity_status/v1.yaml` (+`.go`) | shared entity-status kernel wire mirror (gone-state, precedence) | Go + Rust in-process libs (byte-parity) |
| `contracts/adminjwt/` (Go module) | shared RS256 admin-JWT claims/verify/break-glass | every admin surface; backs INV-T2/T6 |
| `contracts/service_acl/matrix.yaml` | RPC allow-list between services (S11) | `service-acl-matrix-lint.sh` |
| `contracts/admin/registry/*.yaml` | per-domain admin command registry (name, params, impact_class) | `admin-command-registry-lint.sh` + `adminjwt` gate |
| `contracts/capacity/budgets.yaml`, `contracts/alerts/rules.yaml`, `contracts/incidents/severity_matrix.yaml`, `contracts/backup/policy.yaml`, `contracts/chaos/v1.yaml` | capacity / alert / incident-severity / backup / chaos SoTs (each + Go loader + lint) | respective ops modules |
| [contracts/service_contracts.md](../../contracts/service_contracts.md) | narrative index of shared data types + which OpenAPI is authoritative per gateway path | orientation (human, not machine-loaded) |
| `contracts/.spectral.yaml` | OpenAPI lint ruleset | Spectral CI over `contracts/api/**` |

---

## C. Code-level invariants

Durable `INV-<id>` rules cited **at the enforcement site and in a proving test**. Live in `services/` (none in `sdks/`). Grep an ID to find both its guard and its test.

**Tenancy & tool-authority (INV-T\*)** — T1 MCP writes mint a confirm-token (no mutation until redeemed) · T2 admin actions carry RS256 `admin:write`, send **no** `X-User-Id` (identity from trusted envelope) · T3 graph-shape/schema/System-tier changes are **human-confirmed** (agent proposes only) · T4 System-tier admin tools only on the CMS surface · T5 project tools grant-gate via resolve-to-owner, user tools enforce `owner==caller` · T6 admin MCP is a **physically separate** `/mcp/admin` endpoint (un-enumerable without admin token) · T11 reasoning-effort clamped to the caller's grant ceiling.

**Knowledge graph (INV-K\*)** — K1 a proposed edge/fact parks to the **triage inbox**, never a direct Neo4j write · K2 `user_id`/`session_id` come from MCP headers only, never LLM args (arg models `extra="forbid"`).

**Knowledge Access Layer** — **INV-KAL** no service reads/writes glossary EAV or Neo4j KG except through the knowledge-gateway (the single versioned typed boundary). Gated by `scripts/knowledge-access-gate.py` + `scripts/knowledge-http-surface-gate.py` (both pre-commit).

**Facts SSOT** — **INV-FACTS** `entity_facts` is the single source of truth; the EAV projection + prose snapshot are lazy, versioned, **regenerable caches — never truth**.

**Extraction concurrency (INV-C\*)** — C1 per-book serialized transactional writeback · C2 partial-UNIQUE dedup · C3 idempotent replay by `writeback_key` · C4 content-hash precondition (source-drift 409) · C5 idempotent evidence (one row per quote).

**Outbox / observability (INV-O\*, INV-F15)** — O12 per-batch outcome rows are the observability truth · O13 redelivery-stable event IDs → idempotent projection · O14 job-terminal rollup from batch outcomes · F15 chapter status is **derived** from batch-outcome statuses. (INV-O12 also = the transactional-outbox atomic-emit guarantee in glossary.)

**The knowledge MCP "4-source discipline"** — a KG/memory MCP tool's schema is duplicated across **four** artifacts that MUST move in lockstep or a weak model silently loses an arg: (1) Pydantic arg model (`graph_schema_tools.py` `ARG_MODELS`, `extra="forbid"`) · (2) hand-written JSON schema (`definitions.py` `TOOL_DEFINITIONS`) · (3) **FastMCP signature** (`mcp/server.py` — advertises + validates + **STRIPS** any unlisted arg) · (4) committed snapshot + mirror test (`test_mcp_server.py`, `test_graph_schema_tools.py`). In-code drift-lock comments name the tests that go red. (See memory `knowledge-mcp-three-schema-sources-fastmcp-strips`.)

---

## D. Enforcement mechanisms

<a id="d-enforcement-mechanisms"></a>

**Scripts / gates** (all verified present 2026-07-04):

| Script | Enforces | Wiring |
|---|---|---|
| [scripts/ai-provider-gate.py](../../scripts/ai-provider-gate.py) | Provider-gateway invariant + no-hardcoded-model + local-backend-is-BYOK (Py/TS/Go SDK imports, model literals; allowlist + DEFERRED tracking) | pre-commit `--staged` + CI; self-tested by `scripts/test_ai_provider_gate.py` |
| [scripts/language-rule-lint.sh](../../scripts/language-rule-lint.sh) | Language rule I3 vs `contracts/language-rule.yaml` | CI (`lint-foundation.yml`) |
| [scripts/workflow-gate.py](../../scripts/workflow-gate.py) (+`.sh`) | Task Workflow state machine (size, phase, VERIFY/POST-REVIEW/SESSION evidence, cross-service live-smoke soft-warn) | pre-commit + manual; run on Windows via `python scripts/workflow-gate.py` |
| [scripts/knowledge-access-gate.py](../../scripts/knowledge-access-gate.py) | INV-KAL table half (no EAV read outside glossary / no Neo4j driver outside knowledge) | pre-commit `--staged` |
| [scripts/knowledge-http-surface-gate.py](../../scripts/knowledge-http-surface-gate.py) | INV-KAL HTTP half (consumers use `KNOWLEDGE_GATEWAY_URL /v1/kal/...`, not owning services' `/internal/*`) | pre-commit `--staged` |
| [scripts/context-budget-l3-lint.py](../../scripts/context-budget-l3-lint.py) | Context Budget Law **L3** (concise-wire: `ensure_ascii=false`, drop-empty at tool-result serialization) | Context Budget Law T0 |
| [scripts/slo-latency-lint.py](../../scripts/slo-latency-lint.py) | Platform latency SLO SoT (`contracts/slo/latency.yaml`): shape/required-fields/positive-p95/unique-id+route/real-service (P2·D) | `lint-foundation.yml` p1-lints matrix |

**Foundation lint suite** — `.github/workflows/lint-foundation.yml` runs 15 L1 lints as PR checks (catalog: [docs/governance/lint-catalog.md](../governance/lint-catalog.md), **LOCKED**). Platform-relevant: `language-rule`, `outbox-event-emit`, `service-acl-matrix`, `dependency-registry`, `admin-command-registry`.

**Contract / drift-lock tests** (guard the standards above):

| Test | Guards |
|---|---|
| `services/chat-service/tests/test_frontend_tools_contract.py` (BE) | Frontend-Tool Contract — snapshots every schema into `frontend-tools.contract.json`, enforces closed-set-arg⇒enum |
| `frontend/src/features/chat/nav/__tests__/frontendToolContract.test.ts` (FE) | each pure resolver reads every required arg + rejects with an error (no silent no-op) |
| `frontend/src/features/studio/panels/__tests__/panelCatalogContract.test.ts` | advertised `panel_id` enum ⊆ palette-openable ⊆ dock catalog (dockable-GUI lockstep) |
| `services/knowledge-service/tests/test_mcp_contract.py` | MCP dispatch — scope-from-headers-only (D3) + success-discrimination |
| `services/knowledge-service/tests/test_mcp_server.py` + `tests/unit/test_graph_schema_tools.py` | the KG-tool 4-source drift-lock (tool count + enum value-sets + `CLOSED_SET_ARGS`) |
| `sdks/python/tests/test_jobs_contract.py` | Unified Job Control-Plane contract (terminal-status set, stream routing) |
| composition/knowledge/lore-enrichment `test_*_response_contract.py` | per-service API response-shape contracts |

---

## E. Governance & ops

| Standard | Governs | Source | Status |
|---|---|---|---|
| Admin Command Catalog (R13) | admin CLI registered/tiered/audited via one binary + per-domain YAML registry | [docs/governance/admin-command-catalog.md](../governance/admin-command-catalog.md) | **LOCKED** — `admin-command-registry-lint.sh` |
| Foundation Lint Catalog (L1.K) | the 15 CI lints enforcing L1 invariants | [docs/governance/lint-catalog.md](../governance/lint-catalog.md) | **LOCKED** — `lint-foundation.yml` |
| On-Call SLA | severity → TTA/TTM/comms/postmortem targets | [docs/governance/oncall-sla.md](../governance/oncall-sla.md) | **LOCKED** — PagerDuty + `alert-rule-validator.sh` |
| Glossary Canon Outbox Contract (L5.A) | wire schema + outbox timing for canon events | [docs/governance/glossary-service-outbox-contract.md](../governance/glossary-service-outbox-contract.md) | **DRAFT** — `canon_test.go` fixtures |
| Admin Action Policy | admin tooling: compensating events, audit, destructive dual-approval, impact class | [docs/02_governance/ADMIN_ACTION_POLICY.md](../02_governance/ADMIN_ACTION_POLICY.md) | Policy — enforced at review + CI `ImpactClass` lint |
| Cross-Instance Data Access Policy | bans cross-reality live queries (no `postgres_fdw` / fan-out) | [docs/02_governance/CROSS_INSTANCE_DATA_ACCESS_POLICY.md](../02_governance/CROSS_INSTANCE_DATA_ACCESS_POLICY.md) | Policy — enforced at review |
| Service Language Matrix | per-service language/framework/ownership + runtime boundary | [docs/01_foundation/04_TECHSTACK_SERVICE_MATRIX.md](../01_foundation/04_TECHSTACK_SERVICE_MATRIX.md) | Approved v1.3.0 — `language-rule-lint.sh` |
| V1 Boundaries / Working Model / Operating RACI | scope freeze · scrumban cadence · role accountability | `docs/01_foundation/03_V1_BOUNDARIES.md`, `docs/02_governance/{05_WORKING_MODEL_SCRUMBAN,06_OPERATING_RACI}.md` | Approved | 

---

## F. MMO-RPG track (separate sub-project)

The `docs/03_planning/LLM_MMO_RPG/` game sub-project carries its **own** heavily-machine-enforced invariant set (Rust newtypes + clippy + compile-time + CI). Not part of the active novel-workflow product, but listed so the rules are discoverable. Authoritative invariant docs (mostly header **"LOCKED"**):

| Family | Doc | Enforcement |
|---|---|---|
| Foundation Invariants **I1–I19** | [00_foundation/02_invariants.md](../03_planning/LLM_MMO_RPG/00_foundation/02_invariants.md) | per-rule CI lints + Postgres roles + review |
| Kernel API (route-through functions) | `00_foundation/04_kernel_api.md` | CI lints block raw paths + SELECT-only meta role |
| Feature Workflow + ownership/extension/slots | `00_foundation/07_feature_workflow.md`, `_boundaries/0[1-3]_*.md` | `_LOCK.md` single-writer + additive-first + boundary-matrix lint |
| Data Plane **DP-A1–A19 / DP-R1–R8 / DP-T0–T3** | [06_data_plane/02_invariants.md](../03_planning/LLM_MMO_RPG/06_data_plane/02_invariants.md), `11_access_pattern_rules.md`, `03_tier_taxonomy.md` | compile-time (Rust newtypes, module privacy) + `dp::forbid_*` clippy lints |
| Event Model **EVT-A/P/V/S** | [07_event_model/02_invariants.md](../03_planning/LLM_MMO_RPG/07_event_model/02_invariants.md) + `0[4-6]_*.md`, `11_schema_versioning.md` | capability-JWT `produce` claim + validator pipeline + CI replay-test gate |
| LLM Safety (root I/O law + injection defense) | `05_llm_safety/00_principle.md`, `04_injection_defense.md` | event-sourced world SSOT ("LLM narrates, world decides") + RLS + mandatory integration test |
| Locked Decisions ledger | `decisions/locked_decisions.md` | append-only binding precedent |
| Storage resolutions (S5/S11/S12/SR5) | `docs/03_planning/LLM_MMO_RPG/…/02_storage/S*.md` | admin-classification / SVID ACL / WS-security / deploy-safety lints |

---

## Enterprise hardening audit (2026-07-04)

A 6-area investigation (LLM-call logging · logging · security · performance · notification · analytics/learning) is recorded in **[docs/plans/2026-07-04-enterprise-hardening-audit.md](../plans/2026-07-04-enterprise-hardening-audit.md)** — current-state maps, the **P0 live defects** (LLM read-back returns empty; streaming/embed unlogged; payload key = JWT_SECRET; notification `mcp_approval` silently dropped; chat prompt-injection hole; pre-commit hooks inactive), and the **P1 enforcement backlog** that gives the six new standards above their teeth. The standards state the *rule*; the audit states the *gap + the work to close it*. Cross-cutting finding: the apparatus usually already exists at enterprise grade — most work is pointing it at the product + extending Go/Rust-only lints to Python + flipping warn-mode/unwired gates to blocking.

## Known gaps & caveats

1. **⚠️ Pre-commit hooks are NOT active on a fresh checkout.** `git config core.hooksPath` currently returns the default `.git/hooks`, so `ai-provider-gate.py` + the two knowledge KAL gates only run after the **one-time** `git config core.hooksPath .githooks` step (named in CLAUDE.md). Until then, those "ENFORCED" rules are CI-only. **Run it once per clone.**
2. **~~MCP tool I/O discipline fragmented across 4 places~~ → RESOLVED 2026-07-04** — consolidated into **[docs/standards/mcp-tool-io.md](./mcp-tool-io.md)** (input IN-1..8 + output OUT-1..6 + verify-by-effect). *Residual:* the doc's own §Enforcement tracks 3 not-yet-enforced items (no cross-service MCP-tool lint; no repo-wide reference-first snapshot harness; 4-source drift-lock is knowledge-only). Those are candidate enforcement work, not doc gaps.
3. **INV-KAL is enforced but under-documented in the hub** — two pre-commit gates guard it, yet it is not in CLAUDE.md's "Key Rules". Its design home is `docs/specs/2026-06-29-incremental-temporal-knowledge-architecture.md` §6D.
4. **The newest platform standards are DRAFT/DESIGN**, not blocking gates — Context Budget Law, Studio Agent/State/Reconciliation/JSON-Document, AI-Task Standard are *build-to specs*, partially shipped, mostly convention + targeted tests. Their status tokens above are honest; don't assume a red-on-violation gate exists.
5. ~~Dockable GUI has no standard doc~~ → **RESOLVED 2026-07-04** — [`docs/standards/dockable-gui.md`](./dockable-gui.md) consolidates 08/11/12 into DOCK-1..11 and adds DOCK-8 (no internal page-replacement) + DOCK-9 (no hand-rolled viewport overlay), both surfaced while scoping the Glossary dockable migration. DOCK-9's fix turned out to already exist (`components/shared/FormDialog`/`ConfirmDialog`, 21 pre-existing call sites) — only gap closed was a `size` prop for wizard-width content. *Residual:* the six glossary hand-rolled overlays are not yet migrated onto it — that lands with the Glossary cycle itself, not before.
