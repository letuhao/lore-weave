# Post-RAID Comprehensive Review — Findings & Fix Backlog

> **Task:** foundation-mega-task (38-cycle RAID build, branch `mmo-rpg/foundation-mega-task`).
> **Purpose:** durable backlog of every bug / gap / drift found during the post-RAID comprehensive review, so they can be fixed before (or tracked into) the PR→main. The user has decided: **we will fix ALL of these.** Each row is therefore `TO-FIX` unless explicitly an accepted intentional deferral.
> **Status:** LIVING DOC — appended as each review dimension completes.
> **Started:** 2026-05-30. **Reviewer:** post-RAID review (multi-agent, adversarial verify).

## How to read this

- IDs are stable: `PRR-NN`. Severity: 🔴 MAJOR (load-bearing / correctness / compliance) · 🟠 MEDIUM (planned-real artifact missing) · 🟡 LOW (cosmetic / housekeeping / traceability).
- `Status`: `TO-FIX` (will be fixed) · `VERIFY` (needs confirmation before classifying) · `INTENTIONAL` (plan-sanctioned deferral, recorded so it is not re-flagged).
- Sources so far: **Acceptance Audit** (`wnrrtxlx1`, escalations + artifacts + git, with 3 adversarial skeptics). Pending: **Decisions Audit** (`wf4ybi0xw`), **C1–C4 dimension reviews**, **integrated build**.

---

## Verdict (after full review: acceptance + decisions + C1–C4 + build)

- ✅ **Escalations:** all 24 spurious, **0 cycles left incomplete** — double-verified by two adversarial skeptics (high confidence). The `ESCALATIONS.md` entries are noise from a recovery ordering bug (PRR-10).
- ✅ **Git + Build:** all 38 feature commits present/reachable; integrated build **PASS** across all 4 toolchains (Rust 19 crates · 55 Go modules · 5 Python · TS) — *with the stubs in place*. Compiling ≠ runtime-correct.
- ✅ **Contract / library / skeleton layer is real & strong:** dp-kernel (EventStore, load_aggregate, rebuilder), production DDL migrations, contracts (resilience/canon/guardrail/prompt/ws/pii-SDK), eventgen 4-lang codegen, real algorithms (integrity comparator, canary state machine, reality-seeder 1008 LOC, YamlGuardrail 627 LOC, severity classifier). **Provider-gateway invariant (I2) CLEAN** (skeptic-confirmed).
- 🔴 **Runtime + security/compliance layer is NOT functional / PR-ready as a "complete foundation":**
  - *Runtime:* the L2–L7 **worker fleet ships as exit-0 skeletons** → core event-sourcing flow **never live-smoked end-to-end** (PRR-33); **64% of registered events have no projection** (PRR-09); **no CI runs the gates** (PRR-35); a "CLEARED" live-smoke was a dry-run false-green (PRR-34).
  - *Security/GDPR:* PII masking **dead at runtime** (PRR-28) + **no scrubber seam** in the write path (PRR-01); admin-cli **auth forgeable** (PRR-29), **dual-actor forgeable** (PRR-43), **typed-confirm dead code** (PRR-44); **break-glass JWT unimplemented** (PRR-30); **GDPR Art.33 breach flow unwired** (PRR-31); destructive admin commands **return exit-0 success doing nothing** (PRR-05).
  - *Architecture:* `game-server` is a **gateway-bypassing public entry point** (PRR-20, I1).
- **Bottom line:** a coherent, building, **contract-complete foundation SKELETON** with a real-but-incompletely-tracked **live-wiring + security-activation backlog**. The earlier RAID-coordinator "100% ready / 0 escalations" framing was too rosy. **NOT ready to PR to main as "done"** until the fix phase (which we will do) closes the 🔴 items or tracks them honestly as launch-blocking. 45 findings total (PRR-01..45); ~17 🔴 major.

---

## 🔧 Fix Log

