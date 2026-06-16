# OPEN QUESTIONS — LOCKED Decisions

> **Date locked:** 2026-05-29
> **Method:** CLARIFY bottom-up deep-dive per layer + user batch lock per layer (recommended defaults)
> **Total locked:** 73 (3 L1.A + 19 L1.B-L + 8 L2 + 8 L3 + 8 L4 + 7 L5 + 8 L6 + 12 L7)
> **Status:** LOCKED — RAID agents consume these as authoritative; do NOT re-litigate

---

## §1. How to use this file

When a RAID cycle agent (DPS / Adversary / Scope Guard) encounters a design choice that is in this file, the agent MUST apply the LOCKED resolution. Any deviation = ESCALATIONS.md row + abort cycle.

If a RAID agent encounters a design choice NOT in this file AND NOT clearly derivable from the kernel chunks, that is a CLARIFY-time gap — write ESCALATIONS.md row + abort + human reviews.

---

## §2. L1.A — Meta Registry Tables (3 LOCKED 2026-05-29 mid-CLARIFY)

| # | Question | Resolution | Implication |
|---|---|---|---|
| Q-L1A-1 | `session_cost_tracking` placement: meta vs per-reality DB? | **Hybrid:** per-reality DB owns live writes; meta has `session_cost_summary` (60s rollup by new `session-cost-rollup-worker` service) | NEW service in service map; reduces meta cardinality |
| Q-L1A-2 | `canon_entries` location — service map line 71 says meta; S13-D4 says glossary-service | **Glossary DB.** ALL 4 canon tables (canon_entries, canonization_audit, book_authorship, canon_change_log) move OUT of meta. Service map line 71 + line 19 amendment required | L5 inbound canon is event-driven via glossary outbox + RPC; foundation owns contract + meta-worker consumer + per-reality canon_projection |
| Q-L1A-3 | `service_to_service_audit` cardinality strategy | **Full audit from V1**, no sampling | ~10 TB / 5y storage; dedicated audit DB cluster at V2+ (C03 §12O.10 earlier trigger) |

---

## §3. L1.B-L — Infrastructure (19 LOCKED batch 2026-05-29)

| # | Question | Resolution |
|---|---|---|
| Q-L1B-1 | events_allowlist.yaml authoritative source | Auto-derive from service map "Emits events" column + cross-check with `outbox_event_emit_lint` (L1.K.12) |
| Q-L1B-2 | meta-sensitive-read-paths.yml ownership | Platform owns initial set; security team CODEOWNERS on changes |
| Q-L1B-3 | MetaWrite() multi-table TX support | YES — add `MetaWriteBatch(ctx, []MetaWriteIntent) error` helper |
| Q-L1B-4 | Library exports for non-Go (Python knowledge/chat, Rust kernel) | Per-language port for hot-path callers; RPC via meta-worker for cold-path |
| Q-L1B-5 | Library testing infra | Foundation ships `docker-compose.meta-ha.yml` with Patroni + etcd + 1 sync + 1 async |
| Q-L1C-1 | V1 shard provisioning IaC or manual | Foundation V1 = docker-compose single shard; IaC for prod V1+30d |
| Q-L1D-1 | Migration auto-rollback on persistent failure | V1 doc-only manual rollback by SRE; V2+ auto-rollback for non-data-changing migrations |
| Q-L1E-1 | Cross-region DR — V1+30d or V3+? | V3+ per C03 §12O.9 |
| Q-L1E-2 | etcd hosted-managed or self-hosted | Self-hosted on dedicated EC2/EKS (vendor lock avoidance + Patroni docs match) |
| Q-L1F-1 | Multi-instance Redis topology | Shared Sentinel V1; per-AZ V3+ multi-AZ resilience |
| Q-L1G-1 | Stick with pgbouncer (vs pgcat/Odyssey)? | YES; re-evaluate trigger = transaction-pool limits hit V3 |
| Q-L1H-1 | Foundation includes MinIO provisioning? | Confirm MinIO pre-existing for LoreWeave novel platform; foundation adds dedicated `lw-db-backups` bucket only |
| Q-L1H-2 | Restore-drill cadence | Monthly per shard automated; quarterly full-system drill manual |
| Q-L1I-1 | Prometheus topology — single vs HA | HA pair via federation for V1+ |
| Q-L1I-2 | Long-term metric retention | V1 = 30d Prometheus native; V1+30d = Thanos sidecar for 1y+ |
| Q-L1J-1 | Redis control channel separate or shared with cache | Same Redis (lower infra footprint); document risk |
| Q-L1K-1 | Lint tool choices | Mix — semgrep for cross-language patterns, shell+grep for simple, go vet extensions for Go-specific |
| Q-L1K-2 | When does language-rule-lint enforce I3 amendment? | Same commit as I3 amendment (final CLARIFY artifact, `I3_INVARIANT_AMENDMENT.md`) |
| Q-L1L-1 | HPA + KEDA infra — K8s or ECS? | K8s per CLAUDE.md infra hosting model |

