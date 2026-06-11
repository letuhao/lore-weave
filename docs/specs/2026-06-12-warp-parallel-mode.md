# Spec — `/warp` Parallel-Execution Workflow Mode

**Date:** 2026-06-12 · **Status:** DESIGN (awaiting PO sign-off) · **Size:** L (new workflow mode; new command + 1 gate verb + thin script set; reuses RAID/amaw/loom machinery)
**Source discussion:** session 2026-06-11/12 — "tăng tốc phát triển bằng nhiều sub-agent song song trong 1 cửa sổ, kiểm soát ở các nút giao".
**Relates to:** [`agentic-workflow/WORKFLOW.md`](../../agentic-workflow/WORKFLOW.md) (v2.2 spine) · [`.claude/commands/loom.md`](../../.claude/commands/loom.md) · [`.claude/commands/raid.md`](../../.claude/commands/raid.md) · [`docs/amaw-workflow.md`](../amaw-workflow.md) · [`docs/raid/RAID_WORKFLOW.md`](../raid/RAID_WORKFLOW.md)

---

## 1. Problem

Development today runs **one task at a time, sequentially**, even when the work is decomposable into independent slices. The user's current workaround — multiple Opus sessions in separate folders — is clean but pays a heavy **merge/refactor tax** because each session designs its *own* boundaries, which then drift and collide at integration time.

The three existing workflows do not fill the need:

| Mode | Spine | Fan-out | Human gate | Why it doesn't fit |
|---|---|---|---|---|
| `loom` (v2.2) | sequential | none | yes (CLARIFY end, POST-REVIEW) | BUILD is inline-serial; no parallelism at all |
| `amaw` (overlay) | sequential | none | yes + cold-start Adversary | adds *review independence*, not *execution parallelism* |
| `raid` | dependency-ordered cycles (serial spine) | **yes — DPS in worktrees** | **no (auto Scope Guard)** | parallelism exists but is per-cycle, **hand-planned in locked briefs**, needs Cycle-0 infra + mega-plan + quota; fully autonomous (no junction control) |

**Key realization:** the hard, risky machinery for parallel code execution — fan-out sub-agents in isolated worktrees, an integration/rebase node, regression chase, condensed-return context hygiene, per-slice test infra — **already exists and is battle-tested in RAID** (its DPS / Tank / Healer roles). RAID's per-cycle "DPS parallelism plan" *is* a slice manifest — but it is **written by hand**, for a **locked mega-cycle**, and run **fully autonomously**.

So the gap is precise. There is no **parallel + human-gated + lightweight** mode that works on an **everyday task** and **derives the slicing itself**.

```
                 Serial spine          Parallel fan-out
Human-gated      loom (+amaw)          ← /warp  (THE GAP)
Autonomous       (amaw-auto, rare)     raid
```

`/warp` fills the empty cell: RAID's DPS fan-out, but (a) **auto-sliced** instead of hand-written, (b) for **one everyday task** instead of a locked mega-plan, (c) **human-gated at the junction** instead of auto.

## 2. Goals / Non-Goals

