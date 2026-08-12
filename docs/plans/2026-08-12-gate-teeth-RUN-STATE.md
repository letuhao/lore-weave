# RUN-STATE — gate teeth: 41 gates that assert coverage nobody has proven

**Reconciles:** A gate, lint, test, `const` assertion, validator, or an axiom that constrains code ·
MCP Tool I/O Standard · Settings & Configuration Boundary — the first is the governing row; the
others because the recurring defect below is theirs in a different costume (a closed set that is not
enum-locked, a value stored and never consumed). Phase 0 is §1 and was measured, not assumed.

---

## 0 · HOW TO WORK

**Binding execution contract: [`§0.6d` of the reality-layer run-state](2026-08-08-reality-layer-RUN-STATE.md)**, adopted verbatim.

Hazards, each earned in this repo:

* **`--run-all` DETACHED, read the process's REAL exit code** (`BDR-89`/`BDR-90`) — a task
  notification said *"exit code 0"* over a run whose process returned **1**, on 2026-08-11.
* **Edit nothing while a sweep or bite harness runs** (`WSD-8`).
* **Byte-level I/O** for anything a shell executes or any document (`BDR-86`).
* **Never restore a bite with `git checkout`** (`TLD-10`) — it restores from the index and deletes
  unstaged work.
* **A bite harness is an unverified check** (`TLD-11`); its `want` strings are **case-sensitive**.
* **Never hand bash an absolute Windows path** — backslashes are eaten as escapes and every arm
  reports `rc=127`. Use a relative path under `cwd`.
* **Backticks in `git commit -m` trigger command substitution** — use `-F`.

**Not stop conditions:** a commit · a green sweep · a batch finishing · a POST-REVIEW · wanting a
decision this file can make.

---

## 1 · PHASE 0 — measured 2026-08-12

| fact | value | command |
|---|---|---|
| CI-invoked gates | **98** | `gate-teeth-gate.py --list` |
| carrying a red-ability proof | **57** | same |
| carrying none | **41** | same |
| …of those, shell | **26** | `--list \| grep 'no red-ability'` |
| …of those, Python | **15** | same |
| size range | **38 – 386 lines** | `wc -l` |

**Every one of the 98 is already proven able to return non-zero.** What the 41 lack is a proof that
they return non-zero *for their own reason* — that the rule bites rather than the script merely
being capable of exiting 1.

### 1.1 · ⚠️ THE TRAP — why this number sat still

**Proof detection is STRUCTURAL.** `gate-teeth-gate` searches executable text for
`def self_test` / `selftest() {`, or a `test_<name>.py`. **It cannot distinguish a real self-test
from an empty one.** So 41 stub functions would take this baseline to **zero** and prove nothing.

That outcome is **strictly worse than 41**: a gap invites work, a false pass silences review. It is
also exactly `NV-1` — a check that cannot fail is a claim in the costume of evidence — committed
inside the mechanism built to count `NV-1` violations.

**Therefore the unit of progress on this board is not "a `selftest()` exists". It is "a mutation of
the rule makes the self-test red, and the output is pasted."**

### 1.2 · The house pattern, already in the tree

`scripts/emit-migration-0013-lint.sh` is the precedent and is copied rather than reinvented:

1. extract the rule into a **predicate function** a case can drive;
2. `selftest()` asserts **both directions** — the bad sample is flagged, the good sample is not;
3. `case "${1:-}"` runs **`selftest; run_lint`** on a bare invocation, so the proof executes on
   every CI run rather than on request;
4. selftest failure exits **2**, distinct from a lint violation's 1.

### 1.3 · What the first batch found, which generalises

Both gates in batch 1 **counted nothing**. A walk that reached zero services printed `PASS` —
byte-identical to compliance (`BDR-82`). **Assume every one of the 41 has this defect until its
counter is read**; a reach floor is part of the work, not an extra.

---

## 2 · SEALED FORKS

**`GT-F1` · A `selftest()` is not counted until it is BITTEN.** Six steps, output pasted, restore
byte-exact. **Reversal trigger: none.** This is the board's reason to exist (§1.1).

