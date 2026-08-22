# RUN-STATE — the space substrate has a place to spawn on, and nothing that spawns

**Reconciles:** Foundation Invariants **I1–I19** · Data Plane channels **DP-Ch1–Ch37** · No-Defer-Drift · Destructive DB ops in tests · Cross-Instance Data Access Policy — and the reconciliation is this run's whole subject rather than a formality. **Reality bootstrap is already modelled**: `provision_flow` + `reality_seeder` run at provision time and record their phases as *validate · fetch_book_meta · load_checkpoint · transition_active*. **None of them is a space phase**, and `world_seed`/`space_view` — the two modules the predecessor board added — have zero callers outside `tests/`. So nothing here is a new model; every lane-A row is a CALLER into a bootstrap that already exists. No-Defer-Drift is cited because `A5` may legitimately produce register rows instead of code, and each one must earn its trigger through the 5-point gate rather than by saying *"missing infra"*.

> **Read this file FIRST after any compaction.** Then `git log`, then continue. Nothing in this run
> lives only in the conversation.
>
> - **Started:** 2026-08-22 · **Branch:** `feat/game-logic` · **Base `HEAD`:** `ff58f69b1`
> - **Predecessor:** [`2026-08-02-space-substrate-RUN-STATE.md`](2026-08-02-space-substrate-RUN-STATE.md)
>   — 35/35, register empty. This run is what its closure revealed, not what it left undone.
> - **Sibling boards this run finishes rows on:** [reality-layer](2026-08-08-reality-layer-RUN-STATE.md) ·
>   [kernel-state-to-screen](2026-08-21-kernel-state-to-screen-RUN-STATE.md) ·
>   [game-tier-build](2026-08-06-game-tier-build-RUN-STATE.md) · [lore-bible](2026-08-14-lore-bible-RUN-STATE.md)

---

## 0 · The commitment

**PO, 2026-08-02, in substance — the thesis the predecessor was built on:**

> **The map is where everything in the game happens.**

and the request that opened it:

> **"resume to our reality map design to make place where actor can spawn on"**

**The place exists. Nothing spawns on it.** That sentence is this run's entire subject.

**DONE means:** a reality provisioned by the ordinary path comes up with a world, an actor bound to a
node in it, and a caller that can answer *"what is here"* — each proven by running the production
path, not a test fixture. **And** the four rows other boards still hold open are closed or carry a
mechanism. Not more tables. **Callers.**

---

## 1 · Why this run exists — the admission, measured 2026-08-22

The predecessor board closed at 35/35 with an empty register, and every row on it was real. Then the
producers were counted:

| what the space run built | production producer |
|---|---|
| `0024_map_layout` | ✅ `world_seed.rs:462` |
| `0026_place` | ✅ `world_seed.rs:477` |
| `0025_entity_binding` | ❌ **tests only** |
| `0028_portal` | ❌ **tests only** |
| `0029_layer_registry` | ❌ **nothing at all** |
| `0030_encounter` | ❌ **nothing at all** |

And one level up, the two modules the run added are themselves unreached:

- **`world_seed::seed_world` (`world_seed.rs:425`) — zero callers outside `tests/`.**
- **`space_view::assemble` (`space_view.rs:124`) — zero callers outside `tests/`.**

Both are `pub mod` in `lib.rs` and neither is on a route, in a bin, or in a bootstrap path.
`reality_seeder` — the thing that actually runs when a reality is born — records its phases as
*validate · fetch_book_meta · load_checkpoint · transition_active*. **There is no space phase.** Its
`book_reader` docs even say it reads *"initial geography"*, and nothing consumes that into a node.

### The finding, and it is not new — it is `3C` at seven times the scale

[reality-layer §3C](2026-08-08-reality-layer-RUN-STATE.md) states the rule this repo already learned:

> *"An unforgeable mint is dead code until something can mint."* `RealityId` was written, tested and
> **reverted inside an hour** because `new_verified` had no in-crate caller — and
> `#[allow(dead_code)]` was refused as the pragma-as-exemption shape.

