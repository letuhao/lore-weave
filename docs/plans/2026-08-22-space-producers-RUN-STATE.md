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
| `A1` | **MEASURE the bootstrap seam before touching it.** What does `provision_flow` → `reality_seeder` actually execute end to end, in order, on a real provision? Which phase could own space, and what does `book_reader`'s *"initial geography"* return today? | `[x]` | **DONE 2026-08-22 — §3.1 below. The answer is worse than §1 assumed: there is no space phase because THERE IS NO SEEDING PHASE.** `RealitySeeder` prod callers **0** (controls 3 and 7) |
| `A2` | **`seed_world` gets a caller** — a provisioned reality comes up with a world. Bounded by `A1`'s answer; if the seam is a phase, it is a phase | `[x]` | **DONE 2026-08-22 — §3.3.** A 12th provision step `seed_world_structure`, called BETWEEN the two transitions so it runs while the reality is in `seeding`. 181 lib tests (178 → 181), **3 bites**, 3 baselines moved in the same commit |
| `A3` | **SPAWN — `entity_binding` gets a producer.** The row the whole predecessor run existed to make writable. An actor arrives at a node by the production path | `[x]` | **DONE 2026-08-22 — §3.4.** `spawn::site_in_cell`, atomic with actor creation, proven against real Postgres. **The orphan bite fires**: `actors 2 -> 3` when the transaction is removed. 183 lib tests + 4 live suites green |
| `A4` | **`space_view::assemble` gets a caller** — something asks *"what is here"* and gets an answer over the wire | `[x]` | **DONE 2026-08-22 — §3.5.** `POST /internal/v1/space/view`, internal-gated, budget REFUSED not clamped. 187 lib tests; route conformance green in both directions; **3 bites** |
| `A5` | **`portal` / `encounter` / `layer_registry` — DECIDE, do not build on spec.** Each either gets a producer this run or a register row **with a trigger**. `I-1` cuts both ways: a table with no producer is the defect, and a producer with no consumer is the same defect one layer up | `[x]` | **DONE 2026-08-22 — §3.6. All three DEFERRED with mechanisms, and `deferral-gate` moved 9/33 → 12/36 mechanised.** 3 triggers, 3 bites, 2 non-vacuity arms. `Q4`/`Q5` resolved |

#### 3.1 · `A1` — what the seam actually executes at `HEAD`

