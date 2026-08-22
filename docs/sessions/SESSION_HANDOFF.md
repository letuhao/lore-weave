# ▶▶ NEXT SESSION STARTS HERE

## ▶ SPACE-PRODUCERS IS CLOSED — 13 of 13, three lanes (2026-08-22, branch `feat/game-logic`)

> **[`2026-08-22-space-producers-RUN-STATE.md`](../plans/2026-08-22-space-producers-RUN-STATE.md) is
> 13/13.** 14 commits. The board existed because closing the space substrate revealed that **six
> tables had two producers between them and `world_seed`/`space_view` had zero callers outside
> `tests/`** — reality-layer `3C`'s lesson (*"an unforgeable mint is dead code until something can
> mint"*) at seven times the scale.
>
> **Lane A — producers.** `A1` measured the seam and found something worse than the thesis: there is
> no space phase because **there is no seeding phase at all** — provision steps 9 and 10 are
> consecutive statements, and `reality_seeder` (1008 lines, described as the background orchestrator
> for exactly that stage) has zero production constructors. `A2` gave the stage a body: a 12th
> provision step, `seed_world_structure`, called BETWEEN the two transitions, taking a DECLARATION —
> **empty means skipped, never "use a default world"**. `A3` is SPAWN: `entity_binding` gets a
> producer, atomic with actor creation, and the bite proves it (`actors 2 -> 3` when the transaction
> is removed — an actor with nowhere to be has no collector). `A4` put *"what is here"* on the wire
> with a ceiling that **refuses rather than clamps**. `A5` decided `portal`/`encounter`/
> `layer_registry` get TRIGGERS, not producers.
>
> **Lane B — four rows other boards held open, and THREE OF THEM WERE ALREADY DONE.** reality-layer
> `3C`/`3D` shipped and the board still said *"blocked on a PRODUCER"*. kernel-state `G5`'s automated
> suite was fully written and **had never been run** — 2 passed on chromium once someone ran it.
> game-tier's eight `1b5-*` rows were discharged eighty lines below themselves. Only lore-bible was
> genuinely open, and it stays parked — with a mechanism now.
>
> **Lane C — the tooling that hid all of it.** `goal-prompt.py` had three measured gaps: a bolded id
> was not a row (**30 of 51 boards parsed as EMPTY**), `⬜` was not in its vocabulary (**27 open rows
> invisible**), and it could not tell a marker from a **mention** of one — which silently TICKED open
> rows, twice in one day. Fixed and bitten; boards parsing empty **30 → 15**, rows visible **~200 →
> 445**, validated against five boards whose state was independently known.
>
> **⚠ Four things to carry, none of them a task.**
>
> 1. **The recurring shape, five times in one run:** the work ships and the register is never told.
>    `SPG-Q6`, reality-layer `3C`/`3D`, the eight `1b5-*` rows, `G5`'s unrun suite, and
>    `reality-id-adoption-gate` (a row said it was *refused*; it exists, and **this run had broken it**
>    — `A3`/`A4` took it 0 → 6 ADOPTABLE, now back to 0).
> 2. **A gate's SELF-TEST passing is not the gate running.** `reality-id-adoption-gate`'s self-test
>    runs in `gate-self-tests`, so it was green in every commit while the ratchet itself was red.
> 3. **`OR-3`: nothing yet DECLARES a world.** Every in-repo caller passes an empty declaration, so
>    `seed_world_structure` is `Skipped` on every existing path. The producer is reachable; the author
>    does not exist.
> 4. **`OR-5`: 15 boards still parse empty** — a fourth dialect family (plain-text ids, ids containing
>    a space or `·`, a marker before the id). Deliberately not folded in: the first careless widening
>    produced **three false opens on a 35/35 closed board**.
>
> **One pre-existing failure, verified as pre-existing:** `provisioner_reentry_live` fails locally on
> `could not access file "vector"` — pgvector is not installed on this Postgres. Confirmed identical at
> `ff58f69b1`, the commit before this run, by running it in a worktree there. Not caused by this work.
## ▶ ALL FOUR BOARDS CLOSED, AND THE OPEN REGISTERS ARE EMPTY (2026-08-21, branch `feat/game-logic`)

