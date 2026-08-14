# FEATURE #2 — THE PLAYER IS A CONTROL INTERFACE — RUN-STATE

**Opened 2026-08-14** · branch `feat/game-logic` · opened at HEAD `9141c9d22` · size **L**
(files 8 · logic 9 · side-effects 3 — a new internal route, a wire-contract change, meta writes)

**Adopts** [`2026-08-08-reality-layer-RUN-STATE.md`](2026-08-08-reality-layer-RUN-STATE.md) §0.6d as
its execution contract, and §0.6's hazards.

**Reconciles:** User Boundaries & Tenancy — the binding is **per-user**, scope key `user_ref_id`,
and a cross-user read is already registered as a sensitive path · Non-Vacuity — the agent-driver
question is deferred with a trigger, not a prose row · Debugging Protocol — every claim below is a
command, not a memory · Performance Standard — the resolution lands on the commit hot path and must
not add a per-proposal round trip.

---

## §1 PHASE 0 — and it found the feature already half-designed

**Question 1 · what already models "a player controlling an actor"?** A sealed table, and a dropped
predecessor:

* **`migrations/meta/034_actor_control_binding`** — `(user_ref_id, reality_id, actor_id)`,
  `created_at`/`revoked_at`, `PRIMARY KEY (reality_id, actor_id)`. Its header states the framing:
  *"a player is not a KIND of actor — it is a CONTROL INTERFACE: a human with a GUI driving an
  actor. If 'player' is no longer a kind, then `(user, reality, actor)` is the only thing that makes
  a player a player."*
* **`035_drop_player_character_index`** dropped its predecessor after a column audit found no
  keep-argument surviving — `pc_name` was PII, five of six `status` members belonged to the
  transport / `GoneState` / user preferences, `pc_index_id` was a surrogate PK over an existing
  UNIQUE. The deciding reason was the NAME: *"`pc_id` renamed to `actor_id` inside a table still
  called `player_character_index` is `quantity[0] = "hp"` one tier over."*
* **`contracts/meta/events_allowlist.yaml`** already declares `actor.control.granted` / `.revoked` /
  `.erased`, owner `world-service`, asserted by `contracts/meta/pii_l1a2_test.go`.
* **`per_reality/0017_drop_pc_npc_projections`** — the same vocabulary removed one tier down.

**Question 2 · does it have a PRODUCER?** **No, and that is the feature.** The only
`INSERT INTO actor_control_binding` in the tree is a test fixture
(`meta-worker/pkg/user_erased_writer/pglive/integration_pg_test.go`). It has exactly one reader —
the GDPR erasure cascade. **A table with a reader and no writer is the same emptiness that killed
`012`**, and `035`'s own header says `012` was *"empty by construction"* for precisely this reason.

**Question 3 · does it conflict with a decision this round will make?** It CONSTRAINS one, and the
decision is already sealed. `SEALED-SUBJECT` (PO, 2026-08-06):

> *"The subject is resolved on the kernel path, not asked for by the transport… it has to go through
> the kernel. That is the architecture."* The proposal carries the **user**; the authoritative side
> resolves `user → actor` from `actor_control_binding`, which `commit-service` can already reach.
> **"Fixing the transport fixes one instance; moving the resolution kills the class."**

### Prior art — checked, because the shape is not novel

**Unreal Engine's `Controller`/`Pawn` split is this design, shipped since 2004.** A `Controller` is a
*non-physical actor* that **possesses** a `Pawn`; `Possess()`/`Unpossess()` are grant/revoke; and
*"by default, there is a one-to-one relationship between Controllers and Pawns"* is our primary key.
Two findings bear directly on decisions taken here:

* **`APlayerController` and `AAIController` differ only in what drives the decision, not in the
  possession interface.** That is evidence for *"an agent is a principal"* over a `controller_kind`
  column when `PC-AGENT` reopens — and evidence that deferring it costs nothing, because the seat
  does not care who sits in it.
* *"AIControllers exist ONLY on the Server. Clients never execute AI logic."* — the same instinct as
  `SEALED-SUBJECT`: control authority lives where the simulation is.

**Where this design DEPARTS from the engines, deliberately:** Unreal's possession is in-memory,
single-process and per-session. This binding is durable, audited and cross-reality, because a human
exists across realities — `034`'s header argues it, and neither Unreal nor a per-shard MMO
account→character table answers *"which actors do I drive across N worlds"* or *"erase every binding
this human has"*. The table reads like IAM rather than like a game object, and that is the reason.