**Goals**
- **G1. Cut wall-clock** on decomposable tasks by executing independent slices concurrently in isolated worktrees, then reconciling at a defined node — within a *single* main session.
- **G2. Eliminate the merge tax** by *centralizing boundary design* (one frozen interface artifact) before any fan-out, so slices cannot drift apart.
- **G3. A machine-checkable independence guarantee** — pairwise-disjoint write-sets asserted *before* spawning, so two slices can never be silently editing the same file.
- **G4. Keep the human junction.** POST-REVIEW stays a human STOP-and-WAIT (the distinguishing choice vs RAID's auto-gate). The user controls the merge.
- **G5. Reuse, don't rebuild.** Borrow RAID's worktree/test-infra/Tank/Healer machinery, amaw's cold-start reviewers, loom's spine + gate. Net-new surface ≈ a decision layer + one validator.
- **G6. Bias to serial.** When independence is uncertain, fall back to `/loom` in the *same session* — no restart, no penalty.

**Non-Goals**
- **N1. NOT replacing `loom`.** `/warp` is opt-in for decomposable M/L/XL tasks; everyday XS/S work stays serial.
- **N2. NOT RAID.** No locked mega-plan, no Cycle-0 bootstrap, no quota subsystem, no full 12-phase gate per slice. `/warp` is for a *single* task.
- **N3. NOT autonomous.** `/warp` is not a "fire and walk away" mode. It stops at the human junction like `loom`.
- **N4. NOT for refactors of shared types/APIs.** Those mutate a shared surface → not independent → explicitly out of scope (TRIAGE rejects them; see §10).
- **N5. NOT a from-scratch fan-out engine.** The substrate is the `Agent` tool (`isolation:worktree`), exactly as RAID uses it.

## 3. Core principle

> **Centralize boundary design (serial) → parallelize execution within frozen boundaries (fan-out) → reconcile at a defined node (serial).**

Three load-bearing consequences:

1. **Parallelizability is a property of the *decomposition*, not of the task.** The same feature is serial if sliced badly (everyone touches shared types) and parallel if sliced along service/contract lines. Therefore the parallel/serial decision **cannot precede design** — it is an *output* of boundary-finding (§5 fixes the chicken-and-egg in the original sketch).
2. **Independence = disjoint write-sets + a fully frozen inter-slice interface.** All shared-write decisions must be pushed into the frozen artifact *before* fan-out, leaving each slice with only private state. If two slices must co-evolve a shared interface, they are not independent → serial.
3. **The failure cost is asymmetric, so bias to serial.** A *missed* parallelization costs some wall-clock. A *wrong* parallelization (hidden shared write) costs merge hell + wasted tokens + possibly a silent cross-service contract bug. When in doubt, stay serial.

N (slice count) is the number of **disjoint** slices, **not** maximized — pick the *coarsest* slicing that preserves independence (fewer fat independent slices beat many thin ones with high reconcile overhead — Amdahl: the serial design+merge fraction bounds speedup). Capped at the harness concurrency (~10 simultaneous).

## 4. Phase map

`/warp` = `loom`'s 12-phase spine with **3 phases modified (‡)** and **2 nodes inserted (＋)**. Slices do **not** each run the 12-phase gate; only the orchestrator track does (§8).

```
0.  TRIAGE-pre   ＋ cheap pre-filter: additive across ≥2 boundaries? → candidate; mutative-shared? → /loom
1.  CLARIFY        (loom, unchanged) — scope + acceptance criteria; PO checkpoint at end
2.  DESIGN     ‡  BOUNDARY-FINDING: emit Slice Manifest + frozen-interface artifact + merge plan
3.  REVIEW(des)‡  cold-start Adversary on the SLICING (not the code) → PT-verdict GO / NO-GO parallel
4.  PLAN       ‡  emit N hermetic slice briefs (reuse RAID cycle-brief TEMPLATE.md), each refs frozen interface only
5.  BUILD      ‡  FAN-OUT: N Agent sub-agents, isolation:worktree, run_in_background; reuse RAID DPS machinery
5.5 RECONCILE  ＋ Tank rebase (dep-order) + Healer regression chase; contract violation → kick back to DESIGN
6.  VERIFY        (loom) — cross-service live-smoke is the reconcile evidence (≥2-service token already required)
7.  REVIEW(code)  may fan-out by DIMENSION (security/perf/a11y/contract) — reuse amaw Adversary
8.  QC            (loom / amaw Scope Guard) — diff vs spec
9.  POST-REVIEW   HUMAN STOP-and-WAIT (kept — the junction the user controls; NOT RAID-auto)
10. SESSION       (loom) — overwrite ▶ NEXT block; land with the code
11. COMMIT        (loom) — stage changed files only; push only on explicit approval
12. RETRO         (loom) — add_lesson if notable
```

If **PT-verdict is NO-GO** at phase 3 (DESIGN could not produce ≥2 disjoint slices, or the interface won't freeze), `/warp` **falls back to `/loom`'s serial BUILD in the same session** — CLARIFY/DESIGN work is not wasted (G6).

## 5. TRIAGE — the two-stage gate (fixes the chicken-and-egg)

The original sketch put "evaluate parallelizability" *before* design. That can't work: you don't know if independent slices exist until you've drawn the boundaries. So the gate is **two stages**:

### 5.1 PT-pre (cheap, at scoping — before design effort)
A 4-question rubric the orchestrator answers from the task description + a quick repo scan. Purpose: kill obvious-serial cases before spending design effort.

| # | Question | Parallel signal | Serial signal |
|---|---|---|---|
| 1 | **Additivity** | mostly NEW code in NEW locations | mutating shared existing code |
| 2 | **Boundary count** | ≥2 independent service/module subtrees, OR ≥K independent mechanical sites | one tightly-coupled area |
| 3 | **Shared-write magnets** (§10) | none touched, or confinable to one slice | several slices must edit a shared registry/migration/i18n index |
| 4 | **Interface freezability** | inter-slice contract can be fully fixed up front | slices must co-evolve a shared interface |

**Output:** `candidate` (≥3 parallel signals AND Q4 = freezable) → proceed to a boundary-finding DESIGN. Otherwise `not-candidate` → go straight to `/loom`. Conservative: ties resolve to serial.

### 5.2 PT-verdict (the real decision — at end of DESIGN)
DESIGN either produces a **valid Slice Manifest** (§6) that passes the disjointness check, or it doesn't.
- **GO parallel** iff ALL: (a) ≥2 slices, (b) pairwise-disjoint write-sets (machine-checked), (c) frozen interface artifact exists at a pinned sha, (d) the phase-3 Adversary did not BLOCK the slicing.
- **NO-GO** otherwise → fall back to serial `/loom` BUILD (G6).

## 6. The Slice Manifest (the central new artifact)

DESIGN's deliverable changes from "a design" to "a decomposition + a frozen interface + a merge plan". Written to `docs/warp/<task-slug>/manifest.yaml`:

```yaml
task: factory-budget-and-i18n          # slug
frozen_interface:
  - path: contracts/api/campaign.yaml
    sha: <git-blob-sha-at-freeze>        # immutable for the duration of fan-out
  - path: services/campaign-service/internal/types/budget.go
    sha: <...>
slices:
  - id: 1
    label: budget-validate-backend
    writes: [services/campaign-service/internal/budget/**]   # OWN subtree — disjoint
    reads:  [contracts/api/campaign.yaml]                     # frozen only
    acceptance: ["go test ./internal/budget/..."]
  - id: 2
    label: picker-dedup-frontend
    writes: [frontend/src/features/campaigns/**]
    reads:  [contracts/api/campaign.yaml]
    acceptance: ["pnpm -C frontend vitest run campaigns"]
merge_plan:
  integrate_order: [1, 2]                # Tank rebases in this order
  reconcile_evidence: "live smoke: create campaign → budget rejects over-cap → picker dedups"
  on_contract_violation: HALT_REDESIGN   # never patch a slice to absorb a frozen-interface change
```

**Machine-checkable independence** — a new validator (`slice-manifest-validate.py`, §8) enforces, *before any spawn*:

1. **Disjoint writes (hard):** for all i≠j, `writes[i]` and `writes[j]` are **path-prefix-disjoint** (each slice owns a directory subtree or an explicit non-overlapping file list). Overlap → exit non-zero, block.
2. **Reads stay frozen-or-own (hard):** every `reads[i]` glob must resolve under `frozen_interface` paths or under `writes[i]`. A read that lands in another slice's `writes` = a runtime dependency → that slice is not independent → block (or force an `integrate_order` edge + WARN if it reads frozen output only).
3. **Frozen pin present (hard):** every `frozen_interface` entry has a sha. An empty/unpinned interface = nothing actually frozen = block.
4. **N ≥ 2 (else not parallel):** fewer than 2 slices → fall back to serial.

This is the single highest-value piece of new IP: it converts "I hope these don't collide" into an asserted invariant.

## 7. RECONCILE node (5.5)

Borrowed wholesale from RAID Phase 6:
- **Tank** (cold-start sub-agent): rebase slice branches onto the base in `integrate_order`, resolve conflicts conservatively, run the integration test. Unresolvable conflict → ESCALATE to human (not auto-halt — `/warp` is human-gated).
- **Healer** (cold-start sub-agent): run the full suite; for each failure fix root cause (never modify tests to pass); iterate until green or 3 attempts.
- **Contract-violation rule:** if reconcile reveals the frozen interface was wrong, that invalidates *N slices at once* — so the fix is **re-DESIGN the interface**, never a per-slice patch (a per-slice patch re-introduces drift). This raises the value of the phase-3 design Adversary: a wrong boundary is expensive.

**Reconcile evidence = the existing cross-service live-smoke.** When the task touched ≥2 `services/`, VERIFY already requires a `live smoke:` token (workflow-gate soft gate). For `/warp` that token *is* the proof the slices integrate. Note the recurring trap (memory `live-smoke-rebuild-stale-images-first`): **rebuild touched service images before the reconcile smoke** — stale images produce false-greens.

## 8. Enforcement / `workflow-gate` integration

The gate's `.workflow-state.json` is **single-track by design** — do not change that. Integration mirrors RAID exactly:

- The **orchestrator** runs *one* gate track for the whole task (`size`, `phase`, `complete` as usual). Its VERIFY = the reconcile cross-service smoke.
- **Slices are sub-agents** — they do **not** call `workflow-gate.py` (that would corrupt the single state file). A slice just: build → slice-local tests green → return a ≤1500-token structured summary. Precedent: RAID cycle sub-agents run their own gate *in their own context*; here slices are smaller than cycles and need no full 12-phase gate.
- **One new gate verb** — `python scripts/workflow-gate.py slices <manifest.yaml>` runs `slice-manifest-validate.py` and exits non-zero on any §6 violation. Called at the DESIGN→REVIEW boundary (PT-verdict). ~30 LoC + the validator.

No surgery to the existing state machine; the parallel structure lives *above* it.

## 9. Reuse map (borrow, don't rebuild)

| `/warp` need | Source | Concrete asset (verified on disk) |
|---|---|---|
| Fan-out in isolated worktrees | RAID DPS | `Agent(isolation:worktree, run_in_background:true)` pattern; [`scripts/raid/worktrees-create.sh`](../../scripts/raid/worktrees-create.sh), `worktrees-cleanup.sh`, `worktrees-check.sh` |
| Per-slice isolated test infra | RAID B2 | `scripts/raid/test-infra-up-dps.sh` / `test-infra-down-dps.sh` (deterministic ports) |
| Integration/reconcile node | RAID Tank | Phase-6 rebase logic (RAID_WORKFLOW §4) |
| Regression chase | RAID Healer | Phase-6 step 2 |
| Condensed sub-agent returns | RAID P4 | 1500-token structured return contract ([`scripts/raid/cycle-runner-prompt.md`](../../scripts/raid/cycle-runner-prompt.md)) |
| Hermetic slice brief | RAID | [`docs/raid/cycle_briefs/TEMPLATE.md`](../raid/cycle_briefs/TEMPLATE.md) (TL;DR + scope IN/OUT + REMINDERS) |
| Cold-start Adversary (slicing + code) | amaw | "exactly 3 problems" prompt ([`docs/amaw-workflow.md`](../amaw-workflow.md) §Sub-agent prompt templates) |
| Conservative final gate | amaw Scope Guard | CLEAR/BLOCKED diff-vs-spec |
| Human junction | loom | POST-REVIEW STOP-and-WAIT ([`.claude/commands/loom.md`](../../.claude/commands/loom.md) step 6) |
| Phase enforcement | `workflow-gate.py` | orchestrator single track + new `slices` verb |
| Worktree port allocation | RAID B2 formula | reuse with a **warp offset** so warp/raid port ranges never collide |

Net-new = the decision layer (§5 TRIAGE rubric, §6 manifest + validator) and a thin warp-keyed script set (§11). Everything else is assembly.

## 10. Risks + repo-specific shared-write magnets

| Risk | Mitigation |
|---|---|
| **False-independent slicing** (writes disjoint on disk, but a hidden semantic coupling) — the expensive failure | §6 check catches *file* overlap, not semantics. The phase-3 design Adversary is the human-judgment backstop. Bias-to-serial on doubt. |
| **Reconcile cost eats the win** (Amdahl) | Measure reconcile wall-time + conflict count per run (RAID's `health-dashboard.py` P10 is precedent). A task that reconciles painfully twice → demote to serial. |
| **Token cost** ≈ N× BUILD + orchestration (~RAID's $15-30 range) | Opt-in only; never XS/S; the user decides when wall-clock > token cost. |
| **Stale-image false-green at reconcile smoke** | Rebuild touched images first (memory `live-smoke-rebuild-stale-images-first`); `scripts/build-stack.sh` stamps a git-SHA freshness label. |

**Shared-write magnets in *this* repo** (TRIAGE Q3 must explicitly check — these are where "independent" slices secretly collide):
- **DB migration sequence numbers** — two slices each adding `migrations/00N_*.sql` will both grab the next N.
- **DI / route / consumer registration** — a central `RegisterRoutes`/module wiring file every new handler must edit.
- **i18n key files** — the 4-locale key bundles (recent `D-S5C-I18N`) are a single shared surface.
- **OpenAPI index / `contracts/api` aggregation** — but note: the *contract* is the **frozen interface** here, so it must be settled in DESIGN, not edited in a slice.
- **Generated code / barrels** (`index.ts` re-exports, generated clients).

**Rule:** if a magnet is touched, either assign it wholly to **one** slice (serialize just that file) or take the task serial. Never let two slices both write a magnet.

## 11. Build plan

| # | Deliverable | Notes |
|---|---|---|
| B1 | `docs/specs/2026-06-12-warp-parallel-mode.md` | this spec |
| B2 | `.claude/commands/warp.md` | the skill: TRIAGE rubric, phase map, fan-out dispatch (cite cycle-runner pattern), human junction kept |
| B3 | `scripts/warp/slice-manifest-validate.py` | the §6 disjointness/freeze/reads validator |
| B4 | `workflow-gate.py` `slices` verb | thin wrapper calling B3 at the PT-verdict boundary |
| B5 | `scripts/warp/` thin script set | warp-keyed copies/wrappers of RAID `worktrees-*` + `test-infra-*-dps` keyed on `(task-slug, slice-id)` with a port offset (keeps RAID's locked scripts untouched) |
| B6 | `docs/warp/` + `WARP_LOG.md` | per-task manifests + a lightweight run log (slice count, reconcile cost — feeds the Amdahl demotion heuristic) |
| B7 | `scripts/warp/slice-runner-prompt.md` | hermetic per-slice sub-agent prompt (adapt cycle-runner-prompt.md: drop cycle/quota/CYCLE_LOG; keep cold-start + condensed return + worktree + per-slice test infra) |

**Sequencing:** B1 (this) → PO sign-off → B3+B4 (the validator is the safety spine; build + unit-test it first) → B2+B7 (the harness) → B5 (scripts) → B6 (logging) → dry-run on a real decomposable task as the live-smoke.

## 12. Open questions for PO

1. **Name.** `/warp` (warp = the parallel threads on a loom — composes with the loom metaphor). Alternatives: `/fan`, `/loom-parallel`. Lock the name before B2.
2. **Script strategy** — thin warp-keyed fork of the RAID worktree/test-infra scripts (B5, low risk, some duplication) vs. generalizing the RAID scripts to take a namespace arg (less duplication, but edits locked RAID scripts). Recommendation: **fork** — keep RAID stable.
3. **Slice sub-agent model tier** — inherit main-loop model, or default slices to a lighter tier (RAID tiers DPS to Sonnet)? Recommendation: **inherit** for everyday correctness; revisit if token cost bites.
4. **`Agent` tool vs `Workflow` tool as substrate.** Default = `Agent` fan-out (proven in RAID, model-driven, integrates with the skill). For a *purely mechanical* migration (discover sites → transform each → verify), the deterministic `Workflow` tool's `pipeline()` may fit better. Recommendation: `Agent` for v1; note `Workflow` as a future substrate for the mechanical-migration case.

---

*Spec v1 — 2026-06-12. Awaiting PO sign-off before BUILD (B2+).*
