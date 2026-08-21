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
| `G7` the loop BACK — the browser causes the state it renders | `[x]` | **Was declared OUT and it was reachable.** Browser Strike → proposal (`user_ref_id` server-stamped, **no `actor` field**) → `spine --drain-once`: **`consumed 1 · admitted 1 · committed 1 · turn 2`** → publisher → the room's tail → the page updated **with no reload**: `turn 2` and an outcome line **`1 strikes 2 for 9 (31 left)`**. That line prints the hub's NUMBER, not the derived badge |
| `G6` suite + sweep green | `[x]` | **`SWEEP_RC=0` — 91 GREEN / 0 RED / 8 SKIP.** Rust workspace **2568 passed / 0 failed** / 14 ignored · **23 of 23** live suites · frontend-game **214 / 0** (22 files) · game-server **84 / 0** (2 skipped, live Redis) · `service_acl`+`pii`+`meta`+`publisher` green · `design-lint` and `actor-hub-figures` green. **No RED, tracked or otherwise** — the first board of the three where the sweep found nothing of mine to fix |

### Why `G2` is its own row rather than a step of `G5`

`F4`'s stack was assembled by hand across six shell invocations, and it worked. It is also
unrepeatable, which is the same defect `EO-2` opened against `E1` and the same one
`world-actor-subject` closed. A demo somebody else cannot run is a demo that will be wrong within a
week and nobody will know.

---

### `G7` — the boundary was wrong, and the reason it was wrong is the useful part

`§2` put *"a turn RESOLVED from the browser"* OUT, on the grounds that it *"needs the proposal to
survive producer signing (`LW_PRODUCER_KEY_GAME_SERVER` is unset and the room warns that
commit-service will reject it at the producer-identity stage)"*.

**That reason was wrong, and it was wrong in a checkable way.** `services/commit-service/src/bin/spine.rs:128` prints
*"no `LW_PRODUCER_KEY_*` configured — producer identity is NOT enforced"*: with no key on the
CONSUMER side there is nothing to verify against, so an unsigned proposal is admitted. The room's
warning is about what happens when the spine DOES hold a key. I read one side's warning and inferred
the other side's behaviour instead of reading it.

So the only real blocker was a spine that consumes, and `--drain-once` is a spine that consumes.

**What the loop proves that the read half did not.** The proposal came from the browser: the panel's
own Strike button, `user_ref_id` stamped by the server from `LW_WS_DEV_USER_REF_ID`, and **no
`actor` field at all** — `SEALED-SUBJECT` on the wire, verified by reading the entry off the stream.
The island resolved the subject from the binding, `actor_hub::Actor::set_quantity` moved the vital,
and the committed event came back through the publisher to a page that had not reloaded.

**Still not a deployment.** The spine ran as `--drain-once`, invoked by hand between the click and
the update. A real deployment runs it as a consumer, and that binary hangs (`DFO-7`). So the loop is
proven; the AUTOMATIC turn is not.

## §4 OPEN

| row | what | mechanism |
|---|---|---|
| ~~`GO-1`~~ | **CLEARED 2026-08-21, and it was bigger than the row said.** The guest button was one symptom; the cause is that `RequireAuth` landed after the suite was written, so `/world-select` and all four `/play` tests had been asserting against a redirect. **Nobody saw it because `playwright.config.ts` pointed the webServer at `:5174` while `vite.config.ts` had already moved frontend-game to `:5176` with `strictPort`** — so in CI the job times out before running a test, and locally `reuseExistingServer` hands the suite the OTHER app's container. Two defects, each hiding the other. Config repointed; `/login` re-asserted against the form it actually renders; the guarded tests SKIP loudly naming `GO-2`; the dead navigation test replaced by one that asserts the guard. **2 passed / 5 skipped / 0 failed.** Original text: `e2e/smoke.spec.ts` clicks a control that no longer exists. It does `getByRole('button', { name: /Continue as guest/ })` on `/login`; `grep "Continue as guest" frontend-game/src` returns nothing, and the rendered login page offers only email/password and Sign up. So that navigation test either fails or never runs. Found while looking for a way to authenticate. | None. Out of this board's boundary (a different spec, a different feature), recorded rather than absorbed. |
| ~~`GO-2`~~ | **CLEARED 2026-08-21 — auth-service was already running.** I deferred this as "needs auth-service in the demo stack", and `infra-auth-service-1` had been `Up (healthy)` on :8204 the whole time, with the test account CLAUDE.md documents. `POST /v1/auth/login` returns a real token; `isAuthenticated` is `!!accessToken`, so seeding `lw_auth` with it clears `RequireAuth`. **The spec now RUNS: 2 passed.** Bitten — clear `lw.events.<reality>` and it fails with *"no roster entry — the committed event did not reach the fold"*; restore and it passes. `DEMO_DRIVER` is now overridable so the browser's session and the game's driver are the SAME person, which is what production looks like. Original text: the `G5` Playwright spec cannot authenticate. `/play` is behind `RequireAuth`, and the app does not merely read `lw_auth` — it CLEARS a token it cannot use (measured: `localStorage.getItem('lw_auth')` is `null` after the redirect). So a seeded placeholder does not work, which is correct behaviour. Making the spec unconditional needs auth-service in the demo stack plus a seeded user, or a test-only session issuer. | The spec exists and SKIPS loudly, naming `KERNEL_STATE_ACCESS_TOKEN` — the same contract every live suite here honours. It runs the moment a real token is supplied. |

