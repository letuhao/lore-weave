# RUN-STATE — the turn loop: give the spine something that decides *when*

**Reconciles:** Data Plane **DP-A1–A19 / DP-R1–R8 / DP-T0–T3** · Data Plane channels
**DP-Ch1–Ch37** · `contracts/events/_registry.yaml` — the audit is §1 below, and it changed the shape of the work
before any of it was written: **four different things in this repo are called a "turn"**, one of
them is built and is a *different concept* with a near-identical mutator name, the event type this
track introduces is **absent from the authoritative registry**, and the API surface the LOCKED spec
writes against (`DpClient`) **does not exist**.

---

## 0 · HOW TO WORK

**The binding execution contract is [`§0.6d` of the reality-layer run-state](2026-08-08-reality-layer-RUN-STATE.md)** — adopted here verbatim, not copied: the execution invariant, the source-of-truth rule, the six-step bite sequence, the non-negotiable hazards, the blocker rule, the continuation check, the stop-condition list, and the list of things that are NOT stop conditions. Read it before touching anything.

Two hazards from that file apply on every turn of this track:

* **Run `gate-wiring-gate --run-all` DETACHED** (`BDR-89`). It takes ~25 minutes; a foreground call that gets SIGTERM leaves a bite harness's mutation — typically *a deleted assertion* — sitting in the tree, and the `O_EXCL` lock cannot cover it because the signal kills the process that would release it. After any interrupted sweep, `git status` **before** anything else.
* **Never run two sweeps concurrently, or one beside a bite harness** (`BDR-53`).

And one drawn from this track's own audit:

* **`pathlib.Path.write_text` on Windows rewrites newlines** (`BDR-86`). Use `read_bytes`/`write_bytes` for anything a shell executes, and for any document — a line-ending change re-opens a file's entire history to every added-lines gate.

---

## 1 · PHASE 0 — AUDIT-EXISTING, and it moved the work

The goal for this track named Phase 0 as *"where this track has failed twice before"*. It was right to. Each finding below is a command, not a memory.

### 1.1 · Q1 — What already models a "turn"? **Four things.**

| # | what | where | concept | producer? |
|---|---|---|---|---|
| 1 | `TurnContext` / `TurnState` | `contracts/turn/` (Go SSOT) + `crates/dp-kernel/src/turn.rs` (Rust mirror) | **a request's lifecycle** — `Pending → Validating → Routing → Executing → Streaming → Completed/Failed/Cancelled` | ✅ **built, tested, Go↔Rust parity** (cycle 20 / L4.K) |
| 2 | `TurnBoundary` / `advance_turn` | `15_turn_boundary.md` — DP-Ch21..24 | **a per-channel page-flip counter** — *"every reality is a book with discrete page flips that all members of a channel see in order"* | ❌ **0** |
| 3 | `TurnSlot` / `claim_turn_slot` | `21_llm_turn_slot.md` — DP-Ch51..53 | **an advisory hint** — *"actor X is expected to act until time T"*; explicitly **not** an enforcement primitive | ❌ **0** |
| 4 | initiative order | `crates/game-rules/src/combat/initiative.rs` | **whose combat turn it is** — lowest action value acts | ✅ built (domain, unrelated to DP) |

### 1.2 · Q3 — Does it CONFLICT? **Yes, and this is the finding with no gate behind it.**

`§0` of the reality-layer file says question 3 is *"declared rather than glossed"* because no mechanism asks it. Declaring it:

**`dp-kernel::turn::TurnContext::advance(TurnState)` and DP-Ch21's `advance_turn(...)` are unrelated operations one word apart.** Worse, `TurnContext` carries `reality_id`, `session_id` and `actor_id` — *the same scope keys* DP-Ch21's turn lives under — so a reader has every reason to assume they are the same subject. They are not: #1 advances one request through its own lifecycle; #2 advances a shared channel's counter for every member at once.

Had this track skipped the audit and put `advance_turn` in `dp-kernel` beside `turn.rs`, the crate would export two "advance a turn" APIs meaning different things, in the same module namespace. That is the `D-2` vocabulary-collision shape, and it would have been permanent.

### 1.3 · Q2 — Producers and prerequisites, measured