---

## §4. L2 — Event sourcing + Outbox + Publisher (8 LOCKED batch 2026-05-29)

| # | Question | Resolution |
|---|---|---|
| Q-L2-1 | Sync vs async projection — V3+ async? | YES, V1 sync; async deferred V3+ |
| Q-L2-2 | events partition strategy | Monthly (matches R01 §12A.4 archive cadence) |
| Q-L2-3 | event_audit ↔ events linkage (FK or UUID) | UUID pointer (FK breaks after events archived) — confirmed by R01 |
| Q-L2D-1 | Publisher multi-replica trigger | V2 = scale beyond 1000 active realities |
| Q-L2J-1 | Archive worker placement | Dedicated `archive-worker` service (matches publisher pattern) |
| Q-L2K-1 | retention-worker + archive-worker same binary? | Separate (different ops cadence, alert SLOs) |
| Q-L2-4 | xreality.* topic naming | `xreality.<entity>.<verb>` per service map line 60 convention |
| Q-L2-5 | Publisher V1 leader election (N=1 replica means no election needed) | Implement V1 (no-op cost; V2+ scale ready) |

---

## §5. L3 — Snapshot + Projection runtime (8 LOCKED batch 2026-05-29)

| # | Question | Resolution |
|---|---|---|
| Q-L3-1 | Embedding worker placement | V1 in world-service async queue; V1+30d extract if embedding volume justifies |
| Q-L3-2 | Async projection (V3+) | OUT confirmed (per L2 §1) |
| Q-L3B-1 | Projection trait — multiple projections per event? | YES — return `Vec<ProjectionUpdate>` |
| Q-L3E-1 | integrity-checker — separate service? | Separate (different ops cadence, can scale independently) |
| Q-L3I-1 | Embedding dimension 1536 hard-coded | V1 lock 1536; V2+ flexible per-table per-dimension |
| Q-L3-3 | Catastrophic rebuild orchestrator | admin-cli sub-command + `rolling_rebuild` internal lib |
| Q-L3-4 | Verification metadata columns on every projection table | YES; minimal overhead, required for integrity |
| Q-L3-5 | V2 blue-green migration scaffolding in foundation? | NO; V2+ scope per R02 §12B.8 |

---

## §6. L4 — SDK + Kernel API + Macros (8 LOCKED batch 2026-05-29)

