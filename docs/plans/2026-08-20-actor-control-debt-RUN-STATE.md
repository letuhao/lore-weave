# FEATURE #2 DEBT — THE SEAM AND THE AUDITED READ — RUN-STATE

**Opened 2026-08-20** · branch `feat/game-logic` · opened at HEAD `2f554964d` · size **M**
(files ~8 · logic 5 · side-effects 2 — a new internal bridge route, a new machine contract)

**Adopts** [`2026-08-08-reality-layer-RUN-STATE.md`](2026-08-08-reality-layer-RUN-STATE.md) §0.6d as
its execution contract, and §0.6's hazards.

**Reconciles:** MCP Tool I/O Standard — the seam here is not an MCP tool, but it is the same
two-services-two-languages shape the Frontend-Tool Contract governs, and the fix is that standard's
own pattern · User Boundaries & Tenancy — the read this adds is **cross-user by construction** and
must stay on the audited path · Non-Vacuity — both rows exist because a check was missing, so
neither closes without a bite · Security Standard — an operator being able to ask *who drives this
actor* is a new capability, not a convenience.

---

## §1 PHASE 0 — both rows are smaller than they read

Measured at HEAD, not remembered:

* **`contracts/frontend-tools.contract.json` EXISTS** (5,413 bytes, 2026-08-02). The pattern
  `D-PC-SEAM-NO-CONTRACT` names is a real file with a real test behind it, so `SC1` mirrors
  something rather than inventing it.
* **The audited read is already BUILT in Go.** `services/meta-worker/pkg/bridge/actor_control.go`
  has `LiveBinding`, `MetaRegistrar.liveBinding`, the `ReadAuditor` interface and the
  `RecordBindingRead` call that writes `meta_read_audit`. It is private, used only inside the
  write path's CAS. **`RA1` exposes existing machinery over HTTP; it does not build the audited
  read.**
* **`TagActorBindingCrossUser` exists** in `contracts/pii/sdk.go:46`, added during `P1` — the
  constant whose absence `PD-10` recorded.

So the honest scope is: **one contract file and two tests** for the seam, and **one route plus a
client method** for the read. What is NOT small is the last row, and it is not small for a reason
that has nothing to do with code.

---

## §2 BOUNDARY

**IN:** a machine-checked contract for the `admin-cli` ↔ `actor-control` seam, both directions ·
an audited cross-user read of `actor_control_binding`, reachable from Rust · the decision about
whether an operator may use it.

**OUT, each for a stated reason:**

* **The player-facing edge** — the transport still resolves actors from `LW_CHANNEL_ACTOR_MAP`
  (`D-ACTOR-BINDING-NOT-READ-BY-TRANSPORT`). It is the obvious next feature and it is a feature;
  this run is debt.
* **Widening `deferral-gate` past the game tier** — `D-DEFERRAL-GATE-PLATFORM-SCOPE` is a triage
  of ~360 ids, which is a decision about which are still open, not a code change.
* **`D-PC-SEATS`, `D-PC-SF6-REVERSAL`, `D-PC-AGENT`, `D-PC-METAWRITE-NOOP-EVENT`** — the four
  rows whose triggers say they wake on something that has not happened.

---

## §3 BOARD

| slice | state | evidence |
|---|---|---|
| `SC1` the seam contract + the Rust half — the worker emits exactly the declared keys | `[x]` | `contracts/actor-control-worker.contract.json` authored FROM MEASUREMENT; 7 Rust arms, the flags checked BEHAVIOURALLY against the real binary; 5/5 bitten |
| `SC2` the Go half — the struct tags and the argv flags match the same file | `[x]` | 6 Go arms over `reflect` on the real struct + the real `workerArgs`; 6/6 bitten; admin-cli 11 packages green |
| `SC3` a rename on ONE side reds the OTHER — bitten in both directions | `[x]` | folded into `SC1`/`SC2`: each half's harness mutates the OTHER half's subject, so the cross-language direction is what the arms measure |
| `RA1` the bridge READ route — `liveBinding` over HTTP, `meta_read_audit` in the same call | `[x]` | `POST /internal/provisioner/read-actor-control`; 7 Go arms; the one-implementation guard BITTEN (an inlined SELECT reds both of its assertions) |
| `RA2` the Rust half — `BridgeClient` method + a flow function that cannot bypass the audit | `[x]` | `BridgeClient::read_actor_control` + `flow::current_driver`; 6 wiremock arms; the CONTRADICTION guard bitten (`driven:true` with no user must not read as an empty slot) |
| `RA3` ⏸ **POST-REVIEW checkpoint** — expose the holder in `grant-control --dry-run`? | `[ ]` | |
| `SW` suite + sweep green, and the deferral rows closed | `[ ]` | |