**And the LLM-NPC literature does not cover this at all.** The 2025 work (inZOI's SmartJoy at GDC,
`Whispers from the Star`, the memory/reasoning/IO agent frameworks) builds the agent's BRAIN. It
does not ask *"is this agent permitted to act as this character?"*, because in single-player and NPC
contexts nobody forges a subject. Making an agent hold a binding like any other principal is the
unusual part of this design, and it is why `PC-AGENT` is a deferral rather than an omission.

### The live defect this closes

`services/commit-service/src/admission.rs:41` declares `pub actor: u64` on the wire, and
`ChannelRoom` supplies it. **The producer signature is verified; the SUBJECT is not** — so a client
names the actor it is acting as. `PID-D5`'s *"a field that is not on the wire cannot be forged"*
comment sits eleven lines below that field making the argument about `event_category`, one field
over, never applied.

Meanwhile the transport resolves its actor from **`LW_CHANNEL_ACTOR_MAP`, an environment variable**,
because `game-server` ships no Postgres client and must not grow one (`I3`). Tracked as
`D-ACTOR-BINDING-NOT-READ-BY-TRANSPORT`; *seam recorded, NOT implemented*.

---

## §2 BOUNDARY — §0.2

**IN:** a grant/revoke writer for `actor_control_binding` · kernel-side `user → actor` resolution in
`commit-service` · removing `actor` from the proposal wire so the caller cannot assert its own
subject.

**OUT, and each for a stated reason:**

* **Agent/LLM drivers** — **the PO deferred this explicitly**: *"not decide yet but we need agent
  runtime, state machine and more, skip this phase, we will compact in AI feature later."* The
  sealed framing says *"a human with a GUI"*; whether an agent is a principal with a `user_ref_id`
  or wants a `controller_kind` column is the AI feature's call, not this one's.
* **Co-driving** — one live driver per actor stands. `revoked_at` models takeover as revoke+grant.
  The observation that settled it: **an LLM that proposes and a human that commits is not a second
  driver** — that is one driver with an advisor, and an advisor never becomes the subject. What
  remains ("whose submit wins?", "what happens to the other's in-flight turn?") is TURN-economy
  design and belongs to whichever feature owns turns.
* Turns, combat mechanics, progression, presence/online-status (the transport owns it — `012`'s
  audit already ruled on that), and the character-select UI.

---

## §3 BOARD

| slice | state | evidence |
|---|---|---|
| `P1a` the sealed PK made revoke TERMINAL — repaired to match its own header | `[x]` | migration `041`; handoff OK, two-live-drivers still refused |
| `P1b` the WRITER, Go half — two scoped bridge ops through MetaWrite | `[x]` | 10 handler tests, each RUN and PASS; `go vet` clean |
| `P1c` the WRITER, Rust half — `BridgeClient` + two internal routes + the frozen contract | `[x]` | 152 lib tests; route-conformance 5/5, bitten |
| `P2a` the REGISTRY — `S-9`'s conversion site, with a producer | `[x]` | migration `0022`; allocation, adoption and the bijection all proven |
| `P2b` the RESOLVER — two hops, meta → reality → `EntityId` | `[x]` | `crate::subject`; 2 unit arms + the refusal taxonomy |
| `P3` the wire loses `actor`; the transport carries the user | `[x]` | `pub actor: u64` survives only in comments; 133/0 Rust, 70/0 TS |
| `P4` the forged subject is REFUSED, seen to FAIL first | `[x]` | `EntityId(99)` before, `EntityId(1)` after — both pasted below |
| `P3` the wire loses `actor`; the transport carries the user | `[ ]` | |
| `P4` the forged-subject case is REFUSED, proven by a test that fails without the change | `[ ]` | |
| `P5` live: a granted human drives; a revoked one is refused | `[x]` | five transitions against two real databases, pasted below |
| `P6` suite + sweep green | `[x]` | `CARGO_RC=0` 799/0 across 72 · `GO_RC=0` · `SWEEP_RC=0` 91 GREEN / 0 RED / 8 SKIP |

### `P1a` — the constraint did not implement its own sentence