| # | Question | Resolution |
|---|---|---|
| Q-L4A-1 | EventStore trait — sqlx::PgPool exposed or wrapped? | Wrapped (cleaner test mocking + future backend swap) |
| Q-L4B-1 | Macro attribute syntax | `#[handles_event("npc.said")]` (rustc-idiomatic, supports multiple) |
| Q-L4D-1 | ProviderPayload type — opaque or typed enum? | Opaque V1 (cross-provider diversity); typed V2+ |
| Q-L4-1 | Rust client ports for Go contracts — how many languages? | 3 (Go + Rust + Python) for runtime types; TS only for events + WS envelope |
| Q-L4-2 | Single workspace Cargo.toml or split | Single root workspace; per-service members — confirmed by repo state |
| Q-L4-3 | Polyglot type generation — unified or per-contract? | Unified `contractgen` tool (extends `eventgen` scope from L2.G) |
| Q-L4-4 | `contracts/chaos/` deployment — V1 or V1+30d? | V1+30d per SR07 §12AJ implementation phase |
| Q-L4-5 | contracts/* v1.yaml OpenAPI — served by gateway? | Internal documentation V1; api-gateway-bff serves user-facing APIs only |

---

## §7. L5 — Inbound canon ingestion (7 LOCKED batch 2026-05-29)

| # | Question | Resolution |
|---|---|---|
| Q-L5A-1 | glossary-service outbox migration | Separate sub-program before L5 push activates; foundation owns contract + test fixture |
| Q-L5H-1 | Force-propagate consent timeout | 24h; default-to-consent on no-response (needs governance lock later in governance-track sub-program) |
| Q-L5-1 | Canon cache invalidation strategy | Event-driven primary; 60s TTL as fallback |
| Q-L5-2 | translation-service for reality seeding (M-REV-5) | V1 if reality.locale != book.source_locale per M-REV-5 |
| Q-L5-3 | canon_projection schema — single table or per-canon-layer? | Single table with `canon_layer` column |
| Q-L5-4 | glossary-service RPC transport | HTTP/JSON V1 (matches existing LoreWeave novel platform); gRPC V2+ if perf demands |
| Q-L5-5 | L1 axiomatic runtime canon-guardrail | Roleplay-service pre-prompt-assembly check against `canon_guardrail.rs` (L5.I.3) before write |

---

## §8. L6 — WS + Obs/Cap + LLM safety pre-spec (8 LOCKED batch 2026-05-29)

| # | Question | Resolution |
|---|---|---|
| Q-L6-1 | api-gateway-bff WS impl — extend NestJS or new sidecar? | Extend existing NestJS (matches I1 + LoreWeave novel-platform code) |
| Q-L6-2 | WS connection cap per replica V1 | 10K per replica (verified by load test); HPA scales replicas |
| Q-L6F-1 | Admission V1 → V1+30d transition — auto or admin-triggered? | Time-based (foundation ships V1+30d as flag-flip at config); admin can flip earlier |
| Q-L6G-1 | Capacity admission webhook — K8s or ECS? | K8s (matches CLAUDE.md infra); ECS V2+ variant |
| Q-L6H-1 | Composer error handling — fail or best-effort render? | Fail (per S09 §12Y — never emit malformed prompt) |
| Q-L6K-1 | Prompt copy ownership | Feature team / DF3 / future LLM-logic sub-program. Foundation ships empty skeletons. |
| Q-L6L-1 | LLM safety stubs — empty defaults or fail-closed? | Empty (no-op) V1; fail-closed in LLM-safety sub-program |
| Q-L6-3 | Browser WS lib (TS) — foundation owns? | frontend-game team (foundation = server + envelope types only) |

---

## §9. L7 — Operations + Logging + Monitoring (12 LOCKED batch 2026-05-29)

| # | Question | Resolution |
|---|---|---|
| Q-L7A-1 | command_registry.yaml — single or per-domain split? | Per-domain split (`registry/reality.yaml`, `registry/erasure.yaml`, …) + framework auto-merge |
| Q-L7A-2 | Admin CLI distribution | Single binary with subcommands (`admin reality force-close`) — easier ship + version |
| Q-L7B-1 | 27-runbook list — V1 ships all or staggered? | V1 ships ALL 27; stub OK if `last_verified: 1970-01-01` + `verification_method: stub` |
| Q-L7C-1 | PagerDuty vs alternatives | PagerDuty V1 (industry standard, broad integration, ~$25/user/month acceptable) |
| Q-L7C-2 | Solo-dev weekend SLA user-facing? | Internal `docs/governance/oncall-sla.md` V1; user-facing TOS V2+ paid-tier launch |
| Q-L7F-1 | Loki vs ELK vs Datadog? | Loki self-hosted V1 (cost); reconsider V3+ if log volume justifies managed |
| Q-L7K-1 | V1 = GitHub Actions only or ArgoCD too? | GitHub Actions V1; ArgoCD V2+ if multi-cluster |
| Q-L7L-1 | Statuspage.io vs self-hosted? | Statuspage.io V1 (~$29/month, EN+VI); self-hosted V2+ if cost concern |
| Q-L7-1 | incident-bot + statuspage-updater + slo-calc — bundle? | Separate services (clear ops boundaries per service map convention) |
| Q-L7-2 | Comms template pre-approval workflow | Pre-approved templates in `infra/comms/templates/`; legal review process V2+ formal |
| Q-L7-3 | Service mesh (Istio/Linkerd) for tracing/auth? | NOT V1 (adds complexity); revisit V3+ when service count > 30 |
| Q-L7-4 | Frontend RUM ownership | frontend-game team owns RUM; foundation owns backend tracing only |

---

## §10. Summary table — new services surfaced during CLARIFY

These services are NEW (not in original service map line 31-37) and surfaced as consequence of LOCKED decisions:

| Service | Surfaced by | Language | Size |
|---|---|---|---|
| `session-cost-rollup-worker` | Q-L1A-1 hybrid | Go | S |
| `archive-worker` | Q-L2J-1 dedicated | Go | M |
| `retention-worker` | Q-L2K-1 separate | Go | M |
| `integrity-checker` | Q-L3E-1 separate | Go | M |
| `chaos-engine` | L4.O (V1+30d) | Go | M |
| `backup-scheduler` | L1.H | Go | S |
| `embedding-worker` | Q-L3-1 (V1+30d extract) | Rust | M |
| `slo-budget-calculator` | L7.I | Go | M |
| `canary-controller` | L7.K | Go | M |
| `oncall-bot` | L7.C (V1+30d) | Go | S |
| `incident-bot` | L7.D | Go | M |
| `postmortem-bot` | L7.D | Go | S |
| `statuspage-updater` | L7.L | Go | S |
| `alert-recorder` | L7.J | Go | S |

**Plus original 7 in service map line 31-37:** world-service (Rust), travel-service (Rust — deferred), roleplay-service (Rust — deferred), publisher (Go), meta-worker (Go), event-handler (Go), migration-orchestrator (Go), admin-cli (Go).

**Total service count after foundation:** 12 existing + 7 original new + 14 surfaced = **33 services**.

This is significantly higher than the initial 19-service estimate. Cycle 36 (L7.A admin-cli) and capacity budgets must reflect this.

---

## §11. Summary table — new tables surfaced during CLARIFY

In meta DB:
- `session_cost_summary` (Q-L1A-1 rollup) — was not in original list
- Per-table verification metadata (L3.K) — 10 projection tables get 2 new columns each

Removed from meta DB (Q-L1A-2):
- `canon_entries`, `canonization_audit`, `book_authorship`, `canon_change_log` — moved to glossary DB

Net change in meta tables: −4 (canon) + 1 (session_cost_summary) + (verification metadata is ALTER not new table) = **33 meta tables** (down from estimate 36).

New tables in per-reality DB beyond original L2-L3 plan:
- `canon_projection` (L5.D) — new per-reality table for cached canon

Net: per-reality DB has 10 projection tables + canon_projection = 11 tables + events + event_audit + outbox + snapshots = **15 tables per per-reality DB**.

---

## §12. Decisions NOT in this file but referenced elsewhere

Foundation-level decisions made in 00_CLARIFY_MASTER.md (not Q-IDs but still LOCKED):

- **Scope IN/OUT** — see CLARIFY_MASTER §1
- **Tech stack** (Rust kernel-derived / Go meta / Python LLM / TS gateway) — see CLARIFY_MASTER §2; final artifact in `I3_INVARIANT_AMENDMENT.md`
- **Acceptance philosophy** (CI gates + retry 3x + cold-start review + auto post-review) — see CLARIFY_MASTER §3
- **RAID role contract** — see RAID_WORKFLOW.md §2
- **Audit trail format** — see CLARIFY_MASTER §5 + RAID_WORKFLOW.md §6

---

## §13. Re-litigation policy

Once a Q-ID is in this file as LOCKED, the resolution is binding. Re-opening requires:

1. A RAID cycle agent OR human writes an `RFC-<Q-ID>` document in `docs/sessions/` arguing for change
2. Document includes: current resolution, proposed change, evidence why current is broken, expected impact on downstream cycles
3. Human decision (NOT automated): keep | change | escalate to architect role
4. If changed: this file updated + amendment commit + ALL cycles re-evaluated for impact

Default: **STICK WITH LOCKED** unless evidence of serious flaw.

---

## §14. Status

```
[x] L1.A — 3 LOCKED (mid-CLARIFY, structural changes)
[x] L1.B-L — 19 LOCKED batch
[x] L2 — 8 LOCKED batch
[x] L3 — 8 LOCKED batch
[x] L4 — 8 LOCKED batch
[x] L5 — 7 LOCKED batch
[x] L6 — 8 LOCKED batch
[x] L7 — 12 LOCKED batch
[x] TOTAL: 73 LOCKED
```

**File status:** AUTHORITATIVE. RAID agents may not deviate.
