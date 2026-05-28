# Foundation Mega-Task — RAID Cycle Decomposition

> **Parent:** [_index.md](_index.md)
> **Status:** LOCKED 2026-05-29 — ready for RAID execution
> **Total cycles:** 38 (1 RAID infra cycle + 37 foundation cycles across 7 layers)

---

## §1. Execution model

Each cycle is a **single RAID workflow run** (12 phases — see [RAID_WORKFLOW.md](RAID_WORKFLOW.md)). Each XL by AMAW classification.

**Per-cycle prompt template:** see §6. Substitute `<N>` with cycle number.

**Sequencing:**
- Cycles run in dependency order (forward only; no out-of-order)
- Each cycle commits its work to `mmo-rpg/foundation-mega-task` branch (or sub-branches per cycle)
- After ALL 38 cycles complete: batch review → merge to `main` via PR

**Parallelism:** within a cycle, DPS sub-agents may work in parallel worktrees on independent slices (declared per cycle).

---

## §2. Cycle inventory (38 cycles)

### Cycle 0 — RAID Workflow Infrastructure (amended v1.1)

**Size:** M (was S/M; v1.1 amendment added 10 protection scripts → bumped to M)
**Workflow:** Default workflow, NOT RAID — bootstrap problem
**Scope:** Set up RAID v1.1 infrastructure (including §12 context protections) before any RAID-driven cycle.
**Dependencies:** —

**Deliverables (core, v1.0):**
- `docs/raid/RAID_WORKFLOW.md` (copy of [RAID_WORKFLOW.md](RAID_WORKFLOW.md))
- `scripts/raid/orchestrator.py` — main RAID dispatcher
- `scripts/raid/verify-cycle-template.sh` — template for per-cycle verify scripts
- `scripts/raid/escalation-writer.py` — writes ESCALATIONS.md row after 3 failed attempts
- `docs/raid/AUDIT_LOG.jsonl` (empty file, append-only)
- `docs/raid/CYCLE_LOG.md` (skeleton)
- `docs/raid/ESCALATIONS.md` (skeleton)
- `docs/raid/cycle_briefs/` directory — pre-generated briefs for cycles 1-37 (one .md per cycle, per §4 template)

**Deliverables (v1.1 §12 context protections — MANDATORY):**
- `scripts/raid/startup-verifier.sh` — 5-step session startup routine (P2)
- `scripts/raid/in-progress-state-writer.py` — IN_PROGRESS state file writer/reader (P3)
- `scripts/raid/compaction-detector.py` — compaction event detection heuristic (P5)
- `scripts/raid/post-commit-verifier-prompt.md` — Auditor post-commit verifier prompt (P9)
- `scripts/raid/health-dashboard.py` — per-cycle health gauge from AUDIT_LOG (P10)
- `scripts/raid/files-from-cycle.sh` — cross-cycle file lookup helper (P7)
- `docs/raid/IN_PROGRESS/` directory (empty + README schema docs) (P3)
- `docs/raid/IN_PROGRESS/_archive/` directory (empty, archived completed-cycle states) (P3)
- `docs/raid/.session-cycle-lock` (sentinel file for P1 enforcement)
- `docs/raid/cycle_briefs/TEMPLATE.md` — canonical brief template per §4 (P6 structure)

**Deliverables (v1.3 §14 quota-aware execution — MANDATORY for subscription users):**
- `contracts/raid/quota-profile.yaml` (Q3) — current profile: `max-20x`
- `scripts/raid/quota-check.sh` (Q4) — pre-cycle quota check + RUNNABLE/RISKY/WAIT decision
- `scripts/raid/sub-agent-spawn.py` (Q2) — enforces model tiering per role (Opus/Sonnet/Haiku)
- `scripts/raid/quota-summary.py` (Q7) — quota dashboard
- `scripts/raid/session-counter.py` (Q8) — 50-session/month tracking
- `docs/raid/QUOTA_LOG.jsonl` (Q7) — supersedes COST_LOG.jsonl for subscription users
- `docs/raid/RESET_SCHEDULE.md` (Q5-Q6) — known reset windows documentation