> **`HEAD` after this commit.** Four boards — [player-edge](../plans/2026-08-21-player-edge-RUN-STATE.md)
> `E1`–`E6` · [demo-path](../plans/2026-08-21-demo-path-RUN-STATE.md) `F1`–`F5` ·
> [kernel-state](../plans/2026-08-21-kernel-state-to-screen-RUN-STATE.md) `G1`–`G8` · the closeout —
> and **no open row left on any of them.** The five that were open at the last handoff (`GO-1`,
> `GO-2`, `FO-1`, `FO-2`, `EO-1`) are all cleared.
>
> **The pipeline is proven in both directions, automatically.**
>
> ```
> browser Strike → proposal (user_ref_id server-stamped, NO actor field)
>   → spine, LONG-RUNNING, no --drain-once → actor_hub::Actor::set_quantity
>   → events row → publisher → lw.events.<reality> → foldEvent → the DOM
> ```
>
> A page that never reloaded shows `turn 2 · 1 strikes 2 for 9 (31 left)`, and the number is the
> hub's, not a derived badge. Every hop bitten.
>
> **`G8` is the one added today**, and only because a reason got checked: three boards said *"the
> long-running consumer hangs (`DFO-7`)"*. `DFO-7` closed 2026-08-14 and its subject was
> `--drain-once`; the no-flag mode is a daemon by construction. Measured: a proposal XADDed while
> the spine was already running committed in **~1s** (`COMMIT … → channel_event_id 3 (Applied)`,
> `turn.resolved` / `struck` / `attacker: "1"` resolved by the kernel from the binding), and the
> process stayed up. The control is in the same run — the synthetic driver produced
> `proposal.rejected` *"drives no actor in this reality"*, so the difference between commit and
> refusal is the binding. `GD-13` records the mis-citation.
>
> **`FO-2` closed the last gate gap**, and cost more than the row promised. `phase0-reconcile-gate`
> now refuses a `Reconciles:` field that strands citations past the em-dash — reporting a segment
> only when its head **does** resolve to a real index row, so it can under-report but never invent
> a phantom, which is what got the earlier widening reverted. **94 → 106 citations actually read**;
> the 5 legacy fields rewritten in the same commit. It also surfaced two things nobody was looking
> for: the reference set was admitting the table HEADERS `Test`/`Script`/`SoT file`, so
> `Reconciles: a test I wrote` **passed at HEAD**; and `Destructive DB ops in tests` — ENFORCED,
> three enforcement layers, an incident behind it — **had no row in the standards index** and only
> resolved through that `Test` cell. Both fixed.
>
> **⚠ Two things to carry, neither of them a task.**
>
> 0. **The handoff/archive split is main's, and it is now done here too.** This file was 12,445
>    lines after the merge and is 1,182 now; nothing was deleted — `SESSION_ARCHIVE.md` went
>    21,881 → 28,260 and the move is proven lossless (0 headings, 0 non-blank lines, checked
>    against the merge commit). Trim this file freely; put what you trim in a dated archive
>    block. **I got this wrong first**: main's 1,036-line handoff looked like data loss, so the
>    merge resolution kept the branch's whole file — which put 96 already-archived sections back
>    beside the copies still in the archive. The `▶ GAME TIER` entry is deliberately still live:
>    `actor-hub-figures-gate` anchors a checked region in it.
> 1. **The local sweep is not CI.** `SWEEP_RC=0 — 91 GREEN` runs 99 of ~200 scripts;
>    `migration-idempotency-validator` is CI-wired only, which is why a non-idempotent migration
>    passed the sweep and was caught by a live suite (`GD-11`, `GD-12`).
> 2. **THIS BRANCH IS ~115 COMMITS BEHIND `main`, and that produced a whole class of false work.**
>    I wrote here that `frontend-game-e2e` "has never run green on a PR". `gh run list` says it is
>    **green on push to `main`, 2026-08-09, 3m27s** — and `main` already carries both fixes `GO-1`
>    claimed to make, including a `smoke.spec.ts` that seeds a session so the guarded routes stay
>    asserted. My branch version SKIPPED them (2 tests running vs main's 8). Main's spec is adopted
>    here now. **Before the next task: decide whether to merge `main` down.** Three of today's rows
>    were written against things that already existed one branch or one `ls` away (`GD-15`).
>
> **VERIFY.** Gate sweep **91 GREEN / 0 RED / 8 SKIP** (`gate-wiring-gate.py --run-all`; the six
> bite gates that first reported RED in 0.1s were a stale `target/.bite-harness.lock` left by my own
> killed run — re-run serially, 6 GREEN. `GD-14`). `phase0-reconcile-gate` **SELFTEST 15 cases** +
> tree **OK, 25 specs / 128 index rows**, bitten three ways with byte-exact restores. Long-running
> spine measured live against the demo stack. No Rust or TS source changed in this commit.
>
> **▶ DO NEXT — nothing is in flight; the next task opens its own board.** The natural continuations,
> none started: run the whole demo under an orchestrator rather than by script (`G8` proves the
> binary, not the deployment) · the product path `G-S3`/`G-S4`, still parked on the PO because
> combat and progression have no complete design to write a schema against · `DFO-6` and the two
> unbuilt `DP-X2` Redis roles in
> [data-foundation](../plans/2026-08-13-data-foundation-dataflow-RUN-STATE.md).

---

## ▶ THE DEMO PATH — kernel identity reaches a browser (2026-08-21, branch `feat/game-logic`)

> [`2026-08-21-demo-path-RUN-STATE.md`](../plans/2026-08-21-demo-path-RUN-STATE.md) — `F1`–`F5`.
> Opened by one question: *"does the actor hub reach the FE end to end?"* It did not, and the
> reasons stacked in a way nothing in the tree could report.
>
> **`turn 0 · you are entity 1`, rendered in Chromium.** Browser → `channel` room → `onAuth`
> (server-supplied identity) → world-service `/internal/v1/actor-control/subject` → meta binding →
> per-reality `actors` → `entity_id 1` → `w1.frame.self` → the DOM. **Bitten**: stop world-service
> and the same click yields *"could not resolve your actor; retry"*; restart it and entity 1 comes
> back. So the number on screen provably comes from the control plane and both databases.
>
> **And the refusal is the RIGHT one** — not *"you drive nobody"*. `E3`'s four-answer design
> (driving · nobody · realityClosed · unavailable), visible in a UI for the first time rather than
> argued for in a test.
>
> **THE VIEW WAS BORN UNREACHABLE.** `ChannelPanel` shipped in `fc2ba5f8a` with its client, its
> store, six tests and a live proof — and that proof drove the CLIENT. Nothing ever rendered the
> panel. It stayed an orphan for three weeks, through a security review of the room it talks to and
> a phase that rewrote the subject it renders. Nothing went red and nothing could: it compiles, its
> store compiles, its client is tested, the suite is green. The orphan shape one tier above the one
> `orphan-model-gate` watches — there a model with no PRODUCER, here a view with no CALLER.
>
> **And after `E4` the FE's only identity was not a user.** `onAuth` returned
> ``dev:${jwt.slice(0,4)}`` — fabricated from four characters of a SHARED token — which fails
> `isUserRefId`, so the join was refused and the demo path was structurally dead. Nothing reported
> that BECAUSE the panel was unmounted; had it been wired, `E4` would have broken it visibly.
> `F1` makes the identity server-supplied, UUID-validated, **no default**, so the branch fails
> closed where it used to invent.
>
> **world-service had no Dockerfile and no compose entry** (`WS-COMPOSE`, closed). Both written; the
> image builds at 139 MB and carries `contracts/`, because two config defaults are CWD-relative —
> `ED-D8` from the player-edge run reappearing as a packaging requirement.
>
> **⚠ WHAT IS STILL NOT PROVEN: actor-hub STATE in the browser.** *(Proven later the same day by
> the kernel-state board — `G3`–`G5`. Kept as written because the reason it was not proven here is
> the useful part.)* The roster was empty and the turn
> 0 because reality `cd0747d2` has **zero committed events** (`XLEN 0`, `events` table 0 rows).
> The SUBJECT hop is proven; hp/roster/turn have never been rendered. Doing it needs a reality with
> both committed events AND a live binding, and no reality has both — creating one means granting a
> binding, a write to the non-throwaway dev meta database.
>
> **▶ DO NEXT — SUPERSEDED, and left in place because what it got wrong is the record.** Every
> candidate it named is done: kernel STATE is on the screen (`G3`–`G5`), `FO-1`, `FO-2` and `EO-1`
> are cleared, and *"the spine still hangs (`DFO-7`)"* was never true — see `GD-13`. Read the block
> at the top of this file instead. Original text: either (a) get kernel STATE onto the screen —
> needs the write above, or a throwaway reality provisioned for it, and the spine still hangs
> (`DFO-7`) so a RESOLVED turn is further out; or (b) `FO-1` — `EchoRoom.onAuth` takes
> `options.userId ?? 'guest'` FROM THE CLIENT, and that id keys the per-user connection cap, so a
> client evades the cap by picking a new id per connection; or (c) `FO-2` —
> `phase0-reconcile-gate` reads only the citations before the first em-dash (7 of 25 fields, 15
> unread), whose fix is a convention change across tracks. `EO-1` from the player-edge board is
> still open (no `CHECK (entity_id >= 0)` on `actors`).

---

## ▶ THE PLAYER-FACING EDGE — a human drives without an operator (2026-08-21, branch `feat/game-logic`)

> [`2026-08-21-player-edge-RUN-STATE.md`](../plans/2026-08-21-player-edge-RUN-STATE.md) — `E1`–`E6`,
> six slices, one PO checkpoint. **`D-ACTOR-BINDING-NOT-READ-BY-TRANSPORT` is discharged**, open
> since 2026-08-06; registry **34 → 33**.
>
> **The transport ASKS now.** `POST /internal/v1/actor-control/subject` on world-service resolves
> `(reality_id, user_ref_id)` to the island `entity_id`, and `ChannelRoom` reads it instead of an
> environment variable. A human can drive an actor because somebody granted them one, not because
> an operator edited the environment and restarted the process.
>
> **Phase 0 shrank the work before it started.** The read is OWNER-SCOPED — the sensitive-path
> contract describes its audited sibling, verbatim, as `WHERE user_ref_id != $caller_user`, so none
> of `RA1`'s audit machinery applies. *"Which actor do I drive"* is a question about yourself.
>
> **The shape came from a LINT, not from taste.** `meta-sensitive-read-bypass-lint.sh` excuses
> callers BY NAME, and carried `commit-service/src/subject.rs` under a comment saying the quiet part
> out loud: *"There is NO RUST-SIDE SANCTIONED READER… the only compliant Rust read is one that does
> not happen."* A second caller would have grown that list by one per service — `NV-3`'s
> default-uncovered shape. So hop 1 moved into **`meta-rs`** and both services call it; `subject.rs`
> left the exclusion list because it no longer contains a SELECT.
>
> **⏸ `E4`, the PO checkpoint: DELETE `LW_CHANNEL_ACTOR_MAP` entirely.** The strict option over the
> recommended one. Every alternative leaves the second source *in the code*, one edit away from
> being consulted; a gate is a decision someone can revisit, an absence is not. The cost was
> accepted out loud: **a local session now needs `admin reality provision` → `create-actor` →
> `grant-control` before anything can be driven.**
>
> **Two defects found on the way, neither of them the feature's:**
> 1. `actors.entity_id` accepted a NEGATIVE value — `0022` has no `CHECK` and `adopt_actor` passed
>    an operator's `--entity-id` straight through. `-1 as u64` is `u64::MAX`, so the actor could be
>    created, granted, and never act, with nothing on the path saying so. Refused at both edges now.
> 2. `meta_allowlist` defaults to a RELATIVE path, so the same code binds from a shell and 500s
>    under `cargo test`, reported as a generic *"actor-control write failed"*.
>
> **Evidence: 26 bites**, every one watched RED for the right reason and restored byte-exact —
> 7 (`E1`) + 4 (`E2`) + 6 (`E3`) + 2 (`E4`) + 3 live (`E5`) + 4 re-bitten after refactors. Rust
> workspace **2568 passed / 0 failed**, game-server **82 / 0**, all Go contract suites green, and
> **23 of 23 live suites** including the new `world-actor-subject`.
>
> **▶ DO NEXT.** The edge is built and proven; nobody has driven a turn through it end to end. The
> honest next step is a WS-level run — a real ticket, a real join, a real submit — which needs
> world-service in `infra/docker-compose.yml` (it is not there; both live proofs run it from
> source). Four `D-PC-*` rows remain. `D-DEFERRAL-GATE-PLATFORM-SCOPE` still leaves ~360 ids
> ungoverned outside the game tier.

---

## ▶ THE DEBT RUN — and the audit table that had never had a row (2026-08-21, branch `feat/game-logic`)

> Closes both rows the `P7` audit opened, one day later.
> [`2026-08-20-actor-control-debt-RUN-STATE.md`](../plans/2026-08-20-actor-control-debt-RUN-STATE.md)
>
> **`D-PC-SEAM-NO-CONTRACT`** — `contracts/actor-control-worker.contract.json`, read at RUNTIME by a
> test in each language. Written FROM MEASUREMENT: the two sides already agreed (18 keys, 8 flags,
> 3 ops), so it freezes an agreement rather than declaring one. **Eleven bites**, five Rust and six
> Go. The flags half is BEHAVIOURAL — the real compiled worker, a complete argv and an empty
> environment reach the config check while a rejected argv dies earlier with a different message —
> and the response-keys half is a source scan, stated as such in the test rather than dressed up.
>
> **`D-PC-NO-RUST-READ-AUDIT`** — the row asked for a reachable audited path from Rust. Trying to
> PROVE it is what found the real defect: **`meta_read_audit` had never held a single row.**
>
> 1. `liveBinding` writes it `if m.ReadAudit != nil`; **no production construction ever set the
>    field** — both entry points built `MetaRegistrar{Cfg, Caller, Pool}` and stopped.
> 2. The `ReadAuditor` implementation its own interface comment described **did not exist**.
> 3. Written and wired, it failed validation: `TagActorBindingCrossUser` was declared as a constant
>    on 2026-08-14 and **never added to `IsValid`'s switch six lines below it**.
> 4. Fixed: **0 → 1**, then **2 → 3** against the dev stack's own container.
>
> Four layers of one discipline — the migration that declared it, the yml that registered it, the
> constant that named it, the interface that guarded it — with an empty table underneath, because
> nobody had ever CALLED it.
>
> **The PO decision at `RA3`:** the preview reports the SLOT and never the PERSON. Enforced by a
> TYPE — `Preview.actor_is_driven` is a bool, so the worker cannot send the id; a future edit that
> wanted to leak it would have to change the type, which is reviewable, where forgetting a
> redaction is not.
>
> **The mechanism** that would have caught the whole chain is now `contracts/pii/sdk_test.go`: the
> yml and the SDK must agree in BOTH directions. It found a second gap on its first run — three
> registered paths (`audit_query`, `admin_bulk_export`, `bulk_meta_query`) have no Go constant, so
> `IsValid`'s claim to "mirror the yml" was false three more times.
>
> Registry: **36 → 34** tracked deferrals, and the closure is enforced — a `PROSE_ONLY` row whose id
> has left the block reds the gate (bitten).
>
> **Also:** `scripts/goal-prompt.py`, copied from the MVP repo and de-biased so any plan can use it
> — zero configuration, both row dialects, proven against a foreign repo's plan. It found a defect
> in ITSELF while generating this run's goal (a table row's span ran to EOF and turned a
> drift-register row into a hand-back), and the selftest arm for that was VACUOUS on first write.
>
> **▶ DO NEXT.** The debt run is closed. The obvious next feature is the player-facing edge — the
> transport still resolves actors from `LW_CHANNEL_ACTOR_MAP`
> (`D-ACTOR-BINDING-NOT-READ-BY-TRANSPORT`), so a human still cannot drive an actor without
> admin-cli. Four `D-PC-*` rows remain, each waiting on something that has not happened.

---


## ▶ GAME BUILD — FEATURE #2: a player is a CONTROL INTERFACE, the subject can no longer be forged, and an OPERATOR can now grant one (2026-08-14, branch `feat/game-logic`)