### `SC1`–`SC3` — the contract, and what measuring it first changed

**Written from measurement, not from the row.** Rule 3 says measure before building, and it moved
two things. The two sides **already agreed** — 18 JSON keys each, 8 flags each, 3 ops each — so the
file freezes an agreement rather than declaring one, and the commit adds a guard without changing a
byte of behaviour. And `contracts/frontend-tools.contract.json`, the pattern the row told me to
mirror, turned out to be **alive with real readers on both sides**, which is what made mirroring it
the right call rather than a citation.

**The two halves are checked differently, and the asymmetry is stated rather than hidden.**

* **The flags are BEHAVIOURAL.** `Args::parse` runs before `Config::from_env`, so the real compiled
  binary run with a complete argv and an EMPTY environment reaches the config check — exit 2,
  *"missing required env"* — while an argv the parser rejects dies earlier with *"unknown flag"*.
  Two distinguishable messages, no database, the actual parser. `CARGO_BIN_EXE_actor-control` gives
  the test the binary for free.
* **The response keys are a SOURCE SCAN.** Every branch of `emit` needs a database, so the real
  JSON cannot be observed here. Scanning the `json!` literals proves the key NAMES agree — which is
  what a rename breaks — and does **not** prove a branch is reachable. Said out loud in the test's
  own header, because a scan that quietly stood in for behaviour would be the more comfortable lie.

Both halves carry a **can-see-its-subject** arm, because a scanner that matches nothing and a
reflection that finds nothing both report a perfect match with the contract. Those two arms are the
`NV-3` guard on the other five.

`SC3` is not a separate slice in the end: each harness mutates the OTHER language's subject and
watches this language's test go red, so the cross-language direction *is* what the arms measure.
Splitting it out would have been a third run of the same mutations.

### Why `RA3` is a checkpoint and not a task

`D-PC-NO-RUST-READ-AUDIT` says the preview was scoped out *"only because adding a
probe-who-holds-whom capability is a decision, not a convenience."* Building `RA1` and `RA2` makes
that capability **possible**; shipping `RA3` makes it **available to every operator with
`admin:write`**. Those are different acts and only the second needs a human.

The argument for: an operator planning a grant is flying blind, and the one fact that decides
whether the grant will be refused is the one the preview will not tell them.

The argument against: `034` registered this read as sensitive because *who drives whom* is a
per-user fact, and a dry run is the cheapest possible way to ask it repeatedly. An audited probe
is still a probe; the audit records it, it does not prevent it.

**So `RA3` stops and asks.** A long run must not decide, by momentum, a question the row it is
closing explicitly reserved.

---

### `RA1` — the audited read had no door, and the lint cannot see the room

`liveBinding` has written the `meta_read_audit` row since `034` and was **private**, reachable only
from inside the grant/revoke CAS. So a caller in another service had two options: a bare `SELECT`
the lint refuses, or nothing. That is `D-PC-NO-RUST-READ-AUDIT` exactly — **the discipline had no
reachable path, so the first caller to need one would have bypassed it by default rather than by
choice.**

The route reuses `liveBinding` unmodified, so the audit is written by the same line that has always
written it. `ReadActorControl` on the production registrar is a one-line delegate on purpose: a
second query — even an identical one — would be a second place for the audit to be forgotten.

**An undriven actor is `200 {"driven": false}`, not a `404`.** *"Nobody drives this actor"* is a fact
about the world and the single most useful answer a grant preview can get; a 404 would push it onto
the caller's error path, and the first thing anyone writes against a 404 is a retry.

