# CLARIFY Master — Foundation Mega-Task

> **Phase:** CLARIFY (in progress)
> **Created:** 2026-05-29
> **Workflow target:** RAID (new 100%-autonomous workflow — parallel to AMAW v3.0)

---

## §1. Scope — LOCKED 2026-05-29

### IN scope

| ID | Layer | One-line |
|---|---|---|
| L1 | DB physical + Meta registry | per-reality DB provisioner, shared `loreweave_meta` schema, HA |
| L2 | Event sourcing + Outbox + Publisher | events table, outbox pattern, publisher service → Redis Streams |
| L3 | Snapshot + Projection runtime | aggregate snapshot mechanism, projection materialized views |
| L4 | SDK / Kernel API | `contracts/*` (Rust + Go), `#[derive(Aggregate)]` proc-macro |
| L5 | Inbound canon ingestion | push (xreality.canon.*), pull (`[WORLD_CANON]`), reality seeding |
| L6 | WS security + Obs/Cap + LLM safety pre-spec | WS ticket handshake, obs inventory, capacity budgets, prompt skeleton |

### OUT of scope (pushed to subsequent sub-programs)

| Pushed to | Reason |
|---|---|
| Actor substrate (EF_001, RES_001, PL_001/005/006, TDIL_001, AIT_001, PROG_001) | Each is feature-level XL; treating as foundation underestimates each by ~10x |
| Geography + Travel features (V1+30d Plan Cycles 1-7) | Feature layer, depends on foundation |
| LLM logic (intent classifier, world oracle, injection defense) | Feature-level, foundation only ships skeleton (L6) |
| Frontend (`frontend-game/`) | Out of foundation scope |
| Cross-instance MMO travel (MV5) | Deferred per current decisions |

### Open questions deferred to feature programs (not foundation blockers)

| ID | Why deferred |
|---|---|
| Q-A1 — NPC memory at scale | Needs measured retrieval quality, V1 prototype |
| Q-A4 — Retrieval quality evaluation | External, post-foundation |
| Q-D1 — LLM cost/user-hour | Needs V1 prototype to measure |
| Q-E3 — IP ownership legal | External legal input required |
| Q-RISK — R1-R13 mitigation deep review | Already MITIGATED status; deep review can happen during BUILD per cycle |

---

## §2. Tech stack — LOCKED 2026-05-29 (I3 invariant amendment)

```
PRIOR I3 (foundation/02_invariants.md):
  Go for domain services · Python for AI/LLM services · TypeScript for gateway/BFF

AMENDED I3 (this CLARIFY produces a foundation/02_invariants.md PR):
  Rust   — kernel + kernel-derived services that #[derive(Aggregate)]
           (world-service, travel-service, roleplay-service, future actor-substrate
           services)
  Go     — meta-registry library + meta-registry-adjacent services
           (publisher, meta-worker, event-handler, migration-orchestrator, admin-cli)
           + 12 existing LoreWeave novel-platform services (unchanged)
  Python — LLM-heavy services (chat-service, knowledge-service — existing)
  TS     — api-gateway-bff (gateway invariant I1)
```

**Rationale:**
- D-C0-1 already chose Rust for `world-service` + `travel-service` because the DP-kernel
  uses `#[derive(Aggregate)]` proc-macro. The scaffolds in repo (`services/world-service`,
  `services/travel-service`) are already Rust + empty-compiling per V1_30D_CYCLE_LOG.md.
- Go remains correct for meta-registry adjacent services (publisher, meta-worker, etc.)
  because those services consume primitives that don't need the macro.
- Python remains correct for LLM-orchestration-heavy services because LiteLLM ecosystem.

**CI lint update required (in foundation build):** `scripts/language-rule-lint.sh`
must be re-derived to allow `services/world-service`, `services/travel-service`,
`services/roleplay-service` to be Rust.

---

## §3. Acceptance criteria philosophy — LOCKED 2026-05-29

**Principle:** RAID has no human-in-the-loop review during a cycle. Therefore acceptance
must be **purely automatable** — CI exit code = 0 means pass, no exceptions.

