# THE PLAYER-FACING EDGE — A HUMAN DRIVES WITHOUT AN OPERATOR — RUN-STATE

**Opened 2026-08-21** · branch `feat/game-logic` · opened at HEAD `26b60961e` · size **M**
(files ~9 · logic 6 · side-effects 3 — a new internal route, a new ACL edge, a retired env knob)

**Adopts** [`2026-08-08-reality-layer-RUN-STATE.md`](2026-08-08-reality-layer-RUN-STATE.md) §0.6d as
its execution contract, and §0.6's hazards.

**Reconciles:** Gateway invariant `I1` — game-server is the sanctioned second entry point
(`PRR-20`), and this adds an OUTBOUND internal call from it, which the ACL must name · Language
rule `I3` — TypeScript is gateway/realtime; the transport must not grow a Postgres client, and the
whole shape of this phase follows from that · User Boundaries & Tenancy — the read here is
**owner-scoped**, a different tier from `RA1`'s cross-user read · `SEALED-SUBJECT` — the client
still never names its own subject, and `E3` must not become a way to.

---

## §1 PHASE 0 — measured at HEAD

* **`ChannelRoom.actorForUser` reads `LW_CHANNEL_ACTOR_MAP`**, an env dev map of
  `user:entity` pairs. A real human cannot drive an actor unless an operator edits an environment
  variable and restarts the process. `D-ACTOR-BINDING-NOT-READ-BY-TRANSPORT`.
* **game-server ships NO Postgres client** — measured 0 matches for `pg`/`postgres`/`knex` in its
  manifest. That is correct (`I3`) and it is exactly why the row was deferred rather than fixed.
* **The read it needs is OWNER-SCOPED**, and this is the finding that shrinks the phase:
  `WHERE reality_id = $1 AND user_ref_id = $2 AND revoked_at IS NULL`, which is what
  `commit_service::subject` already runs. It is **not** `actor_binding_cross_user`, so none of
  `RA1`'s audit machinery applies. "Which actor do I drive" is a question about yourself.
* **`LOREWEAVE_INTERNAL_TOKEN` already appears in `ChannelRoom.ts` — for INBOUND dev auth**, not
  for outbound calls. So this phase genuinely introduces game-server's first internal HTTP client,
  and that is a thing to declare rather than to slip in.
* **game-server has no caller entry in `contracts/service_acl/matrix.yaml`** — it appears once, in
  a comment about security groups. The edge does not exist yet in either direction.

**The PO chose the seam** (2026-08-21): an internal, owner-scoped route on world-service. Not the
gateway — game-server IS a sanctioned entry point, so routing its own internal lookup back out
through the public edge buys a hop and an auth translation for no isolation. And explicitly **not**
"the client asserts an actor and the server verifies": that is the class `P3` killed, and it was
refused rather than left unmentioned.

---

## §2 BOUNDARY

**IN:** an owner-scoped "which actor do I drive here" route · the ACL edge that permits it ·
game-server reading it instead of the env map, failing CLOSED · the live proof that a human drives
the actor the binding names.

**OUT, each for a stated reason:**

* **Character SELECT** — choosing among several actors you drive. The binding permits one live
  driver per actor, not one actor per user, so a user *can* drive several; picking between them is
  a UI feature and this phase is the resolution underneath it.
* **Spectating and GM override** — `D-PC-SEATS`. A user who drives nobody already gets `self:
  null`, which is today's behaviour and stays; designing a real non-driving seat is that row's job.
* **The grant UI** — how a human comes to hold a binding at all. Today an operator grants it with
  `admin reality grant-control`; a self-service path is a product decision nobody has made.

---

## §3 BOARD

