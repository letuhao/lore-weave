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
| `E1` the owner-scoped route — "which actor does THIS user drive here" | `[ ]` | |
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

## §4 OPEN

| row | what | mechanism |
|---|---|---|

*(empty at open)*

## §5 DRIFT — append as it happens; an empty log is dishonest, not clean

| id | what |
|---|---|

*(empty at open)*

---

```goal-prompt
goal: a human drives the actor their binding names, with no LW_CHANNEL_ACTOR_MAP set anywhere
note: |
  Phase 0: the read is OWNER-SCOPED (WHERE reality_id AND user_ref_id), NOT the cross-user path RA1 built — none of that audit machinery applies. game-server has no Postgres client by design (I3), which is why the seam is HTTP. The PO chose the internal world-service route and explicitly refused "client asserts, server verifies" as the class P3 killed.
stop: |
  a bite does not go red, or goes red for the wrong reason
  the transport would gain a database client, or the client would name its own subject
```

**RESUME: `E1` — the owner-scoped route on world-service. `actor_control_flow` already binds the reality and reaches the per-reality registry; this needs the meta read keyed by `(reality_id, user_ref_id)` and an internal-gated handler over it.**
