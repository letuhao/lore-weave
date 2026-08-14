# RUN-STATE — the data foundation: make one real thing flow through it

**Opened 2026-08-13** · branch `feat/game-logic` · opened at HEAD `718c29fc9`

**Reconciles:** SDK-First · Per-service DB ownership / no cross-DB FK · Performance Standard ·
User Boundaries & Tenancy ·
A gate, lint, test, `const` assertion, validator, or an axiom that constrains code — and the audit that opened this file found the thing all
five govern is **built as a contract and has no data in it**, measured at HEAD:

* `crates/dp` is 3,655 lines with one runtime dependency (`uuid`) and **declares no I/O by design**.
  It exposes **6** of the ~20 primitives `06_data_plane/01 §2.4` names.
* **Production call sites of any tier primitive, outside `crates/dp`: ZERO.** The only `t2_write`
  in the tree is inside `dp-kernel/src/dp_backend.rs`'s own `#[cfg(test)]`.
* The one production backend pair — `KernelWriteBackend` / `KernelReadBackend` — has **zero
  consumers outside the file that defines it**.
* The two services that depend on `dp` (`commit-service`, `world-service`) use it **only** for
  `RealityId` / `SessionContext::bind`. Neither touches the data path.
* `§2.4` says *"Direct Redis access for T0–T2 reads and cache."* **`redis` appears in exactly one
  Cargo.toml in the Rust tree — `services/commit-service`** — for the proposal bus and a ceilings
  bin. **Zero DP crates.** The only `impl Cache` anywhere is `InMemoryCache` in `meta-rs`.
* `dp:events:*` (`DP-Ch17`) still has **0 producers**; `spec_oracle_channels.rs` holds the asserted
  trigger that reds the day it arrives.
* The control plane declares **14 RPCs and 8 return `UNIMPLEMENTED`** — six of them because
  `tier_policy`, `npc_binding` and `schema_version` **have no migration in this repo**.

**This is the actor hub's own failure shape one layer down** — 91 tests, zero consumers — with the
tests to match. `scripts/orphan-model-gate.py` exists because of it. A coverage gate reporting
**84/84 sited** over a surface with zero production callers is the most expensive way this repo has
found to feel finished.

> This file is the commitment. `/goal` holds the session open; **this file holds the work.**
> After any compaction, re-read `§0` FIRST, then `git log`, then continue.

---

## 0 · HOW TO WORK — BINDING

### 0.1 The execution contract

Adopts **§0.6d of [`2026-08-08-reality-layer-RUN-STATE.md`](2026-08-08-reality-layer-RUN-STATE.md)**
unchanged — the execution invariant, the source-of-truth rule, the six-step row-completion contract,
and the non-negotiable hazards. That file also holds §0.6c (sealed forks) and §5
(`BDR-57`..`BDR-90`). Read it before the first batch.

### 0.2 🔴 THE BOUNDARY — this section is the point of this file

The last four days drifted, measured: two tracks measured the tree (`gate-teeth`, `dp-coverage`) and
two left the tier entirely (`authorable-surface`, `lore-bible`). **The PO stated the objective on
2026-08-13:**

> *"the main purpose is build data plane, foundation and wire actor hub, control feature and build
> player feature to consume it, a full dataflow, but seem like we cross the line, there are no
> combat, progression feature yet because they are not complete design yet"*

**IN SCOPE — and nothing else is:** the data-plane foundation, the control plane it needs, the actor
hub wired to it, and one player-facing feature consuming the result end to end.

**OUT OF SCOPE. Each of these is a drift row if it is started, not a judgement call:**

| ⛔ | why |
|---|---|
| **combat** — any rule, tuning surface, or table whose subject is combat | **not completely designed** (PO, 2026-08-13) |
| **progression** — `progression_kinds`, XP, tiers, advancement | **not completely designed** (PO, 2026-08-13) |
| **the lore bible / `G-S3` / `G-S4` / BOOK_TO_GAME** | different track — the authoring pipeline, upstream of the manifest. Parked: [`2026-08-14-lore-bible-RUN-STATE.md`](2026-08-14-lore-bible-RUN-STATE.md) |
| **a new gate whose subject is another gate** | `gate-teeth` closed at baseline ZERO. Measuring the tree is not building the spine |
| **a new coverage/measurement instrument** | unless a board row below needs it as *its own* acceptance evidence, and the row says so |
| **a document as a deliverable** | a schema something validates against and a byte that reaches a store are deliverables. Prose is not |

**The test before starting anything:** *does a byte move through the SDK because of this?* If no,
it is not this run's work — record it in `§4` and move to the next row.

### 0.3 The ordering, and why it is forced

`DF1` first, and it is the smallest row on the board on purpose. Every other row is an
*improvement to a path nothing walks*. A Redis cache for T0–T2 that no caller reads is the same
finding as the one that opened this file, arriving faster. **One real caller first — it is the
measurement that stops this happening again, and it will reveal what is actually missing.**

### 0.4 Per batch, in order

1. State what is being built in one sentence, **from the document**, not from memory.
2. Measure the subject before writing anything.
3. Build the smallest thing that is real.
4. **Bite it**: GREEN → mutate ONE side → genuine RED → restore **byte-exact** → GREEN. Paste it.
5. Update this board with the evidence string.

### 0.5 A STRING THAT LOOKS LIKE A SUBJECT IS NOT THE SUBJECT

The lesson of the three runs before this one, five separate instances: a word in an unrelated
README · a symbol inside the oracle that counts it at zero · a `DetRng` from another crate · a doc
comment saying *"unbuilt"* · a document's own filename. Each read as evidence something exists.

- Measure **existence** in code with comments **stripped**.
- Measure **citation** with comments **counted**.
- Never conflate them, and say which one a check is doing.

**Any new gate ships a `--self-test` AND mutation rows in `gate-bite-harness` in the same commit.**

### 0.6 Hazards — every one of these has bitten

- Run any sweep **DETACHED**; read the process's **REAL** exit code, never a task notification's.
- **Never run two `gate-wiring-gate --run-all` sweeps concurrently** (`BDR-53`). A refusal is exit 2
  — that is failure evidence, not a pass.
- **Edit nothing while a sweep runs.**
- **Byte-level I/O**, and read CRLF **from the bytes** rather than assuming it.
- **NEVER use a heredoc for a patch containing backslashes** — it ate them **seven times** in one
  session. Write the patch to a file with the Write tool.
- **Never hand bash an absolute Windows path.** Repo-relative.
- `-F <file>` for commit messages. `cargo test --workspace` needs **`-j 4`**.
- Every board edit uses an **asserted anchor** (`assert count == 1`), never a bare `str.replace`.

### 0.7 Do not stop

A batch finishing, a commit, a green sweep and an empty turn are **not** stop conditions. If
something genuinely cannot be built, record it in `§4` with what would settle it and move on.
**Commit and push after each batch; report at most once per batch.**

### 0.8 DONE

All of the following, or 45 turns, whichever comes first:

- [x] `DF1` closed — a **production** call site of a DP tier primitive exists, ran live, and the
      resulting row is **pasted from Postgres** (not from a test double)
- [x] `DF2` closed — **and the box as written was wrong, so it is corrected rather than ticked
      over.** It said *"`tier_policy` / `schema_version` / `npc_binding` migrated"*; that named
      three tables and **only one of the three is a table**. `schema_version` is a COLUMN of
      `tier_policy` (`DP-C4`), and `npc_binding` has **no DDL anywhere in the spec**. What
      shipped: `tier_policy` + `tier_capability` migrated, `GetTierPolicy` **answers for real**,
      `UNIMPLEMENTED_METHODS` **8 → 7** with its count guard still green, and the two mis-stated
      blockers corrected. `GetNpcNode` / `ReportNodeHandoff` remain UNIMPLEMENTED on a **design
      gap**, which is the honest status and not the one this box assumed
- [x] `DF3` closed — a Redis-backed cache the SDK reads through for T0–T2, **measured 643.62µs mean over 200 gets against DP-T2's <10ms budget**. Original wording: with a **measured**
      read latency pasted against the `03_tier_taxonomy` budget
- [x] `DF4` closed — the one production aggregate carries a `DP-R2` tier table, and `scripts/dp-r2-tier-table-gate.py` **machine-checks** it by DISCOVERY, so a new aggregate arrives red rather than unnoticed. **Note the box's own wording:** *"every module touching kernel state"* implied many; measured, there is exactly **one** production `DpAggregate` in the tree. The gate covers all of them because it finds them, not because the number is small
- [x] `DF5` closed — five hops, every id pasted (see `§3`). Stated limit: the TS client and the spine BINARY (`DFO-7`) are not driven; every hop shown is production code against a real database
- [x] `cargo test --workspace -j 4` — **2526 passed / 0 FAILED across 189 suites**, run in the two halves `DFO-6` requires (a single DSN cannot serve the workspace: `rebuilder_live` applies `0002`, which DROPs `events`). **`REST_RC=0`** — 2333/0 across 170 suites for everything but `world-service`; **`WORLD_RC=0`** — 193/0 across 19 for `world-service` against its own dedicated pgvector database, as CI provisions it.
      It was 2519/1 an hour ago. The 1 was `DFO-8`, and it is **fixed at root** rather than excused as pre-existing: `rebuilder` could not rebuild ANY projection, and the guard for exactly that was green because it watched a constant instead of the query.
- [x] detached `gate-wiring-gate --run-all` — **`SWEEP_RC=0`**, **90 GREEN / 0 RED / 8 SKIP** (every skip needs a live stack). Re-run at close; the run before it was `SWEEP_RC=1` on ONE gate — `channel-id-adoption`, on the file `DF5` added. The call was already funnelled per `DFD-9`; the missing thing was the RECORDED baseline, which is the ratchet's whole point: an unrecorded count on a new file is indistinguishable from a file that grew. **Second time in one session that `DFD-9`'s lesson caught me and I did not.**

> **Claiming a check passed without pasting its output does NOT satisfy this condition.** The
> `/goal` evaluator reads the transcript and cannot run commands; it enforces persistence, not
> honesty.

---

## 1 · THE BOARD

| batch | subject | state |
|---|---|---|
| ~~`DF1a`~~ | **the write surface's missing half** — `t2_write_channel` / `t3_write_channel`, the scope bounds, `KernelChannelWriteBackend`, and the first production `ChannelTree` | ✅ **CLOSED** — evidence in `§3` |
| ~~`DF1b-i`~~ | **the SDK can name its domain event** — `EVENT_TYPE` + `PAYLOAD_IS_JSON`, both defaulted, backends honour them, non-JSON under the flag REFUSED not wrapped | ✅ **CLOSED** `f4cf8efa3` — row: `event_type npc.said`, `payload {"npc_id":"n-1","utterance":"well met"}` |
| ~~`DF1b-ii`~~ | **one real caller** — the spine's REJECT-COMMIT goes through `dp::t2_write_channel` | ✅ **CLOSED** — production row in `§3` |
| ~~`DF2`~~ | **the control plane's missing tables** — `tier_policy` + `tier_capability` built, `GetTierPolicy` served, `UNIMPLEMENTED_METHODS` 8 → 7 | ✅ **CLOSED** — see `§3` |
| ~~`DF3`~~ | **the T0–T2 cache** — `CacheBackend` seam + `DP-X3` read-through in `dp`, `RedisCache` in `dp-kernel`. Measured **643.62µs** against a **<10ms** budget | ✅ **CLOSED** — see `§3` |
| ~~`DF4`~~ | **`DP-R2` tier tables** — the debt paid for the one production aggregate, and `dp-r2-tier-table-gate` DISCOVERS the rest so a new one arrives red | ✅ **CLOSED** — `§3` |
| ~~`DF5`~~ | **the full dataflow** — player action → actor hub → DP write → events row → wire frame, every hop's id pasted | ✅ **CLOSED** — see `§3` |

**`DF1` split in two on its first measurement, and the split IS the finding.** The row assumed a caller could be wired to the existing surface. It cannot: **`WriteRequest` has seven fields and none of them is a channel**, while `SessionContext` carries `current_channel_id` and the READ side takes the channel from exactly there (`read_projection_channel`). So the SDK's write surface is **structurally incapable of producing a channel-ordered event** — and every write `commit-service` actually performs is channel-scoped, riding `ChannelWriter` for its `channel_event_id`, its epoch fence and its `channel_event_index` row.

**That is why there are zero production callers.** Not neglect — the SDK cannot express the write the production code needs to make. `KernelWriteBackend` would happily accept the call and write an event with `channel_id = NULL`, which `0014_channel_ordering.up.sql` defines as *reality-scoped* and which no channel subscriber will ever read. A silent wrong answer, not an error.

See `§0.3` for why one-caller-first was the forced ordering. It paid immediately: this gap is invisible from the design docs, which describe both forms as though both exist.

---

## 2 · CARRIED IN

| id | what | source |
|---|---|---|
| `DPD-6` | the standards index says `DP-Ch1–Ch37`; the docs declare `Ch1..Ch53`. **16 ids read as ungoverned** in the file CLAUDE.md sends every agent to. Amending a standard is its own change | data-plane coverage run-state §5 |
| `M2` residue | `VerbTable`/`VerbDecl` shipped in `ruleset-core`, and `engine_default.toml` declares **zero verbs** (87 lines, `verb` occurs 0×). The substrate has no rows | this audit |
| `LB0` finding | `lore-enrichment-service` (252 files) already ships the corpus sweep `G-S3` was going to rebuild. Worth keeping when that track reopens | parked lore-bible run-state |

---

## 3 · CLOSED

### `DF1a` — the write surface got its channel half (2026-08-13, `f39982621` + this batch)

