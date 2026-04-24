# Invariants

> **15 rules that every feature must respect.** Each has a concrete enforcement point. If your feature needs to violate one, stop and escalate (see `01_READ_THIS_FIRST.md` §"When you think the kernel is wrong").

Format: **Rule** · **Why** · **Enforced by** · **Source chunk**.

---

## Architectural invariants (from CLAUDE.md)

### I1. Gateway invariant
All external traffic enters through `api-gateway-bff`. No service accepts direct public traffic.
- **Why:** single audit/auth/rate-limit chokepoint; prevents accidental exposure.
- **Enforced by:** AWS security groups (no other service has inbound from public subnet); `contracts/service_acl/matrix.yaml` has no `public → service` entries except `public → api-gateway-bff`.
- **Source:** CLAUDE.md + [02_storage/S11_service_to_service_auth.md](../02_storage/S11_service_to_service_auth.md) §12AA.10.

### I2. Provider-gateway invariant
No direct LLM/AI provider SDK calls anywhere in the codebase. All AI calls go through `contracts/prompt/` (for prompt-shaped calls) or the provider-registry adapter (for raw BYOK calls).
- **Why:** keeps S9 prompt governance + S6 cost controls + S8 PII redaction centralized; prevents regression through any one sloppy prompt builder.
- **Enforced by:** CI lint blocking `import anthropic` / `import openai` / etc. outside `contracts/prompt/` + `services/provider-registry-service/`.
- **Source:** [02_storage/S09_prompt_assembly.md](../02_storage/S09_prompt_assembly.md) §12Y.1; ADMIN_ACTION_POLICY §4.

### I3. Language rule
Go for domain services · Python for AI/LLM services · TypeScript for gateway/BFF.
- **Why:** skill specialization + runtime-stack boundaries.
- **Enforced by:** code review.
- **Source:** CLAUDE.md §Key Rules.

### I4. DB-per-service
Each microservice owns its own Postgres database. Cross-service reads go through RPC, not direct SQL.
- **Why:** service autonomy; schema evolution independence.
- **Enforced by:** per-service Postgres role (S4-D6, 8 roles minimum); services cannot authenticate to other services' DBs.
- **Source:** CLAUDE.md + [02_storage/S04_meta_integrity.md](../02_storage/S04_meta_integrity.md) §12T.6.

### I5. DB-per-reality
Every reality gets its own Postgres database. Sharded many-per-server (R4-L6 up to ~2K/medium or ~10K/large).
- **Why:** blast-radius containment; natural sharding; per-reality backup/restore.
- **Enforced by:** `reality_registry.db_host` + `reality_registry.db_name` schema CHECK constraints; provisioner at R4-L1.
- **Source:** [02_storage/R04_fleet_ops.md](../02_storage/R04_fleet_ops.md) §12D.

---

## Concurrency + state invariants

### I6. Session is the concurrency boundary
One command processor per session. Serial FIFO in-session. LLM calls happen OUTSIDE the DB transaction. Cross-session events go through `event-handler` (R7 / DF13).
- **Why:** multi-aggregate deadlocks solved; LLM latency doesn't hold DB locks; ordering guarantees are local.
- **Enforced by:** `roleplay-service` session-router holds session-locks; LLM calls in separate async tasks; `event-handler` is the only writer for cross-session events.
- **Source:** [02_storage/R07_concurrency_cross_session.md](../02_storage/R07_concurrency_cross_session.md) §12G.

### I7. No cross-reality live queries
Features NEVER query across reality DBs in a single query. Cross-reality state propagation is event-driven via Redis Streams `xreality.*` topics, consumed by `meta-worker`.
- **Why:** R5 anti-pattern; cross-DB query plans are unbounded; reality isolation would break.
- **Enforced by:** `CROSS_INSTANCE_DATA_ACCESS_POLICY.md` in code review + ACL matrix (no service has cross-reality-DB role except `meta-worker`).
- **Source:** [02_storage/R05_cross_instance.md](../02_storage/R05_cross_instance.md) §12E.

