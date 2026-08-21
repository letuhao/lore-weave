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
| `F4` live — a browser shows the entity the binding names | `[x]` | **`turn 0 · you are entity 1`**, rendered in Chromium at `/play`. Server-side corroboration: world-service `http_requests_total{method="POST",status="200"} 1` for the join. **Bitten**: stop world-service, re-join → *"could not resolve your actor; retry"* — NOT "you drive nobody"; restart → entity 1 again. Image builds too: `docker build` rc=0, 139 MB |
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
### `F4` — the chain, and the bite that makes it a proof

**`turn 0 · you are entity 1`** in a browser. The whole path, each hop real:

```
Chromium /play → ChannelPanel → colyseus `channel` room
  → onAuth: LW_WS_DEV_USER_REF_ID (the SERVER's env, never the client)
  → onJoin: resolveSubject → HTTP → world-service /internal/v1/actor-control/subject
  → meta: actor_control_binding WHERE reality_id AND user_ref_id AND revoked_at IS NULL
  → per-reality: actors → entity_id 1
  → w1.frame.self → channel-store → the DOM
```

Entity 1 is actor `9ca0c9c8-…`, which is what `bbbb1111-…` holds the live binding for. Not asserted
from the fixture — **bitten**: with world-service stopped the same click yields *"could not resolve
your actor; retry"*, and restarting it yields entity 1 again. So the number on screen provably comes
from the control plane and both databases, and not from a cache, a default, or the client.

**And the refusal is the RIGHT refusal.** It does not say *"you drive nobody"*. That distinction is
`E3`'s four-answer design — driving · nobody · realityClosed · unavailable — and this is the first
time it has been visible in a UI rather than argued for in a test.

The roster is empty and the turn is 0 because nothing has been committed to this channel's stream.
That is the OUT boundary working as written: joining and seeing the right `self` is this board's
claim; a RESOLVED turn needs the spine, which hangs (`DFO-7`).

| `FO-2` | **`phase0-reconcile-gate` reads only the citations BEFORE the first em-dash.** Authors who write `A - why A - B - why B` get `A` checked and `B` ignored, so *the more prior art a spec cites, the less of it is read*. Measured 2026-08-21: **7 of 25** fields use that shape, **15** citations sit past the first dash unread, and **1 is a genuine phantom** (`SEALED-SUBJECT` in the player-edge plan, now corrected). The gate's own header claims this class was fixed — that fix was for WRAPPED lines; reach has two dimensions and one was repaired. | **A parser widening was written and REVERTED, and that is the finding.** Once prose may contain the separators — which it does, correctly, in `2026-08-15-claim-rot.md` — a citation and a sentence are not distinguishable by punctuation: the widening caught the one real phantom and invented FIVE against a conforming field. A check that reds correct work is how a gate becomes noise someone silences. The fix is to the CONVENTION (refuse an interleaved field, as a closed-set arg refuses a free string), which means rewriting 7 fields across tracks this board does not own — gate #2, large/structural. The revert is documented in the gate beside the line, pointing here. |
| `FO-1` | **`EchoRoom.onAuth` takes `options.userId ?? 'guest'` — from the CLIENT.** That id keys the per-user connection cap (`edge.connectionCap.atCap(authed.userId)`), so a client can evade the cap by picking a new id per connection. Found while auditing the identity path for `F1`; out of this board's boundary (different room, different purpose) and recorded rather than absorbed. | None yet. `F1`'s shape is the fix — an identity the SERVER supplies — but EchoRoom is the V0 echo validator and changing its contract is its own decision. |

## §5 DRIFT — append as it happens; an empty log is dishonest, not clean

| id | what |
|---|---|
| `FD-1` | **The mount passed its test and was unclickable.** `F3`'s scan proved `ChannelPanel` is imported and rendered with both props — all true, and the panel was still unusable: `PlayRoute` is a full-screen canvas with absolutely-positioned overlays, so a panel dropped into normal flow renders *underneath* them and `top-4 left-4` swallows every click. Playwright found it in one action (*"intercepts pointer events"*); no test in this repo would have. **The scan's honest limit, stated when I wrote it, is narrower than I then treated it as** — it proves the code is REACHABLE, and I read the green as "the panel works". Fixed with the positioned wrapper the sibling overlays all use. |
| `FD-2` | **I nearly "fixed" a non-problem.** Before starting the image build I worried `COPY . .` would tar the 6.3 GB of `.claude/worktrees` into the context. `.dockerignore` already excludes `.claude` — line 36. Twenty seconds of measurement against a change to a file every service build depends on. Recorded because the near-miss is the good outcome, and the habit that produced it is the one worth keeping. |
| `FD-3` | **Two gates caught this work and both were right.** `phase0-reconcile-gate` refused the commit for citing `SEALED-SUBJECT`, which has no index row — and chasing why the player-edge plan cites the same phantom and passes found `FO-2`. `actor-hub-figures-gate` refused it because a governed doc claims *"1 of 3 game-tier services in compose"* and `F2` made it 2 — the same doc that named `WS-COMPOSE` as the gap `F2` closed. Neither was noise, and neither was findable by reading. |
| `FD-4` | **The first `LW_CHANNEL_REDIS_URL` pointed at a port nothing listens on.** I wrote `redis://127.0.0.1:6379` from habit; this stack maps Redis to **6399**. The room came up "healthy" anyway, because `/livez` does not touch Redis and the consumer loop fails asynchronously — so a wrong broker address reads as a healthy service until a join goes quiet. The same shape as `streamFor()`'s own comment: *"a consumer cannot quietly point at a stream nobody writes"*. |

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
