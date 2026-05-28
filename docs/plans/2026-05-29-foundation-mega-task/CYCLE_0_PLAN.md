# Cycle 0 Build Plan — Foundation RAID Bootstrap

> **Phase:** DESIGN + PLAN (combined per task XL classification)
> **Status:** REVISED R3 — addresses Adversary R1+R2 findings (see §8)
> **Created:** 2026-05-29 fresh post-PRE_FLIGHT session
> **Revisions:** R2 (post-R1: 3 BLOCK fixes) · R3 (post-R2: 2 BLOCK + 1 WARN fixes)
> **Workflow:** Default + AMAW v3.0 (bootstrap; cannot use RAID itself)
> **Size:** XL — **45 canonical deliverables** (28 new + 9 pre-staged + 8 dirs), ~5000-6000 LOC, smoke test required
>
> **R3 changes summary:**
> - Added `recovery-protocol-runner.sh` (P5 8-step executor) + `recover-from-crash.sh` (operator toolkit)
> - Lock state machine canonical R3: atomic `00X → READY_FOR_<N>` (no UNLOCKED window) + orchestrator refusal rule + crash-recovery table for 8 states
> - §4 P1 expanded: 1A normal flow + 1B 5 paired-state probes + 1C atomicity check
> - §4 P5 expanded: TWO scenarios (CONSISTENT 5A + INCONSISTENT/HALT 5B) = 9 assertions
> - CYCLE_DECOMPOSITION §Cycle 0 fully rewritten v1.4 with `last_synced_with_RAID_WORKFLOW_version` header
> - RAID_WORKFLOW §13.9 COST_LOG.jsonl marked SUPERSEDED; per-cycle Phase 9 vs C0→C1 boundary disambiguated

---

## §1. What Cycle 0 ships

The RAID v1.3 orchestrator + infrastructure that lets cycles 1-37 run autonomously
on subscription Max 20x quota. After C0 smoke green, the auto-dispatcher pauses 60s
then fires `/raid 1`.

**Source of truth:** RAID_WORKFLOW.md §13.9 (v1.2 list) + §14.10 (v1.3 additions),
totaling **43 deliverables** (≈26 new files + 9 pre-staged + 8 dirs).

---

## §2. Deliverable inventory + status

### v1.0 core (5)

| # | Path | Status | Owner batch |
|---|---|---|---|
| 1 | `scripts/raid/orchestrator.py` | TODO | B1 |
| 2 | `scripts/raid/verify-cycle-template.sh` | TODO | B4 |
| 3 | `scripts/raid/escalation-writer.py` | TODO | B1 |
| 4 | `docs/raid/{AUDIT_LOG.jsonl, CYCLE_LOG.md, ESCALATIONS.md, cycle_briefs/}` | DONE (pre-stage) | — |
| 5 | `docs/raid/RAID_WORKFLOW.md` (copy) | TODO | B6 |

### v1.1 §12 context protections (11 — added R3 per Adversary R2 BLOCK 1)

| # | Path | Status | Owner batch |
|---|---|---|---|
| 6 | `scripts/raid/startup-verifier.sh` (P2 5-step routine) | TODO | B1 |
| 7 | `scripts/raid/in-progress-state-writer.py` (P3) | TODO | B1 |
| 8 | `scripts/raid/compaction-detector.py` (P5 detection only) | TODO | B1 |
| 8b | `scripts/raid/recovery-protocol-runner.sh` (P5 8-step recovery executor) | **TODO (added R3)** | B1 |
| 8c | `scripts/raid/recover-from-crash.sh` (operator-only crash recovery toolkit) | **TODO (added R3)** | B1 |
| 9 | `scripts/raid/post-commit-verifier-prompt.md` (P9) | TODO | B4 |
| 10 | `scripts/raid/health-dashboard.py` (P10) | TODO | B4 |
| 11 | `scripts/raid/files-from-cycle.sh` (P7) | TODO | B1 |
| 12 | `docs/raid/IN_PROGRESS/ + _archive/` | DONE (pre-stage) | — |
| 13 | `docs/raid/.session-cycle-lock` | DONE (pre-stage) | — |
| 14 | `docs/raid/cycle_briefs/TEMPLATE.md` (P6) | TODO | B5 |

### v1.2 §13 production-readiness (21 — count incl. dirs/configs)

