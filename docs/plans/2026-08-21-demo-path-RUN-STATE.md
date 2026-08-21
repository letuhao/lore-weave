# THE DEMO PATH — kernel data reaches a browser, or it does not — RUN-STATE

**Opened 2026-08-21** · branch `feat/game-logic` · opened at HEAD `6331c873d` · size **M**
(files ~6 · logic 4 · side-effects 3 — a dev-auth identity, a compose service, a mounted view)

**Adopts** [`2026-08-21-player-edge-RUN-STATE.md`](2026-08-21-player-edge-RUN-STATE.md)'s execution
contract: every row bites, evidence is pasted, a row that cannot be proven stays open.

**Reconciles:** Gateway invariant (I1), Settings & Configuration Boundary, User Boundaries &
Tenancy — game-server stays the sanctioned second entry point (`PRR-20`) and gains no new public
surface; the one new knob is a deploy-time DEV switch with **no default**, never a per-user setting,
so it is env config by the boundary's own test; and the identity it carries is a `user_ref_id`, the
same scope key the binding is keyed by, so no tier changes.

Two sealed decisions govern this work and are NOT rows in the standards index — stated here rather
than cited, because a `Reconciles:` entry pointing at nothing is the phantom-registration shape the
gate exists to catch. **`SEALED-SUBJECT`**: nothing here lets a client name its own subject; the dev
identity is chosen by the SERVER's environment, exactly as the ticket path takes it from a redeemed
ticket. **`E4`'s ruling**: the binding stays the ONE source of who drives what — this adds an
*identity*, never a binding.

---

## §1 PHASE 0 — measured at HEAD `6331c873d`

* **`ChannelPanel` is mounted NOWHERE.** `grep ChannelPanel frontend-game/` outside its own file
  returns zero hits. It is not a stub — it renders the roster, the turn number, `you are entity N`,
  and Strike/Defend/Flee. Its store and client are tested (`channel-client.test.ts`, 6 tests); the
  VIEW has never been rendered by anything, route or test.
* **`fc2ba5f8a` claimed a full live run** — *"JOINED → W0 → W1 folded from the real committed log
  (self 1, turn 1, roster entity-2 hostile healthy) → SUBMITTED → ACCEPTED → channel_event_id 12
  turn.resolved"*. That was the CLIENT and the room. The panel shipped in the same commit and was
  never wired to a route, so the proof and the unreachable code arrived together.
* **The FE's only identity is not a user.** No `LW_WS_REDIS_URL` ⇒ `ticketRedeemerFromEnv()` returns
  null ⇒ the dev static branch returns ``userId = `dev:${jwt.slice(0,4)}` ``. After `E3` that fails
  `isUserRefId` and the join is REFUSED. **The demo path is structurally dead**, and nothing said so
  because the panel was unmounted — had it been wired, `E4` would have broken it visibly.
* **world-service is NOT in `infra/docker-compose.yml`** — `grep '^  world-service:'` returns
  nothing. Both of the player-edge phase's live proofs started it from source.
* **The dev stack already holds the data.** Reality `cd0747d2-4b94-4f68-9efb-93fef6359306` is
  `active`; actor `9ca0c9c8-a48f-4fce-9029-a574be662c2d` → `entity_id 1`; `bbbb1111-…` holds the
  live binding and `aaaa1111-…` a revoked one. Nothing needs provisioning to demo this.
* **`actor-hub` HAS a first consumer** — `commit-service/src/domain/actor.rs` holds an
  `actor_hub::Actor`, and `dataflow_live.rs` walks *action → hub → DP write → events row → wire
  frame* with ids pasted. Its header states the boundary honestly: *"The TypeScript client is not
  driven."* This board is that last hop and nothing else.

---

## §2 BOUNDARY

**IN:** a dev identity that is a real `user_ref_id` · world-service reachable from the compose
stack · the panel mounted · a browser showing the entity the binding names.

**OUT, each for a stated reason:**

* **Real auth end-to-end** (gateway issues a ticket, Redis stores it, game-server redeems it). The
  ticket path already EXISTS and is tested; what is missing is the gateway route that mints one for
  a logged-in user, which is a different service and a different phase.
* **Making the turn RESOLVE.** `fc2ba5f8a` needed the spine running to get `turn.resolved`, and the
  spine binary hangs (`DFO-7`, measured at HEAD and independent of this work). Joining and seeing
  the right `self` is this board's claim; a resolved turn is not.
* **`frontend/` (:5174).** A different app for a different product. This is `frontend-game` (:5176).

---

## §3 BOARD

