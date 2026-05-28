# I3 Invariant Amendment Proposal

> **Source CLARIFY:** [00_CLARIFY_MASTER.md §2](00_CLARIFY_MASTER.md)
> **LOCKED:** 2026-05-29
> **Target file for amendment PR:** `docs/03_planning/LLM_MMO_RPG/00_foundation/02_invariants.md` (§ I3)
> **Companion CI lint:** `scripts/language-rule-lint.sh` (L1.K.10 — re-derived per amended I3)

---

## §1. Current I3 (before amendment)

From `docs/03_planning/LLM_MMO_RPG/00_foundation/02_invariants.md`:

> ### I3. Language rule
> Go for domain services · Python for AI/LLM services · TypeScript for gateway/BFF.
>
> - **Why:** skill specialization + runtime-stack boundaries.
> - **Enforced by:** code review.
> - **Source:** CLAUDE.md §Key Rules.

---

## §2. Amended I3 (after amendment)

> ### I3. Language rule
> Rust for kernel-derived services · Go for meta-registry-adjacent + existing
> domain services · Python for LLM-heavy services · TypeScript for gateway/BFF.
>
> **Full language matrix:**
>
> | Language | Services / scope | Why |
> |---|---|---|
> | **Rust** | `world-service`, `travel-service`, `roleplay-service`, future actor-substrate services (EF / RES / PL / TDIL / AIT / PROG) — any service that uses `#[derive(Aggregate)]` proc-macro | Kernel uses `#[derive(Aggregate)]` proc-macro from `crates/dp-kernel-macros/` (L4.B); macro can only be consumed by Rust crates. Plus: zero-cost abstractions + type safety for the event-sourcing hot path. |
> | **Go** | `auth-service`, `book-service`, `sharing-service`, `catalog-service`, `provider-registry-service`, `usage-billing-service`, `translation-service`, `glossary-service`, `publisher`, `meta-worker`, `event-handler`, `migration-orchestrator`, `admin-cli`, `archive-worker`, `retention-worker`, `integrity-checker`, `chaos-engine`, `backup-scheduler`, `session-cost-rollup-worker`, `slo-budget-calculator`, `canary-controller`, `oncall-bot`, `incident-bot`, `postmortem-bot`, `statuspage-updater`, `alert-recorder`, `embedding-worker` (V1+30d extract) | Domain services that do NOT use `#[derive(Aggregate)]`. Meta-registry primitives (`MetaWrite()` / `AttemptStateTransition()`) are Go-native; existing 12 LoreWeave novel-platform services unchanged. |
> | **Python** | `chat-service`, `knowledge-service`, `video-gen-service` | LiteLLM + Pydantic + asyncio ecosystem for LLM-heavy services. |
> | **TypeScript** | `api-gateway-bff`, `frontend-game` | I1 gateway invariant (NestJS); frontend tooling. |
>
> - **Why:** skill specialization + runtime-stack boundaries + macro-based kernel derivation requires Rust for downstream services.
> - **Enforced by:**
>   - CI lint `scripts/language-rule-lint.sh` (L1.K.10) reads `contracts/language-rule.yaml` mapping `services/<name>/` → expected language; rejects PRs whose service code is in wrong language.
>   - Code review backup.
> - **Source:** CLAUDE.md §Key Rules (original Go/Python/TS rule) + D-C0-1 ([V1_30D_CYCLE_LOG.md](../../V1_30D_CYCLE_LOG.md) Cycle 0 decision establishing Rust for world-service + travel-service) + L4.A-B foundation CLARIFY (extends rule to all kernel-derived services).

---

## §3. Rationale

### 3.1 Why Rust for kernel-derived services

The DP-kernel framework (L4.A) defines core traits (`Aggregate`, `Event`, `Projection`, `Snapshot`). The companion `dp-kernel-macros` crate (L4.B) ships `#[derive(Aggregate)]` and `#[derive(Projection)]` proc-macros that generate trait implementations from struct annotations.

Proc-macros are **Rust-only language feature** — there is no equivalent in Go, Python, or TypeScript. Any service that needs to derive an Aggregate from a struct definition must therefore be Rust.

From the kernel design (L4.A):
- `crates/dp-kernel/` defines `Aggregate` trait
- `crates/dp-kernel-macros/` ships the `derive` macro
- Services that own aggregates (world-service holds `Reality`, travel-service holds `ActorTravelState`, roleplay-service holds `Session`, future actor-substrate holds `Entity`, `Resource`, etc.) all `#[derive(Aggregate)]` on their domain types