| # | Path | Status | Owner batch |
|---|---|---|---|
| 15 | `scripts/raid/worktrees-create.sh` (B1) | TODO | B2 |
| 16 | `scripts/raid/worktrees-cleanup.sh` (B1) | TODO | B2 |
| 17 | `scripts/raid/worktrees-check.sh` (B1) | TODO | B2 |
| 18 | `scripts/raid/test-infra-up-dps.sh` (B2) | TODO | B2 |
| 19 | `scripts/raid/test-infra-down-dps.sh` (B2) | TODO | B2 |
| 20 | `scripts/raid/test-infra-template.docker-compose.yml` (B2) | TODO | B2 |
| 21 | `scripts/raid/cost-tracker.py` (B3 → dual-use Q9) | TODO | B3 |
| 22 | `scripts/raid/cost-summary.py` (B3 → dual-use Q9) | TODO | B3 |
| 23 | `scripts/raid/brief-generator.py` (B4) | TODO | B5 |
| 24 | `scripts/raid/brief-structure-validator.sh` (B4) | TODO | B5 |
| 25 | `scripts/raid/regenerate-briefs.sh` (B4) | TODO | B5 |
| 26 | `scripts/raid/prod-isolation-lint.sh` (B5) | TODO | B2 |
| 27 | `.gitleaks.toml` (B6) | TODO | B2 |
| 28 | `scripts/raid/secret-scan-dps.sh` (B6) | TODO | B2 |
| 29 | `scripts/raid/secret-scan-cycle.sh` (B6) | TODO | B2 |
| 30 | `scripts/raid/secret-scan-final.sh` (B6) | TODO | B2 |
| 31 | `scripts/raid/run-smoke-test.sh` (AUTO) | TODO | B6 |
| 32 | `scripts/raid/auto-dispatcher.py` (AUTO) | TODO | B6 |
| 33 | `docs/raid/cycle_briefs/00X_helloworld_smoke.md` (AUTO) | TODO | B5 |
| 34 | `infra/foundation-dev/docker-compose.yml` (B5) | TODO | B6 |
| 35 | `infra/foundation-staging/terraform/` skeleton (B5) | TODO | B6 |
| 36 | `../foundation-worktrees/{,_archive/,_quarantine/}` dirs (B1, B6) | TODO | B2 |

### v1.3 §14 quota-aware (7)

| # | Path | Status | Owner batch |
|---|---|---|---|
| 37 | `contracts/raid/quota-profile.yaml` (Q3) | TODO | B3 |
| 38 | `scripts/raid/quota-check.sh` (Q4) | TODO | B3 |
| 39 | `scripts/raid/sub-agent-spawn.py` (Q2) | TODO | B3 |
| 40 | `scripts/raid/quota-summary.py` (Q7) | TODO | B3 |
| 41 | `scripts/raid/session-counter.py` (Q8) | TODO | B3 |
| 42 | `docs/raid/QUOTA_LOG.jsonl` (Q7) | DONE (pre-stage) | — |
| 43 | `docs/raid/RESET_SCHEDULE.md` (Q5-Q6) | DONE (pre-stage) | — |

**Newly written this cycle: 29 files + 1 directory tree (R3 added recovery-protocol-runner.sh + recover-from-crash.sh + force-lock-state.sh test helper per R3-WARN-1). Pre-staged: 9 items (file + dirs). Canonical total: 46.**

---

## §3. Build batches (sequential — each commits via per-batch checkpoint to IN_PROGRESS file)

### Batch B1 — Core foundation scripts (7 files) — added recovery-protocol-runner.sh R3
**Purpose:** Orchestration + state machine. Cycles 1-37 depend on these.

- `scripts/raid/orchestrator.py` — main `/raid <N>` dispatcher: routes prompts, spawns sub-agents per §14.2 tier table, integrates startup-verifier + IN_PROGRESS writer + escalation-writer + cost-tracker. **Enforces lock acceptance contract R3:** refuses `/raid <N>` unless `(lock == READY_FOR_<N>) AND (READY_FOR_CYCLE_<N>.signal exists with valid YAML)`. Crash-recovery rules in script doc.
- `scripts/raid/escalation-writer.py` — append rows to ESCALATIONS.md per §5 / §14.5 schema (supports quota_block, error, p5_recovery_inconsistent types)
- `scripts/raid/in-progress-state-writer.py` — YAML+markdown frontmatter writer per §12.3
- `scripts/raid/startup-verifier.sh` — P2 5-step routine
- `scripts/raid/files-from-cycle.sh` — P7 cross-cycle file lookup helper (git log + commit-message parsing)
- `scripts/raid/compaction-detector.py` — P5 detection heuristic (token count delta + tool-result ID disappearance); supports `--test-mode --inject-event` for smoke
- `scripts/raid/recovery-protocol-runner.sh` (**NEW R3 per Adversary R2 BLOCK 1**) — implements §12.5 P5 8-step recovery PROTOCOL executor: re-read IN_PROGRESS, re-read brief, re-read OPEN_QUESTIONS_LOCKED for cycle, cross-ref `git log --since=<phase_started_at>`, cross-ref AUDIT_LOG.jsonl tail, verify DPS worktree states match IN_PROGRESS dps_status. Returns CONSISTENT (continue from phase) OR INCONSISTENT (writes ESCALATIONS row with `type=p5_recovery_inconsistent` + halts). This is the **safety-critical script** — if Raid Leader compaction state diverges, this halts before fabricated commits land.