* **`events.turn_number`** — no migration creates it. Already registered in `spec_oracle_channels.rs`'s `DEFERRED_EVENT_COLUMNS`, and **the recorded reason is precisely this track**: *"15_turn_boundary.md's turn machinery has no implementation and nothing would advance the counter, so the column would be a NOT NULL DEFAULT 0 that never moves."* The register has a shrink arm that fails the day a migration adds the column — so `T1` below **must** pay that row in the same change.
* **`channel_writer_state.last_turn_number`** — absent. The shipped table (`contracts/migrations/per_reality/0014_channel_ordering.up.sql`) is `reality_id, channel_id, current_epoch, last_event_id, updated_at`.
* **DP-Ch51's four columns** (`current_turn_actor`, `turn_started_at`, `turn_expected_until`, `turn_slot_reason`) — absent.
* **`ActorId`** — **no such type exists** in `crates/`. `TurnSlot.actor: ActorId` has no referent.
* **`DpClient`** — **does not exist.** DP-Ch21 and DP-Ch51 both write `impl DpClient { … }`; the SDK's actual write surface is free functions (`dp::t3_write(ctx, …)`). The LOCKED spec is written against an API shape that was never built.
* **`channel_pause` (DP-Ch35)** — unbuilt. Only the `ChannelPaused` variant exists, in `crates/dp/src/error.rs`'s error table. DP-Ch53's three patterns compose it.
* **`turn_boundary` is NOT in `contracts/events/_registry.yaml`** — the authoritative `event_type` registry, which drives `make eventgen` → polyglot outputs and a drift-failing CI leg. A new `ChannelEvent` with `EVENT_TYPE = "turn_boundary"` owes a registry row.

### 1.4 · What the audit changes about the plan

The LOCKED design is sound; what is stale is its **surface assumptions**. This track therefore does **not** re-open DP-Ch21..24 or DP-Ch51..53. It reconciles them with the tree — and every reconciliation is recorded as a sealed fork in §2 rather than made silently.

---

## 2 · SEALED FORKS — decided here, so nobody re-asks

**`SF-1` · `advance_turn` is a free function in `crates/dp`, not a method, and not in `dp-kernel`.**
DP-Ch21 writes `impl DpClient`. There is no `DpClient`; the SDK is free functions taking `&SessionContext`, and `dp::t3_write` is the shape to mirror. Putting it in `dp-kernel` would collide with `turn.rs` (§1.2). **Reversal trigger:** a `DpClient` struct actually appearing in `crates/dp`.

**`SF-2` · The two turn concepts get distinguishing names in prose at every definition site, and are NOT renamed.**
`BDR-55`: renaming moves the number, not the property — and #1 is a Go↔Rust mirror pair with a parity test, so renaming it would break a cross-language contract to solve a readability problem. Instead each definition site states which turn it is and links the other. **Reversal trigger:** a third consumer confusing them in review.

**`SF-3` · `channel_turn_index` stays UNBUILT.**
`15_turn_boundary.md` §DP-Ch22 already frames it as optional and says the anomaly it prevents — two `TurnBoundary` events sharing a turn number after a failover — *"violates no invariant"*. **Reversal trigger:** an observed failover producing duplicates, or a feature that needs turn numbers to be unique keys.

**`SF-4` · DP-Ch53's three patterns are OUT of scope; DP-Ch51/52's primitives are IN.**
The patterns compose `channel_pause`, which is unbuilt, and `21_llm_turn_slot.md` says of its own primitives that they *"are not strictly required for any pattern to work"*. Building patterns on an unbuilt primitive is the orphan shape. **Reversal trigger:** `channel_pause` shipping.

---

## 3 · THE BOARD