**Exit:**
- RAID infra functional; smoke test on a no-op cycle proves orchestrator works
- Smoke test exercises all 10 §12 protections: fresh session, startup routine, IN_PROGRESS state, sub-agent return budget, compaction simulation, brief structure validation, cross-cycle reference, token budget, post-commit verification, health dashboard
- All 37 pre-written cycle briefs follow §4 template + each ≤ 4000 tokens (P6)

---

### Cycles 1-7 — L1 DB Physical + Meta Registry

| # | Title | DPS parallel | Depends on | Brief location |
|---|---|---|---|---|
| 1 | L1.E Meta HA Infrastructure | 4 (primary, sync, async, Patroni) | C0 | `cycle_briefs/01_l1e_meta_ha.md` |
| 2 | L1.A-1 Routing + Lifecycle tables + L1.B Meta library | 3 (tables, library Go, library Rust) | C1 | `cycle_briefs/02_l1a1_l1b_routing_meta_lib.md` |
| 3 | L1.A-2 PII + Identity + Consent tables | 2 (pii crypto-shred, consent ledger) | C2 | `cycle_briefs/03_l1a2_pii_identity.md` |
| 4 | L1.A-3 Audit Infrastructure (5 tables) | 3 (write/read audit, admin audit, svc-to-svc audit, prompt audit) | C2 | `cycle_briefs/04_l1a3_audit.md` |
| 5 | L1.C Provisioner + L1.G Pgbouncer + L1.F Cache | 3 (provisioner, pgbouncer, cache) | C2 | `cycle_briefs/05_l1c_g_f_provisioner_pgb_cache.md` |
| 6 | L1.D Migration Orchestrator + L1.I Per-DB Metrics | 2 (orchestrator, metrics) | C5 | `cycle_briefs/06_l1d_i_migration_metrics.md` |
| 7 | L1.A-4 Billing/SRE tables + L1.H Backup + L1.L Capacity + L1.J Degraded + L1.K 15 lints | 5 (billing+sre, backup, capacity, degraded, lints) | C2-C6 | `cycle_briefs/07_l1a4_h_l_j_k_remainder.md` |

**L1 total: 7 cycles.**

---

### Cycles 8-11 — L2 Event Sourcing + Outbox + Publisher

| # | Title | DPS parallel | Depends on | Brief location |
|---|---|---|---|---|
| 8 | L2.F + L2.G + L2.H + L2.I Schema Infra (registry, eventgen, upcasters, validation) | 4 | C0 (no kernel deps yet) | `cycle_briefs/08_l2_schema_infra.md` |
| 9 | L2.A + L2.B + L2.E Per-reality tables (events, event_audit, snapshots) | 3 | C8, C5 (per-reality DB exists) | `cycle_briefs/09_l2_per_reality_tables.md` |
| 10 | L2.C + L2.D + L2.L Outbox + Publisher + xreality | 3 | C9 | `cycle_briefs/10_l2_outbox_publisher_xreality.md` |
| 11 | L2.J + L2.K Archive worker + Retention worker | 2 | C10 | `cycle_briefs/11_l2_archive_retention.md` |

**L2 total: 4 cycles.**

---

### Cycles 12-16 — L3 Snapshot + Projection Runtime

| # | Title | DPS parallel | Depends on | Brief location |
|---|---|---|---|---|
| 12 | L3.B + L3.C Projection trait + Snapshot read runtime | 2 | C8 (registry exists) | `cycle_briefs/12_l3_projection_snapshot_runtime.md` |
| 13 | L3.A + L3.K Projection tables (10) + Verification metadata | 2 | C12, C9 | `cycle_briefs/13_l3_projection_tables.md` |
| 14 | L3.D + L3.G + L3.H Rebuild (parallel + freeze + catastrophic) | 3 | C13 | `cycle_briefs/14_l3_rebuild.md` |
| 15 | L3.E + L3.F + L3.J Integrity checker (daily + monthly + metrics) | 3 | C14 | `cycle_briefs/15_l3_integrity.md` |
| 16 | L3.I pgvector + Embedding queue | 1 | C13, C5 (provisioner installs ext) | `cycle_briefs/16_l3_pgvector.md` |

**L3 total: 5 cycles.**

---

### Cycles 17-22 — L4 SDK + Kernel API + Macros