`034` says *"two **LIVE** rows for one actor is the confused-deputy state the whole table exists to
make unrepresentable"* and then wrote `PRIMARY KEY (reality_id, actor_id)`, which permits one row
**total**. Measured against a throwaway carrying only `034`:

```text
grant to user A             -> granted
revoke                      -> revoked
grant same actor to user B  -> ERROR: duplicate key value violates constraint
                               "actor_control_binding_pkey"
```

**Revoke was terminal** — an actor whose driver left could never be driven again, by anyone. And the
workaround was worse: re-granting by UPDATE emits the event the allowlist binds to `op: UPDATE`,
`actor.control.revoked`, for what is a GRANT. That is a name that lies, which is the exact defect
`035` deleted a whole table over.

Repaired by `041`: a partial unique index over the LIVE rows. Same throwaway, after:

```text
HANDOFF to user B      -> HANDOFF OK
two LIVE drivers       -> ERROR: duplicate key value violates constraint
                          "actor_control_binding_one_live_driver"
final state            -> 11111111|revoked   44444444|LIVE
```

Non-vacuous in both directions: it permits what the design calls normal and refuses what it calls
unrepresentable. **Safe by measurement** — `SELECT count(*)` on the real `loreweave_meta` returns
`0`; the table has never had a production writer, the same emptiness `035` recorded about `012`.
`migration-manifest-gate` and `pii-classify` both green.

### `P1b`/`P1c` — the writer, and what it refuses

**Go half** — two scoped ops on the existing Rust→Go bridge, whose docstring says the scoping is the
point (*"only two narrow operations, and the SERVER builds the intent"*). The client sends three
uuids and a reason; it cannot choose the table, the operation, the timestamps or the audit actor.
10 handler tests, each seen to RUN:

```text
--- PASS: TestGrantControlCreated · TestGrantControlSameUserIsIdempotent
--- PASS: TestGrantControlOtherUserConflicts · TestGrantControlRequiresAllThreeIDs
--- PASS: TestRevokeControlOK · TestRevokeControlNoLiveBindingIsOK
--- PASS: TestRevokeControlCASMismatchConflicts · TestRevokeControlPassesTheCASThrough
--- PASS: TestActorControlRoutesRequireTheToken · TestActorControlIsAudited
```

**Two asymmetries, both following precedent already in that file:**

* **A grant is not idempotent across principals.** Same user retrying → `200 already_granted`, the
  `register-reality` precedent. A DIFFERENT user → **`409`**. A second principal claiming a subject
  someone else holds is not a retry; answering `200` would hide the table's entire guarantee from
  the caller.
* **Revoke takes an optional `expected_user_ref_id` CAS**, mirroring `TransitionReq`'s
  stale-FromState discipline. Without it, *"revoke the driver of actor X"* silently removes whoever
  took over a second ago.

**Rust half** — `BridgeClient::{grant,revoke}_actor_control`, two `Gate::Internal` routes, and two
new `ProvisionerError` variants so a caller can tell *"somebody else drives this actor"* (a normal
answer) from *"the bridge is down"* (an outage). Rendering the first as a 500 would send an operator
looking for a fault that is not there; the mapping is asserted in both directions.

**Contract frozen in the same commit**, because the gate required it and was right to:
`route_conformance` 5/5, and bitten — removing one `ROUTES` row reds
`the_route_table_lists_every_route_literal_in_the_source` and `every_documented_operation_is_routed`,
restore returns to green.

### `P2` — STOPPED, because the binding is ahead of the actor

The resolver has to return something the island can act on. It cannot, and the reason is the seam
the actor-hub round registered and deferred:

> **`S-9`** — `EntityId(u64)` is *"identity within a reality"*; `GoneState` is keyed by
> `EntityRef { uuid, aggregate_type, reality_id }`; **zero conversion sites exist**. Trigger:
> **platform, when the hub first meets it.**

The hub has now met it. Measured:

* `actor_control_binding.actor_id` is a **UUID** (`034`).
* The island's actor is **`EntityId(pub u64)`** (`sim-core/src/types.rs:17`).
* A repo-wide grep for any `Uuid`↔`EntityId` conversion returns **nothing** outside unrelated
  glossary/projection columns. `S-9`'s *"zero conversion sites"* still holds.

And the deeper half, which is worse than the type mismatch — **the UUID points at nothing**:

