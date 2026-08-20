# FEATURE #2 — THE PLAYER IS A CONTROL INTERFACE — RUN-STATE

**Opened 2026-08-14** · branch `feat/game-logic` · opened at HEAD `9141c9d22`

**Size — as classified, and as it turned out.** Opened **L** (files 8 · logic 9 · side-effects
3 — a new internal route, a wire-contract change, meta writes). **Measured at `P7` close: 52
files, 49 of them source or contract.** The logic estimate held; the BREADTH did not, and per
CLAUDE.md's sizing rule breadth alone does not escalate a tier — a wide, shallow sweep is still
L. The original figure is kept above rather than overwritten, because the interesting fact is
the gap: `P7` was not in the plan when the plan was sized, and neither were the four defects it
found. Re-measure this line at every slice close; it went stale silently once already.

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
  column when `D-PC-AGENT` reopens — and evidence that deferring it costs nothing, because the seat
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
unusual part of this design, and it is why `D-PC-AGENT` is a deferral rather than an omission.

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
subject · **an operator-facing CALLER for that writer** (added at `P7`, 2026-08-20).

The caller was NOT in the original IN list, and that is worth stating rather than quietly
editing in. It was not scope creep: the writer's routes are `require_internal`, so without a
caller the slice shipped a surface nothing could invoke — the same orphan shape §1 opened by
finding. A writer with no invoker does not satisfy *"a hub for a player to control the actors
they own"*; it satisfies the half of it a service can reach. **`create-actor` came with it for
the same reason**: `grant-control` cannot be used against an actor that does not exist, so
shipping the grant alone would have reproduced the trap one level further down.

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
| `P1c` the WRITER, Rust half — `BridgeClient` + two internal routes + the frozen contract | `[x]` | 152 lib tests at the time, **156 now** (`P7` added 4); route-conformance 5/5, bitten |
| `P2a` the REGISTRY — `S-9`'s conversion site, with a producer | `[x]` | migration `0022`; allocation, adoption and the bijection all proven |
| `P2b` the RESOLVER — two hops, meta → reality → `EntityId` | `[x]` | `crate::subject`; 2 unit arms + the refusal taxonomy |
| `P3` the wire loses `actor`; the transport carries the user | `[x]` | `pub actor: u64` survives only in comments; 133/0 Rust, 70/0 TS |
| `P4` the forged subject is REFUSED, seen to FAIL first | `[x]` | `EntityId(99)` before, `EntityId(1)` after — both pasted below |
| `P5` live: a granted human drives; a revoked one is refused | `[x]` | five transitions against two real databases, pasted below |
| `P6` suite + sweep green | `[x]` | at `P6` close: `799/0 across 72` · `GO_RC=0` · `SWEEP_RC=0` 91 GREEN / 0 RED / 8 SKIP. **Re-measured 2026-08-20 at the audit: `cargo test --workspace` = 2549 passed / 0 failed across 193 suites**, `GO_RC=0`, `SWEEP_RC=0` 91 GREEN / 0 RED / 8 SKIP. The old figure covered a SUBSET and did not say so — 193 suites exist, so `across 72` was never the workspace. Scope every count or it reads as the whole tree |
| `P7` the CALLER — `P1`'s writer had no invoker either | `[x]` | 3 admin commands live end to end against real Postgres + the real bridge; 12 steps + 2 `/review-impl` re-proofs pasted below · **20 Go test funcs (24 arms) + 11 Rust** · **three** guards bitten: the bind classifier, the hostport splitter, and the identity-sequence advance |

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
downstream obligation this round creates and does not discharge — recorded as `D-PC-SF6-REVERSAL`
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

### `P7` — the writer I built had no invoker either, one tier up

`P1` existed because `actor_control_binding` had a reader and no writer. The routes that fixed that
are **internal-gated**: `require_internal` + `X-Internal-Token`, correct for a service-to-service
surface and unreachable by any operator. So the grant path shipped with no caller — **the same
orphan shape, moved up a level**. `035` deleted a whole table for this.

**The fork, and why it is not a fill-in.** Phase 0 on the caller found three facts that rule each
other out:

1. **`admin-cli` has no HTTP invoker at all.** Every command is a subprocess (`exec.Command`) or a
   direct `pgxpool`. Calling world-service over HTTP would be a third pattern in a tool that
   deliberately has two.
2. **`contracts/service_acl/matrix.yaml` does not sanction the edge.** admin-cli is a sanctioned
   caller of meta-worker's `MetaWrite`/`MetaReadSensitive`; there is no world-service RPC surface
   for it. The sanctioned path goes to the Go bridge.
3. **But the bridge has neither safety check.** The reality `bind()` and the actor-exists
   precondition live in the world-service handler. Going straight to the bridge would hand an
   OPERATOR a grant path weaker than the one a service gets — and the actor-exists check cannot
   move into meta-worker, because it reads the per-reality database meta-worker does not hold.

I declared the two registry commands before finding this, which left them **declared-but-unwired**
— and the framework's `NotWiredHandler` would have made that exit 0 politely. Reverted, then rebuilt
on the third option: **a worker binary**, the shape `reality provision` (W3) already proved.
Identifiers by flag, secrets by env, one JSON object on stdout, exit code as verdict. No new
pattern in admin-cli, no new ACL edge, and — the part that matters — **no second, weaker check
set**, because the checks moved into a lib module both callers go through.

**Two asymmetries, both deliberate, both recorded so they are not "fixed" later by someone tidying:**

* **Grant binds the reality; revoke does not.** Granting a human control of an actor in a FROZEN
  world is exactly what should not happen. Refusing to *revoke* one is the opposite: it strands a
  player as the driver of a world under maintenance. Revoke is the safe direction and stays
  available.
* **The dry run does NOT report who currently drives the actor.** That is the one fact an operator
  would most like to see, and it is a **cross-user read of `actor_control_binding`** — a path `034`
  registered as sensitive and `PD-10` already caught me bypassing once. A preview that answered it
  would be an *unaudited* way to probe who holds whom. The dry run reports what it can prove without
  that read (the reality accepts commands; the actor exists) and says plainly that the conflict is
  decided at write time, inside the transaction, where a CAS has to live anyway.

### `P7` live — twelve steps, real Postgres, the real bridge, the real worker

Not a mock anywhere. `admin` execs the compiled `actor-control` binary, which binds through
`MetaControlPlane`, reads the per-reality `actors` table, and POSTs to the meta-worker bridge
running in `infra-meta-bridge-1`. Two databases, two languages, three processes.

Getting there needed two repairs to the dev stack, and both are `PD-15`: the bridge image was 37
hours old and **404'd on `grant-actor-control`**, and `loreweave_meta` had never had `039`, `040`
or `041` applied. Neither was visible to any unit suite.

```text
 1  create-actor --dry-run        {"reality_accepts_commands":true,"would_create_actor":true}   exit 0
 2  admin reality create-actor    actor 9ca0c9c8… created in reality cd0747d2… as entity 1      exit 0
 3  grant-control --dry-run       actor exists; user aaaa1111… would be granted control
                                  NOT CHECKED HERE: whether another user already drives it
 4  admin reality grant-control   user aaaa1111… now drives actor 9ca0c9c8…                     exit 0
 5  grant-control (same user)     ALREADY in the requested state (already_granted). Nothing written.
 6  grant-control (other user)    REFUSED — actor 9ca0c9c8… is already driven by another user   exit 3
 7  grant-control (ghost actor)   REFUSED — actor cccccccc… does not exist in reality cd0747d2… exit 3
 8  revoke-control (stale CAS)    REFUSED — expected user does not hold the live binding        exit 3
                                  …and the driver SURVIVED: aaaa1111…  live=true
 9  revoke-control (correct CAS)  actor 9ca0c9c8… has no driver. The binding is history.        exit 0
10  grant-control (the heir)      user bbbb1111… now drives actor 9ca0c9c8…                     exit 0
11  create-actor, bad allowlist   {"conflict":false,…,"status":"failed"}                        exit 1
12  create-actor, FROZEN reality  {"conflict":true,…"status Frozen does not accept commands"}   exit 1
```

The rows those twelve steps left, read back out of the two databases:

