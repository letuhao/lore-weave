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
| `SC1` the seam contract + the Rust half — the worker emits exactly the declared keys | `[ ]` | |
| `SC2` the Go half — the struct tags and the argv flags match the same file | `[ ]` | |
| `SC3` a rename on ONE side reds the OTHER — bitten in both directions | `[ ]` | |
| `RA1` the bridge READ route — `liveBinding` over HTTP, `meta_read_audit` in the same call | `[ ]` | |
| `RA2` the Rust half — `BridgeClient` method + a flow function that cannot bypass the audit | `[ ]` | |
| `RA3` ⏸ **POST-REVIEW checkpoint** — expose the holder in `grant-control --dry-run`? | `[ ]` | |
| `SW` suite + sweep green, and the deferral rows closed | `[ ]` | |

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

## §4 OPEN

| row | what | mechanism |
|---|---|---|

*(empty at open — rows land here as they are found)*

## §5 DRIFT — append as it happens; an empty log is dishonest, not clean

| id | what |
|---|---|

*(empty at open)*

---

```goal-prompt
goal: the admin-cli/worker seam is machine-checked in both directions and a cross-user binding read exists on the audited path
note: |
  Phase 0 measured both rows SMALLER than they read: the contract pattern exists (contracts/frontend-tools.contract.json), and the audited read is already built in Go (liveBinding + RecordBindingRead) and merely private. Mirror and expose; do not invent.
stop: |
  a bite does not go red, or goes red for the wrong reason
```

**RESUME: `SC1` — write `contracts/actor-control-worker.contract.json` from what the worker emits today, then the Rust test that asserts each branch emits exactly those keys.**