| # | Title | DPS parallel | Depends on | Brief location |
|---|---|---|---|---|
| 17 | L4.A + L4.B DP-kernel core + Macros | 2 (kernel, macros) | C0 | `cycle_briefs/17_l4_dpkernel_macros.md` |
| 18 | L4.F + L4.G + L4.N Resilience + Lifecycle + Dependencies | 3 | C17 | `cycle_briefs/18_l4_resilience_lifecycle_deps.md` |
| 19 | L4.H + L4.I + L4.J Observability + Capacity + Supply Chain admission | 3 | C18 | `cycle_briefs/19_l4_obs_cap_supplychain.md` |
| 20 | L4.C + L4.E + L4.K Rust meta client + Entity status + Turn/errors | 3 | C18, C2 (meta lib Go exists) | `cycle_briefs/20_l4_meta_rs_entity_turn.md` |
| 21 | L4.D + L4.L Prompt skeleton + WS skeleton | 2 | C17 | `cycle_briefs/21_l4_prompt_ws_skeletons.md` |
| 22 | L4.M + L4.O + L4.P + L4.Q Service ACL + Chaos + Alerts + PII | 4 | C18, C4 (audit tables) | `cycle_briefs/22_l4_acl_chaos_alerts_pii.md` |

**L4 total: 6 cycles.**

---

### Cycles 23-27 — L5 Inbound Canon Ingestion

| # | Title | DPS parallel | Depends on | Brief location |
|---|---|---|---|---|
| 23 | L5.A + L5.D Canon contracts + Per-reality canon_projection | 2 | C13 (projections), C9 (per-reality DB) | `cycle_briefs/23_l5_contracts_projection.md` |
| 24 | L5.B + L5.C meta-worker canon consumer + user-erased consumer | 2 | C10 (xreality infra), C23 | `cycle_briefs/24_l5_metaworker_consumers.md` |
| 25 | L5.E + L5.F Canon cache + RPC contract | 2 | C23, C22 (ACL matrix exists) | `cycle_briefs/25_l5_cache_rpc.md` |
| 26 | L5.G Reality seeder | 1 | C25, C5 (provisioner) | `cycle_briefs/26_l5_seeder.md` |
| 27 | L5.H + L5.I + L5.J Force-propagate + L1 conflict + History | 3 | C24, C26 | `cycle_briefs/27_l5_advanced_flows.md` |

**L5 total: 5 cycles.**

---

### Cycles 28-31 — L6 WS + Obs/Cap + LLM Pre-spec

| # | Title | DPS parallel | Depends on | Brief location |
|---|---|---|---|---|
| 28 | L6.A + L6.B + L6.E WS server + Ticket + Metrics | 3 | C21 (WS types) | `cycle_briefs/28_l6_ws_server.md` |
| 29 | L6.C + L6.D WS authz + Force disconnect | 2 | C28, C2 (meta authz) | `cycle_briefs/29_l6_ws_security.md` |
| 30 | L6.F + L6.G Admission runtimes (obs + capacity) | 2 | C19 | `cycle_briefs/30_l6_admission_runtimes.md` |
| 31 | L6.H + L6.I + L6.J + L6.K + L6.L Prompt composer + Wrap + Routing + Templates + Stubs | 5 | C21 | `cycle_briefs/31_l6_prompt_stack.md` |

**L6 total: 4 cycles.**

---

### Cycles 32-38 — L7 Operations + Logging + Monitoring

| # | Title | DPS parallel | Depends on | Brief location |
|---|---|---|---|---|
| 32 | L7.E + L7.G Logging libs + Tracing libs | 2 (4 languages each) | C0 | `cycle_briefs/32_l7_logging_tracing_libs.md` |
| 33 | L7.H + L7.F Prometheus/Grafana/Thanos + Loki/Vector | 2 | C32 | `cycle_briefs/33_l7_observability_infra.md` |
| 34 | L7.I + L7.J SLO infra + Alertmanager | 2 | C33 | `cycle_briefs/34_l7_slo_alerts.md` |
| 35 | L7.B + L7.C Runbook library (27 runbooks) + On-call rotation | 2 | C34 | `cycle_briefs/35_l7_runbooks_oncall.md` |
| 36 | L7.A admin-cli framework + ~30 commands | ~6 (by command domain) | C35, all prior L1-L6 (commands touch every domain) | `cycle_briefs/36_l7_admin_cli.md` |
| 37 | L7.D + L7.L Incident infra + Status page | 2 | C35, C34 | `cycle_briefs/37_l7_incident_statuspage.md` |
| 38 | L7.K Deploy pipeline + Canary controller | 1 | C34 (SLO), C7 (capacity), all priors | `cycle_briefs/38_l7_deploy_pipeline.md` |