```text
loreweave_meta.actor_control_binding
  aaaa1111-2222-4333-8444-555566667777 | live=f | 13:56:17
  bbbb1111-2222-4333-8444-555566667777 | live=t | 13:59:26

loreweave_meta.meta_write_audit  (I8 — same transaction as the binding)
  INSERT  live smoke: the operator grants control
  UPDATE  live smoke: the operator takes the character away
  INSERT  live smoke: the heir takes over after the revoke
  row_pk = {"binding_id": "cb9ac4a9-…"}          <- migration 041's new PK, on the real path

lw_reality_cd0747d24b94.actors
  9ca0c9c8-a48f-4fce-9029-a574be662c2d | entity_id 1
```

**Step 10 is the one that could not have happened three days ago.** Under `034`'s
`PRIMARY KEY (reality_id, actor_id)` a revoke was terminal and a second row for the same actor was
impossible; `P1a` repaired that with a partial unique index over LIVE rows, and this is the repair
exercised by a human-facing command rather than by a fixture.

**Steps 11 and 12 exist because of `PD-12`.** They are the two halves of a distinction the first
version of this code did not make, and step 11 is what the live run printed *before* the fix — with
`conflict: true`, telling an operator to reload and decide about a missing table.

#### What the tier bought, measured

`revoke-control` is `tier-1-destructive`, and the registry framework REFUSED the file until
`double_approval_required` was `true` (`registry.go`: tier-1 implies both gates). Reaching step 8
then took four separate refusals, each from a different guard, none of them written by this feature:

```text
missing scope "admin:destructive" (have [admin:read admin:write])
tier-1 command "reality revoke-control" requires a valid --second-actor-token
"reality revoke-control" typed-confirmation required — pass --confirm-token="cd0747d2-…"
REFUSED — expected user does not hold the live binding        <- finally, the feature's own CAS
```

The first draft of the registry entry said `double_approval_required: false`. The right response to
the framework's refusal was to accept the second half of the tier, not to downgrade the tier to
escape it: **if taking a character from a human is tier-1 harm, two-person control is what tier-1
means.**

#### `/review-impl` — two more defects, and both were found by RUNNING it

The adversarial pass produced two findings the whole suite agreed with, and neither was reachable
by reading. Both are fixed, bitten, and re-proved against the live stack.

**1 · A tier-1 REVOKE reported success for a reality that does not exist.** `revoke` deliberately
does not bind (above), so a typo'd `--reality-id` simply found no live binding and returned
`already_revoked` — which `admin` printed as *"was ALREADY in the requested state. Nothing was
written."* and exited **0**. An operator taking a character away reads that as done. The driver
kept driving.

```text
before   revoke-control --reality_id 99999999-…   ALREADY in the requested state   exit 0
after    revoke-control --reality_id 99999999-…   REFUSED — reality_id 99999999-… not found
                                                  in registry                       exit 3
```

The fix is a `reality_registry` lookup, **not** a bind: it answers *does this world exist* without
asking *does it accept commands*, so revoking a driver in a frozen world still works. `NotFound`
also stopped falling through to the 500 wildcard on this surface — here it has exactly one meaning,
and it is the caller's typo.

**2 · Adopting an actor broke the next allocation.** `GENERATED BY DEFAULT AS IDENTITY` does not
advance its sequence when a value is supplied, so `adopt_actor(1)` — the spine case the function
exists for — left the allocator still at 1, and the next `create_actor` collided with the row just
adopted. Proven first against raw Postgres, then end to end. The bite neuters `setval` while leaving
the call and its error handling in place, so only the EFFECT is removed:

```text
MUTANT     adopt 504 -> ok;  allocate -> duplicate key value violates unique
                             constraint "actors_entity_id_unique"        exit 3
RESTORED   adopt 505 -> ok;  allocate -> entity 506                      exit 0
```

Nothing was ever corrupted — `actors_entity_id_unique` refused the write — but a refusal an operator
cannot read is still an outage, and it fires in exactly the scenario adoption was written for.

**Three risks checked and CLEAR, listed because "we looked" is the part that usually goes unsaid:**

