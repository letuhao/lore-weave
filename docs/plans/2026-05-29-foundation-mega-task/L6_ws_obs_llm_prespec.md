# L6 — WebSocket Security + Observability/Capacity Runtime + LLM Safety Pre-Spec

> **Parent:** [_index.md](_index.md)
> **Depth target:** B (artifact-level)
> **Status:** DRAFT — first-pass enumeration

---

## §1. Scope of L6

Operational runtime that takes L4 contract skeletons (`contracts/ws/`, `contracts/observability/`, `contracts/capacity/`, `contracts/prompt/`) and ships their working implementations — EXCEPT actual LLM logic (which is out of foundation per scope decision).

**Relationship to L4:**
- L4.L ships `contracts/ws/` types only (ticket struct, envelope, session_store types)
- L6.A-E ship the running WS server (api-gateway-bff + roleplay-service WS lib)
- L4.H ships obs inventory + admission lib types
- L6.F ships the V1 warn / V1+30d hard-reject admission runtime + budget breach writer
- L4.I ships capacity budgets.yaml + admission lib types
- L6.G ships the deployment-time enforcement
- L4.D ships `contracts/prompt/` skeleton (signatures, intent enum, section enum, audit writer)
- L6.H-K ship the 8-section template composer, input wrapping, canary token, **but NOT** the LLM call itself

**IN scope:**
- L6.A WebSocket server (api-gateway-bff + roleplay-service WS lib)
- L6.B WS ticket handshake server
- L6.C WS per-message re-auth (S2 + S3 per S12 §12AB.L3)
- L6.D WS forced disconnect via Redis control channel
- L6.E WS metrics + alerts
- L6.F Observability admission runtime (V1 warn-and-drop → V1+30d hard-reject)
- L6.G Capacity admission runtime (deployment-time enforcement)
- L6.H Prompt 8-section template composer (Layer 3 of S09)
- L6.I Prompt user-input wrapping + canary token (Layer 4-5 of S09)
- L6.J Prompt provider adapter routing (via `provider-registry-service` — existing — NOT direct SDK calls)
- L6.K Prompt template scaffolding (1 empty `.tmpl` per intent + fixtures stub — actual prompt copy OUT)
- L6.L Empty intent classifier stub + injection defense stub + world oracle stub (foundation ships interfaces; bodies OUT)

**OUT (deferred / out of foundation per scope):**
- Actual LLM-call logic (intent classifier, world oracle, injection defense bodies)
- Prompt template content (the actual instruction text per intent)
- Full S9 Layer 6 (output post-scan, canon-drift lint)
- Full A3/A5/A6 LLM safety logic
- Direct LLM provider SDK integration (goes through existing `provider-registry-service` + `LiteLLM`)

---

## §2. Sub-components

### L6.A — WebSocket server (api-gateway-bff + roleplay-service WS lib)

**Owning chunks:** S12 §12AB (WS security), I1 (gateway invariant)

**Artifacts:**

| ID | Artifact | Type | Notes |
|---|---|---|---|
| L6.A.1 | `services/api-gateway-bff/src/ws/server.ts` | TS code | WS server in NestJS — per I1 gateway invariant |
| L6.A.2 | `services/api-gateway-bff/src/ws/upgrade_handler.ts` | TS code | HTTP → WS upgrade, validates `Sec-WebSocket-Protocol: lw.v1, ticket.<id>` |
| L6.A.3 | `services/api-gateway-bff/src/ws/session_router.ts` | TS code | Routes inbound messages to roleplay-service per session_id |
| L6.A.4 | `services/api-gateway-bff/src/ws/outbound_fanout.ts` | TS code | Consumes Redis Streams `reality:<id>:events` (L2.L) + fans to subscribed WS connections |
| L6.A.5 | `crates/contracts-ws/src/server_lib.rs` | Rust | WS lib for roleplay-service (downstream of api-gateway-bff) |
| L6.A.6 | `services/api-gateway-bff/src/ws/config.ts` | Config | WS upgrade rate limit, max message size, keepalive |
| L6.A.7 | `tests/integration/ws_e2e_test.ts` | Test | E2E: ticket fetch → upgrade → message round-trip → disconnect |

**Acceptance criteria:**
- WS server handles 10K concurrent connections per replica
- Message round-trip latency < 50ms P99
- Per I1, NO direct WS connections to roleplay-service from external clients

---

### L6.B — WS ticket handshake server

**Owning chunks:** S12 §12AB.2 (handshake flow)

**Artifacts:**