| # | row | done = |
|---|---|---|
| `T0` | this file + the audit above | `phase0-reconcile-gate.py` passes on it, with pasted output |
| `T1` | **schema**: per-reality migration adding `events.turn_number` + `channel_writer_state.last_turn_number` | the migration runs AND re-runs clean against a throwaway DB (pasted); the `DEFERRED_EVENT_COLUMNS` shrink arm **FIRES** and is paid by removing the row; migration-manifest + idempotency validators green |
| `T2` | **event type**: register `turn_boundary` in `contracts/events/_registry.yaml` | eventgen regenerated, `eventgen-validate.sh` green, envelope-mirror gate green — all pasted |
| `T3` | **`advance_turn` producer** in `crates/dp` (`SF-1`) + writer-side allocation in `dp-kernel::channel` | the symbol exists in non-comment source; unit tests for the allocation algorithm incl. the `MAX(turn_number)` reseed; `cargo test -p dp -p dp-kernel` green, pasted |
| `T4` | **end to end against the real commit spine** | a test that RUNS and commits a `TurnBoundary` through the existing `ChannelWriter` epoch-fenced path, with the row read back. **State explicitly whether it is a live test or a drill** (§0.5) — a drill does not satisfy the goal |
| `T5` | **oracle for `15_turn_boundary`** | `dp-oracle-coverage-gate`'s `NO_PRODUCER` arm fires for it; the row is removed; the doc enters the coverable denominator with a live asserting oracle; **bitten** per the six steps; baseline recorded |
| `T6` | **`ActorId` + DP-Ch51 slot primitive** — schema columns, `claim_turn_slot`/`release_turn_slot`/`get_turn_slot` | same evidence shape as `T1`+`T3`; `ActorId` defined once, with its home justified against the actor-hub prior art |
| `T7` | **oracle for `21_llm_turn_slot`** | as `T5` |
| `T8` | **full verification** | `cargo test` workspace, a **detached** `--run-all` sweep, both with their REAL exit codes pasted (`BDR-90`: read the RC, not the notification) |

---

## 4 · OPEN, each with a trigger

| id | what | trigger |
|---|---|---|
| `TL-PAUSE` | `channel_pause` (DP-Ch35) is unbuilt, so DP-Ch53's Strict/Concurrent/Cancellable patterns cannot be built | `SF-4`'s reversal — `channel_pause` shipping |
| `TL-DPCLIENT` | two LOCKED docs specify `impl DpClient` and no such type exists; `SF-1` routes around it rather than fixing the docs | a third doc specifying `DpClient`, or the type actually being introduced |
| `TL-TURN-VOCAB` | four concepts named "turn"; `SF-2` documents rather than renames | a review in which two of them are confused |
| `TL-PGVECTOR` | **`template1` on the dev cluster records `vector 0.8.1` as INSTALLED while the cluster has no pgvector files** (PG 18.1 / Alpine), so every database `CREATE DATABASE` makes from it inherits a `pg_extension` row pointing at a missing shared library. `0006_projections` dies on `could not access file "vector"`. This is `W7-TEMPLATE1`'s hazard arriving by its **inverse**: that row warns the template silently *carries* pgvector into every new DB; the live failure is that it silently *claims* to, after the image stopped providing it — so provisioning yields databases that look correct and break on the first vector DDL. Not this track's subject and not fixed here | anyone provisioning a reality that needs embeddings on this cluster, or CI adopting this image. The fix is infra: install pgvector in the image, or drop the stale `pg_extension` row from `template1`. **Do not paper over it in a migration** |
| `TL-DOWN-GUARD` | `0020`'s down migration discards every channel's turn history with no refuse-if-populated guard, unlike `036` in the meta tree. Correct today — nothing writes a non-zero value | **`T3`.** The moment `advance_turn` has a producer, this down migration can destroy live game state. Revisit it in the same change |

---

## 5 · REGISTERS — decisions · parked · debt · drift

**An empty drift log is not evidence of a clean run** (§0.6d). Append as you go.

**`TLD-7` (2026-08-11) — skipping a failed migration produced a CASCADE failure that read as a
second defect.** With `0006_projections` dying on the missing extension, the obvious move was to
skip it and continue. `0008` then failed on `relation "npc_session_memory_embedding" does not
exist` — a consequence of the skip, not an independent problem, and for a moment it read as *"the
migration chain is broken in two places"*. `BDR-56` in its ordinary clothes.

The fix was to stop hand-picking: apply exactly `0020`'s **transitive dependency closure as
declared in `manifest.yaml`** (`0001`, `0002`, `0014`). That is principled rather than
convenient, and it bought a second property free — **if `0020` had needed anything outside its
declared closure, the run would have said so**, which makes the manifest row itself tested rather
than asserted. It didn't; the row is correct.

**`TLD-6` (2026-08-11) — `template1` claims an extension the cluster does not have.** See
`TL-PGVECTOR` in §4. Recorded here for the general shape: **an environment can lie in the
optimistic direction.** `CREATE DATABASE` faithfully copies `template1`'s `pg_extension` rows, so
a cluster that once had pgvector and no longer does hands out databases that pass every
"is the extension installed?" check and fail the first time anything uses it. The check that would
have caught it is `pg_available_extensions` (the files) rather than `pg_extension` (the claim) —
two tables that answer different questions and are easy to mistake for each other.