* **Secrets.** `ACTOR_CONTROL_META_DSN` carries a password and is parsed by sqlx. Three malformed
  shapes were run against the real binary — an unparseable URL, a bad port, a bare scheme — and none
  echoed the password to stderr, which `admin-cli` would have relayed into the operator's terminal.
  The per-reality connection no longer builds a DSN string at all.
* **Tenancy.** No new read or write of `actor_control_binding` outside the audited Go bridge; a grep
  confirms the only Rust reader is still `subject.rs`'s owner-scoped resolver. The dry-run decision
  is what kept it that way.
* **Exit codes.** A conflict is exit 1 with `conflict:true`, which `admin-cli` turns into a non-zero
  exit and a REFUSED message. There is no path where a refusal reads as success — the one that
  existed was finding 1, and it is gone.

**One gap accepted and recorded rather than fixed:** the subprocess seam has **no machine contract**.
The Go struct's json tags and the worker's emitted keys are two lists in two languages, and a rename
on either side passes both suites. It is mitigated rather than unguarded — `RunActorControl` refuses
an outcome the worker did not name, refuses a created actor with no id, and cross-checks the echoed
`reality_id` and `actor_id`, so the load-bearing fields fail loudly — and the twelve-step live run
exercises every branch. But that is a runtime guard and a manual run, not a test. Tracked as
`D-PC-SEAM-NO-CONTRACT`.

#### The wiring policy, both directions

```text
ACTOR_CONTROL_* unset entirely   -> "reality grant-control" (tier-2-griefing) is NOT wired —
                                    refusing to report success for a destructive/griefing command   exit 3
ACTOR_CONTROL_* half-set         -> handler not wired: worker env incomplete: ACTOR_CONTROL_BRIDGE_TOKEN,
                                    ACTOR_CONTROL_SHARD_HOSTPORT, ACTOR_CONTROL_PG_USER,
                                    ACTOR_CONTROL_META_ALLOWLIST                                    exit 2
```

`D-ADMIN-NOTWIRED-EXIT`, held: absent config leaves the command NotWired and the fail-closed tier
policy refuses it; PARTIAL config is fatal and names every gap at once, because that is a typo and
silently refusing would hide it.

## §4 OPEN

> **Where these are actually TRACKED.** Every row below is registered in the game-tier
> deferral registry — the `<!-- deferral-registry:begin -->` block in
> [`docs/03_planning/LLM_MMO_RPG/SESSION_HANDOFF.md`](../03_planning/LLM_MMO_RPG/SESSION_HANDOFF.md)
> — and `scripts/deferral-gate.py` enforces that each carries a mechanism or a declared
> wake-up. **They were not, until the 2026-08-20 audit** (`PD-17`): they lived only here, in
> `docs/plans/`, which the gate does not scan, under a `PC-` prefix its id pattern could not
> match. This section is the REASONING; that block is the obligation. If they ever disagree,
> the block wins.

