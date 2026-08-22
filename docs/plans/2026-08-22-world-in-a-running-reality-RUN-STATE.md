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
| `A2` | **The ten realities come forward to the manifest head — or a decision says which do not.** `I-1` applies: these are NOT throwaways. Dry-run first, on one reality, with the diff shown; **the PO authorises before any live write** | `[x]` | **DONE 2026-08-22 — §3.3, §3.3b, §3.3c. AUTHORISED BY THE PO AND APPLIED: all ten realities are at `0030_encounter`, 26 migrations each, seven tables each, 0 failed.** The authorisation gap it waited in found **four** further defects, one of which would have holed seven of the ten |
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
#### 3.3b · `A2` — the authorised step is now ONE fail-closed command

`migrate` takes **one migration id per invocation**, so bringing a reality from `0021_turn_slot` to
`0030_encounter` is nine of them, in order, with the same six flags each time. **That is a procedure
nobody can re-run correctly** — `G2`'s defect about a demo assembled across six hand-typed shells,
and `EO-2`'s about `E1` before it.

`scripts/bring-reality-forward.sh` **fails closed twice over**: no `--reality`, no run (`rc=2`); no
`--confirm`, no write. It reads the migration list **out of the manifest** rather than hard-coding a
second copy, refuses if it reads none, goes **through the orchestrator** (`I-3`) rather than `psql`,
and verifies afterwards against the reality itself — because a run that reports success while the
table is absent is `1b12-05`'s shape, found once already.

**Plan mode, against the real registry, read-only:**

```
  == 9 migration(s) from the manifest: 0022_actors … 0030_encounter
  == PLAN ONLY (no --confirm). Nothing will be written.
  -- plan 0022_actors
       drainable fleet: 10
       would apply to : 1
         00c7e2c5-…  lw_reality_00c7e2c5cabc @ pg-shard-0.internal
  == planned only. Re-run with --confirm to apply.        rc=0, 9 plans
```

**And plan mode caught a real defect before any write** — exactly its purpose. `mapfile` kept the
`` from python's CRLF output on Windows, and `migrate` answered
`ERROR: migration "0022_actors" not found`. **The fifth escaping failure of this session**, and the
first one a dry run caught rather than a test.

#### 3.3c · `A2` — authorised, and the four defects the wait uncovered

**The PO authorised the live write on 2026-08-22** (*"continue and complete the runstate"*, after
`/goal clear`), which is `I-1`'s *"unless the PO authorises otherwise"* and `D-2` discharged rather
than bypassed. What follows is what the authorised path found before it was allowed to run.

**Four defects, and the first one is the reason this row was worth waiting in.**

| # | defect | who it would have hurt |
|---|---|---|
| 1 | **the pending list was hardcoded `id >= '0022'`** | the SEVEN realities at `0019_channels`. They would have reached `0030_encounter` with `0020` and `0021` missing and nothing saying so — `1b12-05`'s shape and `1b5-H1`'s in one line |
| 2 | **`migrate` never wrote the reality's OWN `schema_migrations`** | every reality, permanently. See below |
| 3 | **`--allowlist` / `--sql-dir` resolved against the wrong directory** — the script `cd`s into the module and only `--manifest` was overridden | the first `--confirm` run, which is where it fired |
| 4 | **the after-check compared a boolean against `t`** while `::text` renders `true` | nobody — it could only ever say ABSENT. **A check that cannot pass is as broken as one that cannot fail** |

**Defects 3 and 4 share a cause worth naming: plan mode does not execute the apply, and does not
execute the verify.** Nine successful plans proved the plan and nothing downstream of it. That is not
an argument against planning first; it is the boundary of what a plan is evidence for.

**Defect 2 is the one that outlives this run.** There are two ledgers and only one had a writer:

```
  instance_schema_migrations  (META)     <- written by the orchestrator
  schema_migrations           (REALITY)  <- written ONLY by the provisioner
```

