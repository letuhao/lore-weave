# S2 / C + C2 — Property + From-Spec Oracle (build plan)

> **Slice:** S2 of the foundation runtime test plan (`docs/specs/2026-06-04-foundation-runtime-test-plan.md` §2.2, §2.3, §10). The LAST correctness-spine slice — completes `B ∧ C ∧ C2 ∧ C3`.
> **Status:** PLAN (written; awaiting human review before BUILD).
> **Task size:** **L–XL** — a new Rust golden-fixture crate (C2) + a Go projection-checker package (C structural) + conformance cases. `/review-impl` before commit (spine).
> **Locked decisions:** C2 = a **central golden-battery crate** + **external JSON fixtures**; C structural = a **Go DB-checker sibling to the ledger** (no-orphan + deterministic-rebuild).

---

## 1. CLARIFY — scope (grounded)

The spine is `B(integrity-checker) ∧ C3(ledger)` live. S2 adds **C** (structural) + **C2** (from-spec).

**Already covered (don't rebuild):** monotonic `aggregate_version` (C3 ledger + generator `Validate`); deterministic `apply_event` (it's a pure fn); generator determinism (proven S3).

**Net-new:**
- **C2 — value-correctness** (highest value: the gap B+C both miss): for each projecting event type, a hand-authored `{envelope → expected projection delta}` fixture independent of the projection impl. `apply_event` computing a wrong-but-structural value is caught here.
- **C structural (DB-level)** — **no-orphan-rows** (every projection row's `event_id ∈ events`) + **deterministic-rebuild** (rebuild 2× → byte-identical projection tables).

**Grounded facts:** `dp_kernel::ProjectionUpdate` derives `PartialEq + Serialize/Deserialize` (`projection.rs:95`) → fixtures compare via JSON value. `ProjectionRunner::apply_one(env) → Vec<ProjectionUpdate>` runs all projections + concatenates — the full delta for one event. The ~14 projecting event types + their arms are in `crates/projections/*`.

### In scope
**C2 (Rust) — HONEST FRAMING (revised after /review-impl):** C2-via-fixtures-I-author is primarily a **regression-lock + spec-encoding** (pins the contract, catches FUTURE drift). To get as much *independence* as available — so it can also catch a *current* wrong value — fixtures are authored from the **design source of truth, NOT the projection code**: the migration column semantics (`0006_projections.up.sql` / `0009`), the locked Q-decisions (Q-L3B-1 fan-out, Q-L3-4 meta, canon_layer enum, etc.), and the arm's *doc-comment contract* — never by dumping `apply_event` output. True independence for the highest-risk types is Option B (deferred). We do NOT claim C2 closes value-level common-mode beyond what an independently-authored fixture can.
1. A new crate `crates/projection-golden` depending on `dp-kernel` + all `projections-*`.
2. JSON fixtures (`fixtures/<event_type>.json`) = `{ "envelope": {…}, "expected_updates": [...] }`, authored from the design source of truth (above).
3. A test harness: walk fixtures → build a `ProjectionRunner` with all projections → `apply_one(env)` → assert `to_value(actual) == to_value(expected)` (JSON diff on mismatch).
4. Fixtures for **every projecting event type** (npc.created/said · session.started/ended/participant_joined/left · pc.spawned/moved/item_acquired/relationship_changed · region.created/ambient_changed · world.kv_set/unset · canon.entry.created/updated/promoted/decanonized) — the same set the S3 generator emits.

**C structural (Go) — SCOPED DOWN (revised after /review-impl):** no-orphan is **tautological after a rebuild today** (the rebuilder writes `event_id` from the event, so every row references a real event; only a future streaming runtime could write an orphan) — it is shipped as a cheap **latent guard**, framed honestly. deterministic-rebuild is **deferred** (pure projections + ordered events are deterministic by construction; near-tautological now → D-C-DETERMINISTIC-REBUILD).
5. `tests/workload-gen/internal/projcheck` — **pure** `CheckNoOrphan(eventIDs, projRows)`: every projection row's `event_id` resolves to a real event (latent guard — fires only when a non-rebuild writer introduces an orphan). Plus a thin `LoadProjections(ctx, db)` fetching `(table, event_id)` from each projection table.
6. A `-check-projections` CLI mode (or extend `-verify`) running no-orphan after emit+rebuild.

### Out of scope
- C2 Option B (independent reference projector in Python) — fixtures (Option A) first; graduate later if maintenance bites (D-C2-REFERENCE-PROJECTOR).
- Re-deriving monotonic-version / determinism already covered by C3/S3.

### Acceptance gate (LOCKED, revised)
- C2: `cargo test -p projection-golden` green — a fixture per projecting event type (authored from the design source, not the code), all matching `apply_one`. A deliberately-wrong fixture is shown to FAIL (prove the oracle bites).
- C structural: `go test ./internal/projcheck/...` green incl a corruption-injection test (a projection row with a dangling event_id → no-orphan fires) — framed as a latent guard.
- Live: emit → rebuild → `-check-projections` clean (0 orphans).
- `language-rule-lint` PASS; `cargo`/`go vet`/`gofmt` clean.
- (deterministic-rebuild deferred — see D-C-DETERMINISTIC-REBUILD.)

---

## 2. DESIGN

```
crates/projection-golden/        # NEW Rust crate (C2)
  Cargo.toml                      # deps: dp-kernel + all projections-* (+ added to workspace members)
  src/lib.rs                      # fixture types (Fixture{envelope, expected_updates}) + loader
  tests/golden.rs                 # walk fixtures/ → apply_one → assert ==
  fixtures/*.json                 # {envelope, expected_updates} per event type
tests/workload-gen/internal/projcheck/   # C structural (Go)
  projcheck.go  + _test           # CheckNoOrphan (pure) over fetched rows
  load.go       + _test           # LoadProjections(ctx, db) → []ProjRow{table, event_id}
cmd/workload-gen/main.go          # + -check-projections mode
```

- **C2 fixture compare:** `serde_json::to_value(apply_one(env)) == to_value(fixture.expected_updates)` — order matters (apply_one is deterministic); on mismatch, pretty-print both for the diff.
- **C2 fixture authoring:** from the **design source of truth** — migration column semantics + locked Q-decisions + arm doc-comment contract — NOT by dumping `apply_event` output. That is the best available independence; honestly, the residual coupling means C2 is mainly a regression-lock (see §1).
- **projcheck no-orphan:** `CheckNoOrphan(eventIDs map[uuid]bool, rows []ProjRow) []Violation` — pure; the loader fetches `event_id` from each projection table (the VerificationMeta column). Latent guard — tautological on a freshly-rebuilt DB today (no non-rebuild writer exists).

---

## 3. PLAN — build increments (TDD)
1. **C2 scaffold** — crate (+ workspace member) + `Fixture` types + loader + harness + 1 fixture (`npc.created`, authored from the migration semantics) proving the harness + a deliberately-wrong fixture proving it FAILS.
2. **C2 fixtures** — author the rest (all projecting event types) from the design source; `cargo test -p projection-golden` green.
3. **projcheck** — `CheckNoOrphan` (pure) + corruption-injection test (dangling event_id fires); `LoadProjections`.
4. **CLI** — `-check-projections` mode (emit→rebuild→no-orphan).
5. **Live VERIFY** — emit → rebuild → `-check-projections` clean on real PG.

### VERIFY gate
`cargo test -p projection-golden` + `go test ./internal/projcheck` + `go vet`/`gofmt`/`language-rule` + `cargo build --workspace` clean; live no-orphan=0; a wrong-fixture + a dangling-event_id both proven to fire.

---

## 4. Risks & open items
- **R1 — fixture independence (the crux; `/review-impl` flagged the original plan oversold it).** A fixture dumped from `apply_event` is a regression-lock, not a correctness oracle. Author each expected delta from the **design source** (migration columns + locked Q-decisions + arm doc-contract) so a reviewer can verify it against the spec, not the code. Be honest in the fixtures' README that C2 is primarily a regression-lock; true independence for high-risk types is Option B (O1). Do not claim more.
- **R2 — VerificationMeta in fixtures.** RESOLVED: `applied_at = env.recorded_at` (`projection.rs:83`), so the fixture's expected_updates are deterministic from the fixture envelope — the `==` compare is sound.
- **R3 — workspace wiring.** A new crate must be added to the workspace `members` + pass `cargo build --workspace` (foundation-ci runs it). Verify in increment 1.

**Open:** O1 — graduate C2 to an independent reference projector (Option B) if fixture maintenance bottlenecks (D-C2-REFERENCE-PROJECTOR).

## 5. Deferred at COMMIT
- **D-C2-REFERENCE-PROJECTOR** (O1) — Python reference projector for a 3-way differential (true independence for high-risk types). Target: if fixture maintenance bottlenecks or a value bug slips the regression-lock.
- **D-C-DETERMINISTIC-REBUILD** (/review-impl) — rebuild-twice byte-identical check. Near-tautological today (pure projections); ship when a nondeterminism source (a streaming projection runtime, HashMap-ordered projection output) appears.
- This completes the spine `B ∧ C ∧ C2 ∧ C3` — with the honest caveat that C2 is a regression-lock + spec-encoding (independence bounded by same-author fixtures) and C structural's no-orphan is a latent guard.
