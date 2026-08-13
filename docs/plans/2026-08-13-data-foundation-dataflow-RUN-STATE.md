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

- [ ] `DF1` closed — a **production** call site of a DP tier primitive exists, ran live, and the
      resulting row is **pasted from Postgres** (not from a test double)
- [ ] `DF2` closed — `tier_policy` / `schema_version` / `npc_binding` migrated; the RPCs that
      cited them **answer for real**, and `UNIMPLEMENTED_METHODS` shrinks with the test still green
- [ ] `DF3` closed — a Redis-backed cache the SDK reads through for T0–T2, with a **measured**
      read latency pasted against the `03_tier_taxonomy` budget
- [ ] `DF4` closed — every module touching kernel state carries a `DP-R2` tier table, and something
      **machine-checks** that it does
- [ ] `DF5` closed — the end-to-end dataflow: one player-facing action → actor hub → DP write →
      projection → wire, **with the ids and payload pasted at each hop**
- [ ] `cargo test --workspace -j 4` — **real exit code pasted**
- [ ] detached `gate-wiring-gate --run-all` — **real exit code pasted**

> **Claiming a check passed without pasting its output does NOT satisfy this condition.** The
> `/goal` evaluator reads the transcript and cannot run commands; it enforces persistence, not
> honesty.

---

## 1 · THE BOARD

| batch | subject | state |
|---|---|---|
| ~~`DF1a`~~ | **the write surface's missing half** — `t2_write_channel` / `t3_write_channel`, the scope bounds, `KernelChannelWriteBackend`, and the first production `ChannelTree` | ✅ **CLOSED** — evidence in `§3` |
| `DF1b-i` | **the SDK cannot carry a DOMAIN EVENT, and every production write in the tier is one.** `KernelChannelWriteBackend` stamps one hardcoded `event_type`, a base64 blob payload and `ruleset_digest: None`. Routing the spine through it as written would be a REGRESSION, not a wiring | ⬜ |
| `DF1b-ii` | **then** the spine's REJECT-COMMIT goes through the SDK, live, with the row pasted from Postgres | ⬜ |
| `DF2` | **the control plane's three missing tables** — `tier_policy` (`DP-C4`), `schema_version` + `npc_binding` (`DP-C2`). Unblocks 6 of the 8 dead RPCs | ⬜ |
| `DF3` | **the T0–T2 cache.** `§2.4`'s "direct Redis access" — zero DP crates have it today, so every tier collapses to the durable path and the taxonomy is a comment | ⬜ |
| `DF4` | **`DP-R2` tier tables per module** — the PO's *"data instance for each module"*, owed by every feature doc and paid by none | ⬜ |
| `DF5` | **the full dataflow** — actor hub + a control feature + a player feature consuming it, end to end | ⬜ |

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

---

## 4 · OPEN ROWS — each must carry a MECHANISM, not prose

| id | what | mechanism / what would settle it |
|---|---|---|
| `DFO-4` | **`proposal.rejected` is written by the live spine, read by two projectors, and is NOT in `contracts/events/_registry.yaml`** (16 entries; it is absent, as is `dp.write.applied`). So the event validator has no schema for the one domain event this system actually produces in anger | registering it is cheap and in scope for `DF1b-i`, which needs a registered type to point `EVENT_TYPE` at. Recorded separately because it is PRE-EXISTING — found by `DF1b`'s measurement, not caused by it |
| `DFO-2` | **`ReadRequest` has no channel either.** `read_projection_channel` checks the session IS in a channel, then builds a `ReadRequest` that cannot say WHICH — so the backend addresses it by cache key alone, and `KernelReadBackend` reads snapshots by `(reality, type, id)`, ignoring the key. A channel-scoped read is therefore servable only by accident | the write side's fix is the template: a `channel: Option<ChannelId>` on `ReadRequest`, taken from ctx, plus a channel read backend. Not done here because `DF1` is the WRITE path and a read with no producer to read from would be the orphan shape again — it becomes real the moment `DF5` needs to read back what `DF1b` writes |
| `DFO-3` | **`DEFERRED_VARIANTS`'s stated blocker for `WrongChannelWriter` is satisfied, and the row is still right.** It names `NodeId`, which has existed since slice 4. The REAL blocker is that `channel_writer_state` has no writer-node column, so the DB can say your epoch is stale but not who holds the lease — `expected: NodeId` has no value to carry. The oracle checks implemented-XOR-deferred and **cannot check that a reason is still the reason** | the corrected blocker is recorded in `dp_channel::channel_err`'s doc comment, where a reader meets it. A mechanism would be an arm asserting each deferred row's blocker type is ABSENT — cheap for a type name, and it would have caught this |
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
| `DFD-1` | **The four days before this file drifted, and no mechanism noticed.** `gate-teeth` and `dp-coverage` were meta-work on the verification layer; `authorable-surface` was the manifest tier; `lore-bible` left the tier entirely and started mapping output onto `progression_kinds` and combat — **features the PO had not finished designing**. Each track individually justified itself, each updated its own board, and nothing held the objective. The `Reconciles:` gate checks that a spec *looked* at the standards index; **no gate asks whether the work is the work that was asked for.** §0.2 is a file, not a gate, and that is a known weaker mechanism — recorded here rather than claimed as solved. |