**One type was reverted for this property. Six tables and two modules shipped with it and the board
was called done.** The difference is not principle, it is *visibility*: `cargo clippy -D warnings`
sees an uncalled crate-private constructor, and **nothing in this repo sees an uncalled `pub` module
or an unwritten table.** That absence is `C1`'s subject and it is why `C1` is on this board rather
than in a backlog.

**The tell to remember:** the predecessor asked *"is every row closed?"* and the answer was honestly
yes. Nobody asked *"can anything reach what the rows built?"* **A board measures what it listed.**

---

## 2 · Invariants this run may not quietly break

| # | Invariant | Source |
|---|---|---|
| I-1 | A new type/table lands **with its producer**, never before | reality-layer §0.6c, proven by `3C` |
| I-2 | `SDF-A31` — an authored node is a `channels` row; a generated cell is an index, **never a row** | doc 41 |
| I-3 | `SDF-R1` — the existence ladder is an **INDEX, not a field** (measured 92.4× at 0.1 % live) | doc 41 |
| I-4 | `SPG-A3` containment is a **matrix validated on write**, never an ordinal ladder | doc 36 |
| I-5 | `SDF-A4` — no hash-ordered iteration, no allocation-derived ordering, no tie-break by display name | doc 41 |
| I-6 | `SDF-A26` — a reader chooses a **budget**, never a field set | doc 41 |
| I-7 | Anything that WRITES goes to a **throwaway database** whose name carries a `test` marker | CLAUDE.md |
| I-8 | A gate's baseline moves in the **same commit** as the code that moved it | repo rule |
| I-9 | **`NV-1/2/3`** — a check that cannot fail is not a check; prove each with a bite | non-vacuity discipline |

---

## 3 · The board

> Ids are **backticked** deliberately. `scripts/goal-prompt.py` cannot read a bolded id — that is
> `C1` — and a board describing the blindness while being invisible to the tool would be the joke
> writing itself.

### Lane A — producers · *the thesis*

| # | Row | Status | Evidence |
|---|---|---|---|
| `A1` | **MEASURE the bootstrap seam before touching it.** What does `provision_flow` → `reality_seeder` actually execute end to end, in order, on a real provision? Which phase could own space, and what does `book_reader`'s *"initial geography"* return today? | `[ ]` | |
| `A2` | **`seed_world` gets a caller** — a provisioned reality comes up with a world. Bounded by `A1`'s answer; if the seam is a phase, it is a phase | `[ ]` | |
| `A3` | **SPAWN — `entity_binding` gets a producer.** The row the whole predecessor run existed to make writable. An actor arrives at a node by the production path | `[ ]` | |
| `A4` | **`space_view::assemble` gets a caller** — something asks *"what is here"* and gets an answer over the wire | `[ ]` | |
| `A5` | **`portal` / `encounter` / `layer_registry` — DECIDE, do not build on spec.** Each either gets a producer this run or a register row **with a trigger**. `I-1` cuts both ways: a table with no producer is the defect, and a producer with no consumer is the same defect one layer up | `[ ]` | |

### Lane B — the rows other boards still hold open

| # | Row | Status | Evidence |
|---|---|---|---|
| `B1` | **reality-layer `3C` + `3D` as ONE commit** — `ids.rs` re-added, `CapabilityToken`, `trait ControlPlane`, `SessionContext`, the `#[cfg(test)]` double. The producer `3C` was waiting for is the control-plane seam, and `3D` *is* that seam | `[ ]` | |
| `B2` | **kernel-state `G5` automated.** Its status cell ticks the MANUAL leg and leaves the AUTOMATED leg unticked — the browser render is proven by hand and by nothing that runs again | `[ ]` | |
| `B3` | **game-tier `1b5-*` — eight rows marked `⬜ OPEN` at `:1700`–`:1707` that a discharge table at `:1787` closes.** The work shipped; the register was never told | `[ ]` | |
| `B4` | **lore-bible `LB1`/`LB2`/`LB3` — unpark or park with a trigger.** `LB0` closed by finding a 252-file `lore-enrichment-service` already doing `LB2`'s sweep. A board parked for a *good* reason still needs the reason written where the next reader looks | `[ ]` | |