**What shipped.** `WriteRequest.channel: Option<ChannelId>` · `t2_write_channel` /
`t3_write_channel` bounded `Scope = ChannelScope`, taking the channel from the CONTEXT (the read
side's stronger convention, not `DP-Ch14`'s `(ctx, channel, …)` sketch — a channel argument would
let a caller write to a channel its session was never moved into) · `Scope = RealityScope` on all
four existing forms · `KernelChannelWriteBackend` over `ChannelWriter` · **`PgChannelTree`, the
first production `dp::ChannelTree`** — every implementor in the tree was a `#[cfg(test)]` double,
so no production session could enter a channel at all, which is the other half of why the channel
write surface had no callers.

**LOCAL path only, stated rather than implied.** `DP-Ch14`'s cross-node routing — the writer-lease
cache and the `RouteChannelWrite` gRPC hop — is **not built**; `route_to_writer` still has zero
occurrences and stays in `CHANNEL_SPECIFIED_NOT_BUILT`. The backend wraps ONE lease and REFUSES a
write addressed elsewhere. A router with one node is a mock in a distributed system's costume.

**THE EVIDENCE — a real row, out of Postgres, written through `dp::t2_write_channel`:**

```
event_id          | 13950068-8b10-4af2-8b2c-8b17bb3289e4
aggregate_type    | dp_channel_fixture
aggregate_version | 1
event_type        | dp.write.applied
channel_id        | 2          <-- THE CLAIM: set, not NULL
channel_event_id  | 1          <-- allocated by the DP-Ch11 CAS
writer_epoch      | 1          <-- the DP-A16 fence stamped it
payload           | {"b64": "KgAAAA=="}          (42i32 LE, byte-exact through the seam)
metadata          | {"dp_tier": "t2", "dp_scope": "channel",
                     "dp_cache_key": "dp:2f7c7508-…:c:2:t2:dp_channel_fixture:b2d7e7c0-…"}
```

The cache key carries `c:2` — the `DP-K7` channel form, with the scope marker and the channel in
it. `channel_event_index` got its row in the same transaction.

**Green, real exit codes:** `dp` 101 passed / 0 failed across 10 suites · `integration_dp_channel`
5 passed / 0 failed **against live Postgres** (`dp_kernel_test` on `infra-postgres-1`, migrations
0002/0004/0005/0013/0014/0016/0019/0020 + default partition) · `dp-aggregate-gate` 0 ·
`crate-purity-gate` 0 · `dp-oracle-coverage-gate` 0 · `gate-wiring-gate` 0 (104 gates) ·
`phase0-reconcile-gate` 0.

**The bites — `scripts/dp-df1a-bite-gate.py`, 5/5, `rc=0`,** and in the tree rather than in this
transcript, because a bite that lives only in a transcript is a defect this project has paid for
twice. Each leg's expected-red marker is the message that ACTUALLY appears, verified by running it:
two legs red on the assertion *under* the `expect_err` (the mutant reaches the dead pool instead of
the guard), and the ancestors leg is caught by `move_to_channel`'s own cycle check — a stronger
guard than the one that leg aimed at. The trybuild pair was bitten by hand:
*"Expected test case to fail to compile, but it succeeded."*

**The coverage ratchet moved on its own, in the right direction:** `DP-Ch` unproven 13 → 12, and
`UNSITED_OK[DP-Ch14]` **EXPIRED** — the row said the invariant could have no enforcement site, and
building one made the gate demand its deletion. **sited 84/84 · proven 65 → 66/84 · `UNSITED_OK`
21 → 20.**

---

### `DF1b`, measured — and the row was wrong in the same way `DF1a`'s was

`DF1a` ended pointing at the spine's REJECT-COMMIT, whose own comment calls it *"the doc-15
`t2_write` outcome"*. Measuring it before touching it (`§0.4`) found that **routing it through the
SDK today would break it**, four ways:

| what the spine writes | what `KernelChannelWriteBackend` would write |
|---|---|
| `event_type: "proposal.rejected"` — read by **two projectors in two languages** (`commit-service/src/wire.rs:92`, `game-server/src/wire/turnOutcome.ts:95` `TURN_OUTCOME_TYPES`) | `"dp.write.applied"`, hardcoded. **Both projectors stop recognising the event.** |
| a structured payload — `rejected_at_stage`, `reason` | `{"b64": "…"}`, an opaque blob |
| metadata the consumers read — `event_category: "T6"`, `turn_number` as a decimal STRING (`CWC-A2`) | `dp_tier` / `dp_cache_key` only |
| `ruleset_digest: Some(isle.digest)` — **`RLS-A13`'s pin, derived from the rules the island actually ran** | `None` |

**So the deeper measurement, and it is the data-foundation finding of this batch:**

* Production writes in the game tier are **domain events**: `proposal.rejected`, `turn.resolved`,
  `ruleset.epoch_activated`, `npc.said`, `world.tick` — named, schema'd, projected.
* **Nothing in the tier persists an aggregate STATE DELTA**, which is what `DP-K5`'s
  `t2_write(ctx, id, delta)` models. Measured: `set_quantity` / `QuantityOrdinal` never reach a
  write path in `commit-service`. **The actor hub folds quantities in memory and they die with the
  island.**
* Two event-sourcing conventions share one `events` table, and the SDK speaks only the one nobody
  uses.

**And the spec sides with the tier, not with the SDK.** `03_tier_taxonomy`'s own `DP-T2` examples
are *"chat messages, most gameplay actions (move intent, NPC dialog line, skill use)"* and `DP-T3`'s
are *"currency mutations, item trades, canon promotion"* — those ARE the domain events already
being written. So the SDK is meant to carry them, and its inability to name one is the gap.

**`contracts/events/_registry.yaml` has 16 entries and `proposal.rejected` is NOT one of them** —
nor is `dp.write.applied`. That is pre-existing and is `DFO-4`.

**The constraint that shapes the fix:** `crates/dp` is a PURE crate — `crate-purity-gate` pins
`external: {"uuid"}` — so it cannot hold a `serde_json::Value`. The payload stays BYTES at the
seam and the BACKEND interprets them. Two defaulted associated consts on `DpAggregate`
(`EVENT_TYPE`, and a flag for whether `Encode` produced JSON) keep all eleven existing impls
compiling untouched while letting a production aggregate say what it really writes — and a
non-object payload under that flag must be a loud REFUSAL, never a fallback to base64. A fallback
is how `DF1a`'s NULL-channel write stayed silent for a month.

### `DF1b-ii`, designed from measurement — three envelope facts, three owners

Routing the spine through the SDK still drops three things the wire contract needs. Measured who
actually reads each:

| fact | who reads it | who should OWN it |
|---|---|---|
| `ruleset_digest` | `RLS-A13`'s pin; `epoch_activation_live.rs` asserts it | **the writer node** — it is the digest of the rules the island is running, and today every call site must remember to stamp it. A forgotten one is silent |
| `turn_number` (metadata, decimal STRING per `CWC-A2`) | **`game-server/src/wire/turnOutcome.ts:125`**, which calls it *"authoritative from the COMMIT — never recomputed here"* | **the channel** — `channel_writer_state.last_turn_number` is DB-authoritative, and `ChannelAppended` already returns it |
| `event_category` (`"T6"` reject, `"T8"` epoch) | `epoch_activation_live.rs:100` asserts it; **removed from the WIRE by `PID-D5`** because reading it off a proposal was a privilege-escalation bug | **the event type** — it is a property of what the event IS, so it belongs beside `EVENT_TYPE` on the aggregate |