## §5 DRIFT — append as it happens; an empty log is dishonest, not clean

| id | what |
|---|---|
| `GD-10` | **Two of the four rows I cleared were deferred against infrastructure that already existed.** `EO-1` said it needed a migrate-existing-realities path — `migration-orchestrator/cmd/migrate` has one. `GO-2` said it needed auth-service in the stack — `infra-auth-service-1` was `Up (healthy)` while I wrote the row. Both reasons would have been re-read and believed next session. **CLAUDE.md's rule is that "missing infrastructure" is unbuilt work, not a blocker; the sharper version is that it is often not even unbuilt** — the check is `ls`, and I skipped it twice in one day while writing rows whose whole purpose is to be trustworthy later. |
| `GD-9` | **I nearly filed an environment collision as a rotten test suite.** Seven e2e tests failed and I was one sentence from recording *"the frontend-game e2e suite is red"*. It was running against `infra-frontend-1` — a DIFFERENT application — because `playwright.config.ts` still names `:5174` and `reuseExistingServer: true` cheerfully took whatever answered. What made the difference was noticing that `/login` had no heading AND `/play` did not redirect: two symptoms that cannot both come from stale assertions, but can both come from the wrong app. **The tell was a failure pattern that did not fit the hypothesis**, and the fix for that is to keep looking, not to write the finding down. |
| `GD-8` | **`citation-gate` blocked the `G7` commit, and it was right.** I cited a bare `spine.rs` with a line number, three times; there are TWO files by that name in this repo (`crates/world-gen/src/shape/spine.rs` and `services/commit-service/src/bin/spine.rs`), so the citation resolved to neither. The gate's own message is the lesson — *"a citation nobody can follow is worse than none: it reports evidence and silences review"* — and it lands hard here, because the paragraph doing the citing is the one correcting a claim I had ALSO not checked. Two unresolvable references inside a correction block about unverified references — and then this row, describing the defect in the defect's own syntax, tripped the gate a second time. Hence the circumlocution above: the gate reads a `name.rs:NNN` anywhere, including inside a sentence about how not to write one. |
| `GD-7` | **I declared something OUT for a reason I had not checked.** `§2` excluded the loop back because the room warns that unsigned proposals are rejected at the producer-identity stage. That warning is about the room's side; the CONSUMER decides, and `services/commit-service/src/bin/spine.rs:128` says plainly that with no key configured identity is not enforced. One grep would have settled it. **A boundary is a claim about the work, and it needs the same evidence as any other claim** — this one cost the board a row it could have had from the start, and the only reason it was recovered is that the PO asked whether the goal was actually complete. |
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

**RESUME: the board is CLOSED — 7 of 7 (`G7` was added after the fact; see the drift log). `GO-1` and `GO-2` remain open and neither is this board's to fix. The question three boards were opened to answer is answered: an event the actor hub produced renders in a browser, and the proof bites. The loop BACK is now proven too: a browser Strike causes the state the browser renders. What is NOT proven is the AUTOMATIC turn — the spine ran as `--drain-once` by hand between the click and the update, and the long-running consumer hangs (`DFO-7`).**
