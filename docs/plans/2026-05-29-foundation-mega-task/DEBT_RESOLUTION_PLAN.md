# Foundation Debt-Resolution Plan

> **Goal:** drive every open `DEFERRED.md` row for the foundation-mega-task to closed —
> turning the contract-complete **skeleton** into a **functional, locally-verifiable
> system**. Source of debt: `POST_RAID_REVIEW_FINDINGS.md` + `DEFERRED.md` (open rows
> 041–080) + the completeness-critic pass.
> **Created:** 2026-05-30 (post-RAID review). **Branch:** `mmo-rpg/foundation-mega-task`.

## 0. Strategy (the operating pattern for every item)

The post-RAID review proved (F7) that the foundation is **docker-compose-testable** here —
standing up `infra/foundation-dev` (Postgres/Redis/MinIO) immediately found + fixed 2 real
bugs that mock-only tests missed. So every live-wiring item follows the **same loop**:

1. **Wire** the skeleton (`cmd/main.go` / interface impl) to the real local adapter (pgx / redis / minio / provider-registry).
2. **Live-smoke** on `infra/foundation-dev` (an end-to-end cross-service assertion, NOT dry-run — see PRR-34).
3. **CI-enforce** it: add the smoke + its lints to `foundation-ci.yml` so it can't regress (this is itself debt — row 078).

**Phase exit gate:** the phase's live-smokes pass on docker-compose AND are wired into CI green.
Each closed item flips its `DEFERRED.md` row to `(ADDRESSED …)` + moves to "Recently cleared".

## 1. Decisions needed from the operator (blockers for some phases)

> **RESOLVED 2026-05-30:** D1 = **LocalStack** (AWS KMS emulation in docker-compose) · D2 = **RS256** (asymmetric) · D3 = world/travel game-domain is a **separate post-foundation track** (P5 stays a gated placeholder) · D4 = **iterate on-branch** (P0 started; no PR until P1–P2 functional). The table below records the original options.

| # | Decision | Affects | Default if unanswered |
|---|---|---|---|
| D1 | **KMS provider** for PII KEK: LocalStack (AWS KMS emul) vs Vault Transit vs a dev `EnvKMS` | P2 (076) | LocalStack in docker-compose (closest to AWS prod) |
| D2 | **Auth-service JWT scheme**: RS256 (asymmetric, prod-shaped) vs HS256 (simpler dev) | P2 (074/075) | RS256 — matches the `auth.Validate` seam comment |
| D3 | **world/travel game domain (079)** in scope of THIS foundation effort, or a separate post-foundation track? | P5 | Separate track — foundation is the substrate |
| D4 | **Push/PR cadence**: PR the skeleton milestone to `main` now, or keep iterating on-branch until functional? | all | Keep on-branch until P1–P2 done |

## 2. Phased plan

Ordering is dependency-driven: enablement → the event-sourcing spine (everything else reads/writes through it) → security/GDPR → ops/deploy → contracts/cleanup → domain.

### Phase 0 — Enablement (unblocks everything; do first)
- **Goal:** reliable local stack + CI that actually enforces the gates, so subsequent wiring is verifiable + regression-proof.
- **Items:** **078** (D-CI-GATE-COVERAGE — wire ~20 missing lints incl. the I2 provider-gateway lint, a Python build/test job, and a docker-compose live-smoke job into `foundation-ci.yml`); **041** (live docker stack smoke harness); a small `infra/foundation-dev` hardening (port-conflict-proof: parametrize host ports; optional LocalStack/Vault service for D1).
- **Exit:** `foundation-ci.yml` runs every lint + Python + a docker-compose PG smoke; `bash scripts/post-raid-review-gate.sh` and all lints green in CI.

### Phase 1 — Event-sourcing spine (the heart)
- **Goal:** the outbox→publish→consume→project→verify data flow runs **end-to-end** on docker-compose, not as skeletons.
- **Items:** **054** (publisher live-wiring: outbox→Redis Streams) → **069 (meta-worker + integrity-checker portion)** (consumers → per-reality projections; integrity-checker drift engine on real PG) → **036/061** (PgEventStore PG path in CI — mostly done in F7, just wire to CI) ; **056**→**057** (archive_state migration → archive-worker: PG→Parquet→MinIO) ; **058** (retention-worker) ; **059**→**060** (embedding-queue live-wiring → Redis-backed FIFO) ; **050/051** (eventgen AST parse / contractgen unify — optional hardening) ; **053** (xreality metadata validator hardening).
- **Exit:** one end-to-end smoke: emit an event → publisher → meta-worker → projection row appears → integrity-checker confirms → archive-worker writes Parquet to MinIO. All on `infra/foundation-dev`, asserted (not dry-run), in CI.

