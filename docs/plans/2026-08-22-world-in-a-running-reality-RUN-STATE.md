# RUN-STATE — the producers are reachable, and no running reality has a world

**Reconciles:** Foundation Invariants **I1–I19** · Data Plane channels **DP-Ch1–Ch37** · No-Defer-Drift · Destructive DB ops in tests · Admin Action Policy — and the reconciliation is again the subject rather than a formality. **Reality provisioning, per-reality migration and the space schema all already exist**: `provision_flow` + `provisioner` run 12 steps including `seed_world_structure`, `services/migration-orchestrator/cmd/migrate` is the per-reality migrator, and `0022`–`0030` are registered in the manifest. Nothing here is a new model. The gap is that **the nine realities on this shard were provisioned before those migrations existed and were never brought forward**, so every table the previous board gave a producer to is absent from all of them.

> **Read this file FIRST after any compaction.** Then `git log`, then continue.
>
> - **Started:** 2026-08-22 · **Branch:** `feat/game-logic` · **Base `HEAD`:** `f1e09a64d`
> - **Predecessor:** [`2026-08-22-space-producers-RUN-STATE.md`](2026-08-22-space-producers-RUN-STATE.md) — 13/13. This run is what its closure revealed, exactly as that board was what the one before it revealed.

---

## 0 · The commitment

**PO, 2026-08-02:** *"The map is where everything in the game happens."*
**PO, 2026-08-22:** *"make place where actor can spawn on."*

The place can now be built and an actor can now be put in it. **No running reality has either.**

**DONE means:** a reality that exists on this shard today has a world, an actor sited in it, and a browser that shows where that actor is — each proven by running the production path. **Not a fresh throwaway. One of the nine.**

---

## 1 · Why this run exists — measured 2026-08-22 at `f1e09a64d`

| what | measured |
|---|---|
| realities on this shard | **9** (`lw_reality_*`) |
| newest migration applied in them | **`0019_channels`** |
| `map_layout` / `entity_binding` / `place` / `portal` / `layer_registry` / `encounter` | **the tables DO NOT EXIST** in any of the nine |
| `actors` (`0022`) | absent too — so the actor registry has no home there either |
| realities with a world | **0** |

The previous board proved the producers are reachable: `seed_world` ← `provisioner_live.rs:632`, `assemble` ← `space.rs:106`, `site_in_cell` ← `actor_registry.rs:74`/`:120`. **All three are reachable and none has ever run against a reality anyone uses.**

### The shape, for the third time

`apply_migrations` was rewritten on 2026-08-08 to apply every manifest migration — and that only ever affected realities provisioned **after** that date. The nine predate it. **A fix that only reaches new subjects is `1b5-H1`'s shape** (*"the fix reached one site of N"*), and `1b12-05` already recorded that *"registration is necessary and not sufficient"*.

**The tell:** the last three boards each ended by discovering that the thing they built had no consumer. This one starts from the consumer and works back.

---

## 2 · Invariants this run may not quietly break

| # | Invariant | Source |
|---|---|---|
| I-1 | Anything that WRITES goes to a **throwaway database** unless the PO authorises otherwise — **and this run's whole subject is NON-throwaway realities**, so `A2` is the row that needs explicit authorisation | CLAUDE.md |
| I-2 | Destructive or irreversible admin actions are **double-approval** | Admin Action Policy |
| I-3 | A migration is applied through the **orchestrator**, never by hand-running SQL | `migration-manifest-gate` |
| I-4 | A new type or table lands **with its producer** | reality-layer §0.6c |
| I-5 | A check that cannot fail is not a check; prove each with a bite | `NV-1/2/3` |
| I-6 | A gate's baseline moves in the **same commit** as the code that moved it | repo rule |

---

## 3 · The board

### Lane A — a running reality gets a world

| # | Row | Status | Evidence |
|---|---|---|---|
| `A1` | **MEASURE the migrate path before touching a real reality.** What does `migration-orchestrator/cmd/migrate` do to an existing reality — which migrations, in what order, with what dry-run? Does it read the manifest, and does it refuse a reality it cannot reach? **Read-only.** | `[ ]` | |
| `A2` | **The nine realities come forward to the manifest head — or a decision says which do not.** `I-1` applies: these are NOT throwaways. Dry-run first, on one reality, with the diff shown; **the PO authorises before any live write** | `[ ]` | |
| `A3` | **Something DECLARES a world** — `OR-3` from the previous board. Every caller passes an empty declaration today, so the seed step reports `Skipped` on every path. Where the declaration LIVES is this row's decision | `[ ]` | |
| `A4` | **An actor is sited in a running reality and the browser shows where it is.** The end of the PO's sentence. Extends `kernel-state-demo.sh`, which already proves browser ← event ← spine | `[ ]` | |