So a migration applied through `migrate` left the reality's own ledger UNMOVED — **the tables were
there and the database said they were not** — and `apply_pending`, which reads exactly that table to
decide what a resume still owes, would have re-applied all eleven. Survivable only because the SQL
happens to be `IF NOT EXISTS`-shaped, which is a property of the files and not a guarantee of the
mechanism. Fixed in `SQLApplier.Apply`, where the schema change happens, so the pair cannot desync.

**The bite, on a fresh copy of a `0019`-cohort reality, with the ledger write removed:**

```
  !! 0020_turn_boundary  applied but ABSENT from the reality's ledger     (x11)
     ledger: 15 migrations, newest 0019_channels
     actors true  map_layout true  entity_binding true  place true
     portal true  layer_registry true  encounter true
  !! 11 check(s) FAILED after a run that reported success.
```

All seven tables present, ledger frozen at `0019_channels`. **That is the defect in one screen**, and
it is the state that would have shipped to all ten. Restored byte-identical, and the restore was then
re-run against a fifth fresh copy to prove it was live and not merely on disk — `WD-1`'s lesson, that
a mutation must be proven applied rather than assumed.

**The permanent guard is `realityLedgerCount` in `migrate-drill`**, asserted separately from
`probeCount`. The pair is the point: one asks *"did the schema change"*, the other *"does the
database say so"*. `probes == n && ledgers == 0` is a real state and was the state at `HEAD`.

**The live run — all ten, through the orchestrator (`I-3`), one reality at a time:**

```
  lw_reality_00c7e2c5cabc   9 applied      (0021 cohort, 3 realities)
  lw_reality_1ec91442100c  11 applied      (0019 cohort, 7 realities)
  ...
  10 of 10 OK, 0 failures

  every reality: 26 migrations, newest 0030_encounter, 7 of 7 tables
  meta: 104 instance_schema_migrations rows, 10 realities, 0 failed   (7x11 + 3x9 = 104)
```

**Both ledgers agree, and they are independent producers** — that agreement is the check, not the
104 itself. Verified by re-measuring the fleet directly rather than by re-reading the script's own
output. Five throwaway rehearsal databases were created and all five dropped; `lw_rehearse%` is empty.
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
| `A4` | **An actor is sited in a running reality and the browser shows where it is.** The end of the PO's sentence. Extends `kernel-state-demo.sh`, which already proves browser ← event ← spine | `[~]` | **THE CHAIN IS BUILT AND PROVEN END TO END — §3.8 — on the THROWAWAY demo stack. 2 passed on chromium; the bite (unsite the actor) reds.** What remains is the substitution onto one of the ten, which is `A2`'s authorisation |

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
| `B1` | **game-tier's `RealityId + SessionContext` row still reads `⬜ board TBD`** — a **fourth** place the finished `3C`/`3D` work is not reflected, after reality-layer, the `1b5-*` rows and `G5`. Found while verifying the previous goal | `[x]` | **DONE 2026-08-22 — §3.5.** Corrected with evidence, and precisely: the TYPES are built, the ADOPTION half is reality-layer `3E` and stays open. `clippy -p dp -D warnings` **rc=0** |
#### 3.8 · `A4` — the chain is built and proven; only the reality is borrowed

**`A4` is NOT blocked on `A2`. Only its last substitution is.** The whole chain now exists and runs:

```
  entity_binding -> world-service POST /internal/v1/space/where-is
    -> game-server ws/place.ts -> W1Frame.place -> ChannelPanel -> the DOM
```

and the browser says `turn 1 · you are entity 1 · at Yen Vu Lau`.

**What was missing: nothing answered *"where is entity N"*.** `assemble` answers *"what is at node
X"*. The server half (`where_is`, three distinct facts) is §`a43e1ca99`; this row is the rest.

**The place lookup is ADVISORY and the subject lookup is not, and that asymmetry is deliberate.** A
failed subject lookup means the room cannot know who is acting, so it binds nobody. A failed PLACE
lookup means a poorer frame, not a wrong one — so it degrades to no location rather than refusing the
join. Making it fail closed would let a space-view outage take down joins that never needed it.