**`GT-F2` · Batch by SHAPE, not by size.** Gates sharing a predicate shape (*"X must appear in
registry Y"*) share their case design, so the second costs a fraction of the first. Ordering by line
count would scatter the shapes and pay the design cost every time.

**`GT-F3` · Every gate gains a REACH FLOOR in the same edit.** `0 < floor < measured`, printed. A
gate that cannot say what it scanned cannot be believed when it says it found nothing (`BDR-82`,
and §1.3 measured it twice out of two).

**`GT-F4` · The baseline moves only DOWN, and only after the bite.** The ratchet already refuses to
pass until the number follows a drop; it must never be raised to accommodate a gate that lost its
proof. **Reversal trigger:** a scope widening that legitimately adds unproven gates — the 2026-08-10
`45 → 55` precedent, which is recorded as the one honest exception.

---

## 3 · THE BOARD

`done =` for every batch row: **each gate carries a predicate-driven `selftest()` asserting both
directions, a reach floor, and a pasted six-step bite; `gate-teeth-gate` green at the lowered
baseline; the batch committed.**

| # | batch | gates | state |
|---|---|---|---|
| `GT1` | registry membership — the smallest two | `capacity-budget-lint.sh` · `service-acl-matrix-lint.sh` | ✅ **43 → 41**, `baed59cad`. 5 bite arms, all byte-exact |
| `GT2` | registry membership — the rest of the shape | `dependency-registry-lint.sh` · `admin-command-registry-lint.sh` · `dep-pinning-lint.sh` · `language-rule-lint.sh` | ⬜ |
| `GT3` | drift / mirror checks | `read-audit-query-type-drift-lint.sh` · `transitions-validation-lint.sh` · `runbook-drift-check.sh` · `projection-coverage-lint.sh` | ⬜ |
| `GT4` | observability inventory | `tracing-completeness-lint.sh` · `observability-inventory-lint.sh` · `dashboard-validator.sh` · `alert-rule-validator.sh` · `slo-latency-lint.py` | ⬜ |
| `GT5` | discipline lints (forbidden-shape scanners) | `timeout-discipline-lint.sh` · `blocking-in-async-lint.py` · `prompt-assembly-discipline-lint.sh` · `raw-sql-lint.py` · `pagination-cap-lint.py` · `logging-discipline-lint.sh` | ⬜ |
| `GT6` | context-budget family | `context-budget-l3-lint.py` · `context-budget-defaults-lint.py` · `context-inspector-checklist-gate.py` · `context-inspector-trace-gate.py` | ⬜ |
| `GT7` | deploy / freeze | `deploy-class-check.sh` · `deploy-freeze-check.sh` · `feature-freeze-enforcer.sh` · `raid/prod-isolation-lint.sh` | ⬜ |
| `GT8` | the remainder, one at a time | `knowledge-access-gate.py` · `knowledge-http-surface-gate.py` · `boundaries-lock-gate.py` · `ingress-admission-gate.py` · `i18n-completeness-gate.py` · `design-draft-token-lint.py` · `game-wire-lint.py` · `sdk-duplication-gate.py` · `phantom-route-scan.py` · `outbox-event-emit-lint.sh` · `role-grant-validator.sh` · `template-fixture-validator.sh` · `runbook-verification-lint.sh` · `perf/bench-gate.sh` | ⬜ |

**The batch list is a WORKLIST, not the scope.** The scope is the predicate *"CI-invoked and no
red-ability proof"*, which `gate-teeth-gate --list` recomputes. A gate added tomorrow joins it
without anyone editing this table — and if this table and the gate ever disagree, **the gate is
right**.

---

## 4 · OPEN ROWS

| id | what | why not here |
|---|---|---|
| `GT-STRUCTURAL-DETECTION` | the ratchet counts a `selftest()` it cannot evaluate (§1.1) | fixing it means executing every gate's self-test and judging it, which is `gate-bite-harness`'s job — the two mechanisms already exist and the gap is that nothing joins them. A real row, deliberately not solved by this board |
| `GT-PERF-BENCH` | `perf/bench-gate.sh` SKIPs in `--run-all` (*"needs a live stack"*) | a gate that cannot run here cannot be bitten here; it needs the stack, and a self-test for it would be testing the skip |

---

## 5 · DRIFT REGISTER

**An empty drift log is not evidence of a clean run.**

| id | what happened |
|---|---|
| `GTD-1` | **The first bite arm certified nothing and looked like a pass.** Blanking the whole meta-write alternation red the self-test — but on its FIRST case, so it proved `contracts/meta` was live and said nothing about the other two. A bite that reds for the wrong reason is a bite that certifies coverage it never exercised. Split into one arm per alternative. |
| `GTD-2` | **Handed bash an absolute Windows path and all four arms died at `rc=127`.** `D:\Works\…` arrives as `D:Works…` — backslashes eaten as escapes. Cost one full harness run to diagnose something the tree had already taught me twice this session. |