```text
$ grep DROP TABLE contracts/migrations/per_reality/0017_drop_pc_npc_projections.up.sql
  npc_session_memory_embedding · npc_pc_relationship_projection · npc_session_memory_projection
  npc_projection · pc_relationship_projection · pc_inventory_projection · pc_projection

$ (a database carrying the FULL per-reality chain)
  ls_commit_dataflow_pg_smoke            (none)
  ls_dp_kernel_channel_writer_pg_smoke   (none)
```

**After the full migration chain, no per-reality actor table survives.** `0017` removed the `pc_*`
/`npc_*` projections as orphans — correctly; they had no producer. The consequence nobody wrote
down is that the platform's only *durable* actor identity went with them. What remains is
`EntityId(1)`, `EntityId(2)`, `EntityId(3)`, hardcoded in `bin/spine.rs` and living in island
memory.

So `034` created a durable pointer to an entity that does not durably exist. That is not a defect in
`034` — it is `S-9` arriving, and `S-9` says whose problem it is: **platform, when the hub first
meets it.**

**What this does NOT block:** `P1` is complete and useful on its own. The table has a writer, the
constraint is correct, the events fire, and the audit row lands in the same transaction. Nothing
about the identity decision changes any of it.

### `P2a` — the PO chose the registry, and `SF-6` says what that means

**Prior art found before writing any DDL, and it is three days old.** `0021_turn_slot`'s manifest
entry says *"No `ActorId` type is introduced (`SF-6`): four spellings of who-is-acting already
exist"*. The rule, from `docs/plans/2026-08-11-turn-loop-RUN-STATE.md`:

> **`SF-6` · No `ActorId` type is introduced.** … Four spellings of "who is acting" already do:
> `sim-core::EntityId(u64)`, the meta audit tables' `actor_id UUID`, `meta_write_audit.actor_id
> TEXT`, and `dp-kernel::pii_sdk`'s `actor_id: String`. A fifth, minted at the data plane, is the
> vocabulary proliferation §1.2 already caught once. … **Reversal trigger:** a single
> actor-identity type being adopted repo-wide, at which point the slot should hold it.

Two consequences, and the first is the one that keeps this honest:

**The registry is NOT a fifth spelling — it is the CONVERSION SITE `S-9` says has zero instances.**
`actors(actor_id UUID, entity_id BIGINT)` mints no new vocabulary; it reconciles spelling #1 with
spelling #2 by writing the mapping down in the one place both tiers can reach. Had it invented a
third name for the same thing, `SF-6` would forbid it and be right.

**And it arms `SF-6`'s reversal trigger.** Once a single actor identity is adopted repo-wide,
`0021`'s `current_turn_actor JSONB` should hold it instead of opaque JSON. That is a real,
downstream obligation this round creates and does not discharge — recorded as `PC-SF6-REVERSAL`
rather than left for whoever next reads DP-Ch51 and wonders why the slot is untyped.

**Scope, stated rather than drifted into:** this round builds the per-reality registry, its
producer, and the resolver that uses it. It does **not** perform the repo-wide adoption — that
touches `GoneState`'s `EntityRef`, `pii_sdk`, the meta audit tables and the turn slot, and doing it
inside a player-control feature is precisely the encroachment `SF-6` and the actor-hub round both
warn about.

### `P2`–`P4` — the class is dead, and here is the red that proves it

**`P2a` the registry.** Migration `0022_actors` maps the platform's `actor_id UUID` to the island's
`EntityId(u64)`. It ALLOCATES the island id (`GENERATED BY DEFAULT AS IDENTITY`) rather than
recording one the island also assigns, because two writers of one number is how `pc_projection` came
to disagree with nothing at all. Proven against a live database:

```text
--- the registry ALLOCATES entity_id ---            1 · 2
--- an existing entity can still be ADOPTED ---     99
--- the BIJECTION: two actors may NOT share one --- ERROR: duplicate key value violates
                                                    constraint "actors_entity_id_unique"