**Three defects found by running it, and the third is the one worth keeping:**

| # | defect | how it surfaced |
|---|---|---|
| 1 | the SQL comments contained backticks, and the heredoc is UNQUOTED | the shell ran them: `kernel-state-demo.sh: line 151: A4: command not found` |
| 2 | the demo added a SECOND root; `channels_root_single` allows one | `ON CONFLICT DO NOTHING` **swallowed** the refusal and the child then failed on a key naming a row never written. The map now hangs off channel 1 |
| 3 | **`#[serde(tag = "kind")]` collided with `EntityLocation.kind`** | `{"kind":"in_cell", …, "kind":"domain"}` — **a duplicate JSON key.** Rust emits both; every parser keeps the LAST, so the discriminant was destroyed and TypeScript read `kind === "domain"` and concluded the entity was nowhere |

**Defect 3 is invisible to every layer except the last one.** world-service's own live test passed —
it reads Rust structs, not JSON. The contract passed — it describes fields, not collisions. Only a
browser reading real JSON could see it, which is the argument for this row existing at all. Renamed
`node_kind`, in the type, the contract and the wire.

**The bite:** delete the `entity_binding` row and re-join — the header renders without a location and
the assertion reds with *"no place — is the actor sited…"*. Restored; green again.

**What is borrowed:** the demo's reality lives in `loreweave_kernel_state_smoke_*`, a throwaway. It
is not one of the ten. `A4` therefore stays `[~]`: **the mechanism is proven, the subject is not the
real one**, and swapping it is exactly what `A2`'s authorisation unlocks.
#### 3.5 · `B1` — the fourth stale reflection, corrected precisely

The game-tier board's slice table read `| **3** | RealityId + SessionContext | ⬜ *board TBD* |`.
That was **accurate about the BOARD and misleading about the WORK**: no game-tier board was ever
written for the slice, and the slice's subject shipped anyway — through the reality-layer board.

Re-verified rather than recalled, by reality-layer `3C`'s **own** criterion:

```
  cargo clippy -p dp --all-targets -- -D warnings   rc=0
  present  verified_uuid_newtype!      (crates/dp/src/ids.rs)
  present  pub struct CapabilityToken  (crates/dp/src/session.rs)
  present  pub trait ControlPlane
  present  pub struct SessionContext
```

**The correction is deliberately NOT a plain tick.** The row's own words are *"re-priced by the 457
bare `reality_id` sites — the largest single mechanical change in the plan"*, and that half is
**adoption**, which is reality-layer `3E` and still open. Ticking the whole row would have swapped one
wrong register for another.

**Fourth instance in two runs** of the same shape: the work ships, and the register that would tell
the next reader is not the one that was updated.
| `B2` | **reality-layer `3E` — decide.** Re-measured 2026-08-22: **195 `reality_id: Uuid` against 11 typed, across 48 files.** It is parked behind slice 5. Either work it or re-park it against **that** number rather than the stale 880/99 | `[x]` | **DONE 2026-08-22 — §3.6. `3E` CLOSES, superseded by a gate.** `reality-id-adoption-gate` reports **0 adoptable**, and `W8` was found discharged in the same pass. **The reality-layer board is now fully closed.** |

#### 3.6 · `B2` — `3E` closes, because a gate replaced its number

**Decision: `3E` is CLOSED, superseded by `scripts/reality-id-adoption-gate.py`** — which is a
stronger mechanism than the row's figure ever was.

The gate reports **0 ADOPTABLE** for both game-layer services, and its scope is **not a list but a
derivation**: `01_scope_and_boundary.md` §4 (`DPA-SCOPE`) names exactly `world-service` and
`commit-service`, and the gate is **anchored on that clause** so a reword of §4 reds it rather than
leaving it quietly enforcing a rule the doc stopped making.