**L7 total: 7 cycles.**

---

## §3. Dependency graph summary

```
C0 (RAID infra)
 ├─→ C1 (L1.E meta HA)
 │    └─→ C2 (L1.A1 + L1.B meta lib)
 │         ├─→ C3 (L1.A2 PII)
 │         ├─→ C4 (L1.A3 audit)
 │         ├─→ C5 (L1.C provisioner + L1.G pgb + L1.F cache)
 │         │    └─→ C6 (L1.D migration + L1.I metrics)
 │         │         └─→ C7 (L1.A4 + L1.H + L1.L + L1.J + L1.K)
 │         │
 │         ├─→ C8 (L2 schema infra)
 │         │    └─→ C9 (L2 per-reality tables) ← also needs C5
 │         │         └─→ C10 (L2 outbox + publisher + xreality)
 │         │              └─→ C11 (L2 archive + retention)
 │         │
 │         ├─→ C12 (L3 traits) ← needs C8
 │         │    └─→ C13 (L3 projection tables) ← needs C9
 │         │         ├─→ C14 (L3 rebuild)
 │         │         │    └─→ C15 (L3 integrity)
 │         │         └─→ C16 (L3 pgvector) ← also needs C5
 │         │
 │         └─→ C17 (L4.A + L4.B kernel)
 │              ├─→ C18 (L4 resilience+lifecycle+deps)
 │              │    ├─→ C19 (L4 obs+cap+supplychain admission)
 │              │    ├─→ C20 (L4 Rust client ports) ← also needs C2
 │              │    └─→ C22 (L4 ACL+chaos+alerts+pii) ← also needs C4
 │              └─→ C21 (L4 prompt + WS skeletons)
 │
 ├─→ C23 (L5 contracts + canon projection) ← needs C9, C13
 │    └─→ C24 (L5 meta-worker consumers) ← needs C10
 │         └─→ C27 (L5 force-prop + conflict + history)
 │    └─→ C25 (L5 cache + RPC) ← needs C22
 │         └─→ C26 (L5 reality seeder) ← needs C5
 │              └─→ C27 (← also)
 │
 ├─→ C28 (L6 WS server) ← needs C21
 │    └─→ C29 (L6 WS security) ← needs C2
 ├─→ C30 (L6 admission runtimes) ← needs C19
 ├─→ C31 (L6 prompt stack) ← needs C21
 │
 ├─→ C32 (L7 logging+tracing libs)
 │    └─→ C33 (L7 Prom+Grafana+Thanos+Loki)
 │         └─→ C34 (L7 SLO + alerts)
 │              ├─→ C35 (L7 runbooks + on-call)
 │              │    ├─→ C36 (L7 admin-cli) ← needs all priors L1-L6
 │              │    └─→ C37 (L7 incident + status page)
 │              └─→ C38 (L7 deploy pipeline) ← needs C7, all priors
```

**Critical path:** C0 → C1 → C2 → C5 → C9 → C13 → C17 → C18 → C32 → C33 → C34 → C35 → C36 (deepest chain).

**Parallelizable batches** (independent sub-trees):
- After C2: C3, C4 parallel
- After C17: C18, C21 parallel
- After C19: C20, C22, C30 parallel
- After C13: C14, C16 parallel
- After C24: C26 + C25 parallel (then both feed C27)
- After C28: C29, C31, C30 parallel
- After C34: C35, C38 parallel; C36, C37 after C35

---

## §4. Per-cycle brief template (v1.1 — lost-in-middle aware per RAID_WORKFLOW.md §12.6 / P6)

Each `docs/raid/cycle_briefs/<NN>_<short_name>.md` follows this structure. **Token cap:
4000 tokens per brief.** Critical info appears at TOP (TL;DR) AND BOTTOM (REMINDERS) —
the middle holds details, which research shows are less reliably retrieved.