### I8. Meta writes go through `MetaWrite()`
Every write to a meta-registry table (in the shared `loreweave_meta` DB) uses `contracts/meta/MetaWrite(ctx, table, op, before, after, actor, reason)`. Audit is append-only; `meta_write_audit` is REVOKE UPDATE/DELETE.
- **Why:** single audit funnel; schema CHECK constraints validated; mutual-exclusion honored.
- **Enforced by:** per-service Postgres role grants SELECT but not INSERT/UPDATE on meta tables except via `MetaWrite()` helper; CI lint flags direct writes.
- **Source:** [02_storage/S04_meta_integrity.md](../02_storage/S04_meta_integrity.md) §12T.3.

### I9. Lifecycle transitions go through `AttemptStateTransition()`
Any change to `reality_registry.status` or other `*_lifecycle_audit` row goes through `contracts/meta/AttemptStateTransition(resource_id, from_state, to_state, reason)`. Validates transition graph. CAS-protected.
- **Why:** prevents concurrent state races (C5 resolution); audit trail is mandatory.
- **Enforced by:** specialization of `MetaWrite()`; lint rule + governance policy addendum in ADMIN_ACTION_POLICY.
- **Source:** [02_storage/C05_lifecycle_cas.md](../02_storage/C05_lifecycle_cas.md) §12Q.

### I10. Prompt assembly through `contracts/prompt/`
All LLM prompts are built via `AssemblePrompt(PromptContext) → PromptBundle`. User content ONLY in `[INPUT]` section, XML-escape-wrapped. Templates versioned in `contracts/prompt/templates/<intent>/v<N>.tmpl`. Fixtures required on version bump.
- **Why:** S9 prompt-injection defense + PII redaction + cost control + S2 capability-based authorization all hang off this single entry point.
- **Enforced by:** CI lint + PR reject condition (ADMIN_ACTION_POLICY §4).
- **Source:** [02_storage/S09_prompt_assembly.md](../02_storage/S09_prompt_assembly.md) §12Y.

---

## Integrity + security invariants

### I11. Service-to-service auth via SVID
Every inter-service RPC requires a SPIFFE-like SVID. ACL matrix at `contracts/service_acl/matrix.yaml` enumerates allowed `(caller → callee + rpc)` pairs. Every RPC declares `x-principal-mode` (`requires_user` / `system_only` / `either`).
- **Why:** confused-deputy defense; credential blast-radius bounded; secret-free workload attestation.
- **Enforced by:** entry middleware + CI lint blocks new RPC without ACL entry; security-team CODEOWNERS review on ACL changes.
- **Source:** [02_storage/S11_service_to_service_auth.md](../02_storage/S11_service_to_service_auth.md) §12AA.

### I12. No hardcoded secrets or model names
Secrets via AWS Secrets Manager + KMS, fetched via SVID-bound policy. Model names resolved from `provider_registry` per user's config.
- **Why:** credential rotation + BYOK support + no compile-time pinning.
- **Enforced by:** CI lint (gitleaks / semgrep rules) + code-review reject condition.
- **Source:** CLAUDE.md + [02_storage/S11_service_to_service_auth.md](../02_storage/S11_service_to_service_auth.md) §12AA.7.

### I13. Outbox pattern for cross-service events
Events to other services are written to `events_outbox` in the SAME transaction as the state change. The `publisher` service drains the outbox to Redis Streams. Redis is a cache; Postgres is SSOT.
- **Why:** atomicity between state and event; no dual-write problem; R12 Redis ephemerality tolerated.
- **Enforced by:** all `services/*/internal/events/` emitters use `outbox.Write(ctx, tx, event)`; CI lint flags `redis.XAdd` outside `services/publisher/`.
- **Source:** [02_storage/R06_R12_publisher_reliability.md](../02_storage/R06_R12_publisher_reliability.md) §12F.