### F1 — Admin-cli execution safety ✅ DONE *(go -C services/admin-cli build + vet + test ./... all exit 0; 11 new/updated tests)*
- **PRR-29** auth fail-closed: `dev:` tokens now require `ADMIN_CLI_ALLOW_DEV_TOKENS=1`; any non-dev token fails closed pending the real signed-JWT verifier. (`internal/auth/auth.go`) — *Remaining: real RS256/JWS verification vs auth-service — coupled to PRR-30 (F3).*
- **PRR-43** dual-actor hardened: tier-1 `--confirm` now requires the second actor's OWN validated `--second-actor-token` (subject must match `--second-actor`, differ from primary, carry the destructive scope). A single operator can no longer forge dual approval. (`internal/framework/dispatcher.go`)
- **PRR-44** typed-confirmation wired: tier-1 `--confirm` now enforces `confirmation.Check(challenge, --confirm-token)` (challenge = target resource id). The previously-dead `confirmation` package is now live. (`dispatcher.go` + `cmd/admin/main.go`)
- **PRR-05** (safety half): `NotWiredHandler` now returns an ERROR for tier-1-destructive / tier-2-griefing — an unimplemented destructive command (e.g. user-erasure) can no longer exit-0 "success". Added `HandlerRegistry.Resolve(c)`. (`internal/framework/handlers.go`) — *Remaining: wiring the 4 real command bodies needs the deferred MetaWrite adapter (D-ADMIN-CLI-METAWRITE / D-ADMIN-CLI-LIVE-WIRING), F3/infra.*

### F2 — Logging PII mask floor + real PII scrubber ✅ DONE *(contracts/logging dev + `-tags=prod`, contracts/meta — build+vet+test green)*
- **PRR-28** logging fail-safe: `jsonLogger.Emit` now applies a hard `piiFloorMask` to any `FieldKindPII` value the redactor declines → raw PII can no longer leak in a non-prod / NoopRedactor build (the previous passthrough leaked it). **Build-tag-agnostic** — no longer depends on `-tags=prod` for the safety floor. (`contracts/logging/logger.go`; the test that asserted the leak was rewritten to assert the floor.)
- **PRR-01** real scrubber: implemented `RegexScrubber` — 7 patterns (email / SSN / IPv4 / IPv6 / credit-card / API-key / phone → placeholders, SHA-256 of original retained), security-first (over-redaction preferred) — replacing the test-only passthrough. (`contracts/meta/scrubber.go` + `scrubber_regex_test.go`.) — *Remaining: wire the scrubber into the metawrite audit write-path seam (PRR-01 NEW-3, needs MetaWrite injection); KMS-backed KEK manager (PRR-02) + erasure runbook (PRR-03) + integration tests (PRR-04) need KMS infra → F3/later.*

### F5a — I3 language-rule enforcement + CLAUDE.md sync ✅ DONE *(`language-rule-lint.sh` PASS on real tree; negative-tested → FAILs on mismatch / `missing`-but-present / absent-row)*
- **PRR-16 + PRR-21**: rewrote `contracts/language-rule.yaml` to map all 34 on-disk services to their real language (was ~30 mislabelled `missing`); hardened `scripts/language-rule-lint.sh` to (a) **FAIL** on a present service declared `missing` (PRR-16), (b) add a **completeness check** that FAILs on a present (toolchain-detected) service with no yaml row (PRR-21), (c) detect Python via `requirements.txt`. The lint now *enforces* I3 instead of NOTE-only — ~21 previously-unguarded services are now covered.
- **PRR-22**: `CLAUDE.md` Language rule updated — added the **Rust** kernel-derived tier + pointed to `contracts/language-rule.yaml` as the authoritative service→language SSOT (rule book no longer drifts from the 35-service reality).
- *Remaining F5: **PRR-24/25** WS ticket-hash wire drift (base64 vs JSON int-array) — Go+Rust change; **PRR-20** game-server gateway bypass — needs an architecture decision (front via api-gateway-bff vs formally amend invariant I1).*

---

## 🔴 MAJOR — to fix

### PRR-01 — L4.Q PII free-text scrubber is a passthrough stub (GDPR)
- **Where:** `contracts/meta/scrubber.go` (and intended `contracts/pii/scrubber.go`).
- **Found:** the 7-pattern regex scrubber (email / phone / ipv4 / ipv6 / credit-card / ssn / api-key) the L4.Q plan + acceptance criterion (L4.Q.6 "Scrubber detects all 7 patterns") require was **never built** — only a `PassthroughScrubber` test-only stub exists. Stub comment defers it to "the S08 §12X.5 implementation cycle" (not part of these 38 cycles).
- **Risk:** PII can leak into logs/audit unredacted. GDPR-load-bearing.
- **Status:** TO-FIX. Implement the real 7-pattern scrubber + tests.