**Without Rust** for these services, every aggregate would need hand-written boilerplate (event handlers, version tracking, snapshot serialization) — which:
- Adds ~500-2000 LOC per aggregate (vs ~50 LOC with macro)
- Defeats compile-time guarantees of the macro (matched events, version monotonicity, payload schema)
- Forks the kernel's source of truth (the macro IS the contract; hand-written impls drift)

### 3.2 Why Go remains for meta + adjacent services

The meta-registry primitives (`MetaWrite()`, `AttemptStateTransition()`) are simple CRUD wrappers around `loreweave_meta` Postgres. They:
- Do NOT derive Aggregate (meta is not event-sourced; it's CRUD-with-audit per S04)
- Need to be callable from EVERY service language → Go provides simple HTTP/gRPC bindings to other languages
- Match existing LoreWeave novel-platform service codebase

Meta-adjacent services (publisher, meta-worker, event-handler, migration-orchestrator) consume the Go meta library directly — Rust would require extra wrapping with no benefit.

### 3.3 Why Python remains for LLM-heavy services

`chat-service`, `knowledge-service`, `video-gen-service` rely heavily on:
- LiteLLM (Python-only) for multi-provider LLM routing
- Pydantic for prompt/response validation
- asyncio for concurrent LLM calls

Rewriting these in Rust would lose access to the Python ML/LLM ecosystem with no offsetting performance benefit (LLM call latency dwarfs runtime overhead).

### 3.4 Why TypeScript remains for gateway/frontend

`api-gateway-bff` is NestJS per I1 gateway invariant — unchanged.

---

## §4. Service map amendment (companion deliverable)

`docs/03_planning/LLM_MMO_RPG/00_foundation/03_service_map.md` requires the following amendments in the same PR:

### 4.1 Existing services table (line 11-22): NO CHANGE
All 12 existing services remain Go/Python/TS as listed.

### 4.2 LLM MMO RPG V1 new services table (line 28-37): UPDATE LANGUAGES

| Service | OLD Language | NEW Language | Reason |
|---|---|---|---|
| `world-service` | Go | **Rust** | Per D-C0-1 + L4.A-B (derives Aggregate) |
| `travel-service` | Go | **Rust** | Per D-C0-1 (deferred; not in foundation but locked) |
| `roleplay-service` | Go | **Rust** | Per L4.A-B (derives Aggregate for Session) |
| `publisher` | Go | Go | unchanged |
| `meta-worker` | Go | Go | unchanged |
| `event-handler` | Go | Go | unchanged |
| `migration-orchestrator` | Go | Go | unchanged |
| `admin-cli` | Go | Go | unchanged |

### 4.3 New services to add to service map (per OPEN_QUESTIONS_LOCKED.md §10)

Add rows for 12 new services surfaced during CLARIFY:

| Service | Lang | Owns | Emits | Consumes | Responsibility |
|---|---|---|---|---|---|
| `session-cost-rollup-worker` | Go | (none — drains per-reality session_cost_tracking) | `billing.session.summary.updated` | per-reality DB poll | Q-L1A-1 hybrid rollup 60s |
| `archive-worker` | Go | (none) | `archive.*` | n/a (cron) | L2.J detach partition → MinIO Parquet |
| `retention-worker` | Go | (none) | `retention.*` | n/a (cron) | L2.K per-event-class cleanup |
| `integrity-checker` | Go | `drift_queue` (per-reality) | `projection.drift.detected` | per-reality DB | L3.E + L3.F daily + monthly checks |
| `chaos-engine` | Go | `chaos_drills` (meta) | `chaos.drill.*` | n/a (scheduled) | L4.O — V1+30d |
| `backup-scheduler` | Go | (none) | `backup.*` | `reality.status.*` | L1.H tiered backup |
| `embedding-worker` | Rust | (none) | `npc.embedding.computed` | per-reality DB queue | L3.I async embedding — V1+30d extract |
| `slo-budget-calculator` | Go | (none — computes from metrics) | `slo.burn.*` | Prometheus query | L7.I |
| `canary-controller` | Go | (none) | `deploy.canary.*` | `deploy.started`, SLO burn | L7.K |
| `oncall-bot` | Go | (none) | `oncall.*` | Slack | L7.C — V1+30d |
| `incident-bot` | Go | (none — manages war room) | `incident.declared` | alert webhooks | L7.D |
| `postmortem-bot` | Go | (none) | n/a | `incident.closed` | L7.D |
| `statuspage-updater` | Go | (none) | n/a (calls statuspage API) | `incident.*` | L7.L |
| `alert-recorder` | Go | (none) | n/a | alertmanager webhooks | L7.J |

### 4.4 Shared meta DB content (line 67-79): UPDATE

OLD line 71:
```
- canon_entries + canonization_audit (S13)
```

REMOVE (Q-L1A-2 LOCKED — canon tables move to glossary-service's glossary DB).

OLD line 19 (glossary-service row):
```
| `glossary-service` | Go / Chi | `glossary` DB (glossary, lore, wiki_articles, wiki_revisions, wiki_suggestions) | `glossary.*`, `wiki.*`, `canon.*` | ...
```

ADD canon tables:
```
| `glossary-service` | Go / Chi | `glossary` DB (glossary, lore, wiki_articles, wiki_revisions, wiki_suggestions, **canon_entries, canonization_audit, book_authorship, canon_change_log**) | `glossary.*`, `wiki.*`, `canon.*`, `canon.change.*` (NEW outbox emission per L5.A) | ...
```

ADD note:
```
- `session_cost_summary` (Q-L1A-1 NEW rollup, written by `session-cost-rollup-worker`)
```

---

## §5. CI lint specification (L1.K.10 `language-rule-lint.sh`)

Reads from `contracts/language-rule.yaml`:

```yaml
# contracts/language-rule.yaml — LOCKED 2026-05-29
services:
  # Rust
  world-service: rust
  travel-service: rust
  roleplay-service: rust
  embedding-worker: rust  # V1+30d
  # Go (existing 12)
  auth-service: go
  book-service: go
  sharing-service: go
  catalog-service: go
  provider-registry-service: go
  usage-billing-service: go
  translation-service: go
  glossary-service: go
  # Go (new 14)
  publisher: go
  meta-worker: go
  event-handler: go
  migration-orchestrator: go
  admin-cli: go
  archive-worker: go
  retention-worker: go
  integrity-checker: go
  chaos-engine: go
  backup-scheduler: go
  session-cost-rollup-worker: go
  slo-budget-calculator: go
  canary-controller: go
  oncall-bot: go
  incident-bot: go
  postmortem-bot: go
  statuspage-updater: go
  alert-recorder: go
  # Python
  chat-service: python
  knowledge-service: python
  video-gen-service: python
  # TypeScript
  api-gateway-bff: typescript
```

Lint logic:
1. Walk `services/<name>/` directories
2. For each, look up expected language in YAML
3. Detect language by file extensions / config files (Cargo.toml=rust, go.mod=go, pyproject.toml=python, package.json=typescript)
4. Detected != expected = FAIL

---

## §6. Commit ordering for the amendment PR

The amendment PR must include in a single commit:

1. `docs/03_planning/LLM_MMO_RPG/00_foundation/02_invariants.md` — I3 amended
2. `docs/03_planning/LLM_MMO_RPG/00_foundation/03_service_map.md` — language column updates + new service rows + meta DB content updates
3. `contracts/language-rule.yaml` — NEW file
4. `scripts/language-rule-lint.sh` — NEW lint script
5. `.github/workflows/lint.yml` — wire lint into CI

**This PR is the deliverable of Cycle 7** (last L1 cycle), since L1.K.10 lint ships there.

**Until that PR merges:** RAID agents working on cycles 1-6 use the LOCKED resolution as written here; the kernel I3 amendment is pending but the decision is binding.

---

## §7. Impact on AGENT_GUIDE.md status vocabulary

No change needed. The amendment uses existing status vocabulary (LOCKED, ACCEPTED).

---

## §8. Cross-reference list

This amendment touches the following kernel docs:

- `02_invariants.md §I3` (this amendment)
- `03_service_map.md` lines 11-37, 67-79
- `04_kernel_api.md` (Rust + Go signatures of MetaWrite, AssemblePrompt, etc. — see L4.C Rust client port specs)
- `06_id_catalog.md` (no change — language is not an ID)
- `07_feature_workflow.md` (no change — workflow unchanged)
- `CLAUDE.md §Key Rules` (root project memory) — language rule line should reference foundation I3 with cross-link

Plus repo-level:
- `Cargo.toml` (workspace) — confirms `services/world-service`, `services/travel-service`, `services/roleplay-service`, etc. as workspace members
- Cycle 7 includes initial Cargo workspace setup for any new Rust services (roleplay-service to be added when L4-relevant cycles run)

---

## §9. Status

```
[x] Amendment text drafted
[x] Companion service map updates drafted
[x] CI lint spec drafted
[x] Commit ordering specified
[ ] PR creation — DEFERRED to Cycle 7 (when L1.K.10 lint ships)
```

**Note:** This file is a CLARIFY artifact + PR planning doc. The actual PR will be authored as part of Cycle 7 RAID execution, using this file as the authoritative source.
