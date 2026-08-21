# KERNEL STATE ON A SCREEN — the last hop, and it writes to nothing real — RUN-STATE

**Opened 2026-08-21** · branch `feat/game-logic` · opened at HEAD `8d85fc33d` · size **M**
(files ~6 · logic 5 · side-effects 2 — a compose service, a demo stack script)

**Adopts** [`2026-08-21-demo-path-RUN-STATE.md`](2026-08-21-demo-path-RUN-STATE.md)'s execution
contract: every row bites, evidence is pasted, a row that cannot be proven stays open.

**Reconciles:** Gateway invariant (I1), Language rule (I3), Settings & Configuration Boundary —
game-server stays the sanctioned second entry point and gains no new public surface; the publisher is
a Go domain worker by `contracts/language-rule.yaml` and stays one; and nothing here adds a user
setting — the new configuration is deploy-time service wiring, the same class as `F2`'s.

The claim `F4` could NOT make is the whole subject: an event produced by the actor hub, rendered in
a browser. `F4` proved the SUBJECT hop — who you are. This is the STATE hop — what is true of you.

---

## §1 PHASE 0 — measured at HEAD `8d85fc33d`

* **`F4` rendered `turn 0` and an empty roster, and that was honest.** Reality
  `cd0747d2-4b94-4f68-9efb-93fef6359306` has **zero committed events**: `XLEN 0` on its stream and
  `SELECT count(*) FROM events` = 0 in `lw_reality_cd0747d24b94`. The roster was empty because there
  was nothing to render, not because the fold is broken.
* **The publisher EXISTS and is wired to nothing.** `services/publisher/pkg/redisemit` is what
  `XADD`s to `lw.events.<reality_id>` — the exact stream `ChannelRoom.streamFor()` consumes — and
  `grep '^  publisher:' infra/docker-compose.yml` returns nothing, with no container running. That
  is unbuilt work, not a blocker: the same gap `F2` closed for world-service, in the same shape.
* **Four `lw.events.*` streams DO carry entries** (XLEN 5, 2, 4, 12) and **none of their realities is
  registered** — `reality_registry` has no row for any of the four. Leftovers from suites that used
  random ids. So no existing reality has both events and a binding, and none can be made to without
  a write.
* **…except that the write has a THROWAWAY home already built.**
  `scripts/smoke/spine-drain-once.sh` provisions `loreweave_spine_smoke_meta` +
  `loreweave_spine_smoke_channel`, applies `migrations/meta` AND
  `contracts/migrations/per_reality`, verifies the four tables the binary needs, and drives the real
  spine. Both names carry the `smoke` marker the fixtures' `guarded()` demands. **This board writes
  only there**, so the Rule-5 question `F4` stopped at does not arise.
* **`DFO-7` does not block this.** The spine BINARY hangs, and `commit-spine-drain-once` passes in
  the live-suite registry with its own runner — so a committed turn is reachable without fixing it.
  A RESOLVED turn rendered live is a different claim and is out (below).
* **`actor-hub` reaches the events already.** `commit-service/src/domain/actor.rs` holds an
  `actor_hub::Actor`, and `dataflow_live.rs` walks *action → hub → DP write → events row → wire
  frame* with ids pasted. Every hop of this board is downstream of a chain that is already proven;
  what is missing is the last two.

---

## §2 BOUNDARY

**IN:** the publisher wired so committed events reach `lw.events.<reality>` · a demo stack standing
entirely on throwaway databases · a browser rendering a roster and a condition that came from a
committed event.

**OUT, each for a stated reason:**

* **Fixing `DFO-7`.** The spine binary hangs and the drain-once path is green; making the long-running
  binary terminate correctly is its own defect with its own row.
* **A turn RESOLVED from the browser** — clicking Strike and watching the outcome return. That needs
  the proposal to survive producer signing (`LW_PRODUCER_KEY_GAME_SERVER` is unset and the room warns
  that commit-service will reject at the producer-identity stage) and the spine to be consuming. This
  board renders committed state; it does not close the loop back.