### PRR-02 — L4.Q production KEK manager not shipped
- **Where:** intended `contracts/pii/kek_manager.go`.
- **Found:** only a `KEKManager` interface + `InMemoryKEKManager` test double in `contracts/pii/sdk.go`. No KMS-wrapping rotate/destroy production impl.
- **Status:** TO-FIX. Implement KMS-backed KEK lifecycle (crypto-shred).

### PRR-03 — L4.Q user-erasure 10-step runbook not shipped
- **Where:** intended `contracts/pii/erasure.go`.
- **Found:** `pii/sdk.go` has only a single `ErasePII` KEK-destroy call, not the 10-step admin/user-erasure runbook logic the plan (L4.Q.5 + test L4.Q.8) requires.
- **Status:** TO-FIX. (GDPR right-to-erasure.)

### PRR-04 — L4.Q PII integration tests not shipped
- **Where:** intended `pii_scrubber_test` (7-pattern), `kek_rotation_test`, `user_erasure_test`.
- **Found:** only `sdk_test.go` covering the GetPII/ErasePII/tag SDK. The acceptance tests follow from PRR-01..03 being absent.
- **Status:** TO-FIX (lands with PRR-01..03).

### PRR-05 — L7.A admin-cli: ~29 of 33 commands are no-op `NotWiredHandler`
- **Where:** `services/admin-cli/cmd/admin/main.go` `defaultHandlers()` (empty — zero `h.Register`), `services/admin-cli/internal/framework/handlers.go` `NotWiredHandler`.
- **Found:** the framework dispatcher (auth→impact→dry-run→dual-approval→audit) is real, and `contracts/admin/registry/*.yaml` declares 33 commands, but **every declared command dispatches to a fixed "recognised-but-not-yet-wired" no-op**. Only 4 real command bodies exist (`capacity_override`, `catastrophic_rebuild`, `rebuild_projection`, `deploy/break_glass`) and even those are **not wired into the dispatcher**. Plan expected real per-command `.go` files (e.g. `reality/force_close.go`, `erasure/user_erasure.go`, `canon/decanonize.go`).
- **Defer-drift:** commit `a7db5cce` names `D-ADMIN-CLI-LIVE-WIRING / METAWRITE / JWT` but **LIVE-WIRING is not recorded in `DEFERRED.md` or `SESSION_PATCH.md`**.
- **Status:** TO-FIX. Wire the dispatcher + implement the command bodies; also backfill the deferral row so tracking is honest.

### PRR-16 — I3 language-rule lint is "enforcement-by-NOTE" (~21 shipped services unguarded) *(decisions-audit; DRIFT)*
- **Where:** `contracts/language-rule.yaml`, `scripts/language-rule-lint.sh:77-80`, wired in `.github/workflows/lint-foundation.yml:38`. Authoritative map: `I3_INVARIANT_AMENDMENT.md:159-201` (§5).
- **Found:** §5 maps every service to its real language, but on-disk `language-rule.yaml` overrides ~30 services to `missing`, and the lint emits only an advisory **NOTE (never FAIL)** when a `missing`-declared service is present on disk. ~21 services that genuinely ship are therefore **unguarded by the I3 invariant lint while CI runs green**: 12 Go workers (publisher, meta-worker, admin-cli, integrity-checker, archive-worker, retention-worker, slo-budget-calculator, canary-controller, incident-bot, postmortem-bot, statuspage-updater, alert-recorder) + world-service (Rust) + 6 existing Go platform services + api-gateway-bff (TS). The file header even claims "FAILS if detected != expected" — contradicted by its own `missing` escape hatch.
- **Risk:** the single decision that most threatens invariant integrity — language drift could land unnoticed.
- **Status:** TO-FIX. Flip every present service in `language-rule.yaml` to its real language per §5, then harden `language-rule-lint.sh` to **FAIL** (not NOTE) on `missing`-but-present. *(C1 dimension review independently checking — cross-confirm expected.)*

---

## 🟠 MEDIUM — to fix