**The split is not a workaround, it is a correction.** Today all three are stamped by hand at each
call site. Moving each to whoever owns the fact makes a forgotten stamp impossible rather than
merely unlikely — and `RLS-A13`'s digest is exactly the kind of thing that goes missing quietly.

**⚠ And the measurement turned up a live discrepancy to settle first:** `turnOutcome.ts` says
`turn_number` is *authoritative from the COMMIT*, but the spine stamps it from a LOCAL counter
(`turn_number` in `bin/spine.rs`) while the DB's value comes back on `ChannelAppended.turn_number`.
Those are two sources for one number. Whether they can diverge is `DFO-5` — it must be answered
before the backend starts stamping from the DB, because if they already differ, moving the source
would change observable behaviour and look like the SDK's fault.

### The four open rows, cleared 2026-08-13 — and one of them was a live bug

| row | outcome |
|---|---|
| `DFO-4` | ✅ `proposal.rejected` registered (`0ae3297c4`) + `ProposalRejectedV1`. `go test ./...` ok |
| `DFO-5` | ✅ **it was a REAL BUG, and the fix already existed** — see below |
| `DFO-3` | ✅ both blockers corrected, and the oracle got the arm that would have caught them |
| `DFO-2` | ✅ `ReadRequest.channel` + the backend REFUSES a channel read it cannot serve |

#### `DFO-5` — the fix was written, and never wired to its consumer

`DFO-5` asked whether the spine's `turn_number` could diverge from the DB's. **It diverges on every
restart**, and the reason is worse than an oversight:

`recovery::WriterRecovery::turn_number` exists *specifically* to fix this. Its own doc comment says
so, in the past tense: *"`spine` seeded it to 0 on every start, so a restart silently rewound the
turn number and every client's `turn_number` went backwards … so it is fixed here rather than left
as a known-broken sibling."*

It was queried from the database, returned, **printed at `services/commit-service/src/bin/spine.rs:123`** — and then line 169 read
`let mut turn_number: u64 = 0;`. The producer landed; the consumer did not. **The defect survived
the commit that claimed to have fixed it.** Its sibling one line up, `aggregate_version`, was wired
correctly, so two adjacent decisions disagreed in a diff nobody re-read — `NV`'s hardest shape.

It is not cosmetic: `game-server/src/wire/turnOutcome.ts:125` reads `meta.turn_number` and calls it
*"authoritative from the COMMIT — never recomputed here"* before rendering it.

**The mechanism** is `services/commit-service/tests/recovered_values_are_consumed.rs`: it parses
`WriterRecovery`'s fields out of the struct (not a hand-written list — a second list is a second
place to forget) and fails if the spine never READS one outside a `println!`. Bitten by restoring
the original bug: `produces ["turn_number"], and bin/spine.rs never READS it`, restore byte-exact,
green.

#### `DFO-3` — a blocker that is satisfied is not a blocker

Two `DEFERRED_VARIANTS` rows said they waited on `NodeId`, which has existed since slice 4. The
existing arm only asked whether a reason was *written*; an implemented-XOR-deferred check cannot see
a reason go stale. **The new arm red on both rows on the live tree the moment it was added** — that
is its bite, unstaged. The real blocker is one column short of the type: `channel_writer_state` can
say your epoch is stale and cannot say who holds the lease, so `expected: NodeId` has no value to
carry. The arm's limit is stated in the code: it covers blockers written as a bare type name; a
prose blocker has no mechanical subject and is held by the non-empty check and a reader.

#### `DFO-2` — the read side got the address, and an honest refusal

`ReadRequest.channel` now carries what `read_projection_channel` already verified. The snapshot
store has **no channel dimension**, so `KernelReadBackend` cannot serve a channel read — it now
REFUSES, naming the channel and why, instead of returning the reality-wide row. Two channels holding
one aggregate id would previously have returned each other's state in silence. Bitten: neutering the
guard turns the refusal into `Ok(None)`, a plain miss indistinguishable from "no such aggregate",
which is exactly how the wrongness stayed invisible.

**Green at close:** `dp` + `dp-kernel` **444 passed / 0 failed across 17 suites** against live
Postgres.

### `DF1b-ii` — the SDK has a production caller, and the row proves nothing was lost

`reject_commit::commit_rejection` → `dp::t2_write_channel` → `KernelChannelWriteBackend` →
`ChannelWriter`. **The row, out of Postgres, written by production code:**

```
event_type        | proposal.rejected     <-- NOT dp.write.applied; both projectors dispatch on it
aggregate_type    | combat_session
aggregate_id      | enc-1
payload           | {"reason": "verb `definitely_not_a_verb` is not in the reality's
                     vocabulary", "rejected_at_stage": "vocabulary"}   <-- a body, not a blob
metadata          | {"dp_tier": "t2", "dp_scope": "channel", "turn_number": "7",
                     "event_category": "T6", "dp_cache_key": "dp:b805adf7-…:c:1:t2:…:enc-1"}
ruleset_digest    | d1ce5eed…beef        <-- RLS-A13's pin survived the seam
channel_id        | 1
channel_event_id  | 1
writer_epoch      | 1
```

`turn_number` is `"7"` — a decimal STRING (`CWC-A2`) and **unadvanced** (`EVT-V4`), asserted against
a non-zero counter on purpose: at 0 the claim would pass whether or not the counter was read at all.

**The three envelope facts went to three owners, and measuring corrected my own design.** The first
version of this row said the CHANNEL owned `turn_number`, because
`channel_writer_state.last_turn_number` is DB-authoritative. Measuring the spine before building it
showed that wrong: **the spine never calls `advance_turn`**, so that column stays 0 on its channel
and `recovery` reads the turn back out of EVENT METADATA. Moving the stamp to the DB would have
replaced a correct value with a zero. Final split: `event_category` → the aggregate (it is a
property of what the event IS) · `ruleset_digest` and the turn counter → the **writer node**.

Each is now stamped once by whoever owns the fact, instead of by every call site that might forget —
which is strictly better than what it replaced, and is why this is a correction rather than a move.

**Green:** `dp` + `dp-kernel` + `commit-service` **569 passed / 0 failed across 44 suites** ·
`file-ceiling-gate` OK (`bin/spine.rs` held at exactly its allowlisted 375 by extracting
`reject_commit`, the same reason `epoch_commit` is its own module).

**⚠ WHAT WAS NOT PROVEN, stated rather than glossed:** the spine BINARY was not driven end to end.
It hangs — see `DFO-7`, and it hangs at `HEAD` too, so it is not this change's doing. The live
witness calls the production functions against a real database; the one double is the
`ControlPlane` that mints the session.

### `DF2` — `GetTierPolicy` answers (2026-08-14, `e9ed525d4` + `a72f6237d`)