| ID | Artifact | Type | Notes |
|---|---|---|---|
| L6.B.1 | `services/api-gateway-bff/src/ws/ticket_endpoint.ts` | TS code | `POST /v1/ws/ticket` — issues one-shot ticket (60s TTL) |
| L6.B.2 | `services/api-gateway-bff/src/ws/ticket_redis.ts` | TS code | Stores ticket in Redis with TTL + atomic DEL on redemption |
| L6.B.3 | `crates/contracts-ws/src/ticket.rs` extended | Rust | (L4.L.2 extension) Ticket validation server-side |
| L6.B.4 | `tests/integration/ws_ticket_test.ts` | Test | Issue ticket; use; verify single-use (replay rejected); expire after 60s |
| L6.B.5 | `runbooks/ws/ticket_replay_attack.md` | Doc | SRE runbook |

**Acceptance criteria:**
- Ticket single-use enforced (Redis atomic DEL)
- Ticket NEVER appears in URL query string (per S12 §12AB.2 step 2)
- TTL 60s exactly
- `user_ref_id + allowed_realities + allowed_scopes + origin_hash + fingerprint_hash` correctly bound in ticket

---

### L6.C — WS per-message re-auth

**Owning chunks:** S12 §12AB.L3 (closes S2-regression-via-WS)

**Artifacts:**

| ID | Artifact | Type | Notes |
|---|---|---|---|
| L6.C.1 | `services/api-gateway-bff/src/ws/per_message_authz.ts` | TS code | Re-runs S2 (session_participants) + S3 (privacy_level) authorization on EVERY inbound AND outbound message |
| L6.C.2 | `crates/contracts-meta/src/authz.rs` Rust port | Code | Shared authz library |
| L6.C.3 | `tests/integration/ws_authz_regression_test.ts` | Test | User leaves session → next inbound WS message rejected; user not in confidential scope → outbound confidential event dropped |
| L6.C.4 | `contracts/observability/inventory.yaml` entries | Registry | `lw_ws_authz_rejections_total{reason}` |

**Acceptance criteria:**
- Per-message re-auth verifiable in test
- Rejection latency < 1ms
- S2 + S3 regressions caught by test fixture

---

### L6.D — WS forced disconnect via Redis control channel

**Owning chunks:** S12 §12AB (forced disconnect, close codes 1000, 4001..4010)

**Artifacts:**

| ID | Artifact | Type | Notes |
|---|---|---|---|
| L6.D.1 | `services/api-gateway-bff/src/ws/control_channel_consumer.ts` | TS code | Consumes Redis Stream `lw:ws:control` |
| L6.D.2 | `crates/contracts-ws/src/close_codes.rs` | Code | Enum of 10 close codes (1000 normal, 4001..4010 specific reasons) |
| L6.D.3 | `services/api-gateway-bff/src/ws/disconnector.ts` | TS code | Closes matching WS connections with correct code |
| L6.D.4 | `tests/integration/ws_forced_disconnect_test.ts` | Test | Emit control event → connection closes within 1s; correct close code surfaced |
| L6.D.5 | `runbooks/ws/forced_disconnect.md` | Doc | SRE runbook |