| slice | state | evidence |
|---|---|---|
| `E1` the owner-scoped route — "which actor does THIS user drive here" | `[x]` | `POST /internal/v1/actor-control/subject`. **7 bites, each watched RED for the right reason** (5 unit + the serde `self` rename + one LIVE). **Live smoke, read-only, 5/5**: driver → `entity_id 1`; the REVOKED user on the SAME actor → `self: null`; unregistered reality → 400; wrong token → 401. Suites `459 passed / 0 failed` (meta-rs 101 · world-service 220 · commit-service 138) |
| `E2` the ACL edge — game-server → world-service, declared | `[x]` | `world-service-rpcs.ResolveActorSubject`, `allowed_callers: [game-server]`, `principal_mode: requires_user`. **4 bites** — remove the caller, flip the mode, rename the RPC, widen the list — each RED for its own reason. `contracts/service_acl` go test green |
| `E3` the transport reads it, and FAILS CLOSED when it cannot | `[x]` | `ws/subject.ts` + `onJoin` now async. **Four answers, not two** — driving · nobody · realityClosed (`4004`) · unavailable (refuse the join). **6 bites**, each RED for the right reason; game-server `81 pass / 0 fail` (was 68). No new dependency: Node's global `fetch`. |
| `E4` ⏸ **POST-REVIEW checkpoint** — retire `LW_CHANNEL_ACTOR_MAP`, or keep it as a declared dev override? | `[x]` | **PO: DELETE IT ENTIRELY.** `actorFromDevMap` gone; `resolveSubject` has no branch left to get wrong. **2 bites** — reintroduce the map, reintroduce `?? '1'` — and the second reds THREE tests. game-server `82 pass / 0 fail` |
| `E5` live — a session drives the actor the binding names, with no env map set | `[x]` | **Two durable proofs, both bitten.** `world-actor-subject` registered in `contracts/testing/live-suites.yaml` — router-driven, two real databases, `1 passed`, **3 live bites** each RED through the runner. `scripts/smoke/player-edge-live.mjs` — the TRANSPORT's own resolver against a running world-service, **5/5**, driver → `entity_id 1`, revoked → nobody; bitten by swapping the two users (3 arms red, rc=1). `D-ACTOR-BINDING-NOT-READ-BY-TRANSPORT` **discharged**; registry 34 → 33 |
| `E6` suite + sweep green | `[ ]` | |

### `E4` — RULED 2026-08-21: **delete it entirely**

The PO took the strict option over the recommended one. What was presented: the map was already
demoted by `E3` (gated behind `LW_WS_DEV_ALLOW_STATIC=1`, warn-logged, never a fallback), and that
flag had come to gate two affordances. Three options — keep as-is, delete, or keep with a split
flag. **Deleted.**

The argument that wins: every option short of deletion leaves the second source *in the code*, one
edit away from being consulted. A gate is a decision someone can revisit; an absence is not. The
cost was accepted out loud rather than discovered later — **a local session now needs
`admin reality provision` → `create-actor` → `grant-control` before anything can be driven**, which
is a real tax on every local run including the PO's own.

The flag-overloading question dissolved with it: with no dev map, `LW_WS_DEV_ALLOW_STATIC` means
only what it always meant. One name, one concept, by subtraction.

**Deleting the code is a fact about today; the test is what makes it a fact about tomorrow.**
`E4 — the env map is GONE, and setting it changes nothing` sets `LW_CHANNEL_ACTOR_MAP` AND
`LW_CHANNEL_DEFAULT_ACTOR` to values that *would* bind if anything still read them, then asserts
nobody is bound. Reintroducing the map reds it; reintroducing `?? '1'` reds three tests.

### Why `E4` was a checkpoint

Retiring the env map is the difference between *"a developer sets one variable"* and *"a developer
must provision a reality, mint an actor and grant it"* before a local session can drive anything.
That is a real cost to every local run, and it is not mine to impose.

The argument for retiring: a fallback that silently answers when the real lookup fails is the
`?? '1'` default in a new costume — and that default is the exact bug this file's ancestor row was
opened about.

The argument for keeping: the map is explicit, per-user, and never lets the CLIENT choose — the
current comment says so and it is true. Kept as a DECLARED override with a loud log, it is a
different thing from a silent fallback.

**The one shape that is already refused:** trying the route and falling back to the map when it
fails. That is a silent fallback whichever way it is described, and it would make an outage look
like a dev convenience.

---

### `E1` — what the measurement changed, and the two things it found

**The shape came from a LINT, not from taste.** `meta-sensitive-read-bypass-lint.sh` forbids a bare
`SELECT … FROM actor_control_binding` under `services/`, `contracts/` and `crates/`, and excuses
files **by name**. `commit-service/src/subject.rs` sat on that list under a comment saying the quiet
part out loud: *"There is NO RUST-SIDE SANCTIONED READER… the only compliant Rust read is one that
does not happen."* Writing E1's query in world-service would have added a second name — `NV-3`'s
default-uncovered shape, where the list grows by one per service and the gate keeps printing PASS.

So hop 1 moved into **`meta-rs`**, the Meta Access Library, and BOTH services call it. `subject.rs`
no longer contains a SELECT, so its exclusion was **removed** rather than kept "just in case": an
exclusion for a file with nothing to exclude is a licence nobody is using, waiting for someone to.
The list now names one **library** where it named one **caller per service** — and what guards the
library is `OWNER_SCOPED_SQL`'s test, asserting each predicate on the executed string, bitten.