### PRR-06 — L4.B `#[derive(Projection)]` proc-macro never shipped
- **Where:** `crates/dp-kernel-macros/` (only `derive_aggregate` exists).
- **Found:** deferred from cycle 17 "to cycle 21", but cycle 21 shipped prompt/ws skeletons instead → never built. Plan listed it as a real artifact.
- **Status:** TO-FIX.

### PRR-07 — L4.B `event_annotations.rs` (@event/@version/@upcast parser) never shipped
- **Where:** `crates/dp-kernel-macros/src/event_annotations.rs` (absent).
- **Status:** TO-FIX.

### PRR-08 — L4.B `derive_projection_test.rs` never shipped
- **Where:** `crates/dp-kernel-macros/tests/derive_projection_test.rs` (absent; follows from PRR-06).
- **Status:** TO-FIX (lands with PRR-06).

### PRR-09 — L3.B projection event-coverage may never have been backfilled
- **Where:** `crates/projections/{pc,npc,region,world_kv,session}/src/lib.rs`.
- **Found:** L3.B ships "skeleton" projections handling only 1–2 representative events per aggregate (e.g. `pc.spawned/moved/item_acquired`), with the rest TODO match arms. The crate doc-comment defers "full event coverage to the **L4–L7 domain cycles**" — but L4–L7 were **infra/ops** layers, not domain projection cycles, so the backfill likely never happened. The L3.B acceptance criterion ("every event type in registry has ≥1 projection that handles it — CI gate") is probably still unmet.
- **Status:** VERIFY → almost certainly TO-FIX. (Dimension review C4 to confirm event-coverage vs the event registry.)

### PRR-17 — session-cost-rollup-worker never scaffolded → empty meta sink *(decisions-audit; debt)*
- **Where:** `migrations/meta/008_session_cost_summary.up.sql` exists, but `services/session-cost-rollup-worker/` is **absent** (35 services on disk, this one missing; `language-rule.yaml` even lists it `missing  # ships L7 ops`).
- **Found:** the locked hybrid-cost decision (Q-L1A-1: per-reality DB live writes + meta `session_cost_summary` populated by a 60s rollup worker) shipped the table but **never built the rollup mechanism** — the summary table is an unpopulated sink. Reviewers would assume cost-rollup works.
- **Status:** TO-FIX. Scaffold the Go worker (S) OR downgrade `008` to a documented stub + add a DEFERRED row.

---

## 🟡 LOW — cleanup / housekeeping

### PRR-10 — recovery-protocol ordering bug → 24 spurious escalations
- **Where:** `scripts/raid/recovery-protocol-runner.sh:50-57` (check-after-archive).
- **Found:** probe re-reads the live `IN_PROGRESS/cycle-NNN-state.md` *after* it was correctly archived, sees it missing, and emits `recovery_halted reason=in_progress_missing` + writes an escalation — for 23 cycles (+ C0 spec_drift). Self-stopped by cycles 36–38.
- **Status:** TO-FIX. Treat "state missing AND cycle DONE/archived" as CONSISTENT (check `_archive/cycle-NN-state.md` before declaring INCONSISTENT, or consult CYCLE_LOG status; or run only on genuine compaction). Then clean/annotate the 24 noise entries in `ESCALATIONS.md` — **and remove the stale `(empty — no escalations yet)` marker at `ESCALATIONS.md:9`** which sits above the 24 rows and fails `CYCLE_DECOMPOSITION §8` acceptance (zero rows or all human-resolved). *(Decisions-audit: P-RAID-P5-recovery-false-positive [debt] + P-RAID-escalations-log-misleading [DRIFT].)*

### PRR-11 — 17 malformed JSON rows in AUDIT_LOG.jsonl
- **Where:** `docs/audit/AUDIT_LOG.jsonl` (C0 bootstrap rows with unquoted `"cycle":00X`).
- **Found:** invalid JSON; breaks any strict line-parser of the append-only log.
- **Status:** TO-FIX. Quote to `"00X"` + add a JSONL validity guard in the audit writer.

### PRR-12 — working tree dirty + missing .gitattributes for .jsonl
- **Where:** `docs/audit/AUDIT_LOG.jsonl` — uncommitted appended line `{"ts":"2026-05-29T19:23:14Z","event":"coordinator_idle"}` (coordinator housekeeping marker from the `next-cycle`→idle call) + Git "LF will be replaced by CRLF" warning.
- **Status:** TO-FIX. Commit/clean the idle marker; add `.gitattributes` forcing LF for `*.jsonl` (and other text) to stop CRLF churn.