```

Adoption is not decoration: `bin/spine.rs` hardcodes `EntityId(1..3)`, so without it the registry
could only describe actors created after it shipped and every running island would be undrivable by
the feature built to drive it.

Its **producer** ships with it — `POST /internal/v1/actors` on `world-service` — and the GRANT path
now REFUSES an actor the registry does not have. `034` left `actor_id` unconstrained because its FK
lives in another database; that is a correct reason to have no foreign key and a bad reason to skip
the check, so the check happens in the one process that can reach both.

**`P2b` the resolver.** `crate::subject` does the two hops — meta `actor_control_binding`
(live rows only) → per-reality `actors` → `EntityId`. Three distinguishable refusals, because *"you
drive nobody here"* and *"the binding points at an actor this reality does not have"* are different
problems for whoever is on call. The `i64 → u64` conversion is CHECKED: `-1 as u64` is `u64::MAX`, a
well-typed number naming nothing — a wrong subject presented as a valid one.

**`P3` the wire.** `pub actor: u64` is gone from `admission::Proposal`; `user_ref_id` replaces it.
Removing the field rather than ignoring it is the point — the compiler then found all **19** call
sites, and an ignored field comes back. `ChannelRoom` sends the user instead, reusing the `userOf`
map that already existed for the `CNC-Q1` rate cap.

**`P4` — the bite.** The new suite was run against a mutant that reads the acting entity off the
wire again, exactly as before:

```text
MUTANT: admission reads the acting entity off the wire again
test a_proposal_naming_another_actor_does_not_become_that_actor ... FAILED
  left: EntityId(99)
 right: EntityId(1)
test the_callers_resolved_subject_is_the_one_that_acts ... FAILED
  left: EntityId(0)
 right: EntityId(7)
