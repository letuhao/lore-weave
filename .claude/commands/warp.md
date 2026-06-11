---
description: Run a task in /warp parallel mode — decompose into provably-disjoint slices, fan them out as worktree sub-agents, reconcile at a defined node, keep the human junction. For decomposable M/L/XL tasks where wall-clock matters. Falls back to serial /loom when the work can't be sliced independently.
---

# /warp — parallel-execution workflow mode

`/warp` weaves a task as **parallel threads on the loom**: it decomposes the work into
**provably-disjoint slices**, fans them out as isolated worktree sub-agents running
concurrently, then **reconciles at a defined junction** you control. It is `loom`'s
12-phase spine with 3 phases changed + 2 nodes inserted — **not** a new workflow and
**not** RAID (no locked mega-plan, no Cycle-0, no quota; fully human-gated).

**SSOT for the design:** [`docs/specs/2026-06-12-warp-parallel-mode.md`](../../docs/specs/2026-06-12-warp-parallel-mode.md).
This command is the operational harness around it.

```
                 Serial spine          Parallel fan-out
Human-gated      loom (+amaw)          ← /warp  (this)
Autonomous       (amaw-auto, rare)     raid
```

**Argument** (optional): the task — free-text, a ticket/milestone id, or `continue`.

## When to invoke /warp — and when NOT

**Use it when** the work is **additive across ≥2 independent boundaries** (separate
services/modules, or many independent mechanical sites) AND the inter-slice contract
can be **fully frozen up front**. Best fit: a feature spanning several services behind a
contract; a mechanical migration over many independent files.

**Do NOT use it** (take `/loom` instead) for:
- XS/S tasks — orchestration overhead dwarfs the win.
- **Refactors of a shared type/API** — they mutate a shared surface; slices aren't independent.
- Anything touching a **shared-write magnet** that can't be confined to one slice:
  DB migration sequence numbers, DI/route/consumer registration, i18n key bundles,
  generated barrels/clients, the OpenAPI index.

**Bias to serial:** a missed parallelization costs some wall-clock; a *wrong* one costs
merge hell + wasted tokens + maybe a silent cross-service bug. When in doubt → `/loom`.

## The phase flow

`/warp` runs `loom`'s phases; the `‡`/`＋` steps are what differ. Slices do **not** run
the workflow-gate; only this orchestrator track does (one `.workflow-state.json`).

```
0.  TRIAGE-pre  ＋ Answer the 4-question rubric (spec §5.1) from the task + a quick scan.
                   <3 parallel signals, or the interface won't freeze → STOP, run /loom instead.
1.  CLARIFY        loom — scope + acceptance criteria. PO checkpoint at end (STOP + WAIT).
2.  DESIGN     ‡ BOUNDARY-FINDING. Produce three artifacts:
                   (a) the frozen interface — settle every shared-write decision, pin each by git blob sha
                   (b) docs/warp/<task-slug>/manifest.yaml — the Slice Manifest (see EXAMPLE-manifest.yaml)
                   (c) merge_plan — integrate order + reconcile evidence + on_contract_violation: HALT_REDESIGN
3.  REVIEW(des)‡ PT-VERDICT. Two gates, both must pass:
                   • python scripts/workflow-gate.py slices docs/warp/<task-slug>/manifest.yaml --verify-frozen
                     (disjoint write-sets + frozen files unchanged vs their pinned sha; BLOCK → fix or /loom)
                   • cold-start Adversary on the SLICING (amaw Adversary prompt) — hidden coupling? magnet? → GO / NO-GO
                   Re-run the gate (esp. --verify-frozen) right before BUILD — catches drift between freeze and fan-out.
                   NO-GO → fall back to serial /loom BUILD in THIS session (CLARIFY/DESIGN not wasted).
4.  PLAN       ‡ Write one hermetic slice brief per slice (reuse docs/raid/cycle_briefs/TEMPLATE.md shape);
                   each references ONLY the frozen interface + its own write-set. Zero cross-slice references.
5.  BUILD      ‡ FAN-OUT (coordinator loop below): N slice sub-agents, isolation:worktree, run_in_background.
5.5 RECONCILE  ＋ Merge slice branches in integrate_order. By disjointness, expect ZERO write-set conflicts.
                   Healer chases regressions (full suite). A real conflict ⇒ the manifest was wrong ⇒ HALT_REDESIGN.
6.  VERIFY        loom evidence gate — the cross-service live-smoke IS the reconcile proof (≥2-service token).
7.  REVIEW(code)  2-stage; may fan-out by DIMENSION (security/perf/a11y/contract) via amaw Adversary.
8.  QC            loom / amaw Scope Guard — diff vs spec.
9.  POST-REVIEW   HUMAN STOP + WAIT — the junction you control (NOT auto). Suggest /review-impl for load-bearing code.
10. SESSION       Overwrite the ▶ NEXT block in SESSION_HANDOFF; land in the same commit.
11. COMMIT        Stage changed files only; message names slices + reconcile. Push only on explicit approval.
12. RETRO         add_lesson if notable.
```