```markdown
# Cycle <N>: <Title>

## 🎯 TL;DR (30 seconds — TOP critical info)
- **Scope:** <one paragraph>
- **Acceptance gate:** `scripts/raid/verify-cycle-<N>.sh` exits 0
- **Top 3 LOCKED decisions consumed:** <Q-ID>, <Q-ID>, <Q-ID>
- **DPS count:** <N>
- **Estimated wall time:** <hours>

## Dependencies (must show DONE in CYCLE_LOG.md)
- Cycles: <list>
- Files expected to exist (grep-able paths): <list>

## Scope (IN)
- <bullet list of artifacts to build>

## Scope (OUT — explicitly)
- <bullet list of what NOT to touch in this cycle>

## Acceptance criteria (CI gates — exit code 0 = pass)
- Tests pass: <list with paths>
- Lints pass: <list>
- Integration smoke: <description>

## DPS parallelism plan
- DPS 1: <slice + worktree files> (return budget: 1500 tokens summary)
- DPS 2: <slice + worktree files>
- ...

## Adversary review focus (cold-start sub-agent — return budget 2000 tokens)
- <what the cold-start adversary should specifically check>
- <known pitfalls / common mistakes for this kind of cycle>

## Scope Guard CLEAR criteria (cold-start sub-agent — return budget 500 tokens)
- All scope items present
- No OUT items touched
- All acceptance criteria met
- Cross-cycle invariants not violated

## Cross-references (for deep-read IF Raid Leader needs to FOCUS mode)
- Layer plan: [L<N>_*.md](../docs/plans/2026-05-29-foundation-mega-task/L<N>_*.md)
- Kernel chunks: <list with §-anchors>
- LOCKED decisions consumed (full list): <all Q-IDs>

## ⚠️ REMINDERS (BOTTOM — re-stated critical info, anti-lost-in-middle)
- 🔴 **Top LOCKED 1:** <Q-ID> → <one-line resolution>
- 🔴 **Top LOCKED 2:** <Q-ID> → <one-line resolution>
- 🔴 **Top LOCKED 3:** <Q-ID> → <one-line resolution>
- 🔴 **Acceptance MUST include:** <key gate that's easiest to forget>
- 🔴 **Do NOT touch:** <out-of-scope items most likely to drift>
- 🔴 **Fresh session reminder:** this is a new `/raid <N>` invocation; no carry-over from prior cycles. Read CYCLE_LOG.md + this brief + LOCKED file ONLY.
```

**Validation (CI lint):**
- `scripts/raid/brief-structure-validator.sh` checks every brief has all 9 sections
  (TL;DR, Dependencies, Scope IN, Scope OUT, Acceptance, DPS plan, Adversary, Scope
  Guard, Cross-references, REMINDERS) + REMINDERS has ≥ 3 🔴 lines + brief ≤ 4000 tokens
- Failing briefs block Cycle 0 exit and any RAID cycle invocation

---

## §5. RAID prompt template v1.1 (paste-and-go for each cycle)