`040_tier_policy` transcribes `DP-C4`'s DDL; the wiring runs
`MetaRead::get_tier_policy` → `MetaControlPlane::tier_policy` → the handler.
**`UNIMPLEMENTED_METHODS` 8 → 7.**

**Five CHECKs are mine**, each because the spec's DDL permits a value that means nothing
(`schema_version = 0`, an empty owner, `tiers_allowed = '{T4}'`, an empty grant, a grant permitting
neither read nor write). **11/11 constraint bites** against real Postgres — every constraint
attempted with a value it must refuse, plus legal rows that must be accepted. up → down → up
round-trips clean.

**The trait method is REQUIRED, not defaulted.** A default returning an empty `Vec` would compile
all four implementors untouched and turn `GetTierPolicy` from an honest `UNIMPLEMENTED` into a
snapshot saying *no aggregate type exists* — which `DP-C4`'s registration flow makes deploy-breaking,
since a service whose aggregate is absent fails at `DpClient::connect`.

**`snapshot_version` is 0 and asserted at 0.** `DP-C5` gives the field meaning through
`StreamTierPolicyUpdates`, and nothing produces a version sequence. A fabricated value would hand a
resuming subscriber a token that looks usable and skips rows.

**Three registers demanded to shrink, each on its first opportunity:** `UNIMPLEMENTED_METHODS`, the
surface count guard, and `CP_TABLES_WITHOUT_A_MIGRATION`.

**Two more blocker strings were wrong the way `DFO-3`'s were.** `schema_version` is a COLUMN of
`tier_policy`, not a missing table; `npc_binding` has **no DDL anywhere in the spec**, so it is a
design gap rather than an unwritten migration. Neither was invented — a fabricated shape in a LOCKED
tier is worse than an absent one, because the next reader cannot tell which it is.

### ✅ `§0.8`'s sweep box — **`SWEEP_RC=0`**

`python scripts/gate-wiring-gate.py --run-all`, detached: **89 GREEN · 0 RED · 1 SKIP**
(`rust-bench-gate` needs a live stack and reports `NOTRUN(setup)`, which the sweep does not count as
a verdict). Includes the new `dp-df1a-bite-gate` at 118.6s and `dp-oracle-bite-gate` 19/19.

**It took two red runs to get here, and both were this run's own doing** — see `§5`. Nothing was
baselined to make it green: `reality-id-adoption` caught a real design flaw (`wire` took a bare
`Uuid` beside the session that already held the verified `RealityId`), `channel-id-adoption` caught
me reproducing a growth pattern whose fix I had read earlier the same day, and the two bite
harnesses scored `MISUSE` — refusing to certify legs whose anchors my own edits had moved.

### `DF3` — the T0–T2 cache exists, and it is measurably a cache (2026-08-14)

`redis` was in **one** Cargo.toml in the whole Rust tree (`commit-service`, for its proposal bus)
and **zero** DP crates, so every tier reached Postgres and `DP-T0..T3` was a taxonomy with one
implementation. `CacheBackend` is now the third seam beside `ReadBackend`/`WriteBackend`; `dp` owns
`DP-X3`'s ALGORITHM and `dp-kernel` owns the socket, which is what keeps `crate-purity`'s
`external: {uuid}` true.

**THE MEASUREMENT — `DP-T2`'s read budget is `<10ms` from cache:**

```
DP-T2 cache read: mean 643.62µs over 200 gets (budget <10ms)
```

Local docker Redis, so this is not a production SLO figure — it is evidence the cache path is
ORDERS faster than the budget rather than accidentally slower, which is the claim worth checking on
a first wiring.

**Three decisions taken from the spec rather than from taste:**

* **A FAILURE IS NOT A MISS.** `get` returns `Result<Option<_>>`. Flattening the error into
  `Ok(None)` would be simpler and would make `DP-X10`'s third case unrepresentable — a **T3 write**
  must return `CircuitOpen{redis}` because it cannot fan out its invalidation, and a T3 write that
  acked having invalidated nothing is precisely what `DP-X1` says T3 exists to prevent.