## BUILD + RECONCILE — coordinator pseudo-flow

```
You (main session) are the /warp COORDINATOR. Pre-flight:
  python scripts/warp/worktrees.py check --task <slug>     # refuse if stale warp worktrees linger
  COMMIT the DESIGN artifacts first (frozen interface + manifest + slice briefs), THEN re-run
    `workflow-gate.py slices <manifest> --verify-frozen`.  ← dry-run finding D1:
    Agent(isolation:worktree) bases each slice on a COMMITTED ref (HEAD), never the
    orchestrator's uncommitted edits. An uncommitted frozen file / brief is invisible to
    the slices. --verify-frozen now BLOCKs a frozen path that isn't committed in HEAD.

BUILD — fan out (one message, all slices, concurrent):
  For each slice in manifest.yaml:
    - Read scripts/warp/slice-runner-prompt.md; interpolate
      <TASK> <SLICE_ID> <SLICE_LABEL> <BRANCH=warp/<slug>/slice-<id>> <WRITES> <READS> <FROZEN_INTERFACE> <ACCEPTANCE>
    - Spawn Agent: { subagent_type: general-purpose, isolation: "worktree",
                     run_in_background: true, prompt: <interpolated> }
  Receive each slice's ≤1500-token structured return (runtime auto-notifies; no polling).
    - result DONE      → record branch + commit_sha
    - result BLOCKED with needs_out_of_scope_write | frozen_interface_insufficient
                       → a DESIGN signal: STOP, return to DESIGN (re-slice / re-freeze). Do NOT patch around it.

RECONCILE (5.5):
  - Merge each DONE slice branch onto the base in merge_plan.integrate_order.
    Disjoint write-sets ⇒ no conflict expected. A conflict on a write-set ⇒ HALT_REDESIGN
    (the disjointness assertion was violated → the manifest is wrong, re-DESIGN).
  - Run the full suite (Healer mindset: fix root cause in product code, never weaken tests).
  - Rebuild touched service images before the cross-service smoke (stale images false-green).

Cleanup (after COMMIT): python scripts/warp/worktrees.py cleanup --task <slug> --delete-branches
```

## The disjointness dividend

Reconcile is near-trivial **by construction**: `workflow-gate.py slices` already proved
every slice's write-set is path-prefix-disjoint, and slices may not write the frozen
interface. So integrating N branches touches N non-overlapping file sets — a sequential
merge cannot conflict on them. If it *does* conflict, that is not a merge to resolve —
it is proof the manifest was wrong, so the response is **HALT_REDESIGN**, not a patch.
This is why `/warp` can skip RAID's heavy Tank conflict-resolution machinery.

**Caveat (the dividend's limit):** disjoint write-sets guarantee no *file* collision —
NOT semantic independence. A slice that under-declares a `reads` dependency can still
compile-then-break at merge with zero file conflict. Catching that is the phase-3
Adversary's job (spec §10), not the validator's. "Disjoint", not "provably independent".

## Reuse map (don't rebuild)

| Need | Asset |
|---|---|
| Independence gate | [`scripts/workflow-gate.py slices`](../../scripts/workflow-gate.py) → [`scripts/warp/slice-manifest-validate.py`](../../scripts/warp/slice-manifest-validate.py) |
| Manifest template | [`docs/warp/EXAMPLE-manifest.yaml`](../../docs/warp/EXAMPLE-manifest.yaml) |
| Slice sub-agent prompt | [`scripts/warp/slice-runner-prompt.md`](../../scripts/warp/slice-runner-prompt.md) |
| Worktree lifecycle | [`scripts/warp/worktrees.py`](../../scripts/warp/worktrees.py) (check / list / cleanup) |
| Slice brief shape | [`docs/raid/cycle_briefs/TEMPLATE.md`](../../docs/raid/cycle_briefs/TEMPLATE.md) |
| Cold-start Adversary / Scope Guard | [`docs/amaw-workflow.md`](../../docs/amaw-workflow.md) |
| Reconcile (Healer mindset) | [`docs/raid/RAID_WORKFLOW.md`](../../docs/raid/RAID_WORKFLOW.md) §4 Phase 6 |
| Human junction | [`.claude/commands/loom.md`](loom.md) POST-REVIEW |

## Operational notes

- Run all scripts from the **repo root** with **`python`** (not the bash wrappers — they
  fail on this project's Windows box).
- The whole `.workflow-state.json` track is the **orchestrator's**; slices are stateless
  sub-agents that just build + return. Don't have slices call the gate.
- `docs/warp/<task-slug>/` holds the manifest + slice briefs for the run (durable record).

## What /warp does NOT do

- Does NOT slice a task that can't be made independent — it **falls back to `/loom`** (no restart, same session).
- Does NOT skip phases or the PO checkpoints (CLARIFY end, POST-REVIEW are human STOPs).
- Does NOT auto-gate POST-REVIEW (that's RAID) — the human controls the merge junction.
- Does NOT let a slice edit outside its write-set, the frozen interface, or a shared-write magnet.
- Does NOT push to origin without explicit approval.