| row | what | mechanism |
|---|---|---|
| `D-PC-SEAM-NO-CONTRACT` | **The admin-cli -> worker subprocess seam is two services, two languages, and no machine-checked contract.** The argv is rendered by `workerArgs` in Go and parsed by `Args::parse` in Rust; the reply is a JSON object emitted by `emit` and unmarshalled into `ActorControlOutcome`. Both sides have unit tests and both would stay green through a rename on either — the exact shape the Frontend-Tool Contract standard exists for (*"a drift/free-string/silent-no-op passes unit tests yet kills the live loop"*). It is NOT unguarded: `RunActorControl` refuses an unnamed outcome and a created actor with no id, the invoker cross-checks the echoed `reality_id`/`actor_id`, and the `P7` live run drives every branch. Those are runtime guards on the load-bearing fields and a manual run, not a test. | the fix is the pattern `contracts/frontend-tools.contract.json` already uses: one checked-in key list, a Rust test asserting each branch emits exactly those keys and a Go test asserting the struct tags cover them, so a rename reds on the side that did not move. The wake-up is a SECOND consumer of the worker's JSON, or the first field added to it after this one |
| `D-PC-NO-RUST-READ-AUDIT` | **There is no sanctioned way for RUST to take an audited sensitive read, and this row exists because the gap was found a slice ago and never written down.** `034` registers a cross-user read of `actor_control_binding` as sensitive; the only audited reader in the tree is Go's `MetaRegistrar.liveBinding`, INSIDE the write path, and it needed a new `TagActorBindingCrossUser` constant because the yml had registered the path since `035` with no SDK constant to reach it (`PD-10`). A Rust caller that wants the same read has no equivalent: it would write a bare `SELECT` and the lint would catch it, which is the lint working and not a path. **`P7` is where this stopped being theoretical.** The single most useful thing a `grant-control --dry-run` could tell an operator is *who drives this actor right now*, and the preview deliberately does not, because the honest way to answer needs an audited bridge READ route that does not exist. The design decision and the missing infrastructure are the same fact. | the wake-up is the first Rust caller that genuinely needs a cross-user read — most likely this preview, the moment an operator asks why it will not tell them. The fix is a bridge read route that writes `meta_read_audit` in the same call, mirroring the write side; it is BUILDABLE, not blocked, and it is scoped out of `P7` only because adding a probe-who-holds-whom capability is a decision, not a convenience |
| `D-PC-METAWRITE-NOOP-EVENT` | **`MetaWrite` emits the outbox event without checking `RowsAffected`.** `contracts/meta/metawrite.go` runs the data statement, then appends the audit row and the outbox event unconditionally — so a CAS'd UPDATE that matches nothing still announces its domain event. **Not introduced here and not this feature's to fix**: the append is shared by every meta table, and `query_builder.go`'s own comment advertises the CAS pattern for migration `011`'s consent revoke, so that path carries it too. Outbox delivery is at-least-once by contract, so a duplicate `actor.control.revoked` for an already-revoked binding is inside what a consumer must tolerate; it is still an event for a write that changed nothing. Designed around with a pre-read, so only a lost race can reach it. | the wake-up is any consumer that treats an outbox event as proof a row changed; the fix is a `RowsAffected == 0` guard on the append, and it belongs to whoever owns `contracts/meta` |
| `D-PC-SF6-REVERSAL` | **This round arms `SF-6`'s reversal trigger and does not discharge it.** `SF-6` refused to type `0021_turn_slot`'s `current_turn_actor` because four spellings of who-is-acting already existed, and named its own reversal: *"a single actor-identity type being adopted repo-wide, at which point the slot should hold it."* The registry built here is the first step toward that type. | the wake-up is the adoption itself — when a single actor identity is used by `GoneState`'s `EntityRef`, `pii_sdk` and the meta audit tables, `0021`'s JSONB column must stop being opaque |
| `D-PC-SEATS` | **One LIVE driver per actor is a DATABASE LAW, and three seats are not drivers.** ⚠ **This row said "the PK" until 2026-08-20, and `P1a` — in this same file — had already replaced it.** Measured: `actor_control_binding_pkey` is now `(binding_id)` and enforces nothing about drivers; the law is `actor_control_binding_one_live_driver`, a UNIQUE index on `(reality_id, actor_id) WHERE revoked_at IS NULL`. A reader following the old wording would have inspected the PK and concluded the constraint was gone. The comparison round found that Unreal's one-to-one is a *default you can override*; ours is a constraint Postgres enforces. So **spectating**, **GM override** and **advisor** must each be designed as something other than a second binding. The advisor case is already settled (an LLM that proposes and a human that commits is one driver plus an advisor; the advisor never becomes the subject). Spectating and GM override are NOT thought about, and the PK will force the question the first time either is asked for. | recorded now rather than discovered later; the wake-up is the first feature that needs a non-driving seat |
| `D-PC-AGENT` | can a controller be an agent, and how is it represented? **Deferred by the PO to the AI feature** (needs an agent runtime + state machine). | it must not be prose-only: the wake-up is the first non-human principal appearing in `actor_control_binding`, and the trigger goes in with `P1` |

### Recently cleared

| row | how it closed |
|---|---|
| `D-PC-ACTOR-IDENTITY` | **Answered by the PO and BUILT — and it stayed on the OPEN list for six days after the slice it claimed to block had shipped.** Its mechanism column read *"`P2` cannot be built until it is answered; the row is the block"*, while `P2a` and `P2b` sat at `[x]` eight lines above it. Measured 2026-08-20: `contracts/migrations/per_reality/0022_actors.up.sql` exists, `actor_registry` exports four functions, `commit_service::subject::resolve_subject` resolves the two hops, and `P5` proved the whole chain against two live databases. The PO chose *"build the per-reality actor registry"*; the row recording that choice as unanswered outlived the answer. **A blocking row that survives its own unblocking is worse than no row** — it argues, in a file a future session trusts, that finished work cannot start. |