**`TLD-5` (2026-08-11) — the shrink arm whose whole purpose was noticing THIS DAY did not notice
it.** `DEFERRED_EVENT_COLUMNS`'s row said, in its own words, that it *"fails the day a migration
adds the column"*. `0020_turn_boundary` added `events.turn_number`, the suite ran, **4 passed**,
and the row survived. The shipped side read one hardcoded file:

```rust
let shipped_sql = migration("0014_channel_ordering.up.sql");
```

`NV-3` — the scope never reaches it. An enumerated scope is **default-uncovered**, and the
unasked question is the only one a deferral register exists to answer: *what about a migration
that does not exist yet?* The register was not wrong about its subject; it was blind to the event
it was written to detect, and it would have stayed blind while reading, to a reviewer, exactly
like a working mechanism.

Fixed by walking every per-reality migration in the **forward** direction, with a reach floor. The
**reverse** arm still reads `0014` alone, on purpose: DP-Ch11 governs what that migration puts on
the event log, so flagging `0013`'s `content_sha256` or `0016`'s `ruleset_digest` would be this
oracle claiming authority over another document's columns. Two directions, two scopes, both
stated at the call site. 3/3 bitten.

**`TLD-4` (2026-08-11) — the most-cited LOCKED standard in this repo is not CITABLE by the gate
that demands citations.** `Reconciles:` is matched against the **first cell** of every standards-index
table row. **Non-Vacuity** never appears in a first cell — it is always the *second* cell of the
quick-nav table, keyed on the concern (*"A gate, lint, test, `const` assertion…"*). So
`Reconciles: … · Non-Vacuity` reds as a phantom row, which is what happened on this file's first
run. Not fixed here: changing the index's shape is a governance edit outside this track, and the
gate is behaving correctly given the data. Recorded because the next author will hit it, and
because the workaround — cite the *concern* phrasing instead — is not discoverable from the error.

**`TLD-3` (2026-08-11) — I wrote two arms that could not fail, in the same session I wrote
`BDR-82` about arms that cannot fail.** Testing that `field_value` STOPS at a paragraph break, I
wrote the trailing text as plain prose: *"Quantum Flux Standard is discussed below."* Removing the
break changed nothing — because the swallowed line joins onto the real citation as **one** entry,
and matching is a substring test, so the real row is still inside it and the entry passes either
way. Both arms agreed with the code and with its negation.

The fix is small and worth stating as a rule: **an arm that tests a BOUNDARY must put a separator
on the far side of it.** Only when the swallowed text becomes an entry *of its own* does the
boundary have an observable effect. Found by biting; invisible on green.

**`TLD-2` (2026-08-11) — `T0`'s own acceptance criterion was weaker than it read, and the gate got
weaker the more prior art you cited.** `phase0-reconcile-gate` read `Reconciles:` with a
`re.MULTILINE` (not `DOTALL`) regex, so `(.+?)$` stopped at the first newline. This file's citation
list wraps — as any list long enough to be worth checking will — so the gate read:

```
read:    'Data Plane **DP-A1-A19 / ...** · Data Plane channels'
ignored: '**DP-Ch1-Ch37** · `contracts/events/_registry.yaml` - ...'
```

**Half the list was invisible, and the visible half ended in the dangling fragment `Data Plane
channels`, which PASSED** because a real row starts with those words and matching is a substring
test. So the gate accepted a truncated citation list and never saw
`contracts/events/_registry.yaml` — the one citation most specific to this track, and the one that
surfaced the unregistered `turn_boundary` event type.

`NV-3`, the scope never reaching it, with the worst possible gradient: **the more conscientious the
author, the longer the line, the more of it goes unchecked.** Now a paragraph read, with four arms
and 3/3 bitten. Existing specs are unaffected in verdict — names precede the em-dash either way —
but their fields are now actually parsed.

**`TLD-1` (2026-08-11) — Phase 0 changed the work, which is the whole argument for it.**
The plan going in was *"build `advance_turn`, then `claim_turn_slot`"*. Three commands later that plan was wrong in four places: the crate it would naturally land in already has a different `turn` with an `advance` method; the API shape both specs write against does not exist; the event type owes a registry row nothing would have reminded me of; and the schema column is already registered as deferred **with this exact track named as its unblocking condition**. None of that is discoverable from the LOCKED documents — every one of them reads as complete.