* **The publisher's own correctness.** Its poll loop, outbox semantics and retry behaviour have their
  own suites. This board wires it and asserts one event arrives; it does not re-test it.

---

## §3 BOARD

| slice | state | evidence |
|---|---|---|
| `G1` the publisher is reachable — Dockerfile + compose, the `F2` shape | `[x]` | `services/publisher/Dockerfile` (37.1 MB, three COPY lines derived from go.mod's three `replace` targets) + a compose service. **`Up (healthy)`**, `healthz`/`readyz` → **HTTP 200** from the host, and the log says `loaded realities drained=10 skipped=0` + `redis connected` — so it read `reality_registry` and resolved all ten DSNs through the host override |
| `G2` a demo stack on THROWAWAY databases — reality registered, actor, binding | `[x]` | `scripts/smoke/kernel-state-demo.sh`. Provisions `loreweave_kernel_state_smoke_{meta,channel}`, applies both migration sets, verifies 7 tables, seeds reality+actor+binding, and starts all three services with a `--down`. **Re-run clean from scratch: RC=0.** Nothing outside the two `smoke` databases is written |
| `G3` a committed event exists, produced by the real path | `[x]` | The real `spine` binary consuming a real proposal off the real stream: **`consumed 1 · admitted 1 · committed 1 · turn 1`**. Payload `{"type":"struck","attacker":"1","target":"2","damage":9,"hp_left":31}` — and `attacker: "1"` is the entity the KERNEL resolved from the binding, since the proposal carried only `user_ref_id`. `SEALED-SUBJECT`, visible in committed data. Producer identity NOT enforced in this run and the binary says so; stated, not glossed |
| `G4` the event reaches `lw.events.<reality>` and the room folds it | `[x]` | Publisher (second instance, pointed at the smoke meta) → **`lw.events.<reality>` XLEN=1**, and the room folded it: the browser turn went 0 → 1 |
| `G5` live — a browser renders a roster entry that came from that event | `[x]` **manual**, `[ ]` **automated** | **`turn 1 · you are entity 1` + roster `entity-2 · healthy · [Strike]`**, reproduced from a clean stack. **Bitten**: delete `lw.events.<reality>`, re-join → `turn 0` and an EMPTY roster; restore → the entry returns. `you are entity 1` survives both, which is the control — the subject hop is independent of events. The Playwright spec is written and SKIPS: `/play` is behind `RequireAuth` and the app CLEARS an unusable token, so it needs one auth-service issued (`GO-2`) |
| `G6` suite + sweep green | `[ ]` | |

### Why `G2` is its own row rather than a step of `G5`

`F4`'s stack was assembled by hand across six shell invocations, and it worked. It is also
unrepeatable, which is the same defect `EO-2` opened against `E1` and the same one
`world-actor-subject` closed. A demo somebody else cannot run is a demo that will be wrong within a
week and nobody will know.

---

## §4 OPEN

| row | what | mechanism |
|---|---|---|
| `GO-1` | **`e2e/smoke.spec.ts` clicks a control that no longer exists.** It does `getByRole('button', { name: /Continue as guest/ })` on `/login`; `grep "Continue as guest" frontend-game/src` returns nothing, and the rendered login page offers only email/password and Sign up. So that navigation test either fails or never runs. Found while looking for a way to authenticate. | None. Out of this board's boundary (a different spec, a different feature), recorded rather than absorbed. |
| `GO-2` | **The `G5` Playwright spec cannot authenticate.** `/play` is behind `RequireAuth`, and the app does not merely read `lw_auth` — it CLEARS a token it cannot use (measured: `localStorage.getItem('lw_auth')` is `null` after the redirect). So a seeded placeholder does not work, which is correct behaviour. Making the spec unconditional needs auth-service in the demo stack plus a seeded user, or a test-only session issuer. | The spec exists and SKIPS loudly, naming `KERNEL_STATE_ACCESS_TOKEN` — the same contract every live suite here honours. It runs the moment a real token is supplied. |

## §5 DRIFT — append as it happens; an empty log is dishonest, not clean

| id | what |
|---|---|
| `GD-3` | **A pid file is only as true as the thing it names, and this cost three separate incidents in one afternoon.** `$!` after `npx vite`, after `go run`, and after `go run` again captured WRAPPERS; the real process kept the port or the database connection. Symptoms differed every time and none of them said "wrong pid": vite refused to start with *"Port 5199 is already in use"* (correct, and I read it as a cache problem), and the publisher held a connection that made `DROP DATABASE` fail on the next run. The eviction I added for that is ALSO insufficient — terminating a backend just makes a 1s poller reconnect. Fixed properly by BUILDING the publisher and running the binary. |
| `GD-4` | **I chose a demo action that renders nothing, and it would have looked like success.** `foldEvent` mutates the view for `struck`, `downed`, `fled` and `moved`; `defended` falls to `default: break`. My first proposal was `defend`, which commits a real event and advances the turn — so the browser would have shown `turn 1` with an empty roster, and "the turn moved" is exactly the partial result worth mistaking for the whole thing. Caught by READING the fold before asserting on it, not by running it. |
| `GD-5` | **I mis-read a log line as a defect.** `channel-room: consuming … from: "$"` looked like the room refusing to replay history, and I said so. It is the TAIL cursor, set after `replayView(..., options.from ?? '0')` has already replayed from zero. The code said one thing and the log said another; reading the code settled it in thirty seconds. |
| `GD-6` | **The hand-driven browser proof was authenticated by accident.** Every manual `/play` visit worked because that browser still carried a session from an earlier navigation. Playwright's fresh context does not, and landed on `/login` — which is how `GO-2` was found at all. A manual run can be authenticated by history; a test never is, and that difference is a reason the manual proof was not sufficient on its own even though it was real. |
| `GD-1` | **A value that PARSES and still dials nothing.** `PUBLISHER_SHARD_HOST_OVERRIDE` is documented `host=host:port`, and `ParseHostOverride` only checks that both sides are non-empty — so `pg-shard-0.internal=postgres` parses cleanly. `resolveHostPort` then returns that value **verbatim** as the dial target and never consults `SHARD_DB_PORT` on the override path, so the port silently vanishes. I wrote the portless form first and caught it by reading the CONSUMER after the parser. **A validator that accepts what its consumer cannot use is not validation**, and the gap between the two is where the config bug lives. |
| `GD-2` | **`docker ps` showed the mapping, the container was healthy, and the host got 404.** My first host port was 8081, where a non-Docker process on this box (`chaos-backend`) was already listening on `0.0.0.0`. Docker bound the mapping anyway and printed `0.0.0.0:8081->8080`, so every visible signal said the publisher was serving and broken, while `wget /healthz` INSIDE the container returned `ok` the whole time. Moved to 8091. **I also mis-diagnosed it once**: I said the HEALTHCHECK must be passing on its `nc -z` fallback, which was wrong — wget was succeeding inside the container. The port-open fallback is still a real weakness in that check, just not the one that was firing. |

---

```goal-prompt
goal: a browser renders a roster entry that came from an event the actor hub produced, with every write landing in a throwaway database
note: |
  Phase 0: the publisher EXISTS (services/publisher/pkg/redisemit XADDs lw.events.<reality>) and is in no compose file — unbuilt, not blocked, same gap F2 closed for world-service. No registered reality has events; the four streams that do carry entries belong to unregistered ids. scripts/smoke/spine-drain-once.sh already provisions loreweave_spine_smoke_meta + loreweave_spine_smoke_channel with both migration sets, so every write this board needs has a throwaway home and the Rule-5 question F4 stopped at does not arise. DFO-7 (the hanging spine binary) does not block this: the drain-once path is green.
stop: |
  a bite does not go red, or goes red for the wrong reason
  a write would touch a database whose name carries no throwaway marker
  the browser would render a value that did not come from a committed event
```

**RESUME: `G1` — the publisher. It has no Dockerfile and no compose entry; `services/world-service/Dockerfile` and the `world-service` compose block from `F2` are the shape to mirror. Measure what it actually needs at runtime before writing either — its env names are its own.**