### I14. Schema evolution is additive-first
New fields are nullable and additive. Breaking changes require a new `event_type` with ≥30d deprecation cooldown + upcaster. Codegen from Go structs → TS + Python.
- **Why:** consumers roll forward without coordination; old events replayable forever.
- **Enforced by:** `contracts/events/` codegen + migration CI check.
- **Source:** [02_storage/R03_schema_evolution.md](../02_storage/R03_schema_evolution.md) §12C.

### I15. Stable IDs never renumber
`R*`, `C*`, `S*`, `SR*`, `HMP`, `M*`, `DF*`, `PC-*`, `IF-*`, `MV*`, `WA-*`, `CC-*` are forever. Retired = `~~strikethrough~~`. New additions take the next free number in their namespace.
- **Why:** cross-doc citations stay valid across sessions; reorg cannot break links.
- **Enforced by:** code review; foundation + each subfolder's `_index.md` documents owned namespaces.
- **Source:** AGENT_GUIDE.md §3 + this folder's `06_id_catalog.md`.

---

## Resilience invariants (SR6)

### I16. Every outbound call declares a timeout
No `context.Background()` for network calls. Sum of timeouts along a call chain must fit the user-visible SLO. Timeouts declared per dependency class in `contracts/dependencies/matrix.yaml`; canonical wrapper `contracts/resilience/WithTimeout(ctx, dep, fn)` reads the default.
- **Why:** unbounded calls cascade into pool exhaustion → cascading failure. Without a call-chain budget, SLO targets (SR1) are unverifiable.
- **Enforced by:** CI lint `scripts/timeout-discipline-lint.sh` (flags `http.NewRequest` / `sql.Query` / `redis.Cmd` / `context.Background()` in call paths to registered deps) + dependency-registry-lint blocking new clients outside matrix.
- **Source:** [02_storage/SR06_dependency_failure.md](../02_storage/SR06_dependency_failure.md) §12AI.3 — decision SR6-D2.

### I17. Every service declares a capacity budget
Every service declares its capacity budget in `contracts/capacity/budgets.yaml` — class (web / worker / data-plane / llm-gateway) + per-tier (V1/V2/V3) × 5 dimensions (`replicas_min`/`max` · `cpu_per_replica` · `memory_per_replica` · `db_pool_size` · `concurrent_llm_calls_per_replica` · `network_egress_mbps`). Deployment blocked for services absent from the registry. Scaling beyond `replicas_max` requires `admin/capacity-override` (S5 Tier 2; 24h-bounded).
- **Why:** undeclared service = unlimited resource consumption = cascading exhaustion = SR1 SLO breach. Capacity must be a commitment backed by the load-test gate (SR8-D8), not a runtime suggestion.
- **Enforced by:** CI lint `scripts/capacity-budget-lint.sh` blocks services missing from `budgets.yaml`; class declaration ↔ deployment kind validated (HPA for web/llm-gateway, KEDA for worker, vertical-only for data-plane); `admin/capacity-override` is the only bypass and is S5-audited with 24h auto-expire.
- **Source:** [02_storage/SR08_capacity_scaling.md](../02_storage/SR08_capacity_scaling.md) §12AK.3 — decision SR8-D2 + SR8-D11 (architect-approved 2026-04-24 via POST-REVIEW per `00_foundation/02_invariants.md` "How invariants get added" process).

---

## How invariants get added

New invariants require:
1. A concrete enforcement point (not "we promise to remember") — CI lint, runtime check, role restriction, or code-review checklist.
2. A kernel-chunk owner (where the rule is authoritative and detailed).
3. Architect sign-off via SESSION_HANDOFF row.
4. Same-commit update to the enforcing mechanism (lint script, middleware, etc.).

Invariants without concrete enforcement are just wishes. Wishes are not invariants.
