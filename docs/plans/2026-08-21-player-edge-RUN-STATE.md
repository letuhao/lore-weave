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
| `E2` the ACL edge — game-server → world-service, declared | `[ ]` | |
| `E3` the transport reads it, and FAILS CLOSED when it cannot | `[ ]` | |
| `E4` ⏸ **POST-REVIEW checkpoint** — retire `LW_CHANNEL_ACTOR_MAP`, or keep it as a declared dev override? | `[ ]` | |
| `E5` live — a session drives the actor the binding names, with no env map set | `[ ]` | |
| `E6` suite + sweep green | `[ ]` | |

### Why `E4` is a checkpoint

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

## §4 OPEN

| row | what | mechanism |
|---|---|---|
| `EO-1` | `actors.entity_id` has **no `CHECK (entity_id >= 0)`**. `checked_island_id` closes it at both code edges, but the column stays permissive, so a future writer that skips the helper is unguarded. Not fixed here because `0022` is applied **per reality at provision time**, so a new migration only reaches worlds provisioned after it — this needs the migrate-existing-realities path, not a new file. | `checked_island_id`'s test is the code-side guard (bitten). The column-side row is declared here rather than left as a comment. |

## §5 DRIFT — append as it happens; an empty log is dishonest, not clean

| id | what |
|---|---|
| `ED-D1` | **Two bite anchors matched nothing, and the run reported them as aborts only because the harness counts occurrences.** The files are CRLF; my anchors used `\n`. Without the `count(anchor) != 1` assertion this would have been two mutations that silently did not happen, each followed by a green run — indistinguishable from a passing bite. Same family as `PD-4` (heredoc backslash mangling): **the encoding of the file is part of the anchor.** |
| `ED-D2` | **B3's first mutant did not COMPILE, and it still went red.** `ProblemDetails::bad_request("bite".into())` is ambiguous across four `From<&str>` impls. `rc != 0` plus a "RED" label looked exactly like a bite; only reading the output showed `error[E0283]`. A broken build is not evidence about a guard. The harness now fails any mutant whose output contains `could not compile` or `error[E0` — because the summary line is identical either way, and I would not have caught the second one. |
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

**RESUME: `E2` — the ACL edge. `contracts/service_acl/matrix.yaml` has no game-server CALLER entry at all (Phase 0 measured one mention, in a comment about security groups), so this declares the first outbound edge from a service that until now only received. The route it names exists and is live-proven: `POST /internal/v1/actor-control/subject`.**