test no_spelling_of_the_claim_reaches_the_subject ... FAILED
```

`EntityId(99)` is the forgery: a proposal claiming `actor: 99` BECOMES actor 99. Restored
byte-exact:

```text
RESTORED byte-exact
test a_proposal_naming_another_actor_does_not_become_that_actor ... ok
test no_spelling_of_the_claim_reaches_the_subject ... ok
test the_callers_resolved_subject_is_the_one_that_acts ... ok
test a_proposal_without_a_submitter_is_refused_at_the_schema_stage ... ok
test result: ok. 4 passed; 0 failed
```

The second failing arm matters as much as the first: `EntityId(0)` means the mutant ignored the
caller's resolved subject entirely. Without it, a "fix" that hardcoded `EntityId(1)` would satisfy
the forgery test and be just as wrong.

**Suites:** `CS_RC=0` — 133 passed / 0 failed across 29 commit-service suites. Game-server: 72
tests, **70 pass / 0 fail**, 2 skipped.

### `P5` — live, against two databases in two tiers

The unit suites prove admission cannot be TOLD who is acting. They cannot prove the resolution
works, because it spans `actor_control_binding` in META and `actors` in the per-reality shard —
mocking either would mock the exact seam `S-9` recorded as having zero conversion sites.

`services/commit-service/tests/subject_live.rs`, run by
`scripts/live-suites.py --only commit-subject` (registered as `commit-subject`, so it is covered by
the registry-driven CI leg like every other live suite):

```text
GRANTED   user 29731ffa-4826-4834-ad39-3a236bfa2fee -> EntityId(4242)
STRANGER  user bb171b31-7d5e-4fed-83f6-6e1aeafc3474 -> refused (no live binding)
REVOKED   user 29731ffa-4826-4834-ad39-3a236bfa2fee -> refused (binding is history)
HANDOFF   user 076d7efe-00ba-4f51-a25b-61b406f98b21 -> EntityId(4242)
DANGLING  actor f1065f68-b2a8-45c5-9024-7375ec21e457 -> refused (no registry row)
test result: ok. 1 passed; 0 failed
```

Five transitions, and each is a claim this feature makes:

* **GRANTED** — the same user resolves to the island entity they drive.
* **STRANGER** — one live binding does not make the reality drivable by anyone who asks. The grant
  is per USER.
* **REVOKED** — refused the instant the binding becomes history. This is the property a cache
  without invalidation would have silently broken, and the reason the resolver does not have one.
* **HANDOFF** — `041`'s repair, exercised end to end. Under `034`'s original
  `PRIMARY KEY (reality_id, actor_id)` this re-grant was impossible and revoke was terminal.
* **DANGLING** — a binding naming an actor the registry does not have is REFUSED BY NAME
  (`UnknownActor`), not resolved to something wrong. The grant route refuses to create one, so this
  had to be constructed directly to prove the resolver reports it.

The "before any grant" assertion runs FIRST, deliberately: without it, a pass could be a row some
earlier run left behind rather than the grant under test.

## §4 OPEN

| row | what | mechanism |
|---|---|---|
| `PC-METAWRITE-NOOP-EVENT` | **`MetaWrite` emits the outbox event without checking `RowsAffected`.** `contracts/meta/metawrite.go` runs the data statement, then appends the audit row and the outbox event unconditionally — so a CAS'd UPDATE that matches nothing still announces its domain event. **Not introduced here and not this feature's to fix**: the append is shared by every meta table, and `query_builder.go`'s own comment advertises the CAS pattern for migration `011`'s consent revoke, so that path carries it too. Outbox delivery is at-least-once by contract, so a duplicate `actor.control.revoked` for an already-revoked binding is inside what a consumer must tolerate; it is still an event for a write that changed nothing. Designed around with a pre-read, so only a lost race can reach it. | the wake-up is any consumer that treats an outbox event as proof a row changed; the fix is a `RowsAffected == 0` guard on the append, and it belongs to whoever owns `contracts/meta` |
| `PC-ACTOR-IDENTITY` | **`S-9` fired: the binding is ahead of the actor.** `actor_control_binding.actor_id` is a UUID, the island's actor is `EntityId(u64)`, zero conversion sites exist, and after `0017` no per-reality actor table survives at all — the only actor identity in the running system is three hardcoded `EntityId`s in island memory. Deciding what an actor's durable identity IS across the platform/simulation boundary is architectural and belongs to the PO. | `P2` cannot be built until it is answered; the row is the block, and the resolver is the wake-up |
| `PC-SF6-REVERSAL` | **This round arms `SF-6`'s reversal trigger and does not discharge it.** `SF-6` refused to type `0021_turn_slot`'s `current_turn_actor` because four spellings of who-is-acting already existed, and named its own reversal: *"a single actor-identity type being adopted repo-wide, at which point the slot should hold it."* The registry built here is the first step toward that type. | the wake-up is the adoption itself — when a single actor identity is used by `GoneState`'s `EntityRef`, `pii_sdk` and the meta audit tables, `0021`'s JSONB column must stop being opaque |
| `PC-SEATS` | **The PK makes one-driver-per-actor a DATABASE LAW, and three seats are not drivers.** The comparison round found that Unreal's one-to-one is a *default you can override*; ours is a constraint Postgres enforces. So **spectating**, **GM override** and **advisor** must each be designed as something other than a second binding. The advisor case is already settled (an LLM that proposes and a human that commits is one driver plus an advisor; the advisor never becomes the subject). Spectating and GM override are NOT thought about, and the PK will force the question the first time either is asked for. | recorded now rather than discovered later; the wake-up is the first feature that needs a non-driving seat |
| `PC-AGENT` | can a controller be an agent, and how is it represented? **Deferred by the PO to the AI feature** (needs an agent runtime + state machine). | it must not be prose-only: the wake-up is the first non-human principal appearing in `actor_control_binding`, and the trigger goes in with `P1` |

## §5 DRIFT — append as it happens; an empty log is dishonest, not clean

| id | what |
|---|---|
| `PD-2` | **I ran the bite against the wrong suite and nearly filed a false finding.** `routes.rs` claims *"a test reads the SOURCE of this file and asserts every `.route(…)` literal it finds is listed here"*. I removed a `ROUTES` row, ran `cargo test --lib -- routes`, saw 6/6 GREEN, and concluded the guard did not exist — a claim without a mechanism. It exists: `tests/route_conformance.rs`, an INTEGRATION test, which `--lib` does not build. Re-bitten against it: two tests red, restore returns 5/5. **A bite that does not red is evidence about the harness before it is evidence about the code**, and I was one step from recording the opposite. |
| `PD-3` | **The suite was already RED before my bite, and the bite is what showed me.** `every_routed_operation_is_documented` fails the moment a route exists with no contract entry: *"this service serves 2 operation(s) no contract in contracts/api/world documents… Contract-first: freeze it in the YAML in the same commit."* I had mounted the routes and moved on. The rule is in CLAUDE.md, the gate is wired, and I still needed the gate to tell me. |
| `PD-4` | **Hazard #5, four times in one day, in a session whose own run-state records it twice.** A heredoc carrying `\\n` inside a Python string mangled a bite script's anchor, so the mutation silently did nothing and the run reported a clean pass. Caught only because the MUTANT banner was missing from the output — the same tell as `LD-7`. Every patch in this slice since goes through the Write tool, and that is now a rule for the rest of the session rather than an intention. |
| `PD-5` | **A regex with `[^,]+` inserted an argument into the WRONG function.** Migrating 19 call sites, I matched the first argument of `admit_t6(` with a character class that stops at the first comma — which for `admit_t6(&proposal_json("p-1", "strike", "x"), …)` is inside the NESTED call. Four files were patched wrongly before the compiler said so. Reverted with `git checkout` and redone with a parenthesis-depth scan; the last three sites it still walked past were done by hand, which is the tell that a hand-rolled parser was the wrong tool for the tail. |
| `PD-6` | **The bite matched zero times and the run that followed looked like a pass.** The anchor embedded `\n` against a CRLF file, so `t.count(...)` was 0, the assert fired — and the `cargo test` chained after it printed 4/4 GREEN for the UNMUTATED code. Identical output to a successful bite. Third instance of this exact shape today (`LD-7`, `PD-4`), and the only reason it was caught is that the MUTANT banner was missing. |
| `PD-7` | **I added a `userOf` map that already existed.** `ChannelRoom` has had one since `CNC-Q1` — the map, its `set` in `onJoin`, its `delete` in `onLeave`, and a read at the top of the very function I was editing. I declared a second one four lines below the first. Phase 0's question 1 at micro scale: *what already models this?* — asked of a whole feature this morning and not of a two-line field this afternoon. |
| `PD-8` | **A test fixture built a state production cannot reach, and my change exposed it.** `ChannelRoom.test.ts` set `actorOf` by reaching past `onJoin` into the privates, without `userOf` — an actor bound to a session with no user. `onJoin` sets `userOf` UNCONDITIONALLY and `actorOf` only when a binding exists, so that state is unreachable. The fixture could construct it only because it skipped the constructor. |
| `PD-9` | **I killed a bite harness and it left a SECURITY REGRESSION in the working tree.** `TaskStop` on a sweep caught `dp-slice5c-bite-gate` mid-mutation, so `crates/dp-control-plane/src/server.rs` kept the mutant — `Status::unauthenticated(format!("capability is not valid: {}", e))` in place of the constant string. That is information disclosure: the control plane telling a caller WHICH kind of capability failure occurred, which is exactly what the guard prevents. It was uncommitted, in a crate this feature never touches, and it would have gone into the commit. **The lesson is narrower than "do not kill sweeps": a bite harness holds source in a MUTATED state, so killing one leaves a deliberate defect behind.** I cleared its stale lock file and moved on — treating the hint as the damage. What actually surfaced it was the failing test printing the MUTANT TEXT rather than a plausible assertion failure. |
| `PD-10` | **The sensitive-read discipline had no reachable path for this table, and I found that by violating it.** `034`'s header says a cross-user read of `actor_control_binding` writes a `meta_read_audit` row; I QUOTED that sentence in this file's own `Reconciles` line and then wrote two bare SELECTs. The lint caught both. One is owner-scoped and matches the GDPR cascade's existing exemption; the other is genuinely cross-user and now writes the row — which required adding `TagActorBindingCrossUser`, because the yml has registered that path since `035` and **the SDK never had a constant for it**. The audited route was unreachable, so the first cross-user reader bypassed it by default rather than by choice. |
| `PD-11` | **`reality-id-adoption-gate` caught a safety property, not a naming one — and the spine was the worst offender.** `dp::RealityId` has NO public constructor: it exists only as the output of `SessionContext::bind`, so holding one proves the control plane confirmed the reality ACCEPTS COMMANDS. `bin/spine.rs` was passing `args.reality` — the raw CLI text — into the new resolver while holding the verified id from its own bind, four lines up. `world-service` now binds before every registry touch, so granting control in a frozen or archived reality is refused rather than recorded. Adoptable is back to **0**. |
| `PD-1` | **I proposed merging to `main` while the goal was unmet.** The PO stopped it: *"our goal still not satisfied yet."* I had spent the preceding hours on CI health — real work, and not the work. The audit that followed took twenty minutes and found the feature was already half-designed, which is time I would not have spent had I kept optimising the thing in front of me. |