### Lane B — the registers this run keeps finding stale

| # | Row | Status | Evidence |
|---|---|---|---|
| `B1` | **game-tier's `RealityId + SessionContext` row still reads `⬜ board TBD`** — a **fourth** place the finished `3C`/`3D` work is not reflected, after reality-layer, the `1b5-*` rows and `G5`. Found while verifying the previous goal | `[ ]` | |
| `B2` | **reality-layer `3E` — decide.** Re-measured 2026-08-22: **195 `reality_id: Uuid` against 11 typed, across 48 files.** It is parked behind slice 5. Either work it or re-park it against **that** number rather than the stale 880/99 | `[ ]` | |

### Lane C — the tooling, again

| # | Row | Status | Evidence |
|---|---|---|---|
| `C1` | **`OR-5` — 15 boards still parse empty**, a fourth dialect family: a plain-text id, an id containing a space or `·`, a marker sitting *before* the id. Needs its OWN measurement: the previous widening produced **three false opens on a 35/35 closed board** before it was tightened | `[ ]` | |

---

## 4 · Decisions taken in advance

| # | Decision | Reason |
|---|---|---|
| `D-1` | **`A1` is read-only and precedes `A2`.** No live reality is written to until the migrate path has been read at `HEAD` and dry-run | The nine are not throwaways. `orphan_scan` exists because a half-finished provision is expensive; a half-finished migration on a live reality is worse |
| `D-2` | **`A2` STOPS for authorisation.** A live write to a non-throwaway database is exactly the STOP condition, and it is reached deliberately rather than by accident | CLAUDE.md's destructive-ops rule, and `I-2` |
| `D-3` | **`A3` may NOT hardcode a starter world.** The previous board refused this twice and the reasoning has not changed: a structure every reality inherits that no author declared is rot | `A2`/`A5` of the predecessor |
| `D-4` | **`A4` uses the demo stack, not a new one.** `kernel-state-demo.sh` already stands up publisher → stream → room → browser and is re-runnable | `G2`'s reason: a demo nobody can re-run is wrong within a week |

---

## 5 · Open register

| id | what | mechanism / what would settle it |
|---|---|---|
| **OR-1** | **Three tables stay deferred with triggers** — `portal`, `encounter`, `layer_registry` — and this board does not reopen them. `space_producer_triggers.rs` reds when each owner arrives | already mechanised; `deferral-gate` counts them |
| **OR-2** | **`reality_seeder` still has 0 production constructors.** Decided in the predecessor's `A2`: the `seeding` stage works synchronously and the orchestrator is a named debt | seeding work outgrowing an HTTP request |

---

## 6 · Drift register

**A run that ends with an empty drift log is not clean — it is dishonest.**

| id | what happened |
|---|---|
| **WD-1** | **The verification script for the previous goal was WRONG, and it said the goal was not met.** It took the FIRST `#[cfg(test)]` in a file as a cut-off; `provisioner_live.rs` has one at line 483 followed by 250 lines of production, so the real `seed_world` call at 632 was filed as test and reported `prod=0`. **The controls did not catch it** — in both control files every `#[cfg(test)]` sits below every call site, so the cut-off happened to land correctly. *A control only proves what it exercises.* The tool can only UNDER-report, so no earlier conclusion changed |

---

## 7 · RESUME

**RESUME: `A1` — read `migration-orchestrator/cmd/migrate` at `HEAD` and dry-run it against ONE of the nine realities. Read-only. Nothing writes to a non-throwaway database until `A2`, and `A2` stops for authorisation (`D-2`). The measured starting point: nine realities, all at `0019_channels`, none of which has `map_layout`, `entity_binding`, `place` or `actors` at all.**

```goal-prompt
goal: a reality that already exists on this shard has a world, an actor sited in it, and a browser showing where that actor is
lanes: |
  A running reality = A1, A2, A3, A4
  B stale registers = B1, B2
  C tooling         = C1
rules: |
  1 A check that cannot fail is not a check. Prove every one with a bite.
  2 Measure before building; re-measure rather than recall.
  3 THIS RUN'S SUBJECT IS NON-THROWAWAY REALITIES. Read freely; STOP before any live write.
  4 A gate's baseline moves in the SAME COMMIT as the code that moved it.
  5 Commit by pathspec. Never `git add -A`.
  6 A migration reaches a reality through the orchestrator, never by hand-run SQL.
  7 Record near-misses in the drift register as they happen.
  8 NO "BLOCKED" that means "I would have to build it".
note: |
  No hardcoded starter world (D-3). A1 is READ-ONLY and precedes A2.
  A2 is expected to stop for authorisation -- that is the design, not a failure.
stop: |
  a live write to a non-throwaway reality has not been authorised
  a sealed decision turns out to be wrong
```