### Phase 2 — Security & GDPR production layer
- **Goal:** the security primitives become **wired + enforced**, not present-but-dead.
- **Items:** **auth-service JWT signing** (prereq, D2) → **075** (break-glass 24h-TTL claim) + **074** (admin-cli RS256/JWS verify, replace dev-token) ; **073** (admin-cli command bodies → MetaWrite adapter; the 4 real bodies + the destructive ones) ; **076** (PII: KMS KEKManager [D1] + scrubber→metawrite seam + erasure.go 10-step runbook + PRR-45 audit-Reason scrub + integration tests) ; **072** (GDPR Art.33 breach flow wired into incident-bot + concrete DPONotifier [fake in dev]) ; **071** (projection erasure handler for `xreality.user.erased`, then remove the coverage-gate allowlist entry).
- **Exit:** live-smokes: forged dev token rejected (prod mode); break-glass requires real dual signed tokens; PII written to audit comes back masked; a user-erasure event tombstones projection rows + starts the 72h clock. In CI.

### Phase 3 — Ops, deploy & remaining workers
- **Goal:** the observability/incident/deploy workers run + the deploy pipeline is live.
- **Items:** **069 (remainder)** (alert-recorder, slo-budget-calculator, incident-bot, postmortem-bot, statuspage-updater live-wiring) ; **064** (canary-controller: pgx DeployStore + Prom SLISource + GH-Actions executor + PagerDuty) + **063** (deploy.yml live steps) ; **066** + **080** (session-cost-rollup-worker scaffold + the 5 empty meta sink-table writers + remove/annotate the orphaned KEDA manifest) ; **070** (logging `-tags=prod` in deployable Dockerfiles + CI assertion) ; **048** (backup live-restore runner) ; **043/042** (Redis adapter / provisioner Effects RPC) ; **044/045/046** (migrate-CLI + provisioner Prom wiring) ; **060** if not done in P1.
- **Exit:** incident→statuspage flow live-smoke; canary advance/abort against injected SLI on the stack; cost rollup populates the meta table.

### Phase 4 — Contracts, architecture & cleanup
- **Goal:** close the contract drifts + architecture verifications + low-severity cleanups.
- **Items:** **068** (WS ticket-hash base64 both sides + envelope.seq enforcement + round-trip test) ; **067** (`#[derive(Projection)]` macro + event_annotations.rs + test) ; **077** (game-WS edge controls verified: handshake auth + caps + audit + SG manifest) ; **065** (the grouped LOW: capacity row, neo4j fail-closed default, broaden llm-import lint, projection test field-assertions + execute-not-grep, CYCLE_LOG headers, naming, phantom service_acl, canon_history 401) ; **049** (lint fixture corpus) ; **052** (CODEOWNERS for contracts/events).
- **Exit:** WS interop test green cross-process; all LOW rows closed.

### Phase 5 — Game domain (separate track; gated on D3)
- **Items:** **079** (world-service GEO_001 + travel-service TVL_001..005 domain aggregates/projections — currently Cycle-5 scaffold binaries). This is post-foundation domain work; only start if D3 says in-scope.

## 3. Coverage table — every open foundation DEFERRED row → phase (nothing dropped)

| Phase | DEFERRED rows |
|---|---|
| P0 Enablement | 078, 041 |
| P1 Event-sourcing spine | 054, 056, 057, 058, 059, 060, 069(meta-worker+integrity-checker), 036/061, 050, 051, 053 |
| P2 Security/GDPR | 074, 075, 073, 076(+PRR-45), 072, 071 |
| P3 Ops/deploy/workers | 069(alert/slo/incident/postmortem/statuspage), 064, 063, 066, 080, 070, 048, 042, 043, 044, 045, 046 |
| P4 Contracts/cleanup | 068, 067, 077, 065, 049, 052 |
| P5 Domain (gated D3) | 079 |

**Out of foundation scope (separate game-frontend / zone-map track — NOT in this plan):** rows 035 (game-server EchoRoom rate-limit), 036(Phaser shim), 037 (V2 asset pipeline), 039/040 (geo-generator calibration/fragmentation). Tracked in DEFERRED.md under their own origins.

## 4. Execution notes
- **Re-run the post-RAID review gate** after each phase (`scripts/raid/post-raid-review-gate.sh`) + re-stamp the verdict; close addressed rows.
- **Per-group commit cadence** (as in the fix phase): one commit per cluster, build+live-smoke green before commit.
- **No push** without operator approval; PR-to-main per D4.
- Effort: P0 small; P1 large (the spine); P2 large (security + infra deps); P3 medium-large; P4 medium; P5 separate. Realistically multi-session.