### PRR-13 — CYCLE_LOG SHA-in-"Started"-column schema drift
- **Where:** `docs/raid/CYCLE_LOG.md`. Header is `| # | Title | Status | Started | Completed | DPS | Notes |`.
- **Found:** the "Started" (date) column holds a commit SHA for cycles **18, 32, 33, 34, 35, 36, 37, 38**; cycle 19 holds literal "TBD". Broader than first thought.
- **Status:** TO-FIX (cosmetic). Normalize — give SHA its own column or move it to Notes; restore Started dates. *(Decisions-audit: P-RAID-cyclelog-sha-column-drift — stems from a two-commit "finalize-sha" dance that breaks the §3 "CYCLE_LOG updated in the SAME commit as code" atomic promise. Either add a dedicated Commit column / amend-in-place after capturing HEAD, or downgrade the §3 promise to "within-the-commit-pair" to match reality.)*

### PRR-14 — CYCLE_LOG missing `## Cycle N` headers for cycles 8–16; state archives 8–16 init-only
- **Where:** `docs/raid/CYCLE_LOG.md` + `docs/raid/IN_PROGRESS/_archive/`.
- **Found:** per-cycle traceability for L2/L3 (8–16) relies on on-disk inspection rather than the log's Notes; archives are init-only stubs.
- **Status:** TO-FIX (traceability, low).

### PRR-15 — commit-naming inconsistency `raid-23`/`raid-24` (no "c")
- **Where:** commits `e3cc66ab`, `00da5c50`.
- **Found:** break the `raid-cN` convention; a strict grep misses them.
- **Status:** TO-FIX (cosmetic) or accept + document the variant.

### PRR-18 — full s2s audit has no tracked capacity-budget row *(decisions-audit; debt)*
- **Where:** `migrations/meta/016_service_to_service_audit.up.sql:1-25` (table correctly built, append-only REVOKE) vs `contracts/capacity/budgets.yaml`.
- **Found:** the decision (Q-L1A-3: full s2s audit, no sampling, ~10TB/5y, dedicated audit DB cluster at V2+) is correctly implemented, but the ~10TB/5y projection lives only in the migration header comment — **no governed row in `budgets.yaml`**, so `capacity-budget-lint` doesn't enforce the V2+ trigger.
- **Status:** TO-FIX (tracking). Add the audit-DB-cluster row to `budgets.yaml` before prod V1+30d.

### PRR-19 — deprecated v1.4 auto-dispatcher artifacts not cleaned *(decisions-audit; debt)*
- **Where:** `scripts/raid/auto-dispatcher.py`, `scripts/raid/run-smoke-test.sh`, `docs/raid/.session-cycle-lock` (stale `READY_FOR_1`).
- **Found:** the v1.4 auto-dispatcher was replaced by the v1.5 Agent-tool Coordinator (sound fix for the auto-dispatch BLOCK), but the deprecated scripts + stale session-cycle-lock remain — reviewers could mistake them for live infra.
- **Status:** TO-FIX. Delete or clearly mark-deprecated; reconcile `.session-cycle-lock` before PR.

---

## ✅ Confirmed solid (no action — recorded for confidence)

- **Escalations:** all 24 spurious, 0 real (two adversarial skeptics survive).
- **Git:** 38/38 feature commits present + reachable; no stray worktrees; empty stash.
- **L1–L3 real:** production-grade meta DDL (CHECK enums, regex constraints, partial/partitioned indexes, append-only REVOKE, lz4, monthly RANGE partitioning); `contracts/meta` MetaWrite CAS+same-TX audit+outbox; world-service Rust provisioner (559 LOC)/deprovisioner/capacity_planner/orphan_scanner; all 15 L1.K lints; eventgen (4-language codegen); publisher (FOR UPDATE SKIP LOCKED poll_loop, leader_election, xreality_fanout); archive/retention workers; dp-kernel `load_aggregate` (606 LOC) + rebuilder work-stealing pool (920 LOC) + integrity-checker byte-equal-diff; pgvector HNSW migration.
- **L4–L7 real (sampled):** dp-kernel EventStore trait + PgEventStore + `#[derive(Aggregate)]`; resilience breaker / dependencies DAG / observability / capacity / supply_chain contracts; entity_status/turn; service_acl default-DENY matrix; canon_projection DDL + meta-worker canon/user-erased/force-propagate consumers; canon-cache (reality-isolated); glossary RPC contracts + Go/Rust clients; reality-seeder (1008 LOC); **YamlGuardrail (627 LOC, full)**; WS NestJS gateway + per-message-authz + 11-variant close-code enum; K8s capacity admission webhook (10KB); logging compile-tag prod/non-prod split; canary-controller **pure 5-stage state machine**; incident-bot severity classifier + gdpr_breach_flow + war_room; statuspage-updater; postmortem-bot; 27 runbooks; deploy.yml classify→freeze→canary chain.