- `scripts/raid/recover-from-crash.sh` (**NEW R3** — operator-only crash recovery toolkit per crash-recovery rules in B6 below) — sub-commands: `--reset-lock` (forces lock=UNLOCKED with audit log entry); `--rewrite-signal <N>` (regenerates signal file from CYCLE_LOG state); `--inspect` (prints lock + signal file status + last 10 AUDIT_LOG entries). Refuses to run while a `/raid <N>` session is active (checks pid file). Required by lock state-machine R3 to handle 4 distinct crash scenarios enumerated in §3 B6 crash-recovery table.

**Risk:** orchestrator.py glue logic + recovery-protocol-runner correctness. If recovery falsely returns CONSISTENT, fabricated commits can land. Mitigation: smoke test exercises BOTH branches (see §4 P5).

### Batch B2 — Production-readiness scripts (10 files + 1 dir tree)
**Purpose:** B1/B2/B5/B6 BLOCKERs.

- `scripts/raid/worktrees-{create,cleanup,check}.sh` (B1 lifecycle)
- `scripts/raid/test-infra-{up,down}-dps.sh` (B2 isolation; uses port allocator per §13.2 formula)
- `scripts/raid/test-infra-template.docker-compose.yml` (B2 template with PG+Redis+MinIO)
- `scripts/raid/prod-isolation-lint.sh` (B5 grep guard)
- `.gitleaks.toml` (B6 config)
- `scripts/raid/secret-scan-{dps,cycle,final}.sh` (B6)
- Create `../foundation-worktrees/{,_archive/,_quarantine/}` dirs (`.gitkeep` for empty)

**Risk:** secret-scan needs gitleaks binary; orchestrator must check at startup. test-infra port collision if cycle_num exceeds bounds.

### Batch B3 — Quota-aware scripts (6 files)
**Purpose:** Q1-Q9 from §14.

- `contracts/raid/quota-profile.yaml` — `max-20x` profile per §14.3
- `scripts/raid/quota-check.sh` (Q4) — pre-cycle check returns PROCEED/RISKY/WAIT
- `scripts/raid/sub-agent-spawn.py` (Q2) — wrapper enforcing model tier per role
- `scripts/raid/quota-summary.py` (Q7) — reads QUOTA_LOG.jsonl, emits dashboard
- `scripts/raid/session-counter.py` (Q8) — 50-session/month tracker
- `scripts/raid/cost-tracker.py` + `cost-summary.py` (B3 → Q9 dual-use) — token + $ accounting