**Acceptance criteria:**
- Propagation SLA < 1s; P99 > 5s → page (per S12)
- All 10 close codes have correct semantic mapping
- Force-disconnect of single user by `user_ref_id` works (all that user's connections close)

---

### L6.E — WS metrics + alerts

**Owning chunks:** S12 §12AB (monitoring), I19 (obs inventory)

**Artifacts:**

| ID | Artifact | Type | Notes |
|---|---|---|---|
| L6.E.1 | `services/api-gateway-bff/src/ws/metrics.ts` | TS code | `lw_ws_*` metrics emission |
| L6.E.2 | `contracts/observability/inventory.yaml` entries | Registry | All `lw_ws_*` metrics declared |
| L6.E.3 | `infra/prometheus/alerts/ws.yaml` | Config | WS alerts (connection saturation, message latency, refresh failures, replay-token reuse) |
| L6.E.4 | `dashboards/ws-health.json` | Grafana | Per-region WS health |
| L6.E.5 | `runbooks/ws/refresh_failures.md` | Doc | SRE runbook (per SR2 alert routing) |

**Acceptance criteria:**
- All metrics inventoried
- Alerts routed to SRE primary per SR2
- Dashboard shows per-region + per-deploy-cohort splits

---

### L6.F — Observability admission runtime (V1 warn-and-drop → V1+30d hard-reject)

**Owning chunks:** SR12 §12AO (admission control), I19

**Artifacts:**

| ID | Artifact | Type | Notes |
|---|---|---|---|
| L6.F.1 | `contracts/observability/admission_runtime.go` (+ Rust + Python) | Code | (L4.H.3 ext) Runtime check on every `lw_*` emission |
| L6.F.2 | `contracts/observability/budget_breach_writer.go` ext | Code | (L4.H.6 ext) Writes `observability_budget_breaches` (meta) row |
| L6.F.3 | `pkg/metrics/admission_lib.go` (+ Rust + Python) | Code | Service-side metric lib wrapper enforcing admission |
| L6.F.4 | `tests/integration/admission_v1_warn_test.rs` | Test | Unregistered metric: V1 mode emits warning + drops; V1+30d mode rejects |
| L6.F.5 | `contracts/observability/migration.md` | Doc | V1 → V1+30d transition runbook |

**Acceptance criteria:**
- V1: warn + drop unregistered (no service crash)
- V1+30d: hard reject (service still functional but metric not emitted)
- Budget breach written within 100ms of rejection
- Library wraps Prometheus client cleanly (no boilerplate in service code)

---

### L6.G — Capacity admission runtime (deployment-time enforcement)

**Owning chunks:** SR08 §12AK (capacity budget enforcement), I17

**Artifacts:**

| ID | Artifact | Type | Notes |
|---|---|---|---|
| L6.G.1 | `infra/k8s/admission-webhook/capacity_checker.go` Go | Code | Kubernetes admission webhook — validates pod spec against budgets.yaml |
| L6.G.2 | `infra/k8s/admission-webhook/deployment.yaml` | IaC | Webhook deployment + cert |
| L6.G.3 | `contracts/capacity/override_handler.go` | Code | Reads override audit table; allows pod that exceeds budget if active override |
| L6.G.4 | `tests/integration/capacity_admission_test.go` | Test | Pod exceeding budget → admission rejects; with valid override → admits |
| L6.G.5 | `runbooks/capacity/budget_breach_at_deploy.md` | Doc | SRE runbook |

**Acceptance criteria:**
- Webhook rejects deploys exceeding budget (without override)
- Override grants 24h auto-expire (per S5 Tier 2)
- Webhook latency < 100ms (doesn't slow deploys)

---

### L6.H — Prompt 8-section template composer

**Owning chunks:** S09 §12Y.4 Layer 3 (strict section structure), I10 invariant

**Artifacts:**

| ID | Artifact | Type | Notes |
|---|---|---|---|
| L6.H.1 | `contracts/prompt/composer.rs` (+ Go + Python) | Code | Composes 8 sections per intent into final prompt string |
| L6.H.2 | `contracts/prompt/section_renderer.rs` | Code | Per-section rendering logic (markdown-safe, escape rules) |
| L6.H.3 | `contracts/prompt/section_validators.rs` | Code | Validates each section conforms to its content rules |
| L6.H.4 | `tests/integration/composer_test.rs` | Test | Render each intent; verify 8 sections present in correct order; user input only in `[INPUT]` |
| L6.H.5 | `tests/integration/composer_security_test.rs` | Test | Injection attempts in user input remain confined to `[INPUT]` section |

**Acceptance criteria:**
- 8 sections always in same order (immutable)
- User input ONLY in `[INPUT]` (verified by security test fixture)
- Composer rendering deterministic (same input → byte-equal output) — enables replay

---

### L6.I — Prompt user-input wrapping + canary token

**Owning chunks:** S09 §12Y.5 Layer 4 (input wrap), Layer 5 (canary token)

**Artifacts:**

| ID | Artifact | Type | Notes |
|---|---|---|---|
| L6.I.1 | `contracts/prompt/input_wrapper.rs` (+ Go + Python) | Code | XML-escapes + wraps user input in `<user_input>...</user_input>` |
| L6.I.2 | `contracts/prompt/canary_token.rs` | Code | Generates unique canary token per prompt; embedded in system section |
| L6.I.3 | `contracts/prompt/canary_detector.rs` | Code | Post-output scan for canary token leak (logs but doesn't act V1) |
| L6.I.4 | `tests/integration/canary_detection_test.rs` | Test | Inject prompt with canary; verify canary present in system section; LLM response containing canary flagged |
| L6.I.5 | `contracts/observability/inventory.yaml` entries | Registry | `lw_prompt_canary_leak_count` |

**Acceptance criteria:**
- Canary token cryptographically random (not predictable)
- Detector flags canary in LLM output
- Wrapping correct XML escape on all 6 patterns (`<`, `>`, `&`, `"`, `'`, NUL)

---

### L6.J — Prompt provider adapter routing

**Owning chunks:** I2 (provider gateway), S09 §12Y.2 (provider_config in PromptBundle)

**Artifacts:**

| ID | Artifact | Type | Notes |
|---|---|---|---|
| L6.J.1 | `contracts/prompt/provider_resolver.rs` (+ Go) | Code | Resolves `model_id` → provider config from `provider-registry-service` (existing) |
| L6.J.2 | `contracts/prompt/provider_router.rs` | Code | Routes prompt to provider via existing `provider-registry-service` adapter (NOT direct SDK call) |
| L6.J.3 | `contracts/service_acl/matrix.yaml` entry | ACL | roleplay-service → provider-registry-service `GetProviderConfig` (`requires_user`) |
| L6.J.4 | `tests/integration/provider_routing_test.rs` | Test | Verifies routing respects provider config; falls back per S6-D5 |
| L6.J.5 | `scripts/prompt-assembly-discipline-lint.sh` (L1.K.14) | CI lint | Already shipped; verifies no direct SDK calls |

**Acceptance criteria:**
- All LLM calls route through provider-registry-service
- CI lint blocks direct SDK imports
- Provider-config caching matches L1.B `consent.go` 5min TTL (or shorter for cost-sensitive ops)

---

### L6.K — Prompt template scaffolding (empty templates per intent)

**Owning chunks:** S09 §12Y.3 (versioned template registry)

**Artifacts:**

| ID | Artifact | Type | Notes |
|---|---|---|---|
| L6.K.1 | `contracts/prompt/templates/session_turn/v1.tmpl` | Template | Empty 8-section skeleton — actual prompt copy OUT of foundation |
| L6.K.2 | `contracts/prompt/templates/session_turn/v1.meta.yaml` | Config | Template metadata (compatible_model_tiers, expected_token_budget, fixture_set, deprecated_at, replay_window_days) |
| L6.K.3 | `contracts/prompt/templates/session_turn/v1.fixtures/` | Fixtures | Basic + injection_canary fixtures (placeholder) |
| L6.K.4 | (repeat L6.K.1-3 for 6 other intents: npc_reply, canon_check, canon_extraction, admin_triggered, world_seed, summary) | — | 7 intents total per S09 §12Y.2 |
| L6.K.5 | `contracts/prompt/registry.yaml` | Config | Active + deprecated registry |
| L6.K.6 | `scripts/template-fixture-validator.sh` | CI lint | Block PR with template version bump without fixture update |
| L6.K.7 | `tests/integration/template_load_test.rs` | Test | Registry loads all 7 intents; missing fixture → fail-fast |

**Acceptance criteria:**
- All 7 intents have v1 skeleton + meta.yaml + fixture stubs
- Registry parses successfully
- CI lint blocks fixture-skipping PRs

**Open question:**
- Q-L6K-1: Who owns prompt copy? Suggested: feature team / DF3 / future LLM-logic sub-program. Foundation explicitly ships empty skeletons + acceptance fixtures.

---

### L6.L — Empty stubs for intent classifier + world oracle + injection defense

**Owning chunks:** 05_llm_safety (A3/A5/A6 — full logic OUT of foundation per scope)

**Artifacts:**

| ID | Artifact | Type | Notes |
|---|---|---|---|
| L6.L.1 | `contracts/prompt/intent_classifier.rs` (+ Go) | Code | Trait/interface for intent classifier; default impl returns `Intent::SessionTurn` (no-op) |
| L6.L.2 | `contracts/prompt/world_oracle.rs` (+ Go) | Code | Trait for World Oracle deterministic-fact lookup; default impl returns empty |
| L6.L.3 | `contracts/prompt/injection_defense.rs` (+ Go) | Code | 5-layer defense interface; default impl is identity (no actual defense V1) |
| L6.L.4 | `docs/foundation/llm_safety_handoff.md` | Doc | Handoff document: foundation ships interfaces; future LLM-safety sub-program ships bodies |
| L6.L.5 | `tests/integration/llm_safety_interface_test.rs` | Test | Verifies trait shape stable; future impl can substitute without breaking signatures |

**Acceptance criteria:**
- Interfaces stable (signature freeze)
- Default stubs compile + run (no-op semantics)
- Test fixtures lock in trait shape

**Note:** This is intentional minimal-impl. Bodies (A3/A5/A6 LLM safety) are a FOLLOW-ON sub-program after foundation locks.

---

## §3. L6 cross-component dependency graph

```
L4.L (ws skeleton) ←─ L6.A + L6.B + L6.C + L6.D + L6.E (running WS impl)
L4.H (obs inventory) ←─ L6.F (admission runtime)
L4.I (capacity budgets) ←─ L6.G (deployment admission)
L4.D (prompt skeleton) ←─ L6.H + L6.I + L6.J + L6.K + L6.L (composer + wrap + routing + templates + stubs)

L6.A ←─ L2.L (consumes Redis Streams reality:<id>:events for outbound fanout)
L6.A ←─ L4.M (SVID for upstream service auth)

L6.C ←─ L4.C (meta authz lib for S2/S3 re-auth)

L6.D ←─ L2.D publisher (publishes lw:ws:control events)

L6.H ←─ L4.D (uses L4.D's PromptContext + PromptBundle types)
L6.J ←─ provider-registry-service (existing — no foundation work)

Approximate ordering: L6.B (ticket) → L6.A (server) → L6.C + L6.D + L6.E (security + control + metrics) → L6.F + L6.G (admission runtimes) → L6.H + L6.I (prompt composer + wrap) → L6.J + L6.K (provider routing + templates) → L6.L (stubs — last)
```

---

## §4. Acceptance criteria for whole L6 (RAID verify gate)

- WS E2E test green (ticket → upgrade → message → disconnect)
- WS per-message re-auth verified
- WS forced disconnect propagates < 1s
- Admission control V1 warn-and-drop verified
- Capacity admission rejects over-budget deploys
- Prompt composer renders 8 sections deterministically
- Canary token detection works
- All 7 intents have skeleton templates
- LLM safety interface stubs compile

---

## §5. Open questions surfaced during L6 enumeration

| # | Question | Suggested resolution | Status |
|---|---|---|---|
| Q-L6-1 | api-gateway-bff WS impl — extend existing NestJS service or new gateway sidecar? | Extend existing NestJS (consistent with I1 + matches existing LoreWeave novel-platform code) | Suggested |
| Q-L6-2 | WS connection cap per replica — V1 sizing? | V1 ceiling = 10K per replica (verified by load test); HPA scales replicas | Suggested |
| Q-L6F-1 | Admission V1 → V1+30d transition — auto or admin-triggered? | Time-based (foundation ships V1+30d as flag-flip at config); admin can flip earlier | Suggested |
| Q-L6G-1 | Capacity admission webhook on K8s — V1 ECS alternative? | Foundation targets K8s (matches CLAUDE.md infra); ECS variant V2+ | Suggested |
| Q-L6H-1 | Composer error handling — fail prompt assembly OR best-effort render? | Fail (per S09 §12Y discipline — never emit malformed prompt) | Suggested |
| Q-L6K-1 | Prompt copy ownership | Feature team / DF3 / future sub-program. Foundation ships empty skeletons. | Suggested |
| Q-L6L-1 | LLM safety stubs — should foundation ship empty defaults or fail-closed defaults? | Empty (no-op) defaults V1; fail-closed in LLM-safety sub-program | Suggested |
| Q-L6-3 | Browser WS lib (TS) — foundation owns or frontend-game team? | Frontend-game team (foundation ships server + envelope types only) | Suggested |

---

## §6. Cycle decomposition hint for L6

| Cycle | Scope | Why grouped |
|---|---|---|
| L6-cycle-1 | L6.A + L6.B + L6.E (WS server + ticket + metrics) | Core WS server stack; depends on L4.L types exist |
| L6-cycle-2 | L6.C + L6.D (per-msg authz + force disconnect) | Security layer on top of core WS |
| L6-cycle-3 | L6.F + L6.G (admission runtimes — obs + capacity) | Admission stack; depends on L4.H + L4.I |
| L6-cycle-4 | L6.H + L6.I + L6.J + L6.K + L6.L (prompt composer + wrap + routing + templates + stubs) | Prompt stack — all foundation contracts for LLM safety pre-spec, no actual LLM logic |

**Total L6 estimate: ~4 RAID XL cycles.**

---

## §7. Status

```
[x] L6 — 12 sub-components enumerated at B-level (A-L)
[x] L6 — cross-component deps mapped
[x] L6 — 8 open questions surfaced
[x] L6 — cycle decomposition hint (~4 cycles)
[ ] L6 — open questions resolved (batch at end of all layers)
[ ] ALL LAYERS COMPLETE → batch resolve open Qs + cycle decomposition + RAID workflow + commit
```