## ☑️ Intentional deferrals (NOT gaps — recorded so they are not re-flagged)

- `services/chaos-engine` binary — V1+30d (Q-L4-4). Interfaces shipped.
- `services/oncall-bot` (L7.C.7) — V1+30d (solo-dev, no handoffs yet).
- Thanos `remote_write` — V1 stub commented (Q-L1I-2).
- Statuspage.io — provider abstracted behind interface (Q-L7L-1).
- 27 runbooks — `verification_method:stub`, `last_verified:1970-01-01` allowed for V1 gate (Q-L7B-1).
- L6.L injection_defense / intent_classifier / world_oracle — no-op defaults; bodies OUT of foundation (Q-L6L-1). *(Note: this is a security interface; confirm bodies are scheduled — see C3.)*
- L6.K prompt templates — empty 8-section skeletons (Q-L6K-1).
- IaC prod-apply (meta-postgres/pgbouncer/shards) — gated to V1+30d (Q-L1C-1); real HCL present.
- `PgEventStore` live-smoke — `D-EVENT-STORE-LIVE-SMOKE-061`.

---

## Decisions Audit (`wf4ybi0xw`) — verdict

Product/architecture **SOUND** (7 valid: canon-out-of-meta, ProviderPayload-opaque, UUID-pointers-not-FK, provider-gateway BYOK chokepoint, full-s2s-audit). 0 superseded. **2 drift** → PRR-16 (I3 lint), PRR-10 (ESCALATIONS log). **6 debt** → PRR-17, PRR-18, PRR-19, PRR-10, PRR-11, PRR-13.

---

## Dimension Review (`wbyqzv11y`) — C1–C4 + integrated build + 3 adversarial skeptics

> Integrated build = **PASS** (earned, skeptic-confirmed): Rust 19 crates + 55 Go modules (`go build`/`vet` per-module — no root `go.mod`) + 5 Python services compile + api-gateway-bff `tsc --noEmit` clean. **Compiles green WITH the stubs in place** — compiling ≠ runtime-correct (see C3/C4). All 3 skeptics: claims **NOT refuted** (I2-clean survives; build-PASS survives; C3-gaps survive **and were materially expanded**).

### C1 — Architecture & invariant drift → DRIFT_FOUND
- **PRR-20 🔴** `game-server` (Colyseus WS :2567 + Express) is a **second public external entry point bypassing api-gateway-bff** → gateway invariant **I1** violation; api-gateway-bff has its own `/ws`, so two parallel external WS surfaces; no amendment sanctions it (`services/game-server/src/index.ts:1-43`). → Front it through the gateway OR formally amend I1+CLAUDE.md with its own auth/rate-limit/audit + enforcement point. (Also `:5174` CORS vs documented `:5173`.)
- **PRR-21 🟠** I3 lint **only iterates YAML keys** → services *absent* from `language-rule.yaml` are never checked (6 on disk: game-server, tilemap-service, statistics-service, notification-service, worker-ai, worker-infra); the promised "service-map cross-check" doesn't exist. → add rows + a completeness lint (FAIL when a `services/<n>/` with a toolchain marker has no row). *(Distinct mechanism from PRR-16.)*
- **PRR-22 🟡/ℹ️** I3 Rust amendment never propagated to **CLAUDE.md** (still "Go/Python/TS", no Rust; service table lists 12 of 35 on-disk services). → sync rule book to the LOCKED invariant.
- **PRR-23 🟡** I1 "Enforced by ACL public→service entries" cites a mechanism `service_acl/matrix.yaml` doesn't implement (it's service→DB only); `statistics-service` exposes `/v1/leaderboard|stats/*` with no auth middleware. → encode the public→service edge or fix the I1 enforcement text.
- ✅ **I2 provider-gateway CLEAN** (skeptic-confirmed): zero direct provider-SDK imports/instantiation in service `app/` code; model selection always via provider-registry; CI lint enforces.