**Risk:** quota estimation is heuristic (Anthropic doesn't expose exact state). Document the heuristic in script comments + calibrate during smoke.

### Batch B4 — Observability + per-cycle verify template (3 files)
**Purpose:** P9, P10, verify-cycle-template.

- `scripts/raid/health-dashboard.py` (P10) — reads AUDIT_LOG, emits per-cycle health summary
- `scripts/raid/post-commit-verifier-prompt.md` (P9) — Auditor verifier prompt template
- `scripts/raid/verify-cycle-template.sh` — template for per-cycle verify-cycle-<N>.sh

### Batch B5 — Brief tooling + 38 generated briefs (3 scripts + 38 briefs + 1 TEMPLATE)
**Purpose:** B4 brief auto-generation + smoke brief.

- `scripts/raid/brief-generator.py` (B4) — parses CYCLE_DECOMPOSITION §2 + cites layer plans + extracts LOCKED Q-IDs → emits brief per §12.6/P6 template
- `scripts/raid/brief-structure-validator.sh` (B4) — checks all 10 sections + ≤4000 tokens + Q-ID resolution
- `scripts/raid/regenerate-briefs.sh` (B4) — re-runs generator on LOCKED file changes
- `docs/raid/cycle_briefs/TEMPLATE.md` (P6) — canonical template (also used by validator as schema reference)
- `docs/raid/cycle_briefs/00X_helloworld_smoke.md` (AUTO) — manual write (no auto-gen)
- `docs/raid/cycle_briefs/{01..37}_*.md` — auto-generated by running brief-generator.py for each

**Risk highest in B5:** brief-generator must produce VALID briefs that pass the validator. If generator output fails validation, smoke test fails and C0 incomplete. Mitigation: hand-write the smoke brief as a known-good template; auto-gen briefs use a simpler "stub-then-fill" pattern — TL;DR + scope + LOCKED list mandatory; details enumerated from CYCLE_DECOMPOSITION §2 row.

### Batch B6 — Semi-AUTO dispatch + RAID_WORKFLOW copy + infra skeletons (5 items)
**Purpose:** AUTO gate + B5 infra. **REVISED R2 per Adversary BLOCK 3** + user choice (see PRE_FLIGHT D6).

- `scripts/raid/run-smoke-test.sh` (AUTO) — runs 00X_helloworld_smoke through orchestrator end-to-end; exit 0 on success; **on success calls auto-dispatcher; on failure writes ESCALATIONS row + exit non-zero (dispatcher does NOT fire)**

- `scripts/raid/auto-dispatcher.py` (Semi-AUTO) — **REVISED R3 per Adversary R2 BLOCK 2** (resolves self-contradiction + paired-state suppression):
  1. Reads `docs/raid/CYCLE_LOG.md` to find next PENDING cycle whose deps are all DONE (`<N>`)
  2. Prints 60-second countdown to stdout (`[60s] [59s] ...`) with `Ctrl-C to halt` banner BEFORE any state mutation — short sleep increments for fast Ctrl-C
  3. **After countdown without interrupt, performs ONE atomic transition** (no UNLOCKED window):
     - Reads current lock value
     - If lock == `00X`: directly write `READY_FOR_<N>` AND `docs/raid/READY_FOR_CYCLE_<N>.signal` in single file-system order via `python -c "open(lock).write('READY_FOR_<N>'); open(signal).write(yaml)"` (Python's file-write atomicity per platform; explicit `os.fsync` after each)
     - If lock == `UNLOCKED`: REFUSE (means smoke didn't run or crashed before signal-emit step) → exit non-zero with `error: lock=UNLOCKED expected 00X; smoke incomplete?`
     - If lock == `READY_FOR_<M>` (M ≠ N): REFUSE (stale signal from prior run) → exit non-zero with `error: stale READY_FOR_<M> signal; manual unlock required`
     - If lock == `<M>` (cycle in progress): REFUSE → exit non-zero with `error: cycle <M> in progress`
  4. Signal file YAML schema (validated by orchestrator on entry):
     ```yaml
     schema_version: 1
     next_cycle: <N>
     ready_at: <ISO>
     deps_satisfied: [<list of done cycle numbers>]
     smoke_evidence_sha: <commit SHA of C0 commit>
     dispatcher_pid: <pid for crash detection>
     ```
  5. Prints user instruction block:
     ```
     ═══════════════════════════════════════════════════════════
     C0 SMOKE GREEN — READY FOR CYCLE <N>
     ═══════════════════════════════════════════════════════════
     1. Close this Claude Code session (P1 fresh-session invariant)
     2. Open a NEW Claude Code session in the same repo
     3. Run:  /raid <N>
     4. Orchestrator validates lock=READY_FOR_<N> AND signal file exists
        with valid YAML before acquiring lock transition READY_FOR_<N> → <N>
     ═══════════════════════════════════════════════════════════
     ```
  6. Exit 0 (signal file + lock state are the durable handoff)

  - **Idempotent:** re-running with `(lock=READY_FOR_<N>, signal present)` no-ops with informational message; re-running after `(lock=<N>, cycle in progress)` REFUSES.

  - **Lock transition contract R3 (canonical state machine):**
    ```
    State: UNLOCKED
      ↓ (smoke start: run-smoke-test.sh writes "00X")
    State: 00X
      ↓ (smoke success: auto-dispatcher.py atomic-writes "READY_FOR_<N>" + signal file)
    State: READY_FOR_<N>      ← signal file MUST exist + YAML valid
      ↓ (fresh session /raid <N>: orchestrator.py validates BOTH lock + signal, then atomic-writes "<N>" + deletes signal)
    State: <N>
      ↓ (cycle commit: orchestrator.py writes "UNLOCKED")
    State: UNLOCKED
    ```

  - **Crash-recovery rules (added R3):**

    | Observed state | Cause hypothesis | Recovery action |
    |---|---|---|
    | lock=UNLOCKED + no signal | clean state | smoke can run normally |
    | lock=00X + no signal | smoke ran, crashed before signal-emit | run `scripts/raid/recover-from-crash.sh --reset-lock` (operator-only) |
    | lock=00X + signal exists | impossible if dispatcher is atomic | corrupted state → MANUAL investigation |
    | lock=READY_FOR_<N> + no signal | dispatcher crashed mid-write | run `recover-from-crash.sh --rewrite-signal <N>` OR --reset-lock |
    | lock=READY_FOR_<N> + signal exists + signal.next_cycle == N | clean ready state | `/raid <N>` proceeds normally |
    | lock=READY_FOR_<N> + signal exists + signal.next_cycle != N | corrupted signal | REFUSE; manual investigation |
    | lock=<N> + cycle commit absent | crashed mid-cycle | `/raid <N>` again triggers P5 recovery-protocol-runner |
    | lock=<N> + cycle commit present in HEAD | success but lock not reset | run `recover-from-crash.sh --reset-lock` (post-success lock-reset failed) |

  - **Orchestrator refusal rule (codified in orchestrator.py):**
    ```python
    def accept_raid_invocation(target_cycle: int) -> bool:
        lock = read_lock()
        if lock != f"READY_FOR_{target_cycle}":
            log_refusal(f"lock={lock} expected READY_FOR_{target_cycle}")
            return False
        signal_path = f"docs/raid/READY_FOR_CYCLE_{target_cycle}.signal"
        if not exists(signal_path):
            log_refusal(f"lock=READY_FOR_{target_cycle} but signal file missing")
            return False
        signal = parse_yaml(signal_path)
        if signal["schema_version"] != 1 or signal["next_cycle"] != target_cycle:
            log_refusal(f"signal corrupted: {signal}")
            return False
        return True
    ```

- `docs/raid/RAID_WORKFLOW.md` — copy of the spec into the live raid dir
- `infra/foundation-dev/docker-compose.yml` (B5) — Patroni + Redis Sentinel + MinIO skeleton (containers defined; not necessarily started in C0)
- `infra/foundation-staging/terraform/main.tf` (B5) — terraform skeleton (provider + empty modules)

---

## §4. VERIFY plan — smoke test exit criteria (REVISED R2)

Smoke test exercises ALL protections per RAID_WORKFLOW §13.7 (revised) + §14 Q-checks.
Concrete pass criteria — **24 checks total** (10 P + 6 B + 8 Q).

### P-protections (10)

1. **P1 fresh-session + lock state machine (REVISED R3 per Adversary R2 BLOCK 2):**

   **1A — Normal flow:** `.session-cycle-lock` transitions `UNLOCKED` → `00X` (smoke start) → `READY_FOR_<N>` (auto-dispatcher atomic) → `<N>` (orchestrator entry) → `UNLOCKED` (cycle commit). Each transition verified by reading lock value at expected checkpoints.

   **1B — Refusal at boundary states (NEW R3):** smoke runs paired-state probes:
   - Probe 1: `orchestrator.py /raid 1` invoked with `lock=UNLOCKED + no signal` → MUST exit non-zero with `error: lock=UNLOCKED expected READY_FOR_1` (closes Adversary R2 BLOCK 2 paired-suppression hole).
   - Probe 2: `orchestrator.py /raid 1` invoked with `lock=READY_FOR_2 + signal exists` → MUST exit non-zero with `error: lock=READY_FOR_2 expected READY_FOR_1` (cross-cycle mistarget refused).
   - Probe 3: `orchestrator.py /raid 1` invoked with `lock=READY_FOR_1 + signal absent` → MUST exit non-zero with `error: signal file missing` (mid-write crash recovery).
   - Probe 4: `orchestrator.py /raid 1` invoked with `lock=READY_FOR_1 + signal.next_cycle=2` (corrupted) → MUST exit non-zero with `error: signal corrupted`.
   - Probe 5: `orchestrator.py /raid 1` invoked with `lock=READY_FOR_1 + signal valid + next_cycle=1` → ACCEPTED (proceeds to acquire `<1>`).

   **1C — Atomicity check:** smoke asserts no intermediate UNLOCKED window exists between auto-dispatcher's `00X` read and `READY_FOR_<N>` write (no observation of UNLOCKED in this window even with concurrent file-watcher probe).

   P1 PASS requires all 1A transitions verified AND all 5 probes 1B return expected exit codes AND 1C atomicity.
2. **P2 startup routine:** verify-script log shows 5 steps executed in order with timestamps.
3. **P3 IN_PROGRESS file:** `docs/raid/IN_PROGRESS/cycle-00X-state.md` exists during run with `current_phase` updated at each phase transition; moved to `_archive/` after.
4. **P4 sub-agent return budget:** smoke spawns a no-op DPS sub-agent via `sub-agent-spawn.py` that returns ≤ 1500 token summary; assertion fails if budget exceeded.
5. **P5 compaction recovery (REVISED R3 — TWO scenarios per Adversary R2 BLOCK 1):**

   **Scenario 5A — HAPPY (CONSISTENT path):**
   - Smoke writes synthetic IN_PROGRESS state with `current_phase=BUILD, dps_status=[{id:1, status:complete, commit_sha=<real-SHA>}, {id:2, status:in_progress}]` matching ACTUAL git worktree state (e.g., commit_sha is a real prior commit).
   - Runs `compaction-detector.py --test-mode --inject-event` → asserts (5A-a) detector returns True.
   - Runs `recovery-protocol-runner.sh 00X` → asserts (5A-b) returns CONSISTENT exit code 0; (5A-c) AUDIT_LOG.jsonl gains `event=compaction_detected` row AND `event=recovery_consistent` row with phase=BUILD, dps_resumed_from=2; (5A-d) does NOT write ESCALATIONS row.

   **Scenario 5B — INCONSISTENT (HALT path — safety-critical):**
   - Smoke writes synthetic IN_PROGRESS state with INTENTIONAL drift: `current_phase=COMMIT, dps_status=[{id:1, status:complete, commit_sha=DEADBEEF1234567890}]` where the SHA does NOT exist in git OR phase=COMMIT while no commit was actually made.
   - Runs `compaction-detector.py --test-mode --inject-event` → asserts (5B-a) detector returns True.
   - Runs `recovery-protocol-runner.sh 00X` → asserts (5B-b) returns INCONSISTENT exit code non-zero; (5B-c) ESCALATIONS row appended with `type=p5_recovery_inconsistent` + specific mismatch description; (5B-d) AUDIT_LOG.jsonl `event=recovery_halted` row written; (5B-e) script does NOT proceed past HALT (verified by absence of any subsequent `event=phase_resumed` row).

   **Both scenarios independent.** P5 PASS requires BOTH 5A-a..d AND 5B-a..e (9 assertions total). False-green only if BOTH the happy detector path AND the HALT branch fire correctly. This addresses R1 BLOCK 2 + R2 BLOCK 1.
6. **P6 brief structure:** smoke brief `00X_helloworld_smoke.md` passes brief-structure-validator.sh AND every auto-generated brief 01-37 passes.
7. **P7 cross-cycle ref:** `files-from-cycle.sh 0` returns non-empty (the C0 commit files); diff vs `git show --stat HEAD` matches expected file list.
8. **P8 token budgets:** AUDIT_LOG rows for the smoke phases ALL contain `raid_leader_token_count`, `wall_time_in_phase_sec`, `sub_agent_invocations_so_far`, `memory_pressure` fields (value can be heuristic but must be present per §12.10 schema).
9. **P9 post-commit verifier:** smoke commit is checked by the verifier prompt template → VERIFIED row appended to AUDIT_LOG; DRIFT_DETECTED would block continuation.
10. **P10 health dashboard:** `health-dashboard.py 00X` emits formatted output containing all 8 §12.10 fields (wall time, sub-agent invocations, peak tokens, compaction events count, memory pressure peak, drift events).

### B-protections (6)

- **B1 worktree lifecycle:** smoke creates worktree at `../foundation-worktrees/cycle-00X-dps-1/` via `worktrees-create.sh 00X 1`; after smoke, `worktrees-cleanup.sh 00X` removes it cleanly; `worktrees-check.sh` after = no stale worktrees.
- **B2 test-infra isolation:** smoke spins `docker compose -p raid-c00X-dps1` (cycle=00X, dps=1, deterministic port = 10001+0 etc.) → up → down → no port collision with existing prod containers (verified via `docker ps` filter).
- **B3/Q9 cost-tracker dual-use:** smoke reads QUOTA_LOG.jsonl; `cost-tracker.py --mode quota` sums smoke run tokens; `cost-tracker.py --mode dollar` returns 0 (subscription user); both modes return without error.
- **B4 brief validator:** smoke brief + 37 generated briefs all exit 0 under brief-structure-validator.
- **B5 prod-isolation:** smoke commit grepped by `prod-isolation-lint.sh` → exit 0 (no `prod.loreweave.app`, no existing prod IPs/strings).
- **B6 gitleaks:** smoke runs `secret-scan-dps.sh 00X 1` + `secret-scan-cycle.sh 00X` + `secret-scan-final.sh 00X` → all exit 0.

### Q-protections (8 — **NEW in R2 per Adversary BLOCK 1**)

- **Q1 plan context:** `quota-check.sh` reads `contracts/raid/quota-profile.yaml` → asserts `plan: max-20x`. If profile missing or different plan → smoke FAIL.
- **Q2 sub-agent model tiering:** smoke spawns a probe via `sub-agent-spawn.py --role DPS --dry-run` → assert stdout contains `model: sonnet-4-6`; `--role scope-guard --dry-run` → `model: haiku-4-5`; `--role raid-leader --dry-run` → `model: opus-4-7`. Three tier assertions; failure of any = BLOCK.
- **Q3 DPS count cap:** `quota-check.sh --classify mega` returns `dps_cap: 5`; `--classify simple` returns `dps_cap: 2` (per §14.3 max-20x profile).
- **Q4 pre-cycle quota check:** `quota-check.sh` invoked at smoke start returns one of `PROCEED|RISKY|WAIT`; writes a row to QUOTA_LOG.jsonl with `event=quota_check, recommendation=<X>`.
- **Q5/Q6 quota-block graceful pause:** smoke simulates quota block by setting env `RAID_SIMULATE_QUOTA_BLOCK=1` mid-phase → `orchestrator.py` catches signal → writes ESCALATIONS row with `type=quota_block` (NOT `type=error`) → exits gracefully (no infinite retry); after re-invoke without env var, orchestrator resumes from IN_PROGRESS (idempotent re-run skips completed phases).
- **Q7 quota observability:** `quota-summary.py` reads QUOTA_LOG.jsonl rows for the smoke run, emits dashboard containing per-phase token estimates + recommendation.
- **Q8 session counter:** `session-counter.py` increments by 1 for the smoke run; reads back as count_this_month=1 (assuming fresh).
- **Q9 dual-use:** covered by B3/Q9 above (verifies cost-tracker.py both modes work).

### Smoke pass exit

All 24 checks emit `[PASS] <check-name>` to stdout. Final line: `[PASS] all 24 smoke checks (P:10 B:6 Q:8) — C0 ready for ready-signal emit`.
Then AUDIT_LOG row: `{"event":"smoke_complete","result":"PASS","check_count":24}`.
Then `run-smoke-test.sh` exit 0 → `auto-dispatcher.py` fires per B6 redesign.

### Smoke fail exit

Any `[FAIL]` → `run-smoke-test.sh` writes ESCALATIONS row with failing check name + last 20 lines of relevant log → exit non-zero → `auto-dispatcher.py` does NOT fire → user manually inspects + fixes + re-runs smoke.

---

## §5. AMAW phase checkpoints

| Phase | Action | Sub-agent | Cold-start? |
|---|---|---|---|
| 1 CLARIFY | DONE — RAID_WORKFLOW + CYCLE_DECOMP read | self | n/a |
| 2 DESIGN | This file | self | n/a |
| 3 REVIEW (design) | Adversary against this PLAN | general-purpose | YES |
| 4 PLAN | Reaffirm batches above; nothing additional to write | self | n/a |
| 5 BUILD | Batches B1-B6 sequential; checkpoint IN_PROGRESS after each batch | self | n/a |
| 6 VERIFY | Run smoke test live | self | n/a |
| 7 REVIEW (code) | Adversary against full C0 diff | general-purpose | YES |
| 8 QC | Re-run smoke after Adversary fixes | self | n/a |
| 9 POST-REVIEW | Scope Guard final gate | general-purpose | YES |
| 10 SESSION | Update SESSION_PATCH + archive IN_PROGRESS | self | n/a |
| 11 COMMIT | Single atomic commit with all 43 + smoke evidence | self | n/a |
| 12 RETRO | AUDIT_LOG row + add_lesson (if ContextHub up) | self | n/a |

---

## §6. Risks + mitigations

| Risk | Mitigation |
|---|---|
| Context exhaustion mid-build | After each batch, checkpoint IN_PROGRESS file; if context tight, propose splitting C0 into C0a/C0b commits |
| Smoke test fails on real Docker | Test infra spins up locally; if Docker port collision (unlikely per §6.2 check showing 10000-20000 free), reduce smoke to dry-run |
| brief-generator emits invalid output | Hand-write 00X_helloworld_smoke as reference; generator unit-tested before mass run |
| AMAW Adversary returns trivial findings | Per AMAW skill: Adversary MUST find EXACTLY 3 problems; accept APPROVED_WITH_WARNINGS after round 2 (pragmatic stop) |
| Auto-dispatcher fires prematurely (smoke false-green) | 60s pause window + explicit user notification; user can ctrl-C |
| Cross-platform shebang (Windows + bash) | Scripts use `#!/usr/bin/env bash`; Windows runs via git-bash which the user already uses |

---

## §7. NOT in C0 scope (explicit)

- Cycle 1 work (only ready-signal emitted; user manually opens fresh session per P1)
- Layer plan implementation (L1-L7 sub-components belong to C1-C37)
- Actor substrate (post-foundation sub-program)
- V1+30d (post-foundation)
- AWS Terraform apply (deferred per PRE_FLIGHT D1)
- ContextHub MCP wiring (optional, may be UNAVAILABLE during smoke)
- Actual session-spawning of /raid 1 (structurally impossible from C0 session per Adversary R1 BLOCK 3; replaced with ready-signal emitter per user choice — see PRE_FLIGHT D6)

---

## §8. Adversary review response log

### Round 1 (2026-05-29) — REJECTED · 3 BLOCK · 0 WARN

**Findings:** `docs/audit/findings-cycle-0-foundation-bootstrap-r1.md`
**AUDIT_LOG row:** `task: cycle-0-foundation-bootstrap, phase: review-design, round: 1, verdict: REJECTED`

| # | Finding (severity) | Fix location in R2 |
|---|---|---|
| 1 | BLOCK — Smoke §4 omits Q1-Q9 quota protections | §4 "Q-protections (8 — NEW in R2)" — 8 new checks added |
| 2 | BLOCK — P5 "asserts detector runs without error" = false-green | §4 P5 row rewritten with synthetic IN_PROGRESS + injected event + 4 assertions a-d |
| 3 | BLOCK — auto-dispatcher.py "spawn /raid 1" structurally impossible | §3 B6 redesigned as ready-signal emitter; §7 non-scope; PRE_FLIGHT D6; RAID_WORKFLOW §13.7 v1.4 |

### Round 2 (2026-05-29) — REJECTED · 2 BLOCK · 1 WARN

**Findings:** `docs/audit/findings-cycle-0-foundation-bootstrap-r2.md`
**AUDIT_LOG row:** `task: cycle-0-foundation-bootstrap, phase: review-design, round: 2, verdict: REJECTED`

| # | Finding (severity) | Fix location in R3 |
|---|---|---|
| 1 | BLOCK — P5 fix paper-thin (no 8-step executor; HALT branch never tested) | §2 added `recovery-protocol-runner.sh` (#8b) + `recover-from-crash.sh` (#8c); §3 B1 documented; §4 P5 rewritten with TWO scenarios 5A (CONSISTENT) + 5B (INCONSISTENT/HALT) totaling 9 assertions |
| 2 | BLOCK — Lock state machine self-contradictory + paired-state suppression of `/raid <N>` refusal | §3 B6 fully redesigned R3: ATOMIC `00X → READY_FOR_<N>` (no UNLOCKED window); orchestrator refusal rule with 5 cases; crash-recovery table for 8 observed states; signal file YAML schema validated; §4 P1 rewritten with 1A normal flow + 1B 5 paired-state probes + 1C atomicity check |
| 3 | WARN — Spec/plan drift: CYCLE_DECOMPOSITION §Cycle 0 stale (Size M, ~25 items); RAID_WORKFLOW §13.9 references renamed COST_LOG.jsonl | CYCLE_DECOMPOSITION §Cycle 0 fully rewritten v1.4 (Size XL, 45 items, all v1.0+v1.1+v1.2+v1.3+R3 enumerated + added `last_synced_with_RAID_WORKFLOW_version` header); RAID_WORKFLOW §13.9 COST_LOG.jsonl marked SUPERSEDED; §5 RAID prompt template clarified per-cycle Phase 9 vs C0→C1 boundary distinction |

### Round 3 (2026-05-29) — APPROVED_WITH_WARNINGS · 0 BLOCK · 3 WARN — **PRAGMATIC STOP (AMAW XL cap)**

**Findings:** `docs/audit/findings-cycle-0-foundation-bootstrap-r3.md`
**AUDIT_LOG row:** `task: cycle-0-foundation-bootstrap, phase: review-design, round: 3, verdict: APPROVED_WITH_WARNINGS, blocker_count: 0, warn_count: 3`

| # | Finding (severity) | Disposition |
|---|---|---|
| 1 | WARN — P1 1B probes 2-4 need test-mode lock-writer (currently unimplementable) | **ADDRESS in B1 build** — add `scripts/raid/test/force-lock-state.sh` test helper; update §4 P1 1B preamble |
| 2 | WARN — Drift-detection header text added but enforcement logic not in B1/B5 deliverable descriptions | **ADDRESS in B1+B5 build** — add Step 6 drift check to startup-verifier.sh; brief-generator refuses on header mismatch; smoke test asserts drift-detection halts |
| 3 | WARN — recover-from-crash.sh "checks pid file" but no orchestrator-pid mechanism specified | **ADDRESS in B1 build** — orchestrator.py writes/deletes `docs/raid/.raid-session.pid`; recover-from-crash.sh refusal logic; crash-recovery table rows 9-10 added |

**Status:** APPROVED_WITH_WARNINGS at R3 = AMAW XL pragmatic stop. BUILD proceeds. The 3 WARNs are **NOT deferred** — they will be addressed during the B1+B5 build batches per the Adversary's specific recommended fixes. Tracker IDs `D-CYCLE-0-LOCK-PROBE-SETUP` / `D-CYCLE-0-DRIFT-ENFORCER` / `D-CYCLE-0-PID-FILE-CONTRACT` ensure traceability.

---

## §9. Residual-risk register (R3 WARNs → BUILD action items)

| Tracker | Severity | Action in BUILD | Owning batch | Completion criterion |
|---|---|---|---|---|
| `D-CYCLE-0-LOCK-PROBE-SETUP` | WARN R3-F1 | Add `scripts/raid/test/force-lock-state.sh <state> [signal-yaml]`; document in §4 P1 1B that probes 2-4 use this helper to pre-position state | B1 | smoke runs probes 2-4 using force-lock-state.sh; helper writes audit row `event=test_lock_forced` |
| `D-CYCLE-0-DRIFT-ENFORCER` | WARN R3-F2 | startup-verifier.sh Step 6: parses `last_synced_with_RAID_WORKFLOW_version` + compares to RAID_WORKFLOW frontmatter; mismatch → ESCALATIONS row `type=spec_drift` + exit non-zero. brief-generator.py refuses to run if mismatch. Smoke asserts both behaviors (bump header → expect halt → restore) | B1, B5 | smoke includes drift-detection assertion; both scripts halt on mismatch |
| `D-CYCLE-0-PID-FILE-CONTRACT` | WARN R3-F3 | orchestrator.py writes `docs/raid/.raid-session.pid` atomically on entry; deletes on commit-success. recover-from-crash.sh: if pid file + process alive → REFUSE; if pid file + process dead → audit `event=stale_pid_cleaned` + proceed. Add rows 9-10 to crash-recovery table | B1 | orchestrator + recover-from-crash both honor pid contract; crash-recovery table has 10 rows |

**Net new deliverable from §9:** `scripts/raid/test/force-lock-state.sh` (1 file). Updated count: **46 canonical deliverables** (29 new + 9 pre-staged + 8 dirs).

---

**End of CYCLE_0_PLAN.md.** R3 APPROVED_WITH_WARNINGS — proceeding to PLAN phase + BUILD.