**`D-PC-NO-RUST-READ-AUDIT` is what made this possible, and it is worth noting it paid off in the
opposite direction from the one expected.** That row was closed by building the CROSS-USER audited
read. Its real dividend was here: the discipline gap it documented is what identified where this
query belonged.

**Finding 2 — `--entity-id -1` was creatable, and permanently unusable.** `0022` put no `CHECK` on
`actors.entity_id` because the identity sequence allocates positives — but `GENERATED BY DEFAULT`
exists so an explicit value CAN be supplied, and `adopt_actor` passed an operator's `--entity-id`
straight through. `commit_service::subject` refuses a negative at turn time with `NotAnEntityId`,
correctly, because `-1 as u64` is `u64::MAX`. **A character that could be created, granted, and
never act, with nothing on the path saying so.** Now refused at the write edge AND the read edge,
from one function (`actor_registry::checked_island_id`) so the two cannot half-change.

**Sealed decisions**

| id | decision |
|---|---|
| `ED-1` | **A driver in a FROZEN reality gets `RealityClosed` (400), not their entity id.** Not a preference — hop 2 reads the per-reality database, which needs a `dp::RealityId`, which has no public constructor. The alternative was a bypass constructor, and the guarantee *"holding one means the control plane approved this"* is worth more than a nicer answer during maintenance. A `null` there would also be a lie. |
| `ED-2` | **The order is: registered? → binding? → bind.** A spectator costs one meta read and never opens a second pool, and an unregistered reality is a **400 before anything else** — because answering *"you drive nobody"* about a world that does not exist is the exact bug the revoke path shipped once. Same shape, caught before it could ship twice. |
| `ED-3` | **A dangling binding is a 400, never `self: null`.** A live binding naming an actor the registry lost is `S-9`'s dangling pointer; rendering it as spectating would demote a player silently and page nobody. |
| `ED-4` | **`actor_id` rides in the response beside `entity_id`.** It is the caller's OWN binding, so neither field is a cross-user disclosure, and it is the durable id an operator greps when someone reports the wrong character — a question that would otherwise need the CROSS-USER read, which is the audited, expensive one. |

### `E3` — four answers, and the one shape that stays refused

**The transport asks now.** `subjectResolverFromEnv()` → `POST /internal/v1/actor-control/subject`,
over Node's global `fetch` (no new dependency, and no Postgres client — `I3` holds).

**The refused shape is "try the route, fall back to the env map".** That is a silent fallback however
it is described: it makes an outage look like a dev convenience, and it is the `?? '1'` default this
function's ancestor was opened about wearing a new costume. So the source is chosen ONCE, at startup,
by configuration — never by which one happened to answer.

**Unconfigured is not permission.** With no `LW_WORLD_SERVICE_URL` the room serves no subject at all
unless `LW_WS_DEV_ALLOW_STATIC=1`. That is the rule `onAuth` already applies to the ticket store six
lines away, in the same file, for the same reason.

**Four answers, because collapsing them is the recurring bug on this seam.** *"You drive nobody"*,
*"this world is closed"* and *"we could not ask"* are three different facts and only the first is
normal. An outage reported as `nobody` would silently demote every player to a spectator with
nothing in the log — the same mistake `classify_bind_failure` prevents one tier down. `realityClosed`
refuses the join with **`4004 CloseRealityArchived`**, which is already in the `§12AB.9` set and
means exactly this; `unavailable` refuses the join *without* a close code, because none of the ten
means "the control plane did not answer" and the contract forbids inventing one.

**A decision worth E4's attention:** `LW_WS_DEV_ALLOW_STATIC` now gates two affordances, which is
normally the overloading `settings-and-config` warns about. Coupled on purpose — dev auth mints
`dev:abcd`, which is not a `user_ref_id`, so the real route *cannot* resolve a dev-authenticated
session and the map is the only thing that can. Splitting them would permit real auth with a dev
binding. **This is the checkpoint's to confirm or reverse.**

## §4 OPEN