### C2 — Contract conformance → DRIFT_FOUND
- **PRR-24 🔴** WS **Ticket hash wire drift**: `ws/v1.yaml:100-101` says base64 `byte`, but Go `ticket.go:53,57` + Rust `ws.rs:184-185` emit a **JSON 32-int array** → client/server can't interop. → base64 both sides (Go marshaler + Rust `serde_bytes`) or change spec to int-array; add round-trip test.
- **PRR-25 🟠** WS `Envelope.seq` (spec min 1, required-for-data) **not enforced** in Go/Rust `Validate` → data envelope with seq 0 passes. → reject + test.
- **PRR-26 🟡** `service_acl/matrix.yaml` lists phantom callers (`roleplay-service`, `knowledge-service`) absent from `services/`; `matrix.go` never checks callers resolve. → soft-lint for unknown caller names.
- **PRR-27 🟡** `canon_history.yaml` omits the `svidBearer` security + 401 its sibling canon contracts have. → add.
- *(WS `TicketRequest` unmodeled + `/v1/ws*` handlers absent = by-design Q-L4-5/Q-L6-3; 7/11 `contracts/api` specs are legacy novel-platform untouched by RAID = out of scope.)*
- ✅ glossary canon RPC contracts faithfully implemented consumer-side (Rust client ↔ YAML).

### C3 — Security & GDPR → GAPS_FOUND  *(highest-stakes; skeptic materially expanded)*
- **PRR-28 🔴** **Logging PII-masking is DEAD at runtime** — nothing builds with `-tags=prod`, so `IsProdBuild=false` everywhere (`compile_guard.go:22`) and `logger.go` gates ALL masking/drop on it → `FieldKindPII` is **not masked in any deployable build**. → add `-tags=prod` to every deployable Dockerfile/CI release + a CI assertion.
- **PRR-29 🔴** **admin-cli auth is a forgeable `dev:`-token skeleton** (`internal/auth/auth.go:43-75`): accepts ANY `dev:`-prefixed token, parses role/scopes/`:break-glass` from the string with zero crypto. Distinct from PRR-05 — even with real bodies the **auth gate is bypassable**. → real signature verification.
- **PRR-30 🔴** **break-glass JWT unimplemented end-to-end** — `auth-service authjwt/jwt.go` has no `break_glass` claim or signing path (grep zero) → the dual-actor policy lib can't be enforced downstream.
- **PRR-31 🔴** **GDPR Art.33 72h breach flow is real logic but entirely unwired** — `incident-bot/internal/gdpr_breach_flow` never constructed, no concrete `DPONotifier`, omitted from the incident pipeline → no live path can start the 72h clock.
- **PRR-43 🔴** *(skeptic)* **dual-actor break-glass forgeable by a single operator** (`dispatcher.go:95-100`, `break_glass/break_glass.go:36-38`) — the "double" actor isn't independently verified.
- **PRR-44 🔴** *(skeptic)* **typed-confirmation is dead code** — `impact_classifier` sets `RequireTypedConfirm:true` for tier-1 but `confirmation/` is never enforced in dispatch.
- **PRR-45 🟠** *(skeptic)* admin audit logs **PII via free-text `Reason`** persisted verbatim while the emitter comment falsely claims "scrubbed".
- **PRR-01 (update) 🔴** *(skeptic NEW-3)* the core write path `contracts/meta/metawrite.go writeOneInTx:240-261` writes audit `BeforeValues/AfterValues` **verbatim with NO scrubber seam** → even a real scrubber wouldn't be invoked. Fix must add the seam, not just the impl.
- ✅ Primitives confirmed real: canon_cache reality-isolation (no cross-reality leak), 128-bit canary, input-wrapper marker-smuggling guard, YamlGuardrail fail-closed, secrets env-var fail-closed. L6.L injection_defense/intent_classifier no-op NOT wired into a live path (correctly deferred — verify the scheduled cycle).