```
/raid

Execute Cycle <N> of the foundation mega-task.

⚠️ FRESH SESSION REMINDER (RAID_WORKFLOW.md §12.1 / P1):
This is a new session. You have NO memory of prior cycles. All state lives
in files — read them.

STARTUP ROUTINE (mandatory 5 steps — RAID_WORKFLOW.md §12.2 / P2):
1. Read docs/raid/CYCLE_LOG.md tail (last 5 entries) — know what's DONE
2. Read docs/raid/cycle_briefs/<NN>_<short_name>.md — THIS cycle's brief
3. Read docs/raid/IN_PROGRESS/cycle-<N>-state.md IF EXISTS (P3 resume)
4. Run scripts/raid/startup-verifier.sh <N> — verify git + deps + clean
5. Read OPEN_QUESTIONS_LOCKED.md sections relevant to this cycle

ONLY AFTER STARTUP ROUTINE: begin Phase 1 (CLARIFY).

Read docs/plans/2026-05-29-foundation-mega-task/L<X>_*.md (the parent layer
plan) and the kernel chunks the brief cites — these give you the FULL spec.

Execute the full 12-phase RAID workflow (see docs/raid/RAID_WORKFLOW.md)
as ONE task:
  CLARIFY → DESIGN → REVIEW → PLAN → BUILD → VERIFY → REVIEW → QC →
  POST-REVIEW → SESSION → COMMIT → RETRO

RAID-specific rules:
- All-or-nothing CI gates (scripts/raid/verify-cycle-<N>.sh exit 0 = pass)
- Retry 3x on VERIFY fail; after 3 fails → write
  docs/raid/ESCALATIONS.md row + ABORT cycle
- POST-REVIEW is AUTO (no human stop) — cold-start sub-agent comparison
  against cycle brief
- Spawn DPS sub-agents per the DPS parallelism plan in the brief
  (worktrees, run_in_background:true, isolation:worktree)
- Sub-agents return ≤1500-2000 tokens condensed summaries (P4) — NOT full
  diffs/logs. Raid Leader queries git/files directly if more needed.
- Write docs/raid/IN_PROGRESS/cycle-<N>-state.md at every phase transition
  (P3) — enables crash recovery
- Cross-cycle reference: read CYCLE_LOG.md row only (~200 tokens), NOT
  prior cycle briefs (P7)
- All decisions LOCKED in OPEN_QUESTIONS_LOCKED.md — do NOT re-litigate

Hard rules:
- This task is Cycle <N> ONLY — do not start any other cycle (P1)
- Every Depends-on cycle in the brief must already show "DONE" in
  docs/raid/CYCLE_LOG.md; if not, STOP and report
- VERIFY must pass with fresh evidence (no "should work")
- At COMMIT: append cycle to CYCLE_LOG.md as DONE in same commit as code
- AFTER COMMIT: spawn post-commit Auditor for verification (P9) — if
  DRIFT_DETECTED → git reset --soft HEAD~1 + ESCALATIONS row
- STOP and write ESCALATIONS.md row if: VERIFY 3-fails, Scope Guard
  BLOCKED, post-commit verifier DRIFT_DETECTED, design-gap surfaced not
  in LOCKED decisions, compaction recovery state inconsistent (P5)
- Hard token ceiling: 150K Raid Leader main context per cycle (P8). If
  cumulative exceeds → halt + ESCALATIONS.

On compaction event (if mid-cycle):
- Pause new tool calls
- Re-read IN_PROGRESS state file (P3)
- Re-read cycle brief
- Verify git log + AUDIT_LOG.jsonl + DPS worktree states match IN_PROGRESS
- If CONSISTENT → continue from documented phase
- If INCONSISTENT → halt + ESCALATIONS (corrupted recovery worse than halt)
```

---

## §6. Per-cycle commit message format

```
feat(raid-cycle-<N>): <one-line summary>

Cycle: <N>
Brief: docs/raid/cycle_briefs/<NN>_<short_name>.md
Scope: L<X>.<Y> sub-components — <names>
DPS sub-agents: <count> in worktrees: <names>
Adversary findings: <count> (all resolved | N escalated)
Scope Guard: CLEAR | BLOCKED
verify-cycle-<N>.sh: exit 0
LOCKED decisions consumed: <Q-IDs>

<short description of what was built + any noteworthy build-time decisions>

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
```

---

## §7. Cycle status board

After C0 ships, all subsequent cycles update `docs/raid/CYCLE_LOG.md` per-commit.

| # | Title | Status | Started | Completed | DPS count | Adversary findings |
|---:|---|---|---|---|---:|---:|
| 0 | RAID infrastructure | PENDING | — | — | n/a (default workflow) | n/a |
| 1 | L1.E Meta HA | PENDING | — | — | 4 | — |
| 2 | L1.A1 + L1.B meta lib | PENDING | — | — | 3 | — |
| ... | (33 more rows) | ... | ... | ... | ... | ... |

(Generated row-by-row by RAID orchestrator at cycle start.)

---

## §8. Acceptance for entire foundation mega-task

After Cycle 38 commits:

1. All 38 cycles show DONE in CYCLE_LOG.md
2. Zero rows in ESCALATIONS.md (or human-resolved if any)
3. End-to-end smoke: provision reality → seed canon → spawn aggregate → emit event → snapshot → restart → reload → re-derive projection → cross-check
4. All 19 invariants (I1-I19 amended for I3 Rust addition) enforced by CI lints
5. All 7 SLIs computed; SLO targets defined per tier
6. All 27 runbooks present + verified
7. Branch `mmo-rpg/foundation-mega-task` opened as PR to `main` with PR description listing all 38 cycles + acceptance evidence

**Then:** foundation is ready for the next sub-program (actor substrate EF/RES/PL/TDIL/AIT/PROG) to begin per V1+30d roadmap.