### Lane C — the tooling that hid the work

| # | Row | Status | Evidence |
|---|---|---|---|
| `C1` | **`goal-prompt.py` reads ZERO rows from 30 of 51 boards.** Including `2026-08-02-actor-substrate` — the predecessor's own sibling, the board whose METHOD the space run copied — which carries **218 bolded pipe-rows** and parses as empty. A tool that decides what a session works on, blind to 59 % of the boards | `[ ]` | |
| `C2` | **`space_view` — the two findings §19 produced and never made rows.** **14.10 ms/assembly is 14 % of a 100 ms tick**, and the shape is an **N+1**: the ancestor walk issues two queries per level. Ancestors are **272 B of 511 B — 53 %** at four levels, ~1 KB at `DP-Ch1`'s full 16. A single recursive CTE collapses the query side | `[ ]` | |
| `C3` | **The two gates refused on their measurements — re-decide or record.** A `reality_id`-scope gate needing live-schema introspection; a half-applied-annotation gate that produced **47 mostly-false candidates**. Each was correctly refused. Neither has a row saying what its replacement needs | `[ ]` | |

---

## 4 · Decisions taken in advance

| # | Decision | Reason |
|---|---|---|
| `D-1` | **`A1` precedes `A2`, and `A2` precedes `A3`.** Measure the seam, then reach it, then spawn into it | The predecessor's own `D-1`: measure before designing. Guessing the seam is how `world_seed` got written against a bootstrap nobody checked |
| `D-2` | **No new table this run.** Every row is a caller, a decision, or a register correction | Six tables with two producers is already the defect. Adding a seventh treats the symptom as the goal |
| `D-3` | **`A5` may legitimately produce NOTHING but register rows.** A trigger is an outcome | `SDF-A19` scale-bound `Domain → World` by a rule, not a quota, and was right to. A producer built to satisfy a board is the speculative-generality this repo already refuses |
| `D-4` | **Scope is the GAME track.** The 26 Writing Studio / Work Assistant / Book-Package boards are a different product in the same monorepo and are **explicitly OUT**, not forgotten — see `§6 OUT-1` | Bundling a 192-slice board for another product into a spine run makes both worse. Named so it cannot be mistaken for closed |
| `D-5` | **`C1` is not a chore.** It ships in this run because it is the mechanism that would have caught `§1` | A finding whose fix is deferred is a finding that recurs. This one already recurred: `SPG-Q6`, `SDF-Q16`, eight retired-row citations, and now six tables |

---

## 5 · Brainstorming queue — answer BEFORE the lane-A row that needs it

**These are open questions, not tasks.** Each names what would settle it, and each blocks exactly one
row. A question that reaches its row unanswered stops the row, not the run.

| # | Question | Blocks | What settles it |
|---|---|---|---|
| `Q1` | **Who owns spawn?** world-service (it owns the tables), actor-hub (it owns the actor), or the control plane (it owns the binding)? `entity_binding` is a *join between two owners* and that is exactly why it has no producer | `A3` | Follow an existing two-owner write in this repo and copy its answer. `actor_control_flow.rs` already crosses this line — read what it did |
| `Q2` | **Is spawn a command, an event, or a proposal?** The proven pipeline is `browser → proposal → spine → hub → events → DOM`. Spawn either joins it or declares why it is bootstrap-only | `A3` | `G7`/`G8`'s measured path. If spawn is bootstrap-only it never gets a proposal — say so and cite the reason |
| `Q3` | **Does a world get seeded at provision, or on first entry?** `SDF-R1` measured lazy materialization at **92.4× at 0.1 % live** — that argues first-entry. Provision-time argues determinism and a simpler seam | `A2` | The `A1` measurement plus `SDF-R1`'s numbers. **Do not re-derive `SDF-R1`; re-read it** |
| `Q4` | **`layer_registry` has no producer because layers have no AUTHOR.** Is that `authorable-surface`'s job, a ruleset-ingest job, or genuinely not yet? | `A5` | Whether any shipped path writes a ruleset digest today. If none does, `layer_registry` is correctly empty and gets a trigger, not a producer |
| `Q5` | **`portal` rows exist; nothing traverses one.** Is movement in scope for this run, or is `portal` a `Q4`-shaped park? | `A5` | `TVL_001`/`08_realtime_movement_authority` — do they already name an owner? If they do, this is a citation, not a design |
| `Q6` | **Is `C2`'s 14 ms a problem yet?** 14 % of a tick is alarming per-assembly and irrelevant at one assembly per player-action | `C2` | Count expected assemblies per tick from the proven pipeline. **`SDF-Q15`'s own lesson: bounded is not free — and neither is it automatically dear** |