### C4 — Test quality & cross-service live-smoke → GAPS_FOUND
- **PRR-09 (update) 🔴** **64% projection coverage gap** — 9 of 14 registered `event_types` have ZERO projection `apply_event` arm (incl. `xreality.user.erased`, a GDPR erasure event); projections also handle 14 events not in the registry.
- **PRR-32 🔴** the L3.B "every event type handled — CI gate" is **ABSENT** (no script cross-references `_registry.yaml` vs apply_event arms) → coverage claim was never enforceable. → add a real registry-vs-projection gate.
- **PRR-33 🔴** **Entire L2–L7 worker fleet ships as exit-0 skeletons** (publisher, archive/retention-worker, integrity-checker, meta-worker, canary-controller, alert-recorder, incident/postmortem-bot `cmd/main.go` = validate config + exit 0) → core **event-sourcing data flow never live-smoked end-to-end**. Partly tracked in DEFERRED.md (rows 054/057/059/064 HIGH) — treat as **launch-blocking**.
- **PRR-34 🔴 FALSE-GREEN** `D-DEGRADED-LIVE-SMOKE` marked CLEARED (cycle 33) but `degraded-live-smoke.sh:68-72` exits 0 in DRY_RUN *before* any docker-up/kill/assert → asserts nothing. → re-open (row 047) until a real run is recorded.
- **PRR-35 🔴** **No CI runs the gates** — `.github/workflows` only tests canary-controller + the tilemap subtree; verify-cycle scripts, foundation `cargo test --workspace`/`go test`, gitleaks are **local-only** → every "N/N PASS" is unverified in CI. → add a foundation-branch CI workflow.
- **PRR-36 🟠** `PgEventStore` Postgres path is **skip-and-return-green** when `LOREWEAVE_TEST_PG_URL` unset (`integration_event_store.rs:34-42`) → production SQL never exercised. (row 061)
- **PRR-37 🟠** integrity-checker drift engine + meta-worker consumer covered **only by in-memory fakes** — the exact mock-only surface the project's own lessons warn about.
- **PRR-38 🟡** verify scripts assert by **grepping test-function names** (existence, not execution).
- **PRR-39 🟡** projection unit tests assert update-count + table-name only, **not field values** → payload-mapping regressions uncaught.

### Build + misc
- ✅ **Integrated build PASS** (skeptic-confirmed) — note: no root `go.mod` (55-module repo; `go build ./...` from root FAILS — must iterate per-module); cargo was cached.
- **PRR-40 🟡** untracked build artifacts in worktree (`infra/pg18test-go/pg18test.exe`, `tools/eventgen/eventgen.exe`) — committed-binary risk for PR; add to `.gitignore`.
- **PRR-41 🟡** `knowledge-service/app/config.py:89` `neo4j_password` defaults to literal `loreweave_dev_neo4j` (env-overridable dev default) — make fail-closed for prod.
- **PRR-42 🟡** `lint-no-direct-llm-imports.sh` scope gap: only py/ts + 3-package regex → can't catch Go/Rust or cohere/mistral/google/vertex/etc. → broaden (defense-in-depth; I2 is still clean today).

---

## Review status

✅ Acceptance Audit (#1) · ✅ Decisions Audit (#2) · ✅ C1 (#5) · ✅ C2 (#6) · ✅ C3 (#7) · ✅ C4 (#8) · ✅ Integrated build (#9)

**Next:** Triage (#10) → final READY/NOT-READY verdict + route every PRR to fix-now or a DEFERRED.md row · Protocol design (#3) + enforce gate (#4) · **Fix phase (#11)** + SESSION/RETRO (#12).

### Finding tally (PRR-01..45)
- 🔴 **major (~17):** PRR-01, 02, 03, 05, 16, 20, 24, 28, 29, 30, 31, 32, 33, 34, 35, 43, 44 *(PII/GDPR · admin-cli auth+wiring · gateway-bypass · WS wire · worker skeletons · projection coverage · CI gates · I3 enforcement)*
- 🟠 **medium:** PRR-04, 06, 07, 08, 09, 17, 18, 25, 36, 37, 45
- 🟡 **low/cosmetic:** PRR-10, 11, 12, 13, 14, 15, 19, 21, 22, 23, 26, 27, 38, 39, 40, 41, 42