**`provision_reality` runs 11 frozen steps** (`PROVISION_STEPS`, *"frozen so external observers can
pin metric labels against them"*). Steps 9 and 10 are these, and they are **consecutive statements**:

```rust
// provisioner.rs:291-298
let seeding = effects.transition_to(req.reality_id, "provisioning", "seeding", &req.reason)?;
steps.push(io(seeding, "transition_to_seeding"));
let active  = effects.transition_to(req.reality_id, "seeding",      "active", &req.reason)?;
steps.push(io(active, "transition_to_active"));
```

**Nothing runs in the `seeding` stage. It is entered and left in two lines.**

`services/world-service/src/lib.rs:29` describes `reality_seeder` as the *"Background orchestrator: seeding → active flow"*, and
it is 1008 lines plus seven submodules. **It has zero production constructors** — all eleven
`RealitySeeder::new` sites are at or below `#[cfg(test)]` (`reality_seeder/mod.rs:573`); no bin, no
`main.rs`, no handler mentions it. Measured with a caller split that **takes controls**, because
"found no callers" and "the query is broken" look identical:

```
RealitySeeder::new         prod=0   test=11   [expect NONE]
world_seed::seed_world     prod=0   test=4    [expect NONE]
space_view::assemble       prod=0   test=1    [expect NONE]
place_and_provision        prod=3   test=0    [CONTROL expect SOME]   <- services/world-service/src/lib.rs:97, server/handlers/realities.rs:16, :118
existing_registration      prod=7   test=0    [CONTROL expect SOME]
```

**Two components both own `Seeding → Active`** — `provisioner.rs:296-298` and the seeder's final
phase at `reality_seeder/mod.rs:495-500` — **and the one that runs does no seeding.** A reality
reaches `active` synchronously inside the provision HTTP request (`server/handlers/realities.rs:118`).

**`book_reader`'s *"initial geography"* returns nothing.** `BookReader::list_regions` defaults to an
empty `Vec` (*"V1: regions are not seeded by the canon path ... geography is per-book SSOT"*), and
`Region` carries `region_id` + a name — **no coordinates and no `MapKind`**, so it could not feed
`map_layout` even if it were populated.

**What this DISCHARGES, and it narrows lane A.** `apply_migrations` was rewritten 2026-08-08
(`1b12-05`) from *"run `0001_initial.up.sql`"* to *"apply every migration the manifest registers, in
order, skipping those already in the ledger"*. **So `0024`–`0030` DO reach a provisioned reality.**
The tables are there. Only the writers are missing — which is exactly the plan's thesis and not one
step worse.

#### 3.2 · The decision `A1` forces on `A2`

**`A2` may NOT simply call `seed_world` from `reality_seeder`.** That would attach a caller to a
module that itself has no caller — **`I-1` violated one level up**, which is the failure `A5`'s note
names in advance. Whatever `A2` does must be reachable by something that RUNS today.

That leaves the seam question open in a specific, decidable way, and `Q3` now has teeth it did not
have when it was written: the provision path is **synchronous inside an HTTP request**
(`run_steps_blocking` → `spawn_blocking`), so provision-time world generation lengthens that request
by however long generation takes. Either the background orchestrator is resurrected (`OR-2`), or the
world is built on first entry, or `world_seed` is driven by an operator path. **`A2` decides and
writes the decision down; it does not get to leave it open.**

#### 3.3 · `A2` — the caller, and where it had to go

**A 12th provision step, `seed_world_structure`, between `transition_to_seeding` and
`transition_to_active`.** `A1` found the `seeding` stage entered and left in two consecutive
statements; this gives it a body. Ordering is the whole property: before the transition in, the
stage has not opened; after the transition out, the reality is already published as active.

**`ProvisionRequest` gains `#[serde(default)] world: Vec<NodeDecl>`, and empty means SKIPPED.**
It does **not** mean *"use a default world"*. A starter map every reality inherits, that no author
declared and no author can change without a code change, is exactly the rot this repo already names
— so the declaration is ingested data or it is nothing. The wire stays backward compatible: a caller
that has never heard of the field provisions as before and gets `Skipped`.

**Reachable three ways, and the operator path refuses a lie.** `POST /internal/v1/realities` carries
`world`; the `provision` CLI takes `--world <file.json>` — a **file**, because a world large enough to
matter does not belong in a shell history — and it **refuses an empty file** rather than silently
skipping, since an operator who typed `--world` meant one. `LiveEffects` connects to the reality's own
DSN, calls `seed_world`, and maps a `SeedReject` to `InvalidState` carrying the `place.*` / `map.*`
rule id, **not** to a shard failure: a refused declaration is the author's error and must not read as
the platform's.

**Three bites, each red for its own reason, each restored byte-identical (`cmp` rc=0):**

| bite | red with |
|---|---|
| seed moved AFTER `transition_to_active` | `left: [..seeding, ..active, seed]` vs `right: [..seeding, seed, ..active]` — *"the world must be written while the reality IS in `seeding`"* |
| a default world substituted when the declaration is empty | *"an empty declaration must report Skipped, got `Done(\"seed_world_structure\")`"* |
| `rename_all` dropped from `WorldScale` | `left: ["Pocket", .. "SuperContinent"]` vs `right: ["pocket", .. "super_continent"]` |

**Three baselines moved in the same commit (`I-8`):** `step_labels_are_frozen_strings` (the 12-label
literal), `contracts/observability/inventory.yaml` (which pins *"PROVISION_STEPS const (11 values)"*
**by name** — measured, not assumed: it is the only external consumer), and
`contracts/api/world/provisioning.v1.yaml` (`world` plus the `NodeDecl` / `PlaceDecl` schemas).

**`Eq` dropped from `ProvisionRequest`, deliberately.** `world` reaches `PlaceDecl.canon_ref`, a
`serde_json::Value` (`PF-D12` defers that schema), which is `PartialEq` and not `Eq` because it can
hold a float. **The derive is gone because the type can no longer make `Eq`'s promise**, not because
the compiler complained.

**And the OpenAPI enum is a promise to callers outside this repository**, so
`the_wire_spelling_of_every_kind_and_scale_is_pinned` asserts all thirteen strings in Rust — renaming
a variant is a source-compatible edit that would otherwise break every external caller in silence.

#### 3.4 · `A3` — spawn, and the property that makes it worth having

**`spawn::site_in_cell` takes a `&mut PgConnection`, not a `&PgPool`, and that is the whole design.**
The actor row and its `entity_binding` land together or neither does. A pool would let the binding
commit independently of whatever created the entity, which is the orphan this module exists to make
impossible — and an actor with no binding has **no collector at all**: `orphan_scan` does not look at
this table, so it is strictly worse than the half-provisioned reality the repo already designed
against.

**`Q1` answered by copying, not deciding.** `entity_binding` is a join between two owners — the
registry knows what an entity IS, the space tree knows where a place is — which is exactly why it had
no producer. `actor_registry::create_actor` already holds both facts in the reality's own database, so
spawn rides the same path, same database, same transaction. **`Q2`: spawn is an ADMIN act.** An actor
is created by an operator or a bootstrap, never by itself, so the act that puts it somewhere is the
same kind of act that brought it into being. A player-initiated MOVE is a proposal; **arriving is not**.

**What spawn refuses to choose.** `lifecycle_state` is a declared ordinal (`0025`'s `D-12`: *"ONE
REALITY'S VOCABULARY, not the engine's"*), and no reality has declared one —
`contracts/meta/transitions.yaml` carries `reality` and nothing for entities. So the caller supplies
it and the CLI takes **all three of `--at`/`--entity-type`/`--lifecycle-state` or none**: a partial
siting has no default to complete it.

**Measured, against real Postgres, in a throwaway that dropped:**

```
A3 SPAWN (real Postgres)
  unsited actor          : entity 1 , 0 bindings
  sited actor            : entity 2 -> cell 1
  refused siting         : actors 2 -> 2 (no orphan)
  double siting          : refused
```

**The bite** — commit the actor row before siting, as the code did before `A3`:

```
THE ORPHAN IS REAL: the binding was refused but 1 actor row(s) survived (2 -> 3).
An actor that exists with nowhere to be has no collector -- `orphan_scan` does not
look at this table
```

Restored byte-identical (`cmp` rc=0), green again. **`adopt_actor` got the same transaction**, and
that is a second fix rather than symmetry: its own comment already warned that a committed row with an
un-advanced identity sequence collides on the next allocation and offered *"re-run the adopt"* as the
repair. A transaction is strictly stronger — nothing lands, so the re-run is safe by construction.

**Found while registering the suite, and it is `C4`:** four live suites were on disk in **no registry
row at all**, three of them from the predecessor run. 23 → 27, and all four then failed the gate's
skip-announcement rule — a suite that did nothing was reading as a pass, which is **drift 11 exactly**.

#### 3.5 · `A4` — the view, over the wire

**`POST /internal/v1/space/view`.** A POST for a read, for the reason the surface already gives at
`/actor-control/subject`: the request names the thing it asks about, so on a public edge it would be
an **oracle over the shape of a world**. `Gate::Internal` for that, not for symmetry.

**`SDF-A26` is honoured structurally** — the body carries caps, never a field list. There is no way to
ask for *"just the occupants"*, because which layers render is the layer owner's declaration.

**A budget over the ceiling is REFUSED, not clamped.** Clamping would answer a smaller question and
label it as the answer to the one asked — the same defect `SpaceView::truncated` exists to prevent one
layer down. `MAX_SECTION = 200` is **binary capacity, not a world limit**: it bounds what one request
costs this process and says nothing about how many doors a room may have. A world that wants a 40-door
plaza is not asking for a bigger request.

**Three bites:**

| bite | red with |
|---|---|
| the route registered but NOT documented | the pre-existing `route_conformance` test, unforced: *"this service serves 1 operation(s) no contract documents: `[("post", "/internal/v1/space/view")]`"* — **both directions**, plus the gate-agreement arm |
| the ceiling CLAMPS instead of refusing | `left: 500, right: 400` — clamping let the request reach a database that is not there, which is exactly what the test claims the ceiling prevents |
| the route mounted OUTSIDE the internal layer | `left: 422, right: 401` — *"the space view must be gated"* |

The second bite is the useful one to keep: the test asserts the ceiling is checked **before** a reality
is bound, and it can only make that claim because `test_state`'s pool points at `127.0.0.1:1`. **A
ceiling enforced after the expensive work is not a ceiling**, and the 500 is what that looks like.

`to_problem` became `pub(crate)` rather than being copied: a second mapping would be a second opinion
on which faults are the caller's, which is the drift its own doc argues against.

#### 3.6 · `A5` — three triggers, and a measurement I took from a document

**All three are DEFERRED, and `D-3` said in advance that a trigger is an outcome.** Each has a named
owner and none of those owners is doing its job:

| table | owner | measured state 2026-08-22 |
|---|---|---|
| `portal` | `TVL_001` → `travel-service` | **the crate EXISTS** — 18 lines, *"Cycle 0 scaffold … compiles empty and has no behavior"* |
| `encounter` | `COMB_002` `tactical_grid` / `combat_session` | no such service, scaffold or otherwise |
| `layer_registry` | **nobody, and that is the finding** | `LayerDef`'s whole vocabulary absent from the authorable surface |

**A deferral that only a document remembers is a wish**, so each is an asserted trigger that reds on
arrival — the shape `deferral-gate`'s own docstring names. `deferral-gate` went from **9 of 33** to
**12 of 36** carrying a mechanism that changes colour by itself, which is the gate confirming these
are code and not prose.

**`Q4` resolved, and it is sharper than the question.** `layer_registry` is empty because **"layer"
means two different things**: `RLS-A3`'s ruleset layer is a priority stack of authored documents; doc
41 §4's feature layer is a data layer bound to a `MapKind`. The authorable surface enumerates only the
first — `home_kinds`, `update_policy`, `lifecycle_policy`, `projection` and `edge_policy` appear
**zero** times in it. **The registry is correctly empty, not forgotten**, and the trigger is the PO's
founding thesis pointed back at itself: *"every new feature will probably attach one more data layer
onto the map."*

**`Q5` resolved as a citation, not a design** — exactly as `Q5` predicted it might be. `TVL_001` already
names the owner; nothing needed deciding.

**THE TRIGGER CAUGHT ME ON ITS FIRST RUN, and that is the point of it.** The first version asked
`path.exists()` and went red immediately: `TVL_001` calls `travel-service` a *"NEW V1+30d service"*,
I read that as *"does not exist"*, and **the filesystem disagreed**. It has been on disk the whole
time. A directory is not an owner, so arrival is now BEHAVIOUR — the crate no longer calling itself a
scaffold, which is the service's own words and therefore honest in both directions. **`PD-4`.**

**Three bites, each restored:**

| bite | red with |
|---|---|
| `travel-service` stops saying "Cycle 0 scaffold" | *"`D-SPACE-PORTAL-NO-TRAVERSER` HAS WOKEN UP … give `0028_portal` a producer"* |
| a `services/combat-service` appears | *"`D-SPACE-ENCOUNTER-NO-OPENER` HAS WOKEN UP: services/combat-service has behaviour"* |
| `home_kinds` added to the authorable surface | *"HAS WOKEN UP: the authorable surface now carries `["home_kinds"]`"* |

Plus two **non-vacuity arms** the deferrals do not need but the mechanism does: `has_arrived` must
answer `true` for a real service, `false` for the scaffold and `false` for nothing — a predicate that
answered `false` to everything would make all three triggers permanently green.

**One home, not three.** The obligations live in the governed `deferral-registry` block; this section
is the reasoning. Rows were briefly added to `docs/deferred/DEFERRED.md` as well and **removed** —
that file is ungoverned history, and a third copy is the drift this run keeps finding.

### Lane B — the rows other boards still hold open

| # | Row | Status | Evidence |
|---|---|---|---|
| `B1` | **reality-layer `3C` + `3D` as ONE commit** — `ids.rs` re-added, `CapabilityToken`, `trait ControlPlane`, `SessionContext`, the `#[cfg(test)]` double. The producer `3C` was waiting for is the control-plane seam, and `3D` *is* that seam | `[x]` | **DONE 2026-08-22 — §3.7. ALREADY BUILT; the board was never told.** Verified by the rows' OWN criteria: `clippy -p dp -D warnings` **rc=0**, and the field → `pub` bite reds `forged_reality_id`. Both boards updated |
| `B2` | **kernel-state `G5` automated.** Its status cell ticks the MANUAL leg and leaves the AUTOMATED leg unticked — the browser render is proven by hand and by nothing that runs again | `[x]` | **DONE 2026-08-22 — §3.8. The suite was already written and had never been RUN.** 2 passed on chromium in ~1.9 s against the real stack; bite `XLEN 1→0` reds both. `FLOW-19`'s shape a second time |
| `B3` | **game-tier `1b5-*` — eight rows marked `⬜ OPEN` at `:1700`–`:1707` that a discharge table at `:1787` closes.** The work shipped; the register was never told | `[x]` | **DONE 2026-08-22 — §3.9. All eight verified against the CODE, not the discharge table, then ticked.** Bite: deleting `channels_id_positive` reds `dp-channels-schema-gate`. One row (`L3`/`L4`) is prose-discharged and says so |
| `B4` | **lore-bible `LB1`/`LB2`/`LB3` — unpark or park with a trigger.** `LB0` closed by finding a 252-file `lore-enrichment-service` already doing `LB2`'s sweep. A board parked for a *good* reason still needs the reason written where the next reader looks | `[x]` | **DONE 2026-08-22 — §3.10. STAYS PARKED — reopening is the PO's call — and the park now has a MECHANISM.** `scripts/lore-bible-park-gate.py`, wired, 7 self-test cases. `deferral-gate` 12/36 → **13/37** mechanised |

#### 3.7 · `B1` — verified, not built

**`3C` and `3D` were already done, and the board still said `⬜ blocked on a PRODUCER`.** `OR-4`
suspected it; `B1` verified it by the rows' **own** stated criteria rather than by presence:

| criterion (the board's words) | result |
|---|---|
| `3C.1` *"`cargo clippy -p dp --all-targets -D warnings` exit 0, i.e. no dead code, which is the whole test of whether the producer exists"* | **rc=0** |
| `3C.2` *"the pins READ, not blessed; bite = field → `pub` breaks it"* | **bitten** — with `pub`, the `E0603` arm disappears and `forged_reality_id` reds on the mismatch, leaving only `E0624`. Restored byte-identical |
| `3D.1`–`3D.4` | `CapabilityToken` + `is_live`, `trait ControlPlane` (`crates/dp/src/session.rs:245`), `SessionContext`, and a `#[cfg(test)]` double — all live |

**`3C` and `3D` did land as one unit, exactly as §0.6c required**, and the in-crate caller `3C` was
waiting for is `services/world-service/tests/support/mod.rs` binding through `ControlPlane`. `A3`
found it by needing a `dp::RealityId` — **the third time in a week that work shipped and the register
was never told** (`SPG-Q6`, the `1b5-*` rows, now this).

**`3E` is genuinely still open**, re-measured: **195 `reality_id: Uuid` against 11
`reality_id: dp::RealityId`, across 48 files.** That is a narrower predicate than the row's own
880/99 — declarations only — so the two numbers do not contradict. The embedding queue has adopted;
the rest has not. Stays parked behind slice 5, and `OUT-2` is unchanged.

**And `B1` produced `C1`'s second half.** Ticking `3C`/`3D` made the reality-layer board read
**0 open of 35** while `3E` was still `⬜` — because **`⬜` is not in `goal-prompt.py`'s vocabulary**.
Measured across every board: **27 open rows are invisible for that reason alone**, and they are not
incidental rows — they are `1b5-H1..L5` (`B3`'s subject), `LB1..LB3` (`B4`'s subject), `3E` and `W8`.

#### 3.8 · `B2` — the suite existed; nobody had ever run it

**`frontend-game/e2e/kernel-state.spec.ts` was already complete** — the roster assertion, the reason
the roster and not the turn number is the assertion, and a **non-vacuity arm** pinning the entry
inside the channel panel beside the `Strike` its own event enables. The board said `[ ] automated`
because the file **had never been executed**.

**This is `FLOW-19`'s shape exactly** — *"a deferral whose discharge procedure has never been run is a
promise, not a plan"* — one tier up: a TEST that has never been run is a claim, not a check.

Two skips stood in the way, and neither was a real blocker:

- `LOREWEAVE_E2E_FULL=1` — a flag `playwright.config.ts` had documented since it was written and
  **nothing had ever read**; this suite is its first consumer.
- a token auth-service issued, because `/play` **clears** a token it cannot use. `GO-2` had already
  cleared this on 2026-08-21 (*"auth-service was already running … `infra-auth-service-1` had been
  `Up (healthy)` on :8204 the whole time"*), and the suite's own run-instructions **omitted the token
  half entirely** — which is why it looked harder than it was.

**Measured, against the real stack** (`kernel-state-demo.sh`: spine committed 1 event, publisher →
`lw.events.<reality>` XLEN=1, world-service :7150, game-server :2577):

```
ok 1 [chromium] the roster entry is in the channel panel, not somewhere else on the page (1.8s)
ok 2 [chromium] a committed strike renders as a roster entry (1.9s)
2 passed (4.5s)
```

**The bite** — `DEL lw.events.<reality>`, XLEN 1 → 0:

```
Error: no roster entry — the committed event did not reach the fold.
       Check XLEN lw.events.<reality> and the publisher log.
```

and **`you are entity 1` still passed**, which is the precise part: the STATE hop failed while the
SUBJECT hop held. Re-seeded, both green again.

**Two real defects fixed while running it.** The spec hard-coded the driver's uuid while the token
supplies its own `sub`, and those must be one person — two constants in two files, neither naming the
other, so the drift was built in; it now takes `KERNEL_STATE_USER_ID`. And the run-instructions have
been replaced with the ones that were actually executed, including `--project=chromium`: without it
playwright launches firefox and webkit too, and **a missing browser BINARY reads exactly like a
failing assertion** — 4 "failures" that were nothing of the kind.

#### 3.9 · `B3` — verified against the code, not against the table that claimed it

**A table saying "discharged" is the same kind of claim the rows themselves were**, so each of the
eight was checked against what shipped:

| row | result |
|---|---|
| `H1` | the only surviving `channel_id UUID` is a **deliberately quoted superseded declaration**, with a reasoned `schema-gate: ok` pragma and the corrected table below it |
| `H2`/`H3` | `parent_depth SMALLINT GENERATED ALWAYS AS ((depth - 1)::smallint) STORED`, **inside the composite foreign key** |
| `H4` | the gate's own self-test: **11 schema mutations each VISIBLE** |
| `M4` | both constraints present **and enforced** — see the bite |
| `M5` | the gate's own self-test: **6 formatting changes each INVISIBLE** |
| `L3`/`L4` | **prose only.** A decision written down; nothing reds if it is forgotten. Recorded as such rather than counted as mechanised |
| `L5`/`L6` | `channels_lifecycle_guard` + `channels_dissolve_order_guard` exist; the idempotency validator covers **142 files across 2 trees**, against the **2** `L6` complained of |

**The bite, because presence is not enforcement.** Deleting `CONSTRAINT channels_id_positive` reds
`dp-channels-schema-gate` with `only in DP-Ch2: ['CHANNELS_ID_POSITIVE']`. Restored byte-identical.

**Three instances of one shape in a single day** — `SPG-Q6`, reality-layer `3C`/`3D` (`B1`), and now
these eight. And `goal-prompt.py` could not have caught any of them: all eight are marked `⬜`, which
`C1`'s second gap makes invisible.

#### 3.10 · `B4` — the park was sound; what it lacked was a mechanism

**The decision is: STAYS PARKED.** The reason is good and it is not a board's to overturn — opening
the track was a boundary violation, and its schema was being written against `progression_kinds` and
combat tuning, features the PO has not finished designing. *"A contract written against a feature that
does not exist"* is the orphan shape `orphan-model-gate.py` already refuses. **Reopening is the PO's
call.**

What was missing is the same thing `A5` supplied: the park **declared** a wake-up and had nothing that
changes colour by itself, so `LB0`'s finding lived only in a paragraph — and the board's own words for
carrying it forward were *"carry that finding forward when this track legitimately reopens"*, which is
a wish.

**`scripts/lore-bible-park-gate.py`**, wired in `.githooks/pre-commit`: reds the moment a lore-bible
**schema or producer** appears under `contracts/`, `crates/`, `services/`, `sdks/` or `clients/`, and
prints `LB0`'s finding at the only moment it matters — **before the sweep gets rebuilt**. Docs do not
trip it; a parked track has to stay thinkable. **It does not forbid the work. It forbids doing the
work without reading why the last attempt stopped.**

**Re-measured: 253 Python files, not 252.** Small, and the point of re-measuring rather than copying.

**Its own self-test caught its regex on the first run.** The boundary was ``, and `` needs a
non-word character while `_` **is** one — so `0099_lore_bible.up.sql` and `lore_bible_section`, the
two shapes the gate most needs to see, both failed to match. **Two of six arms red immediately.** Now
letter-guards, with `folklore_bible` added as a near-miss on the other side. 7 cases, all bite.

`gate-wiring-gate`: 119 → **120 gates, all wired**. `deferral-gate`: **12/36 → 13/37** mechanised.

**Lane B is CLOSED.**

### Lane C — the tooling that hid the work

| # | Row | Status | Evidence |
|---|---|---|---|
| `C1` | **Two dialect gaps, both measured. (1) `goal-prompt.py` reads ZERO rows from 30 of 51 boards.** Including `2026-08-02-actor-substrate` — the predecessor's own sibling, the board whose METHOD the space run copied — which carries **218 bolded pipe-rows** and parses as empty. A tool that decides what a session works on, blind to 59 % of the boards. **(2) `⬜` is not in its vocabulary at all** — it reads only tick-box, check-mark, strike-through and park markers, so **27 open rows across 3 boards are invisible**, including every row `B3` and `B4` are about (`1b5-H1..L5`, `LB1..LB3`, `3E`, `W8`). Found by `B1` (§3.7). **(3) It cannot tell a MARKER from a MENTION of a marker** — this very row listed the vocabulary literally and the parser ticked it, dropping `C1` from its own queue. Third occurrence of that shape today, after row `B2` and the plan's RESUME line | `[x]` | **DONE 2026-08-22 — §3.11. All three fixed and bitten.** Boards parsing empty **30 → 15**; rows visible **~200 → 445**; five boards' state independently confirmed. A **fourth** dialect family measured and left open (`OR-5`) |
| `C2` | **`space_view` — the two findings §19 produced and never made rows.** **14.10 ms/assembly is 14 % of a 100 ms tick**, and the shape is an **N+1**: the ancestor walk issues two queries per level. Ancestors are **272 B of 511 B — 53 %** at four levels, ~1 KB at `DP-Ch1`'s full 16. A single recursive CTE collapses the query side | `[x]` | **DONE 2026-08-22 — §3.12. 13.14 ms → 4.81 ms (2.7×), assembled bytes IDENTICAL.** 2 bites. `Q6` answered: it was never a tick cost |
| `C4` | **`live-suite-registry-gate` walks registry → disk and nothing walks disk → registry.** Found by `A3`: **four live suites existed on disk in NO registry row** — `world_seed_live`, `writer_state_validate_live`, `space_view_measure_live` (all three from the predecessor run) and `A3`'s own. The gate reported *"23 suites, ALL run"* and was **telling the truth about the 23 it could see**. Registering them then surfaced a second latent defect: none of the four announced its skip, so a run that did nothing read as a pass — **drift 11's exact lesson, and the gate has a rule for it that these files were outside of** | `[ ]` | |
| `C3` | **The two gates refused on their measurements — re-decide or record.** A `reality_id`-scope gate needing live-schema introspection; a half-applied-annotation gate that produced **47 mostly-false candidates**. Each was correctly refused. Neither has a row saying what its replacement needs | `[ ]` | |

---

#### 3.12 · `C2` — the N+1, and a question that answered itself

**Re-measured before touching anything** (rule 4): **13.14 ms**, not §19's 14.10 — same shape,
machine variance, and the reason to re-measure rather than quote.

The ancestor walk was a loop issuing `SELECT parent` and then a `node_at` **per level**, against a
`DP-Ch1` bound of 16. One recursive CTE replaces it:

```
  wall-clock per assembly : 13.14 ms  ->  4.81 ms      (2.7x)
  assembled size          : 511 B over 41 nodes  ->  511 B over 41 nodes
  ancestors               : 4 node(s) 272 B      ->  4 node(s) 272 B
```

**The payload is byte-identical.** That is the evidence that matters: the view did not change, only
the number of round trips. And the walk guard moved INTO the query as `up.d < $3`, which is strictly
better — a malformed tree is now bounded by the database rather than by a loop counter only the
caller enforces.

**Two bites, both restored byte-identical:**

| bite | red with |
|---|---|
| `ORDER BY u.d ASC` → `DESC` | `ancestors are [1, 2, 3, 4], wanted [4, 3, 2, 1]` |
| `WHERE u.d > 0` → `>= 0` | `ancestors are [5, 4, 3, 2, 1]` — the node listed as its own ancestor |

**The ordering assertion did not exist before this row**, and that was the real gap: the loop produced
nearest-first *as a side effect of being a loop*, so nothing ever asserted it. A CTE has no inherent
order, and `SDF-A4` forbids incidental ordering — this is precisely the case it means.

**`Q6` is answered, and the answer is that the question had already moved.** `Q6` asked whether 14 ms
is a problem, noting it is *"alarming per-assembly and irrelevant at one assembly per player-action"*.
`A4` settled which one it is: `assemble` is reached through `POST /internal/v1/space/view`, **once per
request**, never per tick. So it was never 14 % of a tick — that framing came from §19 written before
the caller existed. It is now 4.81 ms per request regardless.

**The ancestor payload half is NOT reopened here, and that is a citation rather than a dodge.**
~1 KB at full depth is a PROMPT-tier cost, and `SDF-Q15`'s own test already says the token half
*"stays open at the prompt tier, which owns a tokenizer"*. Measuring bytes again would not move it.

#### 3.11 · `C1` — three gaps, and a fourth I refused to guess at

| gap | before | after |
|---|---|---|
| a **bolded** id is not a row | 30 of 51 boards parsed as EMPTY | boards parsing empty **30 → 15** |
| `⬜` is not in the vocabulary | 27 open rows invisible, incl. every row `B3` and `B4` were about | `3E`, `W8`, `LB1`–`LB3` all visible |
| a **mention** reads as a marker | silently TICKED open rows — twice in one day | a marker must BEGIN a cell |

**Rows visible across all boards: ~200 → 445.** Validated against five boards whose true state I
established by working them this session — space-substrate (closed), space-producers (`C1`–`C4`
open), reality-layer (`3E`+`W8`), lore-bible (`LB1`–`LB3`), kernel-state (closed). **All five match.**

**The first widening OVER-read, and a closed board caught it.** Allowing word markers in any case
reintroduced the mention bug one layer over: `| **8** | Open register | **DONE for this pass** |` read
as OPEN because a cell *begins with the word "Open"*, and so did ``| `R-57` | OpenMW's preload() … |``.
**Three false opens on a board that is 35/35 closed.** Word markers now must be UPPERCASE and whole —
a board writing *"Open register"* as a title is not marking status. `🔴` was dropped entirely: here it
is a **severity** glyph in finding tables, not a state.

**And the bite caught a vacuous arm of my own.** The mention test put its mention in cell 0 — the id
cell, which the reader skips — so reverting `startswith` to `in` left the suite **green**. The arm
passed for the wrong reason. Moved into the description cell, where the real `B2` defect was, it now
reds with `{'Q1': 'x', 'Q2': 'x'}`: **both rows silently ticked.** That is `NV-1`'s exact shape, found
the only way it can be — by mutating and watching.

**`OR-5` is what I did NOT fix.** Fifteen boards still parse empty, and they are a further dialect
family — a plain-text id (`| S1-A1 · audit … | DONE |`), an id containing a space or `·`, a marker
sitting *before* the id (`` | `[x]` **S0** | ``). Each needs its own measurement: a careless widening
over-reads, as this row just demonstrated, and an over-read board sends a session at rows that are not
tasks. **Named, measured, and left — not silently claimed as covered.**

---

## 4 · Decisions taken in advance

| # | Decision | Reason |
|---|---|---|
| `D-1` | **`A1` precedes `A2`, and `A2` precedes `A3`.** Measure the seam, then reach it, then spawn into it | The predecessor's own `D-1`: measure before designing. Guessing the seam is how `world_seed` got written against a bootstrap nobody checked |
| `D-2` | **No new table this run.** Every row is a caller, a decision, or a register correction | Six tables with two producers is already the defect. Adding a seventh treats the symptom as the goal |
| `D-3` | **`A5` may legitimately produce NOTHING but register rows.** A trigger is an outcome | `SDF-A19` scale-bound `Domain → World` by a rule, not a quota, and was right to. A producer built to satisfy a board is the speculative-generality this repo already refuses |
| `D-4` | **Scope is the GAME track.** The 26 Writing Studio / Work Assistant / Book-Package boards are a different product in the same monorepo and are **explicitly OUT**, not forgotten — see `§6 OUT-1` | Bundling a 192-slice board for another product into a spine run makes both worse. Named so it cannot be mistaken for closed |
| `D-6` | **`A2`'s seam is a 12th provision step inside the `seeding` stage — not a resurrection of `reality_seeder`, and not a hook on first entry.** | It fills a stage that already exists rather than inventing one; it is reachable today (the HTTP handler drives `provision_reality`, controls measured at prod=3); and it does not make `world_seed`'s caller a module that itself has no caller. `Q3` is answered the same way: the provision path is synchronous, and step 5 already applies 67 migrations in that same request, so a declared tree of authored rows is not the thing that makes it long |
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
| **OR-5** | **`C1` fixed three measured dialect gaps; 15 boards still parse empty and they are a FOURTH family** — a plain-text id, an id containing a space or `·`, and a marker placed before the id. Measured 2026-08-22, not guessed | Its own measurement, the way `C1`'s three had one. The first careless widening produced **three false opens on a 35/35 closed board**, and an over-read board sends a session at rows that are not tasks — so this is deliberately not folded in |
| **OR-4** | **`3C`/`3D` appear to be ALREADY DONE.** `A3` needed a `dp::RealityId` and found `crates/dp/src/ids.rs:89` present with a crate-private `new_verified`, plus `ControlPlane`, `SessionContext`, `VerifiedBind` and `BindRequest` all live and used by `tests/support/mod.rs`. The reality-layer board still marks `3C` *"⬜ blocked on a PRODUCER"* | `B1` verifies rather than assumes — if true it is `B3`'s shape a second time: the work shipped and the register was never told |
| **OR-3** | **`A2` makes `seed_world` reachable but nothing yet DECLARES a world.** Every in-repo caller passes an empty `Vec` today, so the step is `Skipped` on every existing path; the reality that gets a world is one an operator or a test provisions with `--world`. That is a genuine caller and not a fake one — but a producer with no author is `A5`'s warning pointed at lane A itself | `A3` sites an actor, which needs a node to site it in. If `A3` ends up hand-writing a declaration to test against, that declaration is the missing author and belongs in the repo |
| **OR-2** | **Two components both own the `Seeding → Active` transition** — `provisioner.rs:296-298` (runs) and `reality_seeder/mod.rs:495-500` (does not). The background orchestrator L5.G designed for the `seeding` stage was never started, and the provisioner closes the stage it was meant to occupy | **DECIDED 2026-08-22 by `A2` (`D-6`): the orchestrator is NOT resurrected this run.** The `seeding` stage now does its work synchronously, which is consistent with step 5 already applying 67 migrations synchronously in the same request. `reality_seeder` keeps its 1008 lines and its zero callers, and that is now a NAMED debt rather than an unnoticed one — it wakes when seeding work outgrows an HTTP request, and `A5` is not the row that decides it |
| **OUT-2** | **`3E` is 🅿 PARKED behind reality-layer slice 5** and stays parked — `B1` does not unpark it. Its own board measured **880 across 99 files** against a plan that still says 457 | A production `ControlPlane` implementor exists |

---

## 7 · Drift register

**A run that ends with an empty drift log is not clean — it is dishonest.**

| id | what happened |
|---|---|
| **PD-4** | **I read "NEW V1+30d service `travel-service`" in `TVL_001` and recorded it as *"the service does not exist"*. It has been on disk the whole time.** The document was not wrong — the service is new to the PLAN — but "will be built" and "is not there" are different claims, and I substituted one for the other without looking. Caught by the trigger's own first run, which is the argument for building the trigger before writing the deferral rather than after. **Same shape as `PD-2`**: a claim taken from a document standing next to claims that were measured |
| **PD-3** | **The `Effects::apply_migrations` trait doc said *\"apply `0001_initial.sql` (the SKELETON)\"* while its implementation had applied all 67 manifest migrations since 2026-08-08 (`1b12-05`).** The implementation comment records the rewrite in detail; the trait doc above it was never touched. **A doc on the CONTRACT and a doc on the IMPLEMENTATION are two homes for one fact**, and the rewrite moved only the one it was standing in. Fixed in `A2` |
| **PD-2** | **`world_seed.rs:5-6` asserts that `reality_seeder` *"already runs in the `seeding` lifecycle stage that `provisioner` step 9 transitions into"*. It does not, and I wrote that line eight commits ago.** The paragraph it opens is headed *"What was missing, measured rather than assumed"* — and the half of it that WAS measured (*"every `INSERT INTO channels` in the repository is in a test"*) is still true, which is exactly why the unmeasured half read as credible. **One sentence in a measured paragraph inherits the paragraph's authority without earning it** |
| **PD-1** | **The overview that produced this plan was wrong on its first pass, and wrong in the safe-looking direction.** Reading the boards with `goal-prompt.py`'s row parser reported **0 rows for 30 boards**, and *a board whose rows are invisible is indistinguishable from a board with none open*. It very nearly shipped as **"49 of 51 closed"**. Caught only because `space-substrate` reported 5 rows and the session had just ticked 24 of them. **The disagreement between a tool and a thing I had just done is the whole detection**, and on any board I had not personally worked it would not have existed. This is `C1`'s real severity |

---

## 8 · RESUME

**RESUME: `C3` — the two gates refused on their measurements (a `reality_id`-scope gate needing live-schema introspection; a half-applied-annotation gate that produced 47 mostly-false candidates). Re-decide or record what a replacement needs. Then `C4`. **11 of 13 done; `C3` and `C4` are the last two.**
```goal-prompt
goal: the space substrate has producers reachable by the production path, and the four boards still holding rows open are closed or carry a mechanism
lanes: |
  A producers = A1, A2, A3, A4, A5
  B boards    = B1, B2, B3, B4
  C tooling   = C1, C2, C3, C4
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