| row | what | mechanism |
|---|---|---|
| ~~`EO-2`~~ | **CLEARED at `E5`.** `world-actor-subject` is in the live-suite registry, so the route runs under the registry-driven CI leg like every other suite, and three bites prove it can go red there. The transport half is `scripts/smoke/player-edge-live.mjs`, which is a script rather than a registered suite because the registry is cargo-shaped — same position as `D-EPOCH-SMOKE-NOT-IN-CI` and its two siblings, and it waits on the same stack-up CI job they do. Original text: **`E1`'s live proof is not repeatable.** The 5-arm smoke ran from a scratchpad script against data `P7` left in the dev stack; `live-suite-registry-gate` reports 22 registered suites and the actor-control routes are none of them. The route is therefore covered by unit tests and by one run nobody can re-do. | `E5` owns it: it needs a durable live test anyway, and a route-level suite is the same fixture. If `E5` lands without registering one, this row is the thing that says so. |
| `EO-1` | `actors.entity_id` has **no `CHECK (entity_id >= 0)`**. `checked_island_id` closes it at both code edges, but the column stays permissive, so a future writer that skips the helper is unguarded. Not fixed here because `0022` is applied **per reality at provision time**, so a new migration only reaches worlds provisioned after it — this needs the migrate-existing-realities path, not a new file. | `checked_island_id`'s test is the code-side guard (bitten). The column-side row is declared here rather than left as a comment. |

## §5 DRIFT — append as it happens; an empty log is dishonest, not clean

| id | what |
|---|---|
| `ED-D1` | **Two bite anchors matched nothing, and the run reported them as aborts only because the harness counts occurrences.** The files are CRLF; my anchors used `\n`. Without the `count(anchor) != 1` assertion this would have been two mutations that silently did not happen, each followed by a green run — indistinguishable from a passing bite. Same family as `PD-4` (heredoc backslash mangling): **the encoding of the file is part of the anchor.** |
| `ED-D2` | **B3's first mutant did not COMPILE, and it still went red.** `ProblemDetails::bad_request("bite".into())` is ambiguous across four `From<&str>` impls. `rc != 0` plus a "RED" label looked exactly like a bite; only reading the output showed `error[E0283]`. A broken build is not evidence about a guard. The harness now fails any mutant whose output contains `could not compile` or `error[E0` — because the summary line is identical either way, and I would not have caught the second one. |
| `ED-D7` | **The live suite passed before it could run, and the number said `1 passed`.** `cargo test --test actor_subject_live` with no env prints exactly what a real pass prints — the skip is a `return Ok(())`. I nearly took that as `E5` done. Registering it and running it through `live-suites.py` turned the same test RED three times in a row (a `db_host` CHECK, then a relative allowlist path, then nothing) before it was actually green. **The gap between "the test compiles and returns Ok" and "the test ran" is invisible in the output**, which is why the three live bites exist and not just the run. |
| `ED-D8` | **`meta_allowlist` defaults to a RELATIVE path, so the bind works from a shell and 500s from `cargo test`.** `cargo` runs from the package directory, the binary runs from the repo root, and the failure surfaces as a generic `500 actor-control write failed` because `to_problem`'s wildcard arm hides the detail. Two things worth keeping: the test now derives the path from `CARGO_MANIFEST_DIR`, and **the generic 500 cost more time than the bug did** — the wildcard is correct for a client-facing body, but it means an operator debugging this gets nothing without server logs. |
| `ED-D9` | **The live smoke printed PASS and exited 127.** Node aborted on Windows with `Assertion failed: !(handle->flags & UV_HANDLE_CLOSING)` inside `process.exit()`, after every arm had passed — `fetch`'s keep-alive pool torn down mid-close. Fail-safe rather than fail-open, so it would have shown as a false RED, but an exit code that does not mean what it says is a smoke nobody can put in CI. Fixed with `process.exitCode` and letting the loop drain. **I caught it only because I echoed `$?` instead of reading the PASS line** — the same discipline that caught a wrapper's exit code standing in for the harness's last run. |
| `ED-D4` | **I deleted a deferral's only mechanism while editing a test, and the gate caught it in seconds.** `D-ACTOR-BINDING-NOT-READ-BY-TRANSPORT`'s mechanism was an assertion MESSAGE in `ChannelRoom.test.ts` naming the id; rewriting that test for `E3` removed the sentence, and `deferral-gate.py` immediately reported *"deferral(s) with NO mechanism and no declared reason"*. Worth logging as a gate WORKING rather than as a defect — but the near-miss is real: had the mechanism been a comment instead of a string literal, the stripper would have ignored it either way and I would have learned nothing. |
| `ED-D5` | **I nearly closed that row here, on stubbed `fetch`.** The transport reads the binding now, so the row's literal text is false — the tempting move is to strike it. But every test of that path stubs `fetch`, and a read that has never reached a real service is exactly the state `meta_read_audit` was in for four months: four layers, each correct-looking, empty table underneath. The row stays open until `E5` runs it live. **The rule this cost me: a row closes on the evidence its subject demands, not on the evidence I happen to have.** |
| `ED-D6` | **Two of six `E3` bites did not bite on the first attempt, and only one was a bad mutation.** `D2`'s mutant left a variable unused and failed to TYPECHECK — the harness's compile check (added after `ED-D2`) caught it, which is the second time that guard has paid for itself in one run. `D4` genuinely reddened the right test but on a *different assertion* than I predicted, because the strong claim (`no request was made`) sat after the weak one. Fixed by reordering the test, not the expectation: **an unpredicted red is not a verified one**, and the reorder makes the test state its own priority. |
| `ED-D3` | **I nearly took a green `commit-service` suite as proof the hop-1 repoint worked.** `subject_live` skips loudly when its two DSNs are absent, and in a plain `cargo test -p commit-service` it contributes `0 passed` — a line that scrolls past looking like every other empty bin. The repoint is on exactly that test's path. Running it through `live-suites.py` and then BITING it (drop `revoked_at IS NULL` → the live arm fails) is what turned "the suite is green" into "the query I wrote is the one Postgres executes". |