* **THE TIER decides whether a cache is consulted.** `T0::CACHE_TTL` is `None` (`DP-X7`: *"not
  cached, in-proc only"*), so the branch is on an associated const of the aggregate's own tier, not
  a runtime flag. A T0 aggregate cannot be cached by mistake.
* **It caches the BYTES.** `Encode` encodes a `Delta`; a `Projection` is what a read returns. The
  first draft tried to re-encode the projection and needed an `encode_projection` that does not
  exist — inventing one would have put two serialisations on one aggregate, and two encoders are
  two things that can disagree about a byte.

**`PSETEX`, not `set_ex`, and the reason is a bug that never shipped.** `set_ex` takes SECONDS. Safe
for every `DP-X7` default (shortest is 60 s) and silently wrong for the per-aggregate overrides
`DP-X7` permits: a 300 ms TTL integer-divides to `0` and the entry is either rejected or stored with
**no expiry**, which is the *"invalidation loss plus an infinite TTL = permanent stale read"* the
spec names in as many words. Caught **while drafting**, and pinned live by
`a_sub_second_ttl_still_expires`.

**Green:** `dp` + `dp-kernel` **453 passed / 0 failed across 18 suites** against live Postgres AND
live Redis · read-through bites **4/4** genuine, byte-exact · 5 live cache tests including an
unreachable-cache degrade and a refused zero TTL · `crate-purity` and `dp-aggregate-gate` green.

**Still unbuilt, and named rather than implied:** `DP-X2`'s other two Redis roles. Invalidation
pub/sub does not exist, and the durable channel stream `dp:events:*` still has **zero producers** —
`spec_oracle_channels.rs`'s asserted trigger is what will say when it arrives. Calling this batch
"Redis support" would have covered all three; it built one.

### `DF4` — `DP-R2` gets a mechanism, and the rule turns out to have had no subjects

**Measured first:** exactly **ONE** document in the entire tree contained a `DP-R2` tier table —
`11_access_pattern_rules.md`, **the file that defines the template**. Zero feature docs complied.
`DP-R2`'s stated enforcement is *"review — governance checklist requires the tier table before
sign-off"*, and a checklist nobody runs is a rule with no subjects.

**`2026-08-06-command-hub.md` said so about itself**, in its own header: *"`DP-R2` is OWED and
unpaid: no `DP-T0..T3` tier table exists for any aggregate this spec introduces … Recorded rather
than quietly fixed — the debt is the finding."* `DF4` pays it, for the one aggregate that spec has
since produced in code.

**The table** declares `combat_session` (what `ProposalRejected` writes) as **write T2, no read
tier** — T2 because `DP-T2`'s own examples are *"most gameplay actions … non-canon state changes"*;
not T3 (which blocks the ack on invalidation fan-out, and a refusal has nothing to invalidate); not
T1 (whose ≤30 s crash-loss tolerance would mean a refusal the player never sees). **No read tier
because there is no reader** — the event goes to the client wire, never back through the SDK. `DP-R2`
calls an ambiguous entry a blocker, so the absence is stated rather than left blank.

**`scripts/dp-r2-tier-table-gate.py` is the mechanism, and it DISCOVERS rather than enumerates.**
An enumerated list is `NV-3`'s *default-uncovered* shape: it says nothing about the aggregate added
tomorrow. The gate walks the source for `impl DpAggregate`, reads each `TYPE_NAME`, excludes
`#[cfg(test)]` fixtures by brace-matched span, and demands a row for the rest. **8 self-test cases**
including the one that matters most — that the fixture exclusion does **not** swallow a production
impl in the same file, because an over-broad exclusion is exactly how this gate would go quietly
vacuous.

**And its own bite rows found a vacuity in it.** `gate-bite-harness` ran four mutations and **one
SURVIVED**: the empty-walk `MISUSE` guard lived in `main()`, which the self-test never calls, so a
broken walk would have passed on nothing and no case would have noticed. The decision is now
`verdict()`, reachable by both, with two new arms — an empty tree is MISUSE, and a clean tree is
not, so the first cannot pass by always returning 2. **4/4 red** after the fix.

**Green:** gate `rc=0` (1 production aggregate, `combat_session`) · `--self-test` 8/8 ·
`gate-bite-harness --gate dp-r2-tier-table-gate` **4/4 red** · `gate-wiring-gate` **105 gates**, all
wired · `gate-self-tests` 99 green. Six-step bite on the table itself: deleting the row reds the
gate naming the aggregate and its file, restore byte-exact, green.

### `DF5` — the full dataflow, five hops, every id printed (2026-08-14)

```
HOP 1  player action      input_id = 48df0060-fb18-487c-adbb-17cf4a1752f6
HOP 2  actor hub          actor_id = 7 · fold = [{"actor":"7","delta":-3,"quantity_ordinal":0}]
HOP 3  DP write           channel_event_id = 1 (dp::t2_write_channel)
HOP 4  events row         event_type = turn.resolved · channel_id = Some(1) ·
                          channel_event_id = Some(1) · turn_number = "5" ·
                          ruleset_digest = d1ce5eed…
HOP 5  wire frame         {"channel_event_id":"1","detail":{"events":[…],"type":"resolved"},
                           "kind":"resolved","turn_number":"5"}
```

`turn_number` went **4 → 5**: `DP-A17` says an APPLIED resolution consumes the turn, the mirror of
`EVT-V4`'s refusal that must not. Started at 4 on purpose — at 0 the claim would pass whether or not
the counter was read.

**`bin/spine.rs` now builds NO event envelope at all.** Both commit paths go through the SDK, and
`EventEnvelope`, `now_rfc3339` and `Uuid` became unused imports — the absence is the evidence.
What it used to stamp by hand at each call site is now owned by whoever owns the fact: the event
name and category by the aggregate, the `RLS-A13` digest and the turn counter by the writer node,
`input_id` and the unrun admission stages by the write.

**Two gates corrected the design mid-batch, and both corrections are the finding:**

* **`R10`** refused a `macro_rules!` emitting three impls — after I wrote a comment claiming the rule
  *"does not reach a service crate"*. It reaches the whole repo. **I asserted an exemption from
  memory instead of reading the rule.**
* **`R4`** then refused four aggregates sharing `TYPE_NAME = "combat_session"`: *"two impls under
  one name = two cache entries for one logical aggregate, under two coherency contracts."*
  `TYPE_NAME` is a cache-key token. **Which means `DF1b-i` had put `EVENT_TYPE` on the wrong
  thing** — correct while an aggregate wrote one event, wrong the moment it writes four. Corrected
  to `EVENT_TYPES` (the closed SET, on the aggregate) + a per-write choice the SDK REFUSES outside
  it. A free string would have put an unregistered vocabulary beside the registry, which is what
  the original one-type-per-backend design was right to fear.

**Also closed a contract gap found one path over:** `turn.resolved` / `turn.discarded` /
`turn.buffered` were written by the live spine since S3b and read by `turnOutcome.ts`, with **no
schema and no validator entry** — the same absence `DFO-4` found for `proposal.rejected`.

**WHAT THIS IS NOT.** The TypeScript client is not driven: `turnOutcome.ts` is the other side of
this frame and has its own suite, and asserting the Rust projection while claiming the browser
rendered it would be the mock-standing-in-for-live shape. The spine BINARY is not driven either —
`DFO-7`, and it hangs at `HEAD` independently of this work, measured both ways. Every hop above is
production code against a real database; the boundary is stated rather than blurred.

**Green:** `dp` + `dp-kernel` + `commit-service` **579 passed / 0 failed across 46 suites** ·
`dp-aggregate-gate`, `dp-r2-tier-table-gate`, `crate-purity-gate`, `file-ceiling-gate` all rc=0.

---

## 4 · OPEN ROWS — each must carry a MECHANISM, not prose

| id | what | mechanism / what would settle it |
|---|---|---|
| ~~`DFO-8`~~ | ✅ **CLOSED — and it was not environmental.** Root cause: `decode_event` reads `ruleset_digest`, and of the TWO queries feeding it the global pair BUILT their column list from `EVENT_COLUMNS` while the per-aggregate one **restated it by hand and omitted the column** — so every per-aggregate rebuild failed on its first event and `rebuilder` could rebuild nothing. **The guard for exactly this was GREEN**: it asserted against `EVENT_COLUMNS`, which was correct, so it watched the copy with no defect — `NV`'s adjacent-decision shape. Repaired by DERIVING the query from the constant (`D-319`: deriving beats asserting, it removes the second fact rather than watching it), and the bin now PRINTS each failure's reason instead of only a count. Original: **`rebuilder_round_trip_live_smoke` fails at `HEAD`, and it is not this run's.** `[rebuilder] projection=canon_projection rebuilt=0 skipped=0 failed=1 events=0`. Three environmental causes were eliminated in turn: a shared DB (given its own), a missing pgvector library (moved to the `loreweave/postgres-knowledge` image, where `0006` applies clean), and a dirty schema (dropped and recreated). It fails the same way on a fresh dedicated database. **Attribution checked twice**: no file this run touched is in its path — `git log --name-only 718c29fc9..HEAD` matches only `scripts/projection-coverage-lint.sh`, a shell gate — and neither `bin/rebuilder.rs` nor `crates/rebuilder` reads the event registry or names `canon_projection` | run the `rebuilder` bin by hand against a seeded reality and read why one aggregate fails; `failed=1` with `events=0` says it never loaded a stream, which points at the seeding step rather than the apply. Worth doing because CI runs this leg, so either CI is green on a setup this box cannot reproduce, or the leg is red there too |
| ~~`DFO-7`~~ | ✅ **CLOSED 2026-08-14 — `BLOCK 0` is Redis for *wait forever*.** `connect_signal_bus` passed `block_ms: 0` under a doc comment reading *"`block_ms: 0` NEVER blocks"*, and `BusConfig`'s own field doc agreed — both false, and neither had ever been run against a server. `drain_and_reconcile` is the FIRST statement of the spine's loop and reads `lw.meta.events`, *"empty almost always"*, so the binary blocked on iteration one before it ever saw a proposal. Fixed where the value becomes a command: `read_options()` OMITS the argument at 0 rather than sending `BLOCK 0`, which makes both comments true instead of rewriting them to describe the bug. Bitten on the BINARY: `DRAIN_RC=0` → `MUTANT_RC=124`, hanging on the same printed line this row recorded → restored byte-exact → `RESTORED_RC=0`. The binary is now driven by `scripts/smoke/spine-drain-once.sh` + `tests/spine_drain_once_live.rs`, so *"nothing exercises the one path a deployment runs"* is no longer true. See [the run-state](2026-08-14-spine-drain-once-RUN-STATE.md). Original: **`bin/spine.rs --drain-once` does not drain once — it BLOCKS.** With a message waiting on the stream it reaches *"epoch signals: lw.meta.events …"* and then hangs past a 120s timeout. **Measured at `HEAD` with this whole change stashed: `HEAD_RC=124`, identical** — and an instrumented run showed this change's own code completing (`WIRE: channel resolved`) before the hang, so the block is downstream in the loop, most likely the epoch-signal drain. Two orphaned `spine.exe` processes survived the killed runs and locked the binary, which is the second-order cost | bisect the loop: `drain_and_reconcile` vs `bus.fetch`. It is worth fixing because it is why every live smoke drives COMPONENTS rather than the binary — the one path a real deployment actually runs is the one nothing exercises |
| ~~`DFO-6`~~ | ✅ **CLOSED 2026-08-14, and the row understated it.** It asked to mirror CI's five legs; the measurement found CI provisions a database for **6 of 21** live Rust targets, and the `--workspace` leg sets NO DSN — so the other fifteen ran in CI only in their SKIPPED form. Shipped: `contracts/testing/live-suites.yaml` (authored, because two suites reach `env::var` with the name as a PARAMETER and a grep reports full coverage of an incomplete list), `scripts/live-suite-registry-gate.py` (13 biting arms; cross-checks CI both ways + a ratchet on the uncovered count) and `scripts/live-suites.py` (one database per suite, prints WHY not a count, and reports SKIPPED as NOT-a-pass). **`LS_RC=0` — 21/21.** It immediately found `epoch_activation_live` **dead since `M1`** and never once run. See [the run-state](2026-08-14-live-suites-RUN-STATE.md). Original: **`cargo test --workspace` cannot run against ONE database.** `CARGO_RC=101`: **2505 passed / 1 failed**, the one being `rebuilder_round_trip_live_smoke`. Not my diff — no file I touched is in its path, and it references neither the event registry nor `canon_projection`. Two distinct causes, both environmental: (a) `dp_kernel_test` on `infra-postgres-1` has a `vector` CATALOG ROW with no library, so `CREATE EXTENSION IF NOT EXISTS` says *"already exists, skipping"* and every use fails later; (b) the test applies `0002`, which **DROPs `events`** — wiping `content_sha256`, the channel columns, `ruleset_digest` and the turn columns, which is why the channel suite then failed 6 ways. CI gives it its OWN DB for exactly this reason | a dev-side runner that provisions one DB per live suite, mirroring `foundation-ci.yml`'s five. Until then `--workspace` with a single DSN is a trap that reports code failures for a schema someone else dropped |
| ~~`DFO-5`~~ | ✅ **CLOSED — it was a real bug.** Original: **`turn_number` has two sources.** `turnOutcome.ts:125` calls it *"authoritative from the COMMIT — never recomputed here"*; `bin/spine.rs` stamps it from a local counter, while the DB returns its own on `ChannelAppended.turn_number`. Two sources for one number, and the consumer believes one of them | read both at the same append and compare. A test asserting `metadata.turn_number == ChannelAppended.turn_number` on a live commit would settle it AND keep it settled. Blocks `DF1b-ii`'s move of the stamp to the backend: if they already diverge, moving the source changes behaviour and would look like the SDK's fault |
| ~~`DFO-4`~~ | ✅ **CLOSED** `0ae3297c4`. Original: **`proposal.rejected` is written by the live spine, read by two projectors, and is NOT in `contracts/events/_registry.yaml`** (16 entries; it is absent, as is `dp.write.applied`). So the event validator has no schema for the one domain event this system actually produces in anger | registering it is cheap and in scope for `DF1b-i`, which needs a registered type to point `EVENT_TYPE` at. Recorded separately because it is PRE-EXISTING — found by `DF1b`'s measurement, not caused by it |
| ~~`DFO-2`~~ | ✅ **CLOSED** — `ReadRequest.channel` + a refusal the backend can actually make. Original: **`ReadRequest` has no channel either.** `read_projection_channel` checks the session IS in a channel, then builds a `ReadRequest` that cannot say WHICH — so the backend addresses it by cache key alone, and `KernelReadBackend` reads snapshots by `(reality, type, id)`, ignoring the key. A channel-scoped read is therefore servable only by accident | the write side's fix is the template: a `channel: Option<ChannelId>` on `ReadRequest`, taken from ctx, plus a channel read backend. Not done here because `DF1` is the WRITE path and a read with no producer to read from would be the orphan shape again — it becomes real the moment `DF5` needs to read back what `DF1b` writes |
| ~~`DFO-3`~~ | ✅ **CLOSED** — blockers corrected AND an oracle arm that reds on a satisfied blocker. Original: **`DEFERRED_VARIANTS`'s stated blocker for `WrongChannelWriter` is satisfied, and the row is still right.** It names `NodeId`, which has existed since slice 4. The REAL blocker is that `channel_writer_state` has no writer-node column, so the DB can say your epoch is stale but not who holds the lease — `expected: NodeId` has no value to carry. The oracle checks implemented-XOR-deferred and **cannot check that a reason is still the reason** | the corrected blocker is recorded in `dp_channel::channel_err`'s doc comment, where a reader meets it. A mechanism would be an arm asserting each deferred row's blocker type is ABSENT — cheap for a type name, and it would have caught this |
| ~~`DFO-1`~~ | ✅ **CLOSED by `DF1a`** — all four write forms now bind `RealityScope`, the two channel forms bind `ChannelScope`, and `tests/ui/write_wrong_scope.rs` + `channel_write_wrong_scope.rs` pin both directions. Original text: **the write side had no `Scope` bound at all.** `read_projection_reality` requires `A: DpAggregate<Scope = RealityScope>` — a wrong-scope read is a **compile error**, and `tests/ui/read_wrong_scope.rs` is that claim executed by rustc. `write_at_tier` bounds `Tier` and **not** `Scope`, and performs no runtime scope check. A channel-scoped aggregate written through `t2_write` is accepted silently | closed by `DF1a` giving the write side both forms with the scope bounds the read side already has, **plus a `tests/ui/write_wrong_scope.rs`** mirroring the read-side trybuild case. Until then the asymmetry is real and undefended |

---

## 5 · DRIFT REGISTER

**A run that ends with an empty drift log is not clean — it is dishonest.**

| id | what happened |
|---|---|
| `DFD-2` | **My bite harness restored with `shutil.copy2`, which preserves mtime — so cargo kept running the MUTANT binary while the sha256 check reported BYTE-EXACT.** Four arms scored *"did not return to green"* and a fifth scored a false baseline failure, and the obvious reading was that my guards were broken. They were not; the harness was. **A verification that is silently wrong is worse than one that fails** — had those arms happened to pass, I would have banked five bites that never ran. Found by disbelieving a suspicious pattern (green, red, green-fails, next-arm-green-again), not by any check. The repo's own machinery was already immune: `dp-slice5b-bite-gate.write_txt` uses `path.write_bytes`, which stamps a fresh mtime. **The committed gate imports it rather than repeating my mistake**, and its header says why. |
| `DFD-3` | **Two of my five expected-red markers were wrong, and one was wrong in an interesting way.** I wrote each marker from what the mutation *ought* to trigger. For two legs the mutant still Errs — the lazy pool cannot connect — so `expect_err` succeeds and the red is the assertion beneath it. For the ancestors leg, `move_to_channel`'s own cycle check (*"a channel that is its own ancestor is a cycle"*) fires before the witness's assertion — a STRONGER guard than the one that leg aimed at. All three were scored `WRONG-REASON` by the harness's own marker check and corrected against real output. **Without that check all three would have counted as bites**, which is `BDR-50`/`BDR-56` exactly: a red for an unrelated reason is the failure mode that looks most like success. |
| `DFD-4` | **The bite gate refused to start on a STALE lock** (`exit 2`) left by a `dp-oracle-bite-gate` run I had killed on a 2-minute timeout. The refusal was correct and said exactly what to check; I verified pid 37956 was dead before clearing it rather than deleting the lock on sight. Recorded because §0.6's *"a refusal is exit 2, which is failure evidence, not a passing verification"* met its own case within hours of being written, and because the killed run is itself the hazard: a 2-minute foreground timeout on a harness that needs longer. |
| `DFD-5` | **I used a heredoc for a patch containing backslash escapes, and bash ate them** — producing a `SyntaxError` from a string literal split across lines. Hazard #5 in `§0.6`, which I wrote into this file this morning, and the eighth recorded instance. Knowing a rule and having it in the file is not the same as following it: **intent is not a mechanism**, which is the standards index's own sentence, arriving here about me. |
| `DFD-6` | **The task notification said "exit code 0" and cargo had exited 101.** The notification reports the WRAPPER's status, not the process's. `§0.6`'s first hazard — *read the process's REAL exit code, never a task notification's* — met its own case, and only because I went looking for the number instead of accepting the summary. Had I trusted it, "workspace green" would have gone into the evidence with 1 failure in it. |
| `DFD-7` | **I ran the whole workspace against ONE database and it destroyed the schema.** `rebuilder_live` applies `0002`, which DROPs `events`; every later `ALTER TABLE` column went with it, and the channel suite then failed six ways with `column "content_sha256" does not exist`. I read that as a possible regression from my own change before measuring. It was self-inflicted environment damage, and CI had the answer in a comment I had already read once: *"it needs its OWN DB"*. |
| `DFD-8` | **I wrote a test against a struct name I never checked** — `recovery::Recovered`, when it is `WriterRecovery`. The test's own subject-assert caught it on the first run, which is the only reason it was not a check that silently passed on nothing. Then its field parser took the DECLARATION line as a field and reported a confident failure about a phantom named `struct WriterRecovery {`. **Both are `§0.5` — a string that looks like a subject — inside the test written to catch producers with no consumer.** Seventh and eighth instances. |
| `DFD-9` | **I reproduced a documented growth pattern hours after reading the comment that documents it.** `integration_channel_writer.rs` funnels every `ChannelId::unverified` through ONE helper and says why: it went 3 → 8 in a single commit, the ratchet refused, and funnelling makes the count a property of the FILE rather than of how many tests it has. **I read that comment while studying the suite for `DF1a`** — and then added 8 calls across three files and got the identical refusal. Knowing the fix and having read its rationale did not prevent the defect; the GATE did. Which is the standards index's own sentence arriving again: intent is not a mechanism. |
| `DFD-10` | **Two bite harnesses went red as `MISUSE` because `DF2` moved their anchors, and that is the harnesses working.** Neither scored a false green: each REFUSED to certify a leg it could no longer run. The oracle's failing leg was the `DP-C2` **shrink arm** — *"a register row for a table that DOES have a migration"* — anchored on the very `tier_policy` row the oracle demanded be deleted when `040` landed. The leg's own subject happened to the leg. Worth recording because the tempting fix is to delete a leg whose anchor rotted, and the correct one is to re-point it at a live row. |
| `DFD-11` | **I wrote a comment claiming an exemption from a gate, and the gate refused the commit.** The three turn outcomes went in as a `macro_rules!` with a note saying `dp-aggregate-gate`'s `R10` *"does not reach a service crate"*. It reaches the whole repo. I reasoned about the gate's scope from memory rather than reading it — and then wrote the conclusion into the source as though it were checked, which is worse than getting it wrong silently: the next reader would have believed it. |
| `DFD-12` | **`R4` then proved `DF1b-i`'s design wrong, three commits after I shipped it.** `EVENT_TYPE` as an associated const is correct for an aggregate that writes ONE event and incoherent for one that writes four — and the encounter line writes four. Nothing about that was visible when `DF1b-i` landed with its single `proposal.rejected`; it became visible the moment a second event needed the same aggregate. Recorded because the instinct was to add a second aggregate and keep the const, and the gate is the only reason that shape did not ship. |
| `DFD-13` | **The fifth fix-without-its-consumer, and the one that had a guard.** `event_source.rs`'s own docstring names the column — *"`ruleset_digest` is the one that was not"* — so a previous round FOUND this, fixed the decoder, added `EVENT_COLUMNS`, wrote a test asserting every decoded column is selected, and **left the query that actually runs untouched**. The test passed for as long as the bug existed. What makes this the sharpest instance is that the round which introduced the guard is the round that had the defect in hand: it wrote the words *"is the one that was not"* about a column it did not add to the query. |
| `DFD-14` | **I called it environmental three times before I made it speak.** A shared database, a missing pgvector library, a dirty schema — each eliminated, each reasonable, and each reinforcing "not my problem, pre-existing". The reason was in memory at the moment of the print the whole time: `outcomes` held every error string and the bin reported only `failed=1`. **I attributed a failure four times without ever asking the program why.** The stop hook refusing `[~]` is what forced the question. |
| `DFD-1` | **The four days before this file drifted, and no mechanism noticed.** `gate-teeth` and `dp-coverage` were meta-work on the verification layer; `authorable-surface` was the manifest tier; `lore-bible` left the tier entirely and started mapping output onto `progression_kinds` and combat — **features the PO had not finished designing**. Each track individually justified itself, each updated its own board, and nothing held the objective. The `Reconciles:` gate checks that a spec *looked* at the standards index; **no gate asks whether the work is the work that was asked for.** §0.2 is a file, not a gate, and that is a known weaker mechanism — recorded here rather than claimed as solved. |