---

## 6 · Open register

| id | what | mechanism / what would settle it |
|---|---|---|
| **OUT-1** | **The 26 Writing Studio / Work Assistant / Book-Package boards are out of scope and NOT closed.** Live open rows: `studio-tool-gui` **192 slices, every one `TODO`, never started** · `book-package` 11 open + 3 half-built (`B1` blocked on `M6.1`, *registered but not implemented*) · `work-assistant` `E1`/`E2`/`E7` 🅿 and two rows marked `✅ partial` · `all-tracks-clear` `M2`/`M7`/`M8`/`M10` · S2/S4/S5/S8 residue | A PO decision to resume that product. Recorded here **only** so the 2026-08-22 overview cannot be misread as "44 of 51 closed, nothing left" |
| **OUT-2** | **`3E` is 🅿 PARKED behind reality-layer slice 5** and stays parked — `B1` does not unpark it. Its own board measured **880 across 99 files** against a plan that still says 457 | A production `ControlPlane` implementor exists |

---

## 7 · Drift register

**A run that ends with an empty drift log is not clean — it is dishonest.**

| id | what happened |
|---|---|
| **PD-1** | **The overview that produced this plan was wrong on its first pass, and wrong in the safe-looking direction.** Reading the boards with `goal-prompt.py`'s row parser reported **0 rows for 30 boards**, and *a board whose rows are invisible is indistinguishable from a board with none open*. It very nearly shipped as **"49 of 51 closed"**. Caught only because `space-substrate` reported 5 rows and the session had just ticked 24 of them. **The disagreement between a tool and a thing I had just done is the whole detection**, and on any board I had not personally worked it would not have existed. This is `C1`'s real severity |

---

## 8 · RESUME

**RESUME: `A1` — measure the `provision_flow` → `reality_seeder` seam end to end before touching it. Nothing in lane A may be written against a bootstrap path that has not been read at `HEAD`. `Q3` (provision-time vs first-entry seeding) is answered by that measurement plus `SDF-R1`'s existing numbers — re-read them, do not re-derive them.**

```goal-prompt
goal: the space substrate has producers reachable by the production path, and the four boards still holding rows open are closed or carry a mechanism
lanes: |
  A producers = A1, A2, A3, A4, A5
  B boards    = B1, B2, B3, B4
  C tooling   = C1, C2, C3
rules: |
  1 A check that cannot fail is not a check. Prove every one with a bite.
  2 Measure before building; re-measure rather than recall.
  3 Anything that WRITES goes to a throwaway database. A count is a read; an INSERT is not.
  4 A gate's baseline moves in the SAME COMMIT as the code that moved it.
  5 Commit by pathspec. Never `git add -A`.
  6 A new type or table lands WITH its producer, never before.
  7 Record near-misses in the drift register as they happen, not at the end.
  8 NO "BLOCKED" that means "I would have to build it".
note: |
  No new table this run. Every row is a caller, a decision, or a register correction.
  The Writing Studio / Work Assistant / Book-Package boards are OUT (see OUT-1) and are not closed.
stop: |
  a sealed decision turns out to be wrong
  an action would be destructive or irreversible without authorisation
```