---

```goal-prompt
goal: a human drives the actor their binding names, with no LW_CHANNEL_ACTOR_MAP set anywhere
note: |
  Phase 0: the read is OWNER-SCOPED (WHERE reality_id AND user_ref_id), NOT the cross-user path RA1 built — none of that audit machinery applies. game-server has no Postgres client by design (I3), which is why the seam is HTTP. The PO chose the internal world-service route and explicitly refused "client asserts, server verifies" as the class P3 killed.
stop: |
  a bite does not go red, or goes red for the wrong reason
  the transport would gain a database client, or the client would name its own subject
```

### `E2` — the row, and why it needed a test to exist at all

**Nothing in this repo loads `matrix.yaml` and asks it a question about a new edge.** The
`service-acl-matrix-lint` requires an entry only for services that WRITE META — game-server writes
none, so the lint would never have asked for this row, and once written it would never have checked
it. A YAML row that no code reads is prose with a schema.

What makes it load-bearing is `TestCheckedInMatrix_AllowsGameServerToResolveASubject`, which loads
the shipped file and puts the real `CheckRPCAllowed` to it — following the precedent of
`TestLoadMatrix_FromCheckedInMatrixYAML`, which already does this for `publisher → MetaWrite`. Four
mutations, four reds: delete the caller, flip the mode, rename the RPC, widen the list.

`requires_user` is not decoration. `RpcRule::check_principal_allowed` turns `system_only` into
`DenyPrincipalMismatch` the moment a call carries a user — and every real call to this RPC carries
one, because *"which actor does THIS user drive"* has no meaning without a user. The handler agrees
by construction: `SubjectRequest.user_ref_id` is a `Uuid`, not an `Option<Uuid>`.

**The writers are absent on purpose, and the test asserts their absence.** game-server may ask who a
user drives; it may not decide it. `GrantActorControl`, `RevokeActorControl` and `CreateActor` each
have an arm proving game-server cannot reach them, so adding one later is an argument someone has to
make in a test rather than a line someone can append to a list.

### `E5` — why the row did not close at `E3`

The transport read the binding as of `E3`, so the row's literal text was already false. Closing it
there would have been closing it on **ten unit tests that all stub `globalThis.fetch`** — the right
way to test the room's branching, and worth nothing as evidence that the HTTP call works. A wrong
path, a wrong header name, a wrong request shape or a mis-read response all pass a stubbed test and
fail on the wire. That is the state `meta_read_audit` was in for four months.

So `E5` built two proofs that can be re-run by someone else:

* **`world-actor-subject`** in `contracts/testing/live-suites.yaml` — driven through the ROUTER, so
  the handler, the token gate, the status codes and the `self` wire key are all inside it. Two real
  databases in two tiers, and `dp::RealityId` minted through the real `MetaControlPlane`. Three
  bites, each RED through the runner: drop `revoked_at IS NULL`, stub hop 2's conversion, skip the
  registration check.
* **`scripts/smoke/player-edge-live.mjs`** — the transport's OWN `HttpSubjectResolver` against a
  running world-service. This is the only place the two sides meet. Bitten by swapping the driver
  and the revoked user, which reds three arms and exits 1 — and incidentally proves the fixture's
  two users are distinguished by the SERVER rather than by the assertions.

**The row's first proposal was wrong and the PO said so at the time**, and both turned out to be
true of different things. `SEALED-SUBJECT` moved the AUTHORITATIVE resolution into commit-service: a
proposal carries the user, the server resolves the actor, and a subject the caller cannot assert
cannot be forged. What this phase added is a **display** read — which entity to render as *"you"* —
and that is a different question from who may act. The client still never names its own subject.

**RESUME: `E6` — the full sweep. Every suite plus `gate-wiring-gate --run-all`, and the number goes in the board row rather than a claim that it was green.**
