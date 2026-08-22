# RUN-STATE — the producers are reachable, and no running reality has a world

**Reconciles:** Foundation Invariants **I1–I19** · Data Plane channels **DP-Ch1–Ch37** · No-Defer-Drift · Destructive DB ops in tests · Admin Action Policy — and the reconciliation is again the subject rather than a formality. **Reality provisioning, per-reality migration and the space schema all already exist**: `provision_flow` + `provisioner` run 12 steps including `seed_world_structure`, `services/migration-orchestrator/cmd/migrate` is the per-reality migrator, and `0022`–`0030` are registered in the manifest. Nothing here is a new model. The gap is that **the ten realities on this shard were provisioned before those migrations existed and were never brought forward**, so every table the previous board gave a producer to is absent from all of them.

> **Read this file FIRST after any compaction.** Then `git log`, then continue.
>
> - **Started:** 2026-08-22 · **Branch:** `feat/game-logic` · **Base `HEAD`:** `f1e09a64d`
> - **Predecessor:** [`2026-08-22-space-producers-RUN-STATE.md`](2026-08-22-space-producers-RUN-STATE.md) — 13/13. This run is what its closure revealed, exactly as that board was what the one before it revealed.

---

## 0 · The commitment

**PO, 2026-08-02:** *"The map is where everything in the game happens."*
**PO, 2026-08-22:** *"make place where actor can spawn on."*

The place can now be built and an actor can now be put in it. **No running reality has either.**

**DONE means:** a reality that exists on this shard today has a world, an actor sited in it, and a browser that shows where that actor is — each proven by running the production path. **Not a fresh throwaway. One of the ten.**

---

## 1 · Why this run exists — measured 2026-08-22 at `f1e09a64d`

| what | measured |
|---|---|
| realities on this shard | **10** (`lw_reality_*`), all `status=active` — **the first draft of this table said 9; see `WD-2`** |
| newest migration applied in them | **two cohorts**: 7 at `0019_channels` (15 applied), 3 at `0021_turn_slot` (17) |
| `map_layout` / `entity_binding` / `place` / `portal` / `layer_registry` / `encounter` | **the tables DO NOT EXIST** in any of the ten |
| `actors` (`0022`) | absent too — so the actor registry has no home there either |
| realities with a world | **0** |

The previous board proved the producers are reachable: `seed_world` ← `provisioner_live.rs:632`, `assemble` ← `space.rs:106`, `site_in_cell` ← `actor_registry.rs:74`/`:120`. **All three are reachable and none has ever run against a reality anyone uses.**

### The shape, for the third time

`apply_migrations` was rewritten on 2026-08-08 to apply every manifest migration — and that only ever affected realities provisioned **after** that date. All ten predate it. **A fix that only reaches new subjects is `1b5-H1`'s shape** (*"the fix reached one site of N"*), and `1b12-05` already recorded that *"registration is necessary and not sufficient"*.

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
| `A1` | **MEASURE the migrate path before touching a real reality.** What does `migration-orchestrator/cmd/migrate` do to an existing reality — which migrations, in what order, with what dry-run? Does it read the manifest, and does it refuse a reality it cannot reach? **Read-only.** | `[x]` | **DONE 2026-08-22 — §3.1. Read-only throughout; nothing was written.** Two of `D-1`'s assumptions are NOT expressible with this CLI — see `§3.2` |
| `A2` | **The ten realities come forward to the manifest head — or a decision says which do not.** `I-1` applies: these are NOT throwaways. Dry-run first, on one reality, with the diff shown; **the PO authorises before any live write** | `[~]` | **STOPPED FOR AUTHORISATION — §3.3, and that is `D-2` working, not a failure.** Option **(b)** taken: `--reality` and a fleet-resolving `--dry-run` are built, tested (6 arms), bitten, and REHEARSED against an exact copy of a real reality — **9 of 9 applied clean**. The live write is the only step left |
#### 3.3 · `A2` — built, rehearsed, and stopped at the live write

**Decision: option (b) from §3.2 — add `--reality`.** The other two were worse. **(a)** narrowing the
fleet by editing `reality_registry.status` is *a live write to the meta database made in order to make
a live write safer*. **(c)** a fleet-wide first attempt is the caution `D-1` intended, abandoned.

**Two things shipped, neither of which touches a reality:**