## §5 DRIFT — append as it happens; an empty log is dishonest, not clean

| id | what |
|---|---|
| `PD-12` | **The live smoke found a defect the whole unit suite agreed with, in the FIRST run.** `bind_reality` mapped every `SessionContext::bind` failure to `RealityClosed`, so when the dev meta database turned out to be missing migration `039`, `relation "session_registry" does not exist` reached the operator as **`conflict: true` — "REFUSED. This is a statement about the world, not a failure; reload and decide"**. An outage wearing the costume of a normal answer, inviting someone to go hunting for a reality that was doing exactly what it was told. The split already existed UPSTREAM and I had not looked: `MetaControlPlane` raises `RealityMismatch` for a world that refuses commands and `ControlPlaneUnavailable` for a store it could not read. **This is precisely the distinction `ActorAlreadyDriven` exists as its own variant to preserve — I quoted that reasoning in this file and then collapsed it one layer up.** Fixed with `classify_bind_failure`, bitten (the mutation IS the shipped bug), and re-proved live in both directions: a bad allowlist path now reports `conflict:false status:failed`, a frozen reality still reports `conflict:true`. |
| `PD-13` | **Four of the nine gates the sweep called RED were the sweep's own concurrency.** `gate-wiring-gate --run-all` runs the bite harnesses in parallel and they share ONE lock (`target/.bite-harness.lock`), so `dp-slice1` printed *"REFUSING TO START — another bite harness holds the lock (pid 52660)"* and three siblings failed alongside it. Run serially, all five pass. The lock was still on disk afterwards with a DEAD pid — the same stranded-lock shape as `PD-9`, and this time I checked `git status` for a stranded MUTATION before clearing it (there was none; all 9 modified files were mine). **A red gate whose cause is the harness is worse than a red gate: it spends the credibility of the four that were real.** |
| `PD-14` | **Two gates were already red at HEAD and I had claimed a clean sweep the day before.** `tracing-completeness-lint` was at 50 against a ratchet of 49 — measured with my working tree stashed, so it was not mine — because `handlers/actor_control.rs`, shipped in `23f4492cf`, calls `tracing::error!` fully-qualified and the lint reads the IMPORT. Fixed by importing rather than by moving the ratchet. `actor-hub-figures-gate` then caught three figures I had personally invalidated in the previous hour: applying `0022` to the exemplar reality (12→13 tables), applying the three un-applied meta migrations (29→32), and adding the `actor-control` binary (8→9). **Every one of those was a consequence of my own work that I would not have thought to write down.** |
| `PD-15` | **The dev stack was three migrations behind and nothing said so until a real call failed.** `039_session_registry`, `040_tier_policy` and `041` were committed and never applied to `loreweave_meta`; the bridge container was a 37-hour-old image without the grant/revoke routes at all. Both were invisible to every unit suite, and both would have been invisible to a live smoke that mocked either side. **`file exists in migrations/` and `applied to the database` are different facts, and only one of them is checked anywhere.** Not filed as a deferral — the fix was to apply them and rebuild the image, which I did — but the GAP has no mechanism, and the next person will find it the same way. |
| `PD-16` | **The 400-line file ceiling does not cover `services/world-service`, and my worker is 563 lines.** `file-ceiling-gate` printed OK, and it was telling the truth about its own scope: the tier list is seven directories and world-service is not one of them, so the binary was default-uncovered — `NV-3` exactly. Checked by hand instead (~370 lines of production code, the rest tests) and left as is, because the sibling `provision.rs` in the same directory is **914** lines and splitting mine to a ceiling that governs neither would be a local consistency win and a global inconsistency. Recorded rather than quietly passed: a green gate that never looked is not evidence, and adding the directory to the tier would red on four existing files. |
| `PD-2` | **I ran the bite against the wrong suite and nearly filed a false finding.** `routes.rs` claims *"a test reads the SOURCE of this file and asserts every `.route(…)` literal it finds is listed here"*. I removed a `ROUTES` row, ran `cargo test --lib -- routes`, saw 6/6 GREEN, and concluded the guard did not exist — a claim without a mechanism. It exists: `tests/route_conformance.rs`, an INTEGRATION test, which `--lib` does not build. Re-bitten against it: two tests red, restore returns 5/5. **A bite that does not red is evidence about the harness before it is evidence about the code**, and I was one step from recording the opposite. |
| `PD-3` | **The suite was already RED before my bite, and the bite is what showed me.** `every_routed_operation_is_documented` fails the moment a route exists with no contract entry: *"this service serves 2 operation(s) no contract in contracts/api/world documents… Contract-first: freeze it in the YAML in the same commit."* I had mounted the routes and moved on. The rule is in CLAUDE.md, the gate is wired, and I still needed the gate to tell me. |
| `PD-4` | **Hazard #5, four times in one day, in a session whose own run-state records it twice.** A heredoc carrying `\\n` inside a Python string mangled a bite script's anchor, so the mutation silently did nothing and the run reported a clean pass. Caught only because the MUTANT banner was missing from the output — the same tell as `LD-7`. Every patch in this slice since goes through the Write tool, and that is now a rule for the rest of the session rather than an intention. |
| `PD-5` | **A regex with `[^,]+` inserted an argument into the WRONG function.** Migrating 19 call sites, I matched the first argument of `admit_t6(` with a character class that stops at the first comma — which for `admit_t6(&proposal_json("p-1", "strike", "x"), …)` is inside the NESTED call. Four files were patched wrongly before the compiler said so. Reverted with `git checkout` and redone with a parenthesis-depth scan; the last three sites it still walked past were done by hand, which is the tell that a hand-rolled parser was the wrong tool for the tail. |
| `PD-6` | **The bite matched zero times and the run that followed looked like a pass.** The anchor embedded `\n` against a CRLF file, so `t.count(...)` was 0, the assert fired — and the `cargo test` chained after it printed 4/4 GREEN for the UNMUTATED code. Identical output to a successful bite. Third instance of this exact shape today (`LD-7`, `PD-4`), and the only reason it was caught is that the MUTANT banner was missing. |
| `PD-7` | **I added a `userOf` map that already existed.** `ChannelRoom` has had one since `CNC-Q1` — the map, its `set` in `onJoin`, its `delete` in `onLeave`, and a read at the top of the very function I was editing. I declared a second one four lines below the first. Phase 0's question 1 at micro scale: *what already models this?* — asked of a whole feature this morning and not of a two-line field this afternoon. |
| `PD-8` | **A test fixture built a state production cannot reach, and my change exposed it.** `ChannelRoom.test.ts` set `actorOf` by reaching past `onJoin` into the privates, without `userOf` — an actor bound to a session with no user. `onJoin` sets `userOf` UNCONDITIONALLY and `actorOf` only when a binding exists, so that state is unreachable. The fixture could construct it only because it skipped the constructor. |
| `PD-17` | **Six deferrals I wrote were never tracked by anything, and one of them says in its own text that it must not be prose-only.** The `PC-*` rows in §4 lived in `docs/plans/`; `deferral-gate.py` globs `docs/**/SESSION_HANDOFF.md` and `docs/deferred/*.md`, so it never opened the file. **And the failure was double**: its `ID` pattern is `D-[A-Z]…`, deliberately tight, so even pasting the rows into the registry block left the count at 30 — they were invisible by NAME as well as by location. `D-PC-AGENT` promised *"it must not be prose-only… the trigger goes in with `P1`"*; `P1` shipped six days earlier with no trigger and nothing said a word. Fixed: renamed to `D-PC-*`, moved into the registry (30 → **36** tracked), five PROSE_ONLY rows with real wake-ups, and `D-PC-AGENT` got the ASSERTED TRIGGER it was owed — `actor_control_trigger_test.go`, bitten with a `controller_kind` column, red for the right reason. **And the prefix was not free.** `PC-*` is a CATALOGUED namespace — `00_foundation/06_id_catalog.md` assigns `PC-A1..A3 · PC-B1..B3 · PC-C1..C3 · PC-D1..D3 · PC-E1..E3` to *Player Character semantics*, and `I15` in `02_invariants.md` says those ids *"are forever"*. `PC-D2` is a locked decision about consent-gated PvP. So I minted six ids into a registry someone else owns, for a feature whose subject is also called a player character — which is exactly how the collision went unnoticed. **I invented an id prefix, assumed the tracker would recognise it, and did not check whether it was taken.** The catalog answers both questions and I opened neither: it is Phase 0's question 1 — *what already models this* — asked of a NAME rather than a concept. |
| `PD-18` | **A row claiming to BLOCK a slice outlived the slice by six days.** `D-PC-ACTOR-IDENTITY`'s mechanism column read *"`P2` cannot be built until it is answered; the row is the block"* — while `P2a` and `P2b` sat at `[x]` eight lines above it in the same table, `0022_actors` existed, and `P5` had proved the resolver against two live databases. The PO answered it on 2026-08-14 and I recorded the answer everywhere except the row that asked the question. **A stale blocker is worse than a stale figure**: it tells a future session that finished work cannot start. |
| `PD-19` | **Three claims in this file were measured false, and one contradicted a slice in the same document.** `D-PC-SEATS` said *"the PK makes one-driver-per-actor a database law"* — but `P1a`, nine sections earlier, replaced that PK with `binding_id`; the law is now a partial unique index, and a reader following the row would have inspected the PK and concluded the constraint was gone. The header said `files 8` against a measured **52**. `P6` said `799/0 across 72` where the workspace has **193** suites, so the figure covered a subset and never said so. None of the three was a lie when written; each stopped being true and nothing re-read it. **The fix that generalises is not "be careful" — it is that every number in a run-state should name what it counted.** |
| `PD-9` | **I killed a bite harness and it left a SECURITY REGRESSION in the working tree.** `TaskStop` on a sweep caught `dp-slice5c-bite-gate` mid-mutation, so `crates/dp-control-plane/src/server.rs` kept the mutant — `Status::unauthenticated(format!("capability is not valid: {}", e))` in place of the constant string. That is information disclosure: the control plane telling a caller WHICH kind of capability failure occurred, which is exactly what the guard prevents. It was uncommitted, in a crate this feature never touches, and it would have gone into the commit. **The lesson is narrower than "do not kill sweeps": a bite harness holds source in a MUTATED state, so killing one leaves a deliberate defect behind.** I cleared its stale lock file and moved on — treating the hint as the damage. What actually surfaced it was the failing test printing the MUTANT TEXT rather than a plausible assertion failure. |
| `PD-10` | **The sensitive-read discipline had no reachable path for this table, and I found that by violating it.** `034`'s header says a cross-user read of `actor_control_binding` writes a `meta_read_audit` row; I QUOTED that sentence in this file's own `Reconciles` line and then wrote two bare SELECTs. The lint caught both. One is owner-scoped and matches the GDPR cascade's existing exemption; the other is genuinely cross-user and now writes the row — which required adding `TagActorBindingCrossUser`, because the yml has registered that path since `035` and **the SDK never had a constant for it**. The audited route was unreachable, so the first cross-user reader bypassed it by default rather than by choice. |
| `PD-11` | **`reality-id-adoption-gate` caught a safety property, not a naming one — and the spine was the worst offender.** `dp::RealityId` has NO public constructor: it exists only as the output of `SessionContext::bind`, so holding one proves the control plane confirmed the reality ACCEPTS COMMANDS. `bin/spine.rs` was passing `args.reality` — the raw CLI text — into the new resolver while holding the verified id from its own bind, four lines up. `world-service` now binds before every registry touch, so granting control in a frozen or archived reality is refused rather than recorded. Adoptable is back to **0**. |
| `PD-1` | **I proposed merging to `main` while the goal was unmet.** The PO stopped it: *"our goal still not satisfied yet."* I had spent the preceding hours on CI health — real work, and not the work. The audit that followed took twenty minutes and found the feature was already half-designed, which is time I would not have spent had I kept optimising the thing in front of me. |