**`RA2` is the caller, and the round trip is the point.** `BridgeClient::read_actor_control` is the
only way Rust may ask the question; a `SELECT` in Rust would be a second read with no audit row. The
guard that earns its place is the CONTRADICTION arm: `driven: true` with no parseable `user_ref_id`
must be an ERROR, never `None`. `None` means *the slot is free*, so rounding a malformed reply down
to it would tell a grant preview to go ahead — and the grant would then be refused by a conflict the
preview had just denied existed. The bite installs exactly the tempting simplification (`let Some(..)
else { return Ok(None) }`) and the arm reds.

**Measured while biting it: `meta-sensitive-read-bypass-lint` would NOT have caught the mutant.** It
excludes `services/meta-worker/pkg/bridge/actor_control.go` **wholesale**, because `liveBinding`'s
own SELECT is the sanctioned read. That exclusion was granted for ONE function and silently covers
every function in the file, including ones written afterwards — the escape hatch not reaching its
own reason. So `TestTheAuditedReadHasOneImplementation` is not belt-and-braces; it is the only belt,
and the test says so in its own header rather than implying company it does not have.

## §4 OPEN

| row | what | mechanism |
|---|---|---|

*(empty at open — rows land here as they are found)*

## §5 DRIFT — append as it happens; an empty log is dishonest, not clean

| id | what |
|---|---|
| `AD-1` | **My shell's cwd had drifted and I read three empty greps as a finding.** Checking whether `contracts/frontend-tools.contract.json` — the pattern this row cites — still had consumers, I ran the greps from `services/admin-cli`, where a repo-relative path matches nothing. The output was empty three times and I was one sentence from recording *"the pattern the row names is itself an orphan, a contract file with no test behind it"* in Phase 0. It is not: it has readers in `chat-service`'s tests and in four `ai-gateway` files. **Rule 1 is written about numbers and this was its shape exactly — an EMPTY result read as a result.** What caught it was `ls` on the same path failing with *"No such file or directory"* for a file I had listed successfully ten minutes earlier; the contradiction was the tell, not any check. A grep that finds nothing and a grep that cannot see anything are the same output. **It then happened AGAIN** an hour later, from `services/meta-worker`, on the check that the bite harness had left nothing stranded — so the fix is not vigilance: every repo-relative command in this run now starts from an explicit `cd` to the root. |
| `AD-2` | **The lint that should have been the second guard on the audited read cannot see the file at all.** `meta-sensitive-read-bypass-lint` excludes `services/meta-worker/pkg/bridge/actor_control.go` **wholesale** — a reasoned exclusion, granted because `liveBinding`'s SELECT *is* the sanctioned audited read. But it was granted for one FUNCTION and covers the whole FILE, forever, including functions written afterwards. Measured, not assumed: the `RA1` mutant that inlines a second `SELECT` and skips `RecordBindingRead` passes the lint. **This is the escape-hatch-cannot-reach-its-reason shape from the Non-Vacuity standard**, and it is why `TestTheAuditedReadHasOneImplementation` is the ONLY mechanism rather than a redundant one. Narrowing a shell-grep exclusion to a function is not something that tool can express, so the honest resolution was a structural test plus this row — not a claim of defence in depth that does not exist. |


---

```goal-prompt
goal: the admin-cli/worker seam is machine-checked in both directions and a cross-user binding read exists on the audited path
note: |
  Phase 0 measured both rows SMALLER than they read: the contract pattern exists (contracts/frontend-tools.contract.json), and the audited read is already built in Go (liveBinding + RecordBindingRead) and merely private. Mirror and expose; do not invent.
stop: |
  a bite does not go red, or goes red for the wrong reason
```

**RESUME: `RA3` — the ⏸ POST-REVIEW checkpoint. The capability now EXISTS; whether `grant-control --dry-run` should expose the holder to every operator with `admin:write` is the decision `D-PC-NO-RUST-READ-AUDIT` reserved. Present both arguments and WAIT.**