- **`--reality <id[,id]>`** narrows the fan-out. The fleet was all-or-nothing; `ActiveRealities`
  returns every drainable row and nothing filtered it. **An id outside the fleet is a REFUSAL** —
  a typo would otherwise select nothing, `runLive` would print *"no active realities to migrate"*,
  exit **0**, and an operator would believe a migration reached a reality it never touched.
- **`--dry-run` with `--meta-dsn` now resolves the REAL fleet** and prints the plan. Until now a dry
  run never opened a database, so there was no way to ASK for authorisation with anything concrete;
  the only way to learn what a migration would do was to run it.

**Against the real registry, read-only:**

```
  PLAN (nothing is written)
    route          : internal/runner with concurrency=10
    drainable fleet: 10
    would apply to : 1
      00c7e2c5-cabc-421a-b3a2-c49a23288e4f  lw_reality_00c7e2c5cabc @ pg-shard-0.internal

  ERROR: --reality 00000000-dead-beef-... is not in the drainable fleet of 10;
         refusing rather than narrowing to nothing
```

**Six unit arms, and the bite is the refusal.** Making an unknown id `continue` instead of erroring
reds two of them — including `a,typo`, which silently applied to `a` alone. Restored byte-identical.

**REHEARSED on a throwaway that is an exact copy of a real reality** (`pg_dump --schema-only` plus the
`schema_migrations` ledger: **17 migrations, newest `0021_turn_slot`** — identical to the source):

```
  0022_actors .. 0030_encounter        9 applied, 0 failed
  map_layout=true entity_binding=true place=true portal=true
  layer_registry=true encounter=true actors=true
```

**The harness that said that is proven able to say the opposite** — fed a deliberately broken
statement it reports `ERROR: relation "map_layout" already exists`. It had already caught a real
mistake: MSYS path translation mangled `/tmp/m.sql` and **all nine reported FAILED**, which is what a
harness is for.

**The rehearsal's one gap, measured rather than waved at.** It carried schema and ledger but no other
data, so the single data-touching migration — `0027`, which adds a foreign key — was not exercised
against rows. So the rows were counted: **all ten realities have 0 `channel_writer_state` rows and 0
orphans.** The gap is empty in practice, and `0027` adds the key `NOT VALID` in any case.

**`A2` STOPS HERE.** Everything that can be done without writing to a non-throwaway reality is done.
The remaining step is nine live invocations against real realities, which is `D-2` and the STOP list.
| `A3` | **Something DECLARES a world** — `OR-3` from the previous board. Every caller passes an empty declaration today, so the seed step reports `Skipped` on every path. Where the declaration LIVES is this row's decision | `[x]` | **DONE 2026-08-22 — §3.4.** `contracts/world/demo_v1.json`, validated in CI and **seeded against a real database: 5 nodes, 2 places.** The live arm caught a defect the pure check could not see, and that gap is now closed too |
#### 3.4 · `A3` — the declaration, and the defect only a database could see

**`contracts/world/` is the home.** A declaration is **data an author edits**, so it is a contract
artifact rather than a constant. `D-3` holds: nothing there is applied to a reality unless a caller
names it — `ProvisionRequest.world` still defaults to empty and empty still means *skipped*.

`demo_v1.json` is a real five-node world: `world → region → locale → {domain, domain}`, the two
domains carrying places, which is the smallest shape that gives an actor somewhere to be.

**Two checks, because they answer different questions.**

- `world_declarations.rs` — every `*.json` parses, is non-empty, and passes `validate`. **Subject
  floor included**: an empty directory would make it pass forever.
- a live arm in `world_seed_live` — the file actually SEEDS. `validate` is **pure and has never seen
  a `CHECK`**, so the two claims are genuinely different.

**And the live arm earned its place on the first run.** It refused the file:

```
  seed the AUTHORED world: new row for relation "place"
  violates check constraint "place_type_closed"
```

I had written `"market"`; the column wants `"marketplace"`. **`validate` passed it and the database
did not** — which is precisely the gap the arm was written to cover, found immediately.

**So the gap was then closed on the pure side too**, rather than left for the next author to hit
against a half-created reality: `world_declarations.rs` now reads `place_type_closed` **out of
`0026_place.up.sql`** and checks every declared type against it. Parsed, never copied — a second
list of ten strings would drift, and the first time `0026` gained an eleventh the copy would go on
refusing it.

**Bites — four, each restored byte-identical:**