### Per-cycle VERIFY rules

```
1. Every cycle MUST ship a file: scripts/raid/verify-cycle-<N>.sh
2. That script runs: cargo test + golangci-lint + replay-determinism gate
   + capacity-budget-lint + observability-inventory-lint + cycle-specific integration
3. Exit 0 = PASS. Anything else = FAIL.
4. Gate set per cycle is declared in the cycle brief (CYCLE_DECOMPOSITION.md).
```

### On VERIFY fail — retry policy

```
1. Agent reads test output, attempts a real fix (no paper-over, no skip-test).
2. Max 3 retry attempts per cycle.
3. After 3 failures: write a row to docs/raid/ESCALATIONS.md with:
   - Cycle N
   - Failure mode (test name + last 10 lines of error output)
   - 3 fix attempts + why each failed
   - Suggested escalation type (kernel-design gap / external dep / unclear spec)
4. Then ABORT the cycle. Workflow halts. Human picks up from escalation row.
```

### Phase 7 REVIEW rules (no human)

```
1. Adversary sub-agent (cold-start, reuses AMAW v3.0 pattern):
   - Reads cycle brief + diff + verify evidence
   - Returns FINDINGS list (severity = blocker / major / minor / note)
2. Scope Guard sub-agent (cold-start):
   - Reads cycle brief acceptance criteria + diff
   - Returns CLEAR or BLOCKED with reason
3. If Adversary blockers OR Scope Guard BLOCKED → retry cycle with fix (counts toward 3x).
4. If CLEAR → proceed to COMMIT.
```

### Phase 9 POST-REVIEW rules (no human)

```
Replace the AMAW human checkpoint with auto-comparison:
1. Sub-agent (cold-start) reads cycle brief, full diff, verify-cycle-<N>.sh output.
2. Compares: scope drift? acceptance unmet? cross-cycle invariant broken?
3. Emits CLEAR (proceed to commit) or BLOCKED with reason (escalation row + abort).
```

---

## §4. RAID role contract (preview — full spec in RAID_WORKFLOW.md)

| Role | Cold-start? | Owns |
|---|---|---|
| Raid Leader | NO (main session) | Orchestration, dispatch DPS, gather output |
| Tank | YES per cycle | Architecture guard, kernel invariant defense, integration rebase |
| DPS (1..N parallel) | YES per worktree | Build one slice of cycle in own worktree |
| Healer | YES per cycle | Test repair, regression chaser, after Tank rebase |
| Adversary | YES per cycle | Cold-start code review (carry-over from AMAW v3.0) |
| Scope Guard | YES per cycle | Brief-vs-diff comparison (carry-over from AMAW v3.0) |

---

## §5. Audit trail — LOCKED 2026-05-29

Every cycle appends to:
- `docs/raid/AUDIT_LOG.jsonl` — machine-readable per-phase events (mirrors AMAW)
- `docs/raid/CYCLE_LOG.md` — human-readable summary per cycle (mirrors V1_30D_CYCLE_LOG.md)
- `docs/raid/ESCALATIONS.md` — only when a cycle aborts after 3 retries

Per-cycle commit message format:
```
feat(raid-cycle-<N>): <one-line summary>

Cycle: <N>
Brief: docs/plans/2026-05-29-foundation-mega-task/CYCLE_DECOMPOSITION.md §<N>
DPS sub-agents: <count> in worktrees
Adversary findings: <count> (all resolved / N still open if escalated)
Scope Guard: CLEAR
verify-cycle-<N>.sh: exit 0

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
```

---

## §6. Status

```
[x] Scope locked
[x] Tech stack locked (I3 amendment pending)
[x] Acceptance philosophy locked
[ ] L1 deep-dive (12 sub-components enumerated, going deeper)
[ ] L2 deep-dive
[ ] L3 deep-dive
[ ] L4 deep-dive
[ ] L5 deep-dive
[ ] L6 deep-dive
[ ] RAID workflow spec
[ ] Cycle decomposition
[ ] I3 invariant amendment PR (final artifact)
```