**The residue is structurally out of scope, not unfinished.** Of 195 bare `reality_id: Uuid`
declarations repo-wide:

```
  98  services/world-service   -> the gate classifies these: 0 adoptable, 60 exempt, 21 boundary
  71  crates/dp-kernel         -> CANNOT hold a RealityId. It carries dp-crate = true, it IS the
                                  data plane, and new_verified is pub(crate) to dp.
  12  crates/meta-rs   10 crates/rebuilder   4 others  -> not game-layer per DPA-SCOPE
```

**The row's headline number was corrected five times** — 457 → 884 → 178 → 84 → 76 → a three-way
split — and the gate's own docstring records each correction narrowing it to *"something truer"*.
**A count that keeps being wrong is a proxy**; the gate replaced it with the property.

**And `W8` was found discharged in the same pass.** It read *"⬜ subsumed by `W3`"* — true, and left
open. `capacity_glue::live_snapshot` reads `FROM shard_utilization` (`capacity_glue.rs:103`) and the
real path calls it at **both** entry points, `provision_flow.rs:177` (placement, under the advisory
lock) and `:224` (resume). Its own comment states the property `W8` asked for: *"a fabricated
snapshot here would reintroduce the drill's defect"*.

**The reality-layer board is now 37 of 37.**
### Lane C — the tooling, again

| # | Row | Status | Evidence |
|---|---|---|---|
| `C1` | **`OR-5` — 15 boards still parse empty**, a fourth dialect family: a plain-text id, an id containing a space or `·`, and a marker sitting *before* the id. Needs its OWN measurement: the previous widening produced **three false opens on a 35/35 closed board** before it was tightened | `[x]` | **DONE 2026-08-22 — §3.7. It is THREE families, measured, and only ONE got a widening.** 15 → 13 empty, 445 → 498 rows, and **four genuinely-open rows surfaced** — one of them a PO checkpoint |

#### 3.7 · `C1` — three families measured, one widened, two refused

`OR-5` called it *a fourth dialect family*. Measured, it is **three**, and they are not equally safe:

| family | rows | verdict |
|---|---|---|
| **marker BEFORE the id** — `` \| `[x]` **S0** \| `` | 17 | **WIDENED.** Unambiguous: the tick box is already in the vocabulary, only its POSITION was new |
| plain-text id in cell 0 — `\| S1-A1 · audit … \| DONE \|` | 132 | **REFUSED** |
| bolded id containing a space or `·` | 30 | **REFUSED** |

**Why the marker-first family was invisible to BOTH halves at once:** `ROW_TABLE` reads an id out of
cell 0, and the status scan starts at cell 1. A board that puts the tick box in cell 0 and the id
after it defeats each of them separately.

**Result: boards parsing empty 15 → 13, rows visible 445 → 498, and four genuinely-open rows
surfaced** — `event-causality` `S6`/`S8`/`S9` and `story-seed` `S5`. Each verified against the source
as a real tick box, and `S5` is a **PO checkpoint** whose own text says *"STOP HERE"*. It was
invisible to the tool that decides what a session works on.

**Why the other two are refused, and it took one command to see it.** The plain-text family has no
delimiter separating an id from prose, so the obvious pattern matches the **header row**
(`| phase | status | evidence |`) on its first try — and headers are merely the first false positive
one notices. 132 candidate rows behind a pattern like that is **exactly** the shape that produced
three false opens on a 35/35 closed board last time. `OR-5` stays open, now with its families named
and counted rather than lumped.

**Bite:** disabling the branch reds the new arm with `{}` — no rows at all. Restored byte-identical.
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

**RESUME: `A2` — STOPPED FOR AUTHORISATION (§3.3). It is now the ONLY thing left: `A1`, `A3`, `B1`, `B2`, `C1` are done and `A4`'s whole chain is built and proven end to end on the throwaway stack (§3.8), browser included. What `A2` unlocks is the substitution of a REAL reality for the borrowed one — nothing else.**

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