| bite | red with |
|---|---|
| a place on a `locale` | `PlaceOnNonDomain { node: 3, kind: "locale" }` (`place.invalid_place_type_for_channel_tier`) |
| the locale re-kinded to `arena` | `ContainmentViolation { node: 3, parent_kind: "region", child_kind: "arena" }` |
| a second root | `MultipleRoots` |
| `"market"` restored | *"node 5 declares place_type `market`, which `0026_place`'s `place_type_closed` would refuse"* — **without a database** |

**Live evidence:** `A3 AUTHORED WORLD: 5 nodes, 2 places, from contracts/world/demo_v1.json`.
| `A4` | **An actor is sited in a running reality and the browser shows where it is.** The end of the PO's sentence. Extends `kernel-state-demo.sh`, which already proves browser ← event ← spine | `[ ]` | |

#### 3.1 · `A1` — what `migrate` actually does, read at `HEAD`

| question | answer |
|---|---|
| how many migrations per invocation? | **ONE.** `migrate <migration_id>`. Bringing the fleet to head is **9 invocations** (`0022`…`0030`) |
| which realities? | **ALL of them.** `realityreg.ActiveRealities` = every row whose `status` is in `{seeding, active, pending_close, frozen, migrating}`. **There is no `--reality` flag** |
| are `0022`–`0030` breaking? | **all nine are `breaking: false`** → `internal/runner`, concurrency 10. The canary path and its nil `Verifier` (fail-closed) never engage |
| what does `--dry-run` show? | **routing only.** It never opens the meta DB: it prints *"would: route through internal/runner with concurrency=10"* and stops. It cannot name a reality, show a diff, or say which are behind |
| does it refuse a reality it cannot reach? | **No — it continues and reports.** `cmd/migrate/main.go:217` counts per-reality `Succeeded` and prints `done: N applied, M failed`, returning an error only after the fan-out. **A partial fan-out is possible and is reported, not prevented** |
| how does it reach the shard? | `db_host` is `pg-shard-0.internal`, which does not resolve from a dev box. `--host-override` exists for exactly this |

**The fleet, measured (read-only):**

```
  7 realities  0019_channels   15 applied   map_layout absent
  3 realities  0021_turn_slot  17 applied   map_layout absent
 10 total, all status=active, all missing 0022-0030
```

**The probe is controlled**, because `f` everywhere proves nothing on its own: the same
`to_regclass('public.map_layout') IS NOT NULL` returns **`t`** against
`loreweave_kernel_state_smoke_channel`, a database that does have the tables.

#### 3.2 · What `A1` forces on `A2`, and it contradicts `D-1`

**`D-1` says *"dry-run first, on one reality, with the diff shown"*. The CLI can do NEITHER.**

- **One reality** — there is no targeting flag. The fleet is whatever `ActiveRealities` returns.
- **A diff** — `--dry-run` does not connect to anything. It is a manifest lookup that prints a route.

So `A2` cannot follow `D-1` as written, and the honest options are three: **(a)** temporarily narrow
the fleet by `status` so only one reality is drainable, **(b)** add a `--reality` flag to the CLI, or
**(c)** accept a fleet-wide apply on the grounds that all nine migrations are additive and
`breaking: false`. **`A2` decides and records which, and it still stops for authorisation before any
live write** — that half of `D-1` stands untouched.

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
| **WD-2** | **I wrote "nine realities" and there are TEN.** It reached the board's §1, the RESUME line, the goal prompt and a commit message before `A1` counted properly. The original probe loop listed ten rows and I read nine — **a number I produced from a listing rather than from a `count(*)`**, which is the same class as `PD-4` (a claim taken from a document instead of measured). `A1` also found the fleet is not uniform: **two cohorts, not one** |
| **WD-1** | **The verification script for the previous goal was WRONG, and it said the goal was not met.** It took the FIRST `#[cfg(test)]` in a file as a cut-off; `provisioner_live.rs` has one at line 483 followed by 250 lines of production, so the real `seed_world` call at 632 was filed as test and reported `prod=0`. **The controls did not catch it** — in both control files every `#[cfg(test)]` sits below every call site, so the cut-off happened to land correctly. *A control only proves what it exercises.* The tool can only UNDER-report, so no earlier conclusion changed |

---

## 7 · RESUME

**RESUME: `A2` is STOPPED FOR AUTHORISATION (§3.3) and `A4` depends on it — an actor cannot be sited in a running reality until that reality has the tables. `A3` is done (§3.4): `contracts/world/demo_v1.json` exists, validates in CI and seeds against a real database. While `A2` waits, lane B (`B1`, `B2`) and lane C (`C1`) need no live reality and can proceed.**

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