| slice | state | evidence |
|---|---|---|
| `F1` a dev identity that can BE a subject — `LW_WS_DEV_USER_REF_ID`, UUID-validated, no default | `[x]` | `onAuth` no longer fabricates. **2 bites**: give the var a default (reds the fail-closed arm), let a join option override it (reds the client-cannot-choose arm). game-server **84 pass / 0 fail** |
| `F2` world-service in compose, and game-server pointed at it | `[x]` | New `services/world-service/Dockerfile` (the image carries `contracts/`, because two config defaults are CWD-relative — the `E5` lesson as a packaging requirement). Compose service + healthcheck + `:7120`; game-server gains `LW_WORLD_SERVICE_URL`, `LW_CHANNEL_*`, and the no-default dev identity. `docker compose --profile game config` rc=0 |
| `F3` the panel is MOUNTED, and a test keeps it mounted | `[x]` | Mounted in `routes/play.tsx` beside `EchoPanel`. `channel-panel-reachable.test.ts` — 3/3, **bitten** by unmounting it (the state HEAD was in until today). Its reach arm fired for real on the first run and caught two path bugs |
| `F4` live — a browser shows the entity the binding names | `[ ]` | |
| `F5` suite + sweep green | `[ ]` | |

### Why `F1` is a narrowing, not a loosening

Today the dev branch **invents** an identity from the first four characters of a shared token, and
every session on a box shares it. `F1` replaces that with a value an operator must supply, validated
as a UUID, **with no default** — so the branch fails closed where it used to fabricate. It is the
same shape `E4` applied one layer down: an identity may be declared, never guessed.

It does NOT reintroduce what `E4` deleted. `LW_CHANNEL_ACTOR_MAP` said *which actor a user drives* —
a binding, and a second source of truth against `actor_control_binding`. This says *who the
developer is*, which is the ticket's job on the real path. The binding still comes from the
control plane, and a dev user with no grant still drives nobody.

---

### `F1`–`F3` — what the measurement changed

**`F1` is a narrowing.** The dev branch returned `` `dev:${jwt.slice(0,4)}` `` — an identity
fabricated from four characters of a SHARED token, so every session on a box was one "user". After
`E3` it was not a user at all: `dev:dev_` fails `isUserRefId`, so the subject lookup refused it and
**the whole demo path was dead**. Nothing reported that, because the only view that would have shown
the refusal is mounted nowhere. Now the value must be supplied and must parse as a UUID, with no
default — the branch fails closed where it used to invent.

It does **not** reintroduce what `E4` deleted. `LW_CHANNEL_ACTOR_MAP` said which ACTOR a user drives:
a binding, and a second source of truth against `actor_control_binding`. This says who the DEVELOPER
is, which is the redeemed ticket's job on the real path. A dev user with no grant still drives
nobody, and the binding still comes from the control plane.

**`F2` found that world-service had no Dockerfile at all** — only `Dockerfile.orphan-scanner`. The
image copies `contracts/` because `PROVISION_SQL_DIR` and `PROVISION_META_ALLOWLIST` default to
CWD-relative paths; that is `ED-D8` from the player-edge run reappearing as a packaging requirement,
and in a container it would have surfaced as the same generic `500` that cost an hour there.

**`F3`'s test is a source scan, and here that is the RIGHT strength rather than a weaker proxy.**
The defect is *"no file references this component"* — a reference scan does not approximate that
property, it IS that property. Rendering `PlayRoute` instead would be strictly weaker: it pulls in
Phaser, react-three and a query client, so it would fail for a dozen reasons that are not "the panel
is unmounted", and a mock deep enough to make it pass would be mocking the wiring under test.

## §4 OPEN

| row | what | mechanism |
|---|---|---|
| `FO-1` | **`EchoRoom.onAuth` takes `options.userId ?? 'guest'` — from the CLIENT.** That id keys the per-user connection cap (`edge.connectionCap.atCap(authed.userId)`), so a client can evade the cap by picking a new id per connection. Found while auditing the identity path for `F1`; out of this board's boundary (different room, different purpose) and recorded rather than absorbed. | None yet. `F1`'s shape is the fix — an identity the SERVER supplies — but EchoRoom is the V0 echo validator and changing its contract is its own decision. |

## §5 DRIFT — append as it happens; an empty log is dishonest, not clean

| id | what |
|---|---|

*(empty at open)*

---

```goal-prompt
goal: a browser renders the entity that actor_control_binding names, with no invented identity anywhere
note: |
  Phase 0: ChannelPanel is mounted NOWHERE and its client was live-proven without it. After E4 the FE's only identity (`dev:xxxx`) is not a user_ref_id, so the join is refused — the demo path is structurally dead and nothing reported it because the view was unreachable. The dev stack already holds reality cd0747d2, actor 9ca0c9c8 -> entity 1, and a live binding for bbbb1111.
stop: |
  a bite does not go red, or goes red for the wrong reason
  a change would let the CLIENT choose its identity or its actor
  the dev branch would gain a DEFAULT identity rather than failing closed
```

**RESUME: `F1` — the dev identity. `onAuth`'s static branch returns `` `dev:${jwt.slice(0,4)}` ``; replace it with a server-supplied `LW_WS_DEV_USER_REF_ID` that must parse as a UUID, and fail closed when it is absent. The client must not gain any say in it.**