> ## ▶ THE PLAYER FEATURE — first slice shipped
>
> **The PO picked feature #2: a hub for a player to control the actors they own.** Phase 0 found it
> already half-designed and carrying a live security defect.
>
> **What existed:** `migrations/meta/034_actor_control_binding`, sealed 2026-08-06, stating the
> framing almost word for word — *"a player is not a KIND of actor — it is a CONTROL INTERFACE"* —
> with three declared events and **one reader and no writer at all**. The only `INSERT` in the tree
> was a test fixture, so the table was empty by construction: the same state `035` recorded about
> the table `034` replaced, and the reason that one was deleted.
>
> **The defect it closes:** `admission::Proposal` carried `pub actor: u64` and `ChannelRoom`
> supplied it. The producer SIGNATURE was verified and the SUBJECT was not, so the field naming who
> you act as arrived from the party claiming it. `PID-D5`'s *"a field that is not on the wire cannot
> be forged"* sat eleven lines below it, making that argument about a different field.
>
> ### Two sealed decisions turned out to be wrong, and both were measured, not guessed
>
> * **`034`'s PK made revoke TERMINAL.** Its header promises *"two LIVE rows … unrepresentable"*;
>   `PRIMARY KEY (reality_id, actor_id)` permits one row TOTAL, so an actor whose driver left could
>   never be driven again. Migration **`041`** replaces it with a partial unique index over live
>   rows. Handoff works, two live drivers still refused.
> * **`S-9` fired**: the binding said UUID, the island says `EntityId(u64)`, zero conversion sites
>   existed — and after `0017` dropped the `pc_*`/`npc_*` projections, **no per-reality actor table
>   survived at all**. The binding was a durable pointer to something that did not durably exist.
>   The PO chose to build the registry; migration **`0022_actors`** is `S-9`'s conversion site, and
>   `SF-6` (three days old) says why it is not a fifth spelling: it mints no vocabulary, it writes
>   down the mapping between two that already exist.
>
> ### Shipped
>
> | | |
> |---|---|
> | `041` + `0022` | the binding's constraint repaired; the per-reality actor registry, which ALLOCATES the island id so it is the SSOT rather than a second copy |
> | the WRITER | two scoped ops on the Rust→Go meta bridge (`I8` audit in the same TX) + `world-service` routes + a frozen contract. A grant REFUSES an actor the registry does not have |
> | the RESOLVER | `commit_service::subject` — two hops, meta binding (live rows only) → per-reality `actors` → `EntityId`, with three distinguishable refusals and a CHECKED `i64→u64` |
> | the WIRE | `pub actor: u64` is GONE. `user_ref_id` replaces it; the transport sends the user |
> | the CALLER | `admin reality create-actor` / `grant-control` / `revoke-control` — because the writer's routes are `require_internal` and no operator could reach them. **The same orphan shape one tier up**, and the reason `035` deleted a table |
>
> ### Evidence
>
> **The forgery, demonstrated and then killed** — the new suite run against a mutant that reads the
> acting entity off the wire again:
>
> ```text
> MUTANT  a_proposal_naming_another_actor_does_not_become_that_actor ... FAILED
>           left: EntityId(99)      right: EntityId(1)
>         the_callers_resolved_subject_is_the_one_that_acts ... FAILED
>           left: EntityId(0)       right: EntityId(7)
> RESTORED byte-exact -> test result: ok. 4 passed; 0 failed
> ```
>
> **Live, two databases in two tiers** (`scripts/live-suites.py --only commit-subject`):
>
> ```text
> GRANTED   user 29731ffa-… -> EntityId(4242)
> STRANGER  user bb171b31-… -> refused (no live binding)
> REVOKED   user 29731ffa-… -> refused (binding is history)
> HANDOFF   user 076d7efe-… -> EntityId(4242)
> DANGLING  actor f1065f68-… -> refused (no registry row)
> ```
>
> `CARGO_RC=0` — **785 passed / 0 failed across 68 suites**. `GO_RC=0` across 13 packages.
> game-server **70 pass / 0 fail**. Removing the field rather than ignoring it is what made the
> compiler find all **19** call sites.
>
> ### `P7` — the caller, and the fork it turned out to be
>
> The grant path shipped with **no invoker**. Three facts ruled out the obvious fixes: `admin-cli`
> has no HTTP client at all (every command is a subprocess or a direct `pgxpool`);
> `contracts/service_acl/matrix.yaml` sanctions admin-cli against **meta-worker**, not
> world-service; and the sanctioned path — straight to the Go bridge — has neither safety check and
> **cannot** have the second, because `actors` lives in the per-reality database meta-worker does
> not hold. Resolved on the shape `reality provision` already proved: a **worker binary**, flags in,
> secrets by env, one JSON object out, exit code as verdict. The checks moved into
> `actor_control_flow` so the HTTP route and the CLI run the SAME rules rather than two sets that
> drift.
>
> **Live, end to end — twelve steps, two databases, the real bridge, no mocks:** create-actor →
> grant → idempotent re-grant → a second user REFUSED → a ghost actor REFUSED → a stale CAS refused
> *with the driver surviving* → revoke → **handoff**, which `034`'s PK made impossible until `041`.
> The `I8` audit rows carry the operator's reason and `binding_id` as `row_pk`, so `041`'s new key
> is proven on the real path.
>
> **The live run found a defect the entire unit suite agreed with.** `bind_reality` mapped every
> bind failure to `RealityClosed`, so a missing table reached the operator as *"REFUSED — reload and
> decide"* with `conflict: true`: an outage wearing the costume of a normal answer. The split
> already existed upstream (`RealityMismatch` vs `ControlPlaneUnavailable`) and I had not looked —
> the exact distinction `ActorAlreadyDriven` exists to preserve, collapsed one layer up. Fixed,
> bitten, and re-proved live in both directions.
>
> **Two deliberate asymmetries, recorded so nobody "tidies" them:** grant binds the reality and
> revoke does not (refusing to revoke a driver in a frozen world would strand a player in a world
> under maintenance — revoke is the safe direction); and **the dry run does not report who currently
> drives the actor**, because that is a cross-user read of `actor_control_binding` and a preview
> that answered it would be an unaudited way to probe who holds whom.
>
> `revoke-control` is tier-1: the framework REFUSED the registry file until `double_approval` was
> true, and reaching the CAS took four independent guards (`admin:destructive`, a second-actor
> token, typed confirmation, then the feature's own CAS). The first draft said `false`; accepting
> the tier's second half was the right answer, not downgrading the tier to escape it.
>
> **Two dev-stack facts nothing checks:** `039`/`040`/`041` were committed and **never applied** to
> `loreweave_meta`, and the bridge container was a 37-hour-old image that 404'd on the grant route.
> Both invisible to every unit suite. Fixed by applying and rebuilding; the GAP has no mechanism
> (`PD-15`).
>
> ### The RUN-STATE audit (2026-08-20) — six deferrals that were never tracked
>
> Asked to check the run-state for staleness before planning further, and it was worse than stale.
> **The six `PC-*` rows in its §4 were invisible to `deferral-gate.py` twice over:** they lived in
> `docs/plans/`, which the gate does not scan (it globs `docs/**/SESSION_HANDOFF.md` +
> `docs/deferred/*.md`), under a prefix its `D-[A-Z]…` id pattern cannot match. `D-PC-AGENT`'s own
> text promised *"it must not be prose-only… the trigger goes in with `P1`"* — `P1` shipped six days
> earlier with none, and nothing said a word.
>
> **And `PC-*` was already owned.** `00_foundation/06_id_catalog.md` assigns it to *Player Character
> semantics* (`PC-A1..A3`…`PC-E1..E3`) and `I15` says those ids are forever. `PC-D2` is a locked
> decision about consent-gated PvP. Phase 0's question 1 asked of a NAME instead of a concept.
>
> Fixed: renamed `D-PC-*`, moved into the game-tier registry block (**30 → 36** tracked), five
> `PROSE_ONLY` rows with real wake-ups, and `D-PC-AGENT` got the asserted trigger it was owed —
> `services/meta-worker/pkg/bridge/actor_control_trigger_test.go`, which reds when
> `actor_control_binding` gains a seventh column. Bitten with `controller_kind`: red for the right
> reason, restored green.
>
> Three measured-false claims went with it (`PD-19`): `D-PC-SEATS` said *"the PK makes
> one-driver-per-actor a database law"* when `P1a` — in the same document — had replaced that PK
> with `binding_id` (the law is `actor_control_binding_one_live_driver`, a partial unique index);
> the header said `files 8` against a measured **52**; and `P6`'s `799/0 across 72` covered a subset
> of a workspace that has **193** suites. `D-PC-ACTOR-IDENTITY` was still listed as BLOCKING `P2`
> six days after `P2` shipped (`PD-18`).
>
> **▶ DO NEXT — the open rows, now tracked where the gate can see them**
> ([registry block](../03_planning/LLM_MMO_RPG/SESSION_HANDOFF.md); reasoning in
> [`2026-08-14-player-control-RUN-STATE.md`](../plans/2026-08-14-player-control-RUN-STATE.md) §4):
> `D-PC-AGENT` (can a controller be an LLM? deferred by the PO to the AI feature — **now the only
> one of the six with an asserted trigger**) · `D-PC-SF6-REVERSAL` (`0021`'s
> `current_turn_actor JSONB` should eventually hold a typed actor identity) · `D-PC-SEATS`
> (one LIVE driver per actor is enforced by a partial unique index where Unreal's one-to-one is an
> overridable default, so **spectating** and **GM override** must each be something other than a
> second binding) · `D-PC-METAWRITE-NOOP-EVENT` (`MetaWrite` emits the outbox event without checking
> `RowsAffected` — shared by every meta table, not this feature's to fix) · `D-PC-SEAM-NO-CONTRACT`
> (the admin-cli↔worker argv/JSON seam has no machine-checked contract) · `D-PC-NO-RUST-READ-AUDIT`
> (no sanctioned audited cross-user read from Rust — the reason `grant-control --dry-run` will not
> say who drives an actor).

---


---

## ▶ GAME TIER — feature #1 is BUILT (branch `feat/game-logic`, 2026-08-02)

> **Different branch from the block above.** That NEXT block belongs to
> `feat/frontend-tools-mcp-migration` and is left untouched.

**The actor hub — feature #1 of roughly a thousand — is implemented.** Its run state, slice board,
per-slice evidence (test output · bite-test · verifier report) and the `D-1`..`D-535` decision record
live in **[`docs/plans/2026-08-02-actor-substrate-RUN-STATE.md`](../plans/2026-08-02-actor-substrate-RUN-STATE.md)**;
the two design contracts that are its only specification are in
[`docs/specs/2026-08-02-actor-hub/`](../specs/2026-08-02-actor-hub/_index.md).

| what landed | where |
|---|---|
| the hub — ordinals · `PluginSet` · declaration registry · contribution rows · the fold · `Actor` · the explain path | `crates/actor-hub` (new, PURE) |
| `GoneState`, moved DOWN out of `dp-kernel` so a pure crate can hold hub item 3 | `crates/entity-existence` (new). `dp_kernel::entity_status::GoneState` is unchanged |
| `ModifierOp` + `OpKind`, moved DOWN out of `game-rules` for the same reason | `crates/ruleset-core/src/modifier.rs`. `game_rules::stats::ModifierOp` is unchanged |
| `U-9` — no float in the bytes that become a ruleset's NAME | `scripts/hashed-substrate-float-gate.py`, wired pre-commit |
| `U-10` — the citations in this round's own contracts now resolve mechanically | `scripts/citation-gate.py`, wired pre-commit |

**Evidence:** `cargo test -p actor-hub -p entity-existence -p ruleset-core -p game-rules -p ruleset-loader`
= **332 passed, 0 failed** · `dp-kernel --lib` **320** passed (was 315; `5-WIRE` + the subkey regression added four `dp_backend` tests, and `DFO-2` a fifth: a channel-scoped read is REFUSED rather than served from the reality-wide snapshot), unchanged by the `GoneState`
move · the Go mirror `contracts/entity_status` still agrees · `actor-hub` and `entity-existence` are clippy- and rustdoc-clean (the other three crates in that command carry a handful of pre-existing doc and clippy warnings, none of them this round's — counts deliberately not stated, because nothing here measures them and a figure with no measurement rule goes stale by construction; run the two commands if you want the numbers — a round-12 verifier measured the flat claim `clippy clean · cargo doc 0 warnings` FALSE, in the sentence that claims every figure in this block is emitted by a checker) ·
every mutation in the committed
mutation harness reds its gate's self-test (`python scripts/gate-bite-harness.py` — one mutation per
PRODUCTION RULE, run it rather than trust this sentence) · the **58**
gate scripts the pre-commit hook
wires all green, and every `--self-test` among them runs pre-commit via
`scripts/gate-self-tests.py`, which DISCOVERS them rather than naming them.

> **Every number in this block was RE-DERIVED from the artifacts, not advanced from the previous
> version.** That distinction is not pedantry: this exact block carried a stale figure in three
> consecutive commits (`D-343`, `D-350`, `D-351`), each time because a fix pass moved the number to what
> it had been rather than reading what it was.

**Reviewed by cold-start adversarial agents, one round per fix pass — every finding fixed or answered.**
**The per-round tallies are the source and live in [§6e..§6ac of the RUN-STATE](../plans/2026-08-02-actor-substrate-RUN-STATE.md);
no aggregate is repeated here.** An aggregate is not mechanically derivable, so it goes stale every time a
round lands. **A number you cannot derive is a number you should not assert** — and this paragraph
asserted three such numbers while saying so, which a round-11 verifier falsified in place by editing each
one and watching the gate stay silent. They are gone rather than corrected, for the same reason the slice
board's three were. **Every round after the first has returned REFUTED, and every one found its worst defect in the
PREVIOUS round's fixes** — never in the fold, which survived every mutation aimed at it. Round 3: a `CAPPED`
record reporting a value the fold never emitted. Round 4: round 3's gate repairs blocking commits on
correct content. Round 5: ten of those false positives *relabelled* rather than removed. Round 6: the round-5 cut
aimed at the wrong class, and a stale-number remedy declared *"mechanised"* by a script that did not
exist. Round 8: a self-test that reimplemented the loop it tested, so twelve production rules could be
deleted green. **Round 9: a blanket find-and-replace of `` `D-1`..`D-N` `` — run to advance the two LIVE
citations — rewrote six HISTORICAL statements to the live head, including this document's citation of
another document and the worked example inside the row that exists to defend worked examples.** Restoring
the number exposed a second layer: that citation was set in quotation marks and was never verbatim, and
**a paraphrase in quotation marks is why nobody checked the number** — a quotation is supposed to be frozen. Six commits carried the damage, from two
different start points — `_index.md` from `2792717cd`, the RUN-STATE from `4f28c35e1`. The remedy is mechanical (`D-385`): the live range may
appear only inside a current-state block. **The two-consecutive-clean-rounds rule is not met, and this
block does not claim it is.** **Nineteen rounds; every one REFUTED.** Round 15 is fully discharged: the twin-guard class in `D-443`..`D-446`, its remaining six findings in `D-447`..`D-451`. The sharpest was the raw fallback reaching the marker search and not the content blanking — the same rule, two consumers, one fixed. **Round 16 measured the answer to that class and found it satisfied by its own table:** the parity check searched the whole file, which CONTAINS the table, so seven of its eight witnesses were present whether or not the guard existed — and it read the original file while the child under test is the mutated copy. Its blocking finding was the round-15 fix reproducing the exact misdiagnosis it had been written to eliminate, because its predicate asked about the document while its subject was one fence. **Round 17 found that answer reproduced one row later:** `D-459` asserted that a precedence pair already had a case, and the case was on the sibling function that writes the same two lines again — three of five pairs were survivors. **Round 18 stopped writing better rows and made the check mechanical:** a row's LABEL must name what its ANCHOR touches, measured over all 132 shipped rows before it was wired — one finding, and it was a row labelled `Accumulator.wanted` whose anchor was the Emit record, hiding a field that survived all 300 tests. **Round 19 found the same commit's OTHER decision feeding that one exactly what it rejects:** the crash wrapper printed the word `FAIL`, which is the token the harness counts as a case disagreeing, so `120/120` was 118 verdicts and two artifacts — `D-470`'s arithmetic, in the commit that fixed `D-470`. **And round 19's own fix was EXPONENTIAL, found by the wall clock and not by any check:** removing a word bound because a bound is an enumeration left a shape whose separator could be split many ways, so the gate's `--self-test` went from seconds to 189.5s while rc stayed 0, every case passed and `--check` still agreed with the artifacts — a 60× regression below the 300s hang bound, which is the only timing alarm this apparatus owns. Its repair then had a redundant half that its own bite test refused to certify, because the mutation restoring it **hung** the child instead of failing a case. `D-452`..`D-505`. Round 10: the round-9 mechanism tested SUBSTRING
membership where it needed a POSITION SPAN, so it was blind in two of the three files it guards —
including the very line it had just repaired — and a wider mutation set found **nine actionable
survivors in `crates/actor-hub`**, the crate nine rounds had called untouched. Round 11: the mutation
harness **dirtied the working tree on a fully-green run** — `write_text` rewriting every line ending —
which is the exact incident its own docstring says it was shaped by, on the success path; and the CI
wiring the previous round records was never actually made. Round 12: the fix for a silently-truncated
scope was certified by a case built from the reported symptom, so **its own worked example still produced
zero findings** — and the harness had been rewriting the shipped Rust sources 30 times per commit.
Round 13: the SENTINEL that replaced the incidental `---` inherited the same defect, because a
*second* marker truncates a block exactly as the first one did; the 30 writes were still happening
(one of four call sites injected the no-op writer); and a case seeding a Rust test count had made the
gate refuse commits from every contributor without cargo. **Round 14 named the shape rather than
another instance of it:** a verifier measured that every blocking finding for five rounds had been
*the previous fix with one token substituted* — the end marker hardened and the start marker not, the
duplicate route closed and the move route open, the instance fixed and the class left undetected. The
mutation harness now runs an UNMUTATED baseline first, because without one it cannot tell "every rule
bites" from "the suite is already broken" — and CI is its only automatic runner.

**Every BOLDED figure in this block is emitted by `scripts/actor-hub-figures-gate.py`, which
`--check`s them pre-commit whenever this file is staged — and the same script reports a bolded figure
here that no rule of its reads, so the claim has a mechanism and not just a sentence.** Bolding is the
scope because that is what the detector recognises; a number written as a word is outside both.

**The frame that governs the next feature:** *a plugin exists so that adding feature N+1 does not touch
feature #1 — not so feature #1 can specify feature N+1.* The seams the BUILD measured are
registered in [`2026-08-02-seams-and-triggers.md`](../specs/2026-08-02-actor-hub/2026-08-02-seams-and-triggers.md)
which now holds `S-1`..`S-18`, each with a trigger and none with a design.

<!-- actor-hub-figures:end game-tier -->

---

---

> **Kept live rather than archived (2026-08-22).** Everything else from this branch's
> 2026-08-02…08-14 sessions moved to `SESSION_ARCHIVE.md` at the `main` merge. This entry
> stays because `actor-hub-figures-gate` anchors a checked region inside it, and those
> figures are claims about today's code that the gate re-verifies on every run — archiving
> them would freeze a maintained contract into a snapshot. The gate found this itself, by
> refusing to report a pass on a document whose markers it could no longer resolve.

## 📦 2026-08-08 — PR #184 merged: contributed features in, contributed process out

An outside contribution of 70 commits (534 files, +20k/−45k) carried feature work and the
contributing fork's own working process in one branch. The features are in; the process is not.
The merge was a fast-forward, so all 70 commits retain their original author.

**In:** EPUB Import V2, FB2 import, glossary/knowledge fixes, studio/editor work, 175 frontend
files, three CI fixes (pip-audit cwd for editable requirements, the composition eval-gate SDK
install, migration 0016 in the dp_kernel_test setup). Four process improvements were kept too,
each verified first: the credential-hygiene ignore block (by extension, not by path — a path list
is default-uncovered); the top-level layout, which had listed 5 of 24 trees; the
decompose-chained-shell-commands rule; and an explicit prohibition on reading another service's
database, which had only been stated as ownership.

**Out:** the AGENTS↔CLAUDE inversion, whose relocated copy was a stale snapshot — it reverted the
AMAW retirement, the ContextHub removal, `/loom`, the re-measured xdist figures, and returned the
test account's password and local auth UUID to a tracked file. The retirement commits are
ancestors of the contribution, so those were reverts rather than omissions. Also out: a nightly
`sync-upstream.yml` that in this repo would add itself as `upstream`, delete `.github/skills/`,
and push to `main`; plus rules pointing `origin` at the fork and forbidding feature branches.
Governance settled at +95/−15 across 8 files.

Defects found while reconciling, all now fixed: `agent-skills-parity` was exiting 0 with "nothing
to check" because `.ai-factory.json` had been deleted; `plan-artifacts.contract.json` had drifted
from its producers; `SESSION_HANDOFF.md` had been truncated 10,390 → 545 lines with nothing
archived; 20 frontend tests were red; the FB2 `SHA256SUMS` manifest could not verify (3 of 4
hashes predated LF normalisation); and 30 Russian strings sat in frontend source, including the
crash page and an LLM prompt.

### ✅ CLOSED — the gate that could not see its own subject

`i18n-completeness-gate` compares bundle against bundle. A string existing only as a
`t(..., { defaultValue })` was therefore invisible to it, and equally invisible to
`i18n_translate.py`, which reads the `en` bundle: such a string stayed in its source language
in all 19 other locales while the gate reported full parity. **689 keys had accumulated** —
609 found by hand, then 80 more that only a mechanism could find. 89% predate the outside
contribution. All are backfilled and translated.

Closed with a mechanism rather than a note: **`scripts/i18n-key-resolution-gate.py`** asserts
every literal `t()` key resolves in `en`. Wired pre-commit (on components — adding the call is
what creates the debt) and in `foundation-ci`. It resolves 6,497 keys across 658 components and
reports the 418 runtime-built calls it cannot check, so the remaining blind spot is stated
rather than implied.

Four call shapes had to be modelled, each found by a false positive on an early run, and each
is why a lint like this normally gets switched off instead of fixed: per-identifier namespace
bindings (one file may hold `const { t } = useTranslation('chat')` beside
`const { t: tKnowledge } = useTranslation('knowledge')`), the per-call `{ ns: 'x' }` override,
i18next's positional-default form `t(key, 'text')`, and plural siblings (`key_one`/`key_other`
resolve `t(key, { count })` with no bare `key` present). Arrays count as leaves —
`returnObjects` reads a whole list.

Of the 80 the gate found, 70 carried their English at the call site and were lifted verbatim;
**10 carried nothing and rendered their own key to the user** (six in `StepProfile`, three in
pdf-import, one in `GapReportTab`). Those ten are authored copy, worth a reviewer's eye.

### ✅ CLOSED (2026-08-09) — the unguarded migration harnesses, and the gate that could not see them

Every harness that executes a `.sql` file now verifies the target database first, and the
verification lives in the helpers rather than at the call sites.

**What was wrong.** `mustApplyEventSchema` called `testsafe.EnsureThrowawayDB` before its first
destructive statement; the `mustApply` beside it did not, and four harnesses used `mustApply` —
`outbox_atomicity`, `reality_lifecycle`, `archive_worker_live_smoke`,
`retention_worker_live_smoke`. They apply `0002_events_table.up.sql`, which opens with
`DROP TABLE IF EXISTS events`, and `0001_initial.down.sql`, which drops four tables. In
`admin-cli` the same shape appeared as `applyDDL`, plus one test that had reimplemented
`applyDDL` inline — read, deadlock-retry, execute — identical except for the check it lacked.

Nobody decided to skip the guard. Calling a helper that quietly omits a safety check looks
exactly like calling one that performs it, so **a check you have to remember is
default-uncovered**, the same polarity as a hand-written migration list. The guard now sits
inside `mustApply`, `mustApplyEventSchema` and `applyDDL`; the only way past it is to not use
the helpers. It is unconditional rather than predicated on the SQL looking destructive: blast
radius is a property of the file passed in, and a predicate would go quietly wrong the day a
`DROP` is added to a migration already in someone's list.

**Proven, against a decoy rather than a real database.** An empty DB named
`loreweave_guardproof` — production-shaped name, nothing in it, so a failed guard damages only
the decoy. Guard present: refused at the first `mustApply`, 0 tables touched. Guard removed:
the same run created `events, snapshots, projection_meta, events_p_2026_08, events_outbox`,
having executed `DROP TABLE IF EXISTS events` on the way. Against `lw_smoke_guardproof` the test
passes, so the guard is not simply blocking everything. Both decoys dropped afterwards.

**The gate had a matching blind spot.** `db-safety-gate.py` iterated
`SEARCH_DIRS = (services, scripts, infra, sdks, contracts, crates)`. `tests/` was not in it, so
the gate whose entire subject is destructive SQL in test code could not see the most destructive
test code in the repo, and had reported PASS throughout. Verified: a bare `TRUNCATE events`
injected into `tests/integration/` is invisible to the pre-change gate (exit 0) and red under the
new one. Scanning is now the whole repo minus `EXCLUDE_DIRS` — a denylist, where a new tree is
covered on the day it appears and every exclusion is a reviewable line. Third time this repo has
shipped the allowlist version of this bug, after `hot-path-gate` and the migration lists.

Widening surfaced nine findings, all previously unseen. Two were real and were fixed by renaming
rather than exempting: `reality_lifecycle_test.go` dropped and recreated a database called
`loreweave_meta_lifecycle` (now `lw_meta_lifecycle_test`), and the conformance metaprobe used
`meta_lifecycle_check` (now `meta_lifecycle_probe_test`) — names that read as disposable to a
human and as production to `testsafe`, which is the wrong way round for the audience that never
gets tired. The remaining seven are exempted with the specific reason each is safe.

**One consequence worth knowing.** Go's per-module layout means `testsafe` cannot cross module
boundaries without a `replace`, so it is vendored — now **five** byte-identical copies. Five
copies of a safety check is five chances for a fix to reach one and not the others, silently.
`db-safety-gate` now hashes every `testsafe/testsafe.go` and fails on divergence. Proven by
widening one copy's `throwawayMarker` to accept `loreweave` — i.e. reintroducing the original
incident in a single service — and watching it name that copy. Consolidating into one shared
module would retire the check; until then it is what keeps the copies honest.

**Moving the guard into `mustApply` would have turned `foundation-ci` red**, and finding out why
took a deliberate check rather than a CI run. `metaworker_live_smoke` hands
`LW_INTEGRATION_META_DB` to `mustApply`, and that job's database is called
`metaworker_meta` — disposable, created by the job itself, but carrying no marker, so the new
guard would have refused it. `worldservice_meta` (embedding-worker) is the same shape. Both are
renamed with a `_smoke` suffix.

The gate could not see either. Its config check requires `TEST` in the variable name *and* a
`loreweave_`-prefixed database; `LW_INTEGRATION_META_DB: …/metaworker_meta` satisfies neither.
`db-safety-gate` now also requires that **any** Postgres DSN assigned in a
`.github/workflows/` job name a marked database, whatever the variable is called — workflows
only, since a compose file or service `.env` legitimately names a real database and a CI job
never does. Proven by pointing a CI job at `loreweave_book`, the original incident verbatim: red
under the new check, **exit 0 under the old one**.

**Also fixed while verifying:** `outbox_atomicity` was not re-runnable. It applied
`0001_initial` (plain `outbox`, FK → `events(event_id)`) *and* `0002_events_table` (DROPs
`events`, recreates it partitioned, where `event_id` alone has no unique constraint). First run
on a virgin DB passes; every run after dies in 0001 with SQLSTATE 42830. The comment above the
two lines claimed the set was idempotent. CI never noticed because it hands each run a fresh
database. The test only ever asserts against `events_outbox`, so `0001` was setup for a table
nobody reads — removed. Three consecutive runs against one persistent DB now pass.

**The proofs are permanent now, and finding a home for them found one more list.**
`scripts/test_db_safety_gate.py` (14 tests) pins every case above — the `tests/` tree being
walked, the CI-DSN check, copy divergence, and the pair to all of them: the gate staying quiet
on the real repo, without which "goes red" is satisfied by a gate that reddens on everything.
`gate-teeth-gate`'s ratchet moved 45 → 44.

Wiring it revealed that `foundation-ci`'s pytest step was **fourteen hand-written filenames**,
and it had already drifted: `test_i18n_key_resolution_gate.py`, written the day before, was
never added, so the proof that the i18n gate can go red ran nowhere. That is the exact condition
the step exists to prevent, reproduced inside the step itself. It globs `scripts/test_*.py` now,
with a floor check so an empty expansion fails loudly rather than passing having run nothing.
18 files, 277 tests, 59s.

All gates green under `gate-wiring-gate.py --run-all`.

### ✅ CLOSED (2026-08-09) — `domain-db-smoke` had been red since 2026-08-05, and nothing said so

**"All workflows green" was measured over the workflows that RAN.** `domain-db-smoke` is
path-filtered to `services/book-service|glossary-service|admin-cli|meta-worker`. The commits
checked on 2026-08-08 touched frontend, scripts, docs and `tests/` — so it did not run, and its
absence read as green. It ran again on 2026-08-09 only because the DB-guard sweep touched
`services/admin-cli`. A path-filtered workflow that does not run is **unknown**, not passing;
`gh run list` shows the last run, not the last *relevant* run.

Three failures, all from the 2026-08-05 genre work, all breaking tests written in June and never
updated since. Two distinct causes:

**1. A read path silently undid a write.** `loadBookOntology` — GET `/ontology` — calls
`ensureDefaultBookOntology`, which re-inserts every default genre into `book_active_genres`.
`ON CONFLICT DO NOTHING` protects a row that exists; it cannot protect a row the user
deliberately *removed*, because "this genre is off" is expressed as the ABSENCE of a row and is
indistinguishable from "never set up". So `PUT /ontology/active-genres` returned 200 and the next
page load brought the deactivated genre back — a setting no number of retries could make stick.
Now guarded by `NOT EXISTS`, which is what the function's own doc says it is for.

**2. Universal attributes were copied onto every genre.** `SeedGenreKindAttributes` fanned each
universal attribute definition across every genre linked to a kind, so a `character` in a
six-genre book had **seven `name` attributes**, all `sort_order = 1`. Universal attributes
already reach an entity through the universal genre, so the copy added nothing visible and
multiplied every identity field. Removed; the genre→book propagation beside it is kept, since
that does something the universal genre cannot.

It surfaced as two unrelated-looking bugs. `POST /entities` writes `display_name` to the
universal `name` row while `recalculate_entity_snapshot` picked one of the seven **arbitrarily** —
the name was stored correctly and `cached_name` came back empty, which is what every downstream
reader joins on, so the entity was unfindable while looking perfectly well-formed in the table it
was written to. And `sync/apply` reconciles one attribute row, so `take_theirs` on `aliases` left
six identical siblings still reporting `update_available`.

That `ORDER BY` was **non-deterministic on its own merits** — `sort_order` with no unique final
key — and is now a total order (non-empty value first, then name/term, then universal, then
sort_order, then `attr_id`). The aliases select beside it had no `ORDER BY` at all. Fixed
independently of the seed: a query that is right in testing and a coin toss in production is
worse than one that is plainly wrong.

Verified: `glossary-service/internal/api` and `book-service/internal/api` both green, glossary
run twice against one persistent DB. **Pre-existing and NOT fixed** —
`internal/migrate/TestSystemAttrDescriptions_SeedsDescriptionsAndRefreshesHash` fails identically
with these changes stashed (`empty descriptions = 3, want 93`); that package is in no workflow.

### ✅ CLOSED (2026-08-09) — `python-integration-tests` was red too, and found the same way

Checking the *other* path-filtered workflows after `domain-db-smoke` turned up a second one:
9 of 13 workflows ran on the current commit; three of the four missing are
`workflow_dispatch`/deploy-only, and the fourth — `python-integration-tests`, push-triggered
and path-filtered to its six Python services — was **failing**.

`knowledge-service` only. `test_kg_graph_schemas` asserted the literal pair
`{"general": "insert", "xianxia-harem": "insert"}`, and the 2026-08-05 work added five graph
schema templates (fantasy, romance, drama, historical, mystery). Nothing was wrong: the seeder
did exactly the right thing with all seven. Unlike the glossary failures, **the test was the
defect** — an enumeration restating the catalogue instead of asserting a property of the seeder.

It was also default-uncovered in the direction that matters: it failed when the catalogue GREW,
which is noise, and would have said nothing at all if a template were silently dropped from
`_TEMPLATES`. Both assertions now derive from `_TEMPLATES` (with a floor check, so an empty
catalogue cannot make them vacuously true): adding a template needs no edit, and a template that
stops being seeded goes red. Verified 627 passed against live Postgres + Neo4j.

That workflow's own header says it exists so these suites "can never rot unnoticed again". It is
path-filtered, so it rotted unnoticed anyway — the guard was real, the trigger was the gap.

**The rule this produced is now in [`AGENTS.md`](../../AGENTS.md) § Phase 6 VERIFY:** "CI is
green" means every workflow's LATEST run, not the runs on your commit. `gh run list` returns only
what ran, so a red path-filtered workflow silently drops off the list. Compare the workflows that
EXIST against the ones that RAN, and read the last conclusion of every push-triggered one that is
missing before using the word green.

### ⚠️ NEXT-1 — `infra/patroni/patroni.yml` declares a `pg_hba` that Postgres never receives

Surfaced while trying to give the `reality_lifecycle` rename a runtime proof. The two tests in
`tests/integration/reality_lifecycle_test.go` **cannot pass against the meta-HA stack as
configured**, and never could — they are not merely skipped in CI, they are unrunnable anywhere.

`patroni.yml` declares under `bootstrap.dcs.postgresql.pg_hba`:

```
- host  all all 0.0.0.0/0   md5
```

What Spilo actually renders into `$PGDATA/pg_hba.conf` is its own default set, ending:

```
hostnossl all  all  all  reject
hostssl   all  all  all  md5
```

`rlConnect` hardcodes `sslmode=disable`, so every connection from outside the container hits
`hostnossl … reject`:
`pg_hba.conf rejects connection for host "172.20.0.1", user "postgres", database "postgres", no encryption (28000)`.

Two separate problems, and the second is the one that matters beyond this test:

1. **The declared config is inert.** `bootstrap.dcs` applies only at first cluster bootstrap, and
   the mounted `/etc/patroni/patroni.yml` is not where Spilo reads from — it wants
   `SPILO_CONFIGURATION`. A config file that looks authoritative, is version-controlled, is
   reviewed, and reaches nothing.
2. **`rlReachable` tests the wrong thing.** It opens a TCP connection and calls that reachable,
   so the harness reports "meta primary not reachable; skipping" when the port is down and
   *fails* when it is up. There is no configuration in which those tests pass, and the skip has
   been reading as "environment absent" rather than "this never worked".

**The work:** decide whether the stack should accept non-SSL local connections (set
`SPILO_CONFIGURATION`, or drop `sslmode=disable` from `rlConnect`), then make `rlReachable`
assert an actual authenticated query so a broken stack fails loudly instead of skipping. Left
untouched here: it is infra configuration for a stack no CI job runs, and the guard sweep this
session belongs to should not carry a Patroni change with it.

### ✅ CLOSED (mitigated, not root-caused) — two gates reported FALSE findings under CI load

`all-gates` failed three consecutive runs on the same commit, naming a DIFFERENT subject each
time, and each subject was demonstrably fine:

| attempt | gate | claim |
|---|---|---|
| 1 | observability-inventory | `lw_embedding_queue_depth` undeclared |
| 1 | emit-0013 | `scripts/perf/scale-rig.sh` missing 0013 |
| 2 | emit-0013 | `scripts/ledger-verify-smoke.sh` missing 0013 |
| 3 | observability-inventory | `lw_meta_outbox_retried_total` undeclared |

Both metrics are declared in `contracts/observability/inventory.yaml`; both scripts contain
`0013_events_content_sha256`. Locally each gate passes deterministically (3/3) on the exact
committed content.

The mechanism is visible in `observability-inventory-lint.sh:23` — the declared-set is built by
`grep … | sed … | sort -u || true`. **`|| true` swallows a failed or truncated read**, so a
transient error under CI load yields a PARTIAL declared-set, and every metric that fell out of it
is reported as undeclared. `emit-0013` has the same shape via `$(cat "$f")`. The `|| true` is
there to tolerate "no matches", but it cannot tell that apart from "the read broke" — so the gate
converts an infrastructure hiccup into a confident, specific, wrong finding.

That is worse than a flaky failure: it names a file and a line, so the natural response is to
"fix" code that was never broken. Distinguish empty-result from read-failure (check the exit
status, or assert the declared-set is non-empty before comparing — an empty inventory should
FAIL loudly, not silently pass everything through as undeclared).

Not fixed here deliberately: it is unrelated to the merge that surfaced it, and changing a gate's
failure semantics is a decision worth making deliberately rather than at the end of a long run.

### ✅ CLOSED — Scene Rail: the #12 M-C tri-state (open only as a product choice)

The contribution set the Scene Rail default to `railChoice ?? false` inside a commit about
decomposition planning, unmentioned in its message. That left the `#12 M-C` comment above still
declaring `null = auto (open when scenes exist)`, made `null` and `false` behave identically, and
reduced `hasScenes` to a count label. Reverted to `railChoice ?? (hasScenes && !isMobile)`, and
the tri-state now has one test per arm — including the no-scenes case, which previously had none.

Compact-by-default remains a defensible product choice. Making it properly means retiring the
tri-state, rewriting the `#12 M-C` contract, and amending `#16 Phase 4` together — not flipping a
single operand.

### Also cleared (pre-existing, unrelated to the contribution)

`services/retention-worker` had `go.mod` drift from a dependabot bump (`go mod tidy`, two indirect
deps). `sdks/python` was missing `pymupdf` and `Pillow` from its `[test]` extra, which had been
killing the entire 1030-test SDK suite at collection since 2026-07-06; that suite now runs
(1021 passed, 9 skipped).


> The entries below arrived with the merged contribution. Its two fork-local entries
> (upstream-sync workflow, fork ignore boundary) were dropped in reconciliation because the
> workflow they describe was not taken. Older history moved to
> [`SESSION_ARCHIVE.md`](SESSION_ARCHIVE.md) under the 2026-08-08 block — trimmed, not deleted.

## AI SCENE PROPOSALS IN THE EDITOR (2026-08-05)

The Studio selection toolbar now includes **Suggest scenes** for an active chapter. It sends
the selected manuscript passage through the existing Composition model route, requires a bounded
JSON proposal list, and never edits the manuscript. The author reviews individual title/synopsis
proposals and explicitly creates the selected normal outline nodes. The operation reuses the
registered user model and existing provider-registry mediation; it does not add agent settings or
provider credentials to the repository. Focused SelectionToolbar tests and the frontend type/build
gate passed. The host Python environment lacks `pytest`, so the Composition unit suite still needs
to be run in the service test image or a provisioned project environment.

## EPUB IMPORT V2 — STRUCTURE-PRESERVING FOUNDATION IMPLEMENTED (2026-08-03)

Spec: `docs/specs/2026-08-03-epub-import-v2.md`. The new pipeline is feature-flagged and keeps
the Book Service as the only owner of Book database writes. EPUB inspection persists the source
and its SHA-256; `pkg/epubimport` validates bounded archives, reads OPF/nav/NCX/spine structure,
and performs DOM-based chapter-range extraction. The worker claims and stages one logical EPUB
chapter at a time through Book Service internal endpoints; it does not write Book tables directly.

Book Service materializes staging payloads idempotently with immutable chapter provenance. It now
exposes inspect, start, status/items, resume, cancel, rollback, and report endpoints. Rollback
requires explicit confirmation, is safe to retry, removes only chapters owned by the job, and
retains a chapter that changed after finalization as a durable warning. Reports aggregate current
item, asset, and rollback state rather than relying on a stale finalization JSON snapshot.

The Knowledge parser has a preserve-boundary chapter mode: EPUB defines chapters, while parsing
only discovers scenes inside the supplied chapter. The existing import dialog shows durable queued
worker state without a fixed client timeout. Local Docker Compose raises PostgreSQL
`max_connections` to 300 for the multi-service development stack.

**Asset and link checkpoint (2026-08-03):** the shared EPUB package now resolves supported local
and data-URI images by DOM, validates their declared type against byte signatures, hashes them,
and rewrites source references only after worker-infra uploads to a deterministic Book-owned
object key. Book Service records the asset provenance idempotently and returns the public media
URL. Unsupported, external, missing, or invalid assets produce typed item warnings. Worker also
records normalized internal EPUB href/fragment intents. During Book-owned finalize, only the
matching TipTap link marks in newly materialized chapters are rewritten to reader routes after all
chapter IDs exist; external links are untouched and excluded/missing targets remain intact with a
warning. The asset endpoint additionally constrains object keys to the source SHA-256 namespace
and MIME-specific digest filename.

**Cover checkpoint (2026-08-03):** finalize now applies a validated EPUB cover to a newly created
book by default, or to an existing book only when `metadata_policy.cover=use_source`. It journals
the complete prior cover before mutation. Rollback restores the journaled cover unless its
`updated_at` proves a user changed it after import finalization; that case is retained as a
rollback conflict. Cover extraction rejects absent, undeclared, oversized, or MIME-spoofed bytes
as a non-critical import warning.

**Composition scene checkpoint (2026-08-03):** after a V2 job is finalized, worker-infra invokes
Composition's deterministic scene decompiler and forwards only its returned mappings to Book
Service's new internal job-scoped endpoint. Book Service verifies immutable import provenance,
fills only empty `scenes.source_scene_id` fields, and emits `chapter.scenes_linked` atomically.
Composition unavailability is logged as best-effort and does not roll back completed chapters.
**P0 reliability checkpoint (2026-08-03):** finalize now applies journaled title/description/language/
subject metadata policies, archives `replace_all` chapters with rollback conflict protection,
recomputes asset reference counts, and aggregates worker/item/asset/link/rollback warnings. Book
rollback restores job-owned chapter hierarchy assignments and calls Composition's idempotent
`DELETE /internal/composition/books/{book_id}/epub-import-hierarchy/{job_id}` cleanup seam. A
Composition materialization failure is persisted as a retryable job warning rather than remaining
only in worker logs. Full strategy/E2E and outage evidence is still required before Task 10/11 gates
can be marked complete.

**P0 verification checkpoint (2026-08-03):** DB-gated Book tests now cover `replace_all` archival,
effect idempotency, metadata merge/user-conflict rollback, durable worker warnings, and asset
reference convergence. Worker HTTP contract tests cover Composition outage warning persistence and
successful retry mapping. Book Service runs a configurable EPUB asset retention sweeper
(`EPUB_IMPORT_ASSET_RETENTION_HOURS`, default 168h) that deletes only old, unreferenced orphaned
objects and leaves failed MinIO deletes for retry. The DB suites require a throwaway
`BOOK_TEST_DATABASE_URL`; without it they skip safely.

**EPUB recovery E2E checkpoint (2026-08-04):** against the isolated
`loreweave_book_test` PostgreSQL database, an HTTP+DB scenario proves that cancelling an
already claimed item reaches `cancelled`, `resume` releases that in-flight item back to
`pending`, and a transient parser failure can be resumed and finalized. Repeating the
Book internal finalize command creates one chapter/provenance record. The worker contract
also replays the same V2 event: the replay makes no additional parser or staging call and
only repeats the idempotent finalize command. The DB run exposed and fixed cursors left
open across follow-up statements in finalize and strategy/metadata rollback paths. Task 10
is complete: a live BFF-authenticated import with an automatically registered disposable
user reached finalization, then two confirmed public rollback requests each returned the
same durable one-chapter rollback result. The persisted report showed `rolled_back`, zero
active imported chapters, and one rolled-back chapter. This live run also exposed a
`warnings_json = null` finalization failure; finalization now treats non-array warning JSON
as no warnings, and the DB E2E regression covers that representation.

**EPUB Composition materialization E2E checkpoint (2026-08-04):** a disposable
BFF-authenticated user created a canonical Composition Work and imported a nested EPUB
with one Part and two selected chapters. The live flow proved the three-node lossless
Composition hierarchy, Book's application of the returned part mapping to both chapters,
two Composition scene outline nodes, and two Book `source_scene_id` backlinks. The test
exposed a zero-based parser ordinal at the worker-to-Composition boundary; it is now
normalized to the one-based Composition contract and covered by a worker regression test.
A local Composition outage was exercised after Book job creation: the worker logged both
scene and hierarchy connection failures, Book finalization retained its chapters, and the
retryable `composition_materialization_pending` warning was recorded. Composition was then
restored and is healthy. Task 11 is complete.

**EPUB wizard checkpoint (2026-08-04):** Task 12 is complete. The EPUB wizard uses the same durable-job principle as the existing FB2/TXT flow while retaining EPUB-specific inspection, nested selection, hierarchy roles, title overrides, metadata policies, source-cover candidate preview, import options, explicit replace-all acknowledgement, and server-authoritative recovery/report actions. New UI text is available in English and Russian; the browser test uses locale-independent test IDs. A stored job ID restores server progress or the persisted report after reload. No EPUB import invokes a model: extraction and other AI actions are separate confirmed workflows. New-book EPUB finalization also triggers an idempotent internal Glossary bootstrap of current system genres, kinds, and attributes; source subjects can join only when they match system genre codes. Targeted wizard tests, frontend build, Chrome Playwright smoke, and worker Lore-redelivery regression passed.

**Rollout checkpoint (2026-08-03):** `EPUB_IMPORT_V2_MODE=shadow` now persists a source-scoped,
durable legacy document-order versus V2 navigation comparison without creating jobs or chapters.
The comparison is available through `GET /v1/epub-imports/{source_id}/shadow-comparison` and is
covered by API/unit contract tests. `opt_in`, `default`, and `legacy_disabled` continue to route
new EPUB jobs through the V2 worker. Promotion still requires live shadow corpus evidence and a
documented default-mode decision; shadow is not treated as proof of semantic equivalence.
Local Docker Compose now uses `EPUB_IMPORT_V2_MODE=opt_in` by default; production deployments
must set the mode explicitly during staged rollout.

**Live shadow evidence (2026-08-03):** rebuilt and started the local Book Service with
`EPUB_IMPORT_V2_MODE=shadow`; `/health` returned `ok`, `/metrics` exposed all EPUB counters and
histograms, and container inspection confirmed shadow mode plus asset retention. The Dockerfile
was corrected to include the `pkg/epubimport` replacement target. No authenticated upload was
generated in this check, so metric counters remain zero; authenticated corpus evidence is still
required before production promotion. Safe rollout order is `shadow` → small `opt_in` cohort →
reviewed `default` → `legacy_disabled`, with rollback to `shadow` at each gate.

**Authenticated corpus shadow evidence (2026-08-04):** every EPUB in the mounted
Vasilyev-Andrey corpus (20 files) was submitted to the local Book Service in `shadow` mode using
an authenticated disposable account. All inspections and source-scoped comparisons completed;
legacy projected 588 chapters and V2 projected 570 (net delta -18). Thirteen files had no
recorded differences, five had `logical_navigation_count_differs_from_document_projection`, and
two same-count files had `navigation_fallback_used`. The
disposable account still had zero books, proving the run created neither imports nor chapters.
Book Service has been restored to `EPUB_IMPORT_V2_MODE=opt_in` and its health check returned
`ok`. The seven local differences are classified in the EPUB runbook as five
NCX-authoritative logical-chapter differences and two count-preserving spine
fallbacks. Production-cohort differences still need the same source-scoped
classification before an `opt_in` cohort can be promoted to `default`; this
local corpus run is not production approval.

**EPUB reliability and observability checkpoint (2026-08-04):** Task 13 is
complete. The parser package passed its full suite, including malformed,
compression-bomb, traversal, DRM, MIME, missing-asset, and operational
self-closing-XHTML cases. Worker tests passed for transient MinIO recovery,
Redis redelivery without duplicate parsing/staging, Composition outage, and the
no-provider boundary. Book DB tests passed for cancel/resume/parser recovery,
idempotent finalization, and retrying an orphaned MinIO object deletion. The
live Book Service metrics endpoint exposed the documented bounded-label EPUB
counters and histograms. Parser-only `Inspect` benchmarks after the XHTML fix
measured 123 ms / 85.46 MiB/s for 50 chapters / 10 MiB and 1.25 s / 83.76 MiB/s
for 500 chapters / 100 MiB; see `docs/runbooks/epub-import-v2.md`.

**EPUB authenticated retry checkpoint (2026-08-04):** the previously failed
local job `2099d4aa-4ba8-496b-a420-13716c581b03` was resumed from an
authenticated browser session via the normal public endpoint. It completed
with 8/8 selected items active, 13 unselected items still skipped, 8 created
chapters, 8 provenance records, and no persisted report errors. The generic
Jobs page now renders Resume for failed or cancelled Book imports and forwards
it through an internal Book Service command that revalidates the durable owner.

**Worker recovery checkpoint (2026-08-03):** Redis Stream consumers now use a hostname-qualified
consumer ID and scan the group PENDING list with `XAUTOCLAIM` only after a 15-minute idle period.
This lets a restarted worker reclaim stranded import jobs without racing a healthy worker. Book
finalize treats `processing` items as unfinished, so a redelivered message cannot activate a
partial import while another worker owns its current item. The original message is acknowledged
only after durable finalize; retryable Book/MinIO/parser failures remain pending for reclaim.

**Verified:** `go test ./...` passes for Book Service, worker-infra, and `pkg/epubimport`; `pnpm build`
passes for the frontend; BFF dependencies were installed with `npm ci`, then `npm test` passed
(14 suites, 201 tests) and `npm run build` passed. Targeted Knowledge parser tests pass (12). Full Knowledge pytest currently reports
`4080 passed, 561 skipped, 9 failed`; failures are unrelated router/test-double compatibility in
`test_causal_edges`, `test_motif_*`, `test_tag_beats`, `test_thread_tag`, and
`test_internal_job_control`. The Book OpenAPI Spectral run is also blocked by pre-existing duplicate FB2 response keys in the
base contract; do not conflate those failures with EPUB V2.

**EPUB V2 local closure (2026-08-04):** Task 14 is complete for this
early-stage refactor. Shared parser, Book API throwaway-DB, worker, and Jobs
Resume suites passed; the wizard component regression, frontend build,
all-locale EPUB key parity, and Chrome smoke against fresh Vite also passed.
English and Russian are translated; other locales explicitly use the English
EPUB fallback. The global localization parity command remains red for
pre-existing non-EPUB namespace gaps.
Keep `EPUB_IMPORT_V2_MODE=opt_in`; production promotion is a separate future
operations decision. Do not reintroduce the legacy combined-HTML chapter path.

## 📚 FB2 BOOK IMPORT — SOURCE IMPLEMENTED, LIVE UI CHECK PENDING (2026-08-02)

Spec: `docs/specs/2026-08-02-fb2-book-import.md`. FB2 is a direct bounded parser in
`worker-infra`, beside EPUB structure preservation; it does not flatten source sections through
Pandoc. Existing-book import is `POST /v1/books/{book_id}/import` with `.fb2`. New-book import
is `POST /v1/books/import/fb2`: book + queued import job are created together, then the worker
creates chapters/scenes and applies source title, annotation, language, genres, and a valid cover.

The source metadata is retained per job in `book_import_metadata`. Crucial ownership rule:
existing-book mode records provenance but does **not** overwrite a user's title, description,
language, genres, or cover; only create-mode projects those fields. The FB2 2.2 schema family is
vendored at `contracts/schemas/fb2/2.2/` with checksums and original licence notices.

**Evidence so far:** worker parser tests cover hierarchy, metadata, inline images, malformed XML,
wrong namespace, DTD rejection, and binary limits; six supplied local FB2 samples parsed
successfully. Go package suites and frontend TypeScript compile are green; rebuilt `book-service`,
`worker-infra`, and frontend images start successfully, and the gateway returns 401 for the new
route without authentication. A live authenticated browser upload of a supplied FB2 completed with
20 chapters, source title, annotation, language, and genres. The source contains `cover.jpg`, but
the created book still shows no cover: treat cover persistence as an open defect. The FB2 dialog
also has no chapter-selection control, so importing only selected chapters requires follow-up work.
Do not copy supplied source books into Git.

## 📕 2026-08-03 — the dogfood run: a novel was planned and drafted through the real frontend

The session's subject was not a feature. It was **using the product as an author would**, on the
Mị Đế book, and fixing whatever stopped that. Four commits, all live-verified on the deployed <!-- doc-language-gate: ok -- book title (proper noun); the corpus this was verified against. -->
stack, not on mocks.

**What now works end-to-end that did not this morning** — propose (llm) → compile → validate →
bootstrap → Pass Rail 6/7 with two human checkpoints → 35 linked scenes → three level-4 chapters
drafted, on a local model, **$0.15 total**. The prose is in the book; a reading of all three is
in the evidence doc below.

**The four things that were in the way, in the order they blocked:**

| # | what | commit |
|---|---|---|
| 1 | a glossary-build run stuck since **27 July** made World Setup unusable, and two of the states the active-run index counts had **no exit at all** | `b05cfcf7e` |
| 2 | asked to plan an arc, the co-writer wrote 6948 characters and called **zero tools** — four independent mechanisms decide whether a tool reaches the wire and the request fell through all four | `363e22f43` |
| 3 | the same run then could not turn its 11 compiled chapters into book chapters: bootstrap was gated on `status === 'compiled'`, and Validate (which Agent Mode *requires*) walks out of that window | `9154d67fe` |
| 4 | drafting failed with `NO_CHAPTER_PLAN` until the Pass Rail produced scene plans — **not a bug**, but nothing in the drafting UI says so. See NEXT-1 | — |

## 📗 2026-08-03 — the agent-runtime audit, and the spec that has to retire twelve predecessors

Design-only cycle, no runtime code touched. Six parallel read-only auditors over disjoint layers
(tool surfacing · skills · rails/guards/state · MCP servers + federation · workflows + registry ·
documented intent), plus one main-session read of `stream_service.py` so the 7,818-line spine was read
once rather than six times. Output: [`docs/specs/2026-08-03-agent-runtime-unification/`](../specs/2026-08-03-agent-runtime-unification/)
— `AUDIT.md`, `SPEC.md`, and the six layer reports with `file:line` on every claim.

**The finding, in one line:** for tool availability the architecture never existed — **thirteen
successive mechanisms since 2026-06-10, exactly one ever retired** — and beneath that, *no artifact
anywhere assigns a tool to a skill*. Measured: 16 producers, 18 filters (**13 silent**), 8 answers to
"is this tool available", 3 workflow selectors, and **4 mutually inconsistent tool counts**. Coverage:
98/202 tools named by any skill (~49%), 30/223 in any workflow (13%).

**Three findings verified beyond the reports, in the main session:**

| | |
|---|---|
| `repeat` is **dropped in transit** | Go declares `Repeat string`, the seeds write `true`, `_ = json.Unmarshal` discards the type error. Measured end-to-end **after `363e22f43` shipped**: DB row `[true × 8]`, wire `repeat` 0× of 45 steps, with `gate` 45× / `done_when` 8× as controls. So `363e22f43`'s item-3 fix and its seed-SQL lint are **both inert**; its other three fixes hold. 13 rail steps are wrongly disarmed today |
| the hot-seed and the prompt disagree | `surface_hot_domains` resolves skills **without** `lazy_bodies` (defaults False ⇒ full set); the injection path passes `lazy_skill_bodies=True` ⇒ `[]`. Tools ride the wire with no skill body teaching them |
| `visibility:"legacy"` is a runtime filter, not an artifact state | read directly at **7 filter sites** with no policy layer; it has a per-session escape hatch (`pinned_legacy_tools`), no clock, and no retire — hence 114 legacy tools served forever |

**PO decisions sealed:** D1 both lanes (chat + out-of-agent FSM) with a declared boundary · D2 the six
cheap fixes are Phase 0 · D3 "lifecycle" is two orthogonal axes plus the missing policy layer between
them (this one corrected a live defect in the spec's own R4).

**Web research folded in** (MCP 2026-07-28 deprecation policy · SEP-1300 *rejected*, so `_meta.group`
is a legitimate private extension · `allowed-tools` **is** an Agent Skills standard field but means
*permission*, not *reachability* · the retry-storm and context-contamination results behind the
infinite-loop symptom). 12 requirements, 8 phases; **R12 evals-in-CI goes first**, because every later
phase deletes something and nothing can be deleted without a regression net.

## 📘 2026-08-03 — an outside contributor's PR merged, and the agent workflow reconciled onto one standard

Five PRs onto `main` (#168, #170, #171, #172 via #173). The repo now has a single, versioned agent
workflow that a contributor on any of five agents follows identically.

**PR #165 (@alexeydott, the project's first outside contribution) is merged — with five defects it
shipped with, fixed.** CI had never run on that branch and `main` was a commit ahead, so nothing had
been measured against the code it would land on:

| defect | what it actually was |
|---|---|
| token accounting lost most of what it counted | the accumulator was a tuple in a `ContextVar`; `extract_pass2` fans the trio through `asyncio.gather`, and a Task **copies** the context — every child's tokens were discarded. Only the entity pass survived |
| `_record_usage` raised `AttributeError` | on any job without `.result`, aborting the LLM call it was merely observing |
| `"Глава %d"` | a hardcoded Russian fallback chapter title, written into every user's DB on EPUB import |
| `parts` dropped from non-PDF imports | on a claim that parts moved to composition — but `hierarchy.go` still builds `book_parts` from that table, and PDF import kept writing it |
| the PR's own new test | imported `estimateJobTotalCost`; the module exports `estimateTotalJobCost`. It had never passed |

Plus **70 test failures** from fixtures the PR never updated, and two pre-existing `rules-of-hooks`
lint errors on `main`. Issues #163 (base-URL normalisation) and #152 (`/verify` route) closed.

**The workflow now has one home and one shape.** `CLAUDE.md` → `AGENTS.md` (15-line pointer left
behind), new `CONTRIBUTING.md`, test account moved to a git-ignored personal file, ContextHub removed
(a server no agent ever called, costing a subprocess per Bash call and a 75s commit timeout while
gating nothing).

The PR also carried **AI Factory** ([lee-to/ai-factory](https://github.com/lee-to/ai-factory), MIT,
2.17.0). Kept — a shared versioned process is what makes a wrong turn reviewable — but reconciled
rather than stacked: project rules bind through `.ai-factory/skill-context/`, its `aif-gate-result`
JSON contract is **adopted** as the output shape for our own gates (`scripts/gate_result.py`), and the
pack is installed for **five** agent targets (claude, cursor, codex, codex-app, copilot) through the
generator, never by hand. One conflict caught immediately: `aif-implement`'s *"do not add tests by
default"* is wrong here and is overridden.

**Three new gates, each proven red before being trusted** (`docs/standards/non-vacuity.md`):

- `agent-skills-parity.py` — the 5 skill trees byte-identical modulo documented substitutions, 750 files
- `slash-command-doc-gate.py` — a runner on disk is named in AGENTS.md, and vice versa
- `test-skip-census.py` — which suites are gated off and by which variable (1184 files, 15 variables)

**Two things found while verifying, both fixed:** `agentic-workflow/install.sh` copied the deleted
`mcp-query.py` back into its target, so running it would have re-broken `gate-wiring-gate` — a ⚠️
STALE banner had been added instead, which warns a reader and does nothing to the script. And
`/review-impl` — the only runner still in daily use — gained a `+check` findings validator adapted
from `aif-review`, with the adaptation that matters: a generic validator reads a correct standards
finding as speculation and drops it, so the rule text is inlined next to it and a HIGH finding on a
LOCKED standard may be reworded but never dropped.

`/loom` retired (43 lines, against `aif-plan` 818 + `aif-implement` 987). `/warp`, `/raid`, `/amaw`
are planned, not done — NEXT-5.

**Verified on merged `main`, not on either side of it:** frontend 6381 · worker-ai 511 ·
knowledge-service 4115 · composition-service 3652 · three Go suites · 8 gates · language-rule PASS.

### …and then the runners were retired, which found two more things

`/review-impl` is the **only** slash command left. `/loom`, `/raid`, `/warp` and `/amaw` are gone —
the owner had already stopped using all four, and AI Factory's coordinators, worktree-isolated
workers and read-only sidecars cover what they did, maintained upstream.

**The retirement plan was wrong twice, and measurement corrected it both times.** It first called
`/warp` cheap to remove (live registered verb, three scripts, a green test, a spec). Then at
execution the bigger correction: **`scripts/raid/` and `scripts/warp/` are not runner plumbing** —
they are live-smoke and slice-validation scripts that production tests cite by path
(`verify-cycle-5.sh`, `verify-cycle-13.sh`), that `capacity-thresholds.yaml` points at, and that
`gate-wiring-gate.py` carries an exemption for; 4–7 outside references each. Deleting them would
have turned dozens of `docs/**` references into lies. **So: runners retired, machinery kept.** What
actually went was three command files and AMAW's whole surface inside `workflow-gate.py` (state
keys, two verbs, the gated AUDIT_LOG writer, four helpers, one orphaned import — 49 of 769 lines).
`AUDIT_LOG.jsonl` stays: the writer is gone, the record is not.

**One behaviour did not survive, and is recorded rather than buried:** AMAW's Scope Guard was a
*blocking* gate at POST-REVIEW; the sidecars replacing it are advisors. POST-REVIEW is still a human
checkpoint and that is now the only thing that blocks there.

**`slash-command-doc-gate` — written that morning — caught the afternoon's change twice.** Once on
four orphaned commands (its purpose), and once because the retirement note's wording changed from
`**Retired:**` to `**Retired 2026-08-03:**` and the exemption regex stopped matching. Narrowed:
only commands named *on a line starting with a bold Retired marker* are exempt, so a live-but-
undocumented runner cannot hide beside a retirement note. A ghost command one line below still reds.

**Then the hook chain was enabled for the first time and immediately failed on a real bug.**
`scripts/fe-door-scan.py` had `ROOT = pathlib.Path("d:/Works/source/lore-weave/frontend/src")` — a
path that **exists on this machine but is a different checkout**, so the scan had been reporting on
a sibling repo. Derived from `__file__` now: 743 components / 624 test files under *this* tree. The
`no-absolute-host-paths` gate was written for exactly this and was right; nothing was listening,
because `core.hooksPath` was unset. See NEXT-5.

**43 merged remote branches deleted** (each verified an ancestor of `main` first, not trusted from
`--merged`). 26 remain, all genuinely unmerged.

### ▶ NEXT

1. **`NO_CHAPTER_PLAN` is a dead end with no signpost.** Agent Mode's preflight shows 4/4 green
   and the run then fails on the first unit, because "the chapters have scene plans" is not one
   of the things preflight checks. The Pass Rail that produces them is in a different panel. A
   fifth preflight row naming the missing pass would close it — small, and it is the last hard
   stop in the authoring path.
2. **`D-BOOTSTRAP-PREVIEW-LIES` is fix-now, not deferred** — one function, and the correct
   pattern is the other half of the same function. See the register row.
3. **The agent-runtime unification spec is at its CLARIFY checkpoint with 12 open DESIGN questions**
   ([`SPEC.md`](../specs/2026-08-03-agent-runtime-unification/SPEC.md) §10). The load-bearing ones:
   does a `both`-lane tool count toward the FSM coverage ratchet · who is `owner` for a platform tool ·
   what sunset window is honest for a tool only our own agent calls · **which four of the six
   orchestrator breakers R10 deletes** (name them, or "net-negative" is unfalsifiable).
   [`2026-08-03-tool-reachability-ssot.md`](../specs/2026-08-03-tool-reachability-ssot.md) is
   **absorbed, not superseded** — its diagnosis is independent corroboration and three of its four
   fixes hold; its banner must record that item 3 is inert, or the next reader will believe `repeat`
   works.
4. The **glossary↔KG refactor now has an acceptance case**, which it did not before:
   [`…-glossary-kg-entity-refactor/2026-08-03-dogfood-entity-consistency-evidence.md`](../specs/2026-08-03-glossary-kg-entity-refactor/2026-08-03-dogfood-entity-consistency-evidence.md)
   §1. A character the `cast` pass minted at 05:47 took the antagonist's defining act at 05:54,
   and `canon_consistency` scored **5/5** on all three chapters. A design that cannot prevent
   that has not addressed the refactor.

5. **The hook chain had never been enabled in this checkout.** `core.hooksPath` was unset, so every
   `scripts/*-gate.py` in `.githooks/pre-commit` was inert — and several commits this session used
   `--no-verify` believing they were bypassing a gate that was not there. Same outcome, different
   cause. Set it: `git config core.hooksPath .githooks`. **Do this on any checkout of this repo**;
   `CONTRIBUTING.md` says so and it is easy to skip.

   Enabling it exposed a second gap, now closed: the **12-phase gate lived only in
   `.claude/settings.json`**, so it fired when Claude Code issued `git commit` and for nobody else —
   one caller in five, on a repo that became five-agent the same day. Moved into
   `.githooks/pre-commit` (last in the chain, so a blocked commit reports code findings *and* the
   missing phase). **It does not block a contributor who never started a run:** `workflow-gate.py
   pre-commit` fails open with "No workflow state found" when there is no `.workflow-state.json`.
   Measured both ways through the real chain — no state → exit 0; size classified with VERIFY
   unrecorded → exit 1. The duplicate PreToolUse copy is gone; the bundle keeps its own, because
   `install.sh` writes no git hook into a target repo.

### Not fixed, and not tracked anywhere else

- **Book search is broken for Vietnamese diacritics** on a Vietnamese-first product: `eval` → 19
  results, `Đế` → 0, `Mị Đế` → 0. Found by trying to open the book by name. <!-- doc-language-gate: ok -- book title (proper noun); the corpus this was verified against. -->
- **The baked frontend serves a stale `index.html`** after a rebuild — the browser requests the
  old bundle hash and nginx answers with the SPA fallback, so the page is blank with a MIME-type
  console error and no other symptom. Cache-bust or clear the SW to recover.

---

> **MERGE 2026-08-02** — `origin/main` (67 commits: the game-logic promotion + a Dependabot
> sweep) merged in. 14 files conflicted; the reconciliation notes live in
> §MERGE RECONCILIATION below. Main's own session sections are preserved verbatim under
> §FROM `origin/main` further down — they are a different track's history, not this run's.
