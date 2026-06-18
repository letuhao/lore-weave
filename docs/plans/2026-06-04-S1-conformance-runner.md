# S1 — Conformance Runner + Catalog (build plan)

> **Slice:** S1 of the foundation runtime test plan (`docs/specs/2026-06-04-foundation-runtime-test-plan.md` §1.3, §10).
> **Status:** PLAN (written; awaiting human review before BUILD).
> **Task size:** **XL** (12 files — workflow-gate reclassified from L; new test tree + new Go module + new CI workflow + per-case catalog; side effects: CI). Full 12 phases, no skips; `/review-impl` before commit (spine-adjacent). Built solo (human-in-loop, per-phase checkpoints — no autonomous run, no subagent).
> **Build order context:** `S1 → S3 → {S2, S2b, S4, S9} → …`. S1 has **no upstream dependency** and is the contract every later slice reports verdicts into. It is the correct first build.
> **Locked decisions (this session):** Go harness · new `conformance-ci.yml` · full S1 production-shaped.

---

## 1. CLARIFY — scope & acceptance

### Problem
The foundation has ~28 lints + ~5 live-smokes + Go/Rust test suites, each signalling pass/fail via **ad-hoc exit codes**, wired piecemeal into `foundation-ci.yml` / `lint-foundation.yml`. There is no uniform results contract, no `notrun`/`skip` discipline, no known-failures (expunge) list, and no machine-readable run history. A real LTP/xfstests-style suite ships exactly that machinery — and every later slice (C/C2/C3 oracles, fault matrix, perf gate) needs **one verdict contract** to report into. That contract IS the S1 build.

### In scope (S1)
1. `tests/conformance/` tree (`catalog/generic/` + per-service dirs).
2. **Verdict schema** `{pass | fail | notrun | skip}` — a Go contract + emit lib, wrapping heterogeneous case kinds (shell-lint exit-code · Go `-tags=integration` · Rust test · live-probe) into one result.
3. **notrun/skip semantics** — `notrun` = couldn't run (precondition/infra missing); `skip` = legitimately not-applicable on this stack (I4 single-superuser, I5 before provisioner). Distinct, both non-failing.
4. **Expunge / known-failures list** — xfstests `-E` semantics: a `fail` on an expunged case is downgraded to `skip(expunged)` with a tracked Deferred-Items ref; surfaced in the summary, does **not** break the gate. Wired to DEFERRED 149 (catastrophic-rebuild), monthly L3.F.
5. **Results store** — machine-readable JSONL per run (history-friendly; parallels the perf time-series §8 needs for change-point detection).
6. Fold **≥1 lint-case** (`projection-coverage-lint.sh`) + **≥1 live-probe-case** (`publisher-live-smoke.sh`) as real first cases proving the wrapper end-to-end.
7. **`conformance-ci.yml`** runs the runner → green; gate fails iff any `fail`.
8. **Unit tests** for the runner: verdict-mapping · precondition→notrun · skip_when→skip · expunge-filter · summary exit-code · catalog parse · results round-trip.

### Out of scope (later slices — do NOT build here)
- The actual oracles (C/C2/C3 = S2/S2b), workload generator (S3), runtime invariant probes I4/I5/I8/I9 (S4), fault injection (S6), perf harness (S7). S1 only builds the **contract + runner + catalog** they plug into.
- Migrating the *entire* existing lint fleet into the catalog — S1 folds **2 representative cases** (one lint, one live-probe) to prove both the pass-path and the notrun-path. Bulk migration is incremental, tracked, post-S1.
- Running a live Postgres/Redis service-container in CI to exercise a smoke's pass-path on CI — start `notrun`-on-CI (infra unavailable); graduate later (open item O1).

### Acceptance gate (definition of done) — LOCKED
All of in-scope 1–8 above, plus:
- `go test ./...` green in `tests/conformance/`.
- Runner executed locally against the real catalog: `projection-coverage-lint.sh` → **pass**; `publisher-live-smoke.sh` → **notrun** (no stack) or **pass** (stack up). JSONL emitted and inspected.
- `conformance-ci.yml` valid (actionlint if available) and exercised.
- `language-rule-lint.sh` still PASS (confirm the new Go module under `tests/` is not misread as a service — O3).

---

## 2. DESIGN — the runner

### 2.1 Shape: declarative catalog + Go runner
A **declarative YAML catalog** (matching the repo's `_registry.yaml` / `language-rule.yaml` conventions) lists cases; a **Go runner** loads it, evaluates preconditions, executes each case, maps the outcome to a verdict, and emits results. Declarative-catalog (not Go-registered cases) keeps case authorship open to non-Go contributors and keeps the runner generic.

```
tests/conformance/
  go.mod                              # new module: loreweave.dev/conformance (mirrors the repo's multi-go.mod layout)
  cmd/conformance/main.go             # entrypoint: load → run → emit → exit
  internal/
    catalog/   catalog.go  + _test    # YAML schema, load/parse/validate
    verdict/   verdict.go  + _test    # Verdict enum {pass|fail|notrun|skip} + Result struct + JSONL marshal
    runner/    runner.go   + _test    # precondition gate, exec, exit-code→verdict mapping, summary
    expunge/   expunge.go  + _test    # known-failures load + downgrade(fail→skip-expunged)
  catalog/
    generic/   projection-coverage.yaml   publisher-smoke.yaml
    expunge.yaml                      # known-failures, each row → Deferred-Items ref
  README.md
.github/workflows/conformance-ci.yml
```
*(`results/` JSONL is a run artifact — gitignored, uploaded by CI; not committed.)*

### 2.2 Case schema (`catalog/**/*.yaml`)
```yaml
id: projection-coverage          # unique, stable
description: "L3.B every event type accounted for (PRR-32)"
invariant: PRR-32                # optional I-ref / PRR-ref for traceability
kind: lint                       # lint | go-test | rust-test | live-probe
command: ["bash", "scripts/projection-coverage-lint.sh"]
requires: []                     # preconditions: docker | database_url | redis_url | ...
skip_when: []                    # stack predicates: single-superuser | no-provisioner | ...
fail_closed_on_setup_error: false  # exit>=2 → fail (true) vs notrun (false, default)
expunge: null                    # or a Deferred-Items id; presence downgrades fail→skip
```

### 2.3 Verdict mapping (the core contract)
| Situation | Verdict | Reason captured |
|---|---|---|
| `requires` unmet (no docker / no `DATABASE_URL`) | **notrun** | `"precondition unmet: <req>"` |
| `skip_when` predicate true (single-superuser, no-provisioner) | **skip** | `"not applicable: <pred>"` |
| exit 0 | **pass** | — |
| exit 1 | **fail** | stderr tail |
| exit ≥2 (misuse/setup), `fail_closed_on_setup_error=false` | **notrun** | `"harness/setup error: exit N"` |
| exit ≥2, `fail_closed_on_setup_error=true` | **fail** | stderr tail |
| would-be `fail` but `id ∈ expunge.yaml` | **skip** (expunged) | `"expunged → <deferred-id>"` |

Grounded in the real convention: lints exit `0=clean / 1=violation / 2=misuse` (`projection-coverage-lint.sh:15`). Live-probes need the docker stack (`publisher-live-smoke.sh:34`) → `requires: [docker]` → **notrun** when absent (matches the CLAUDE.md `"live infra unavailable"` token).

### 2.4 Results + summary
- Per case → one `Result{id, kind, verdict, reason, duration_ms, invariant}` line in JSONL.
- Summary to stdout: counts per verdict + the expunged/notrun/skip lists (never silent).
- **Exit code:** non-zero **iff** any verdict == `fail` (after expunge downgrade). `notrun`/`skip`/`pass` never fail the gate — this is what lets the live-stack half degrade to notrun on a dev box without flapping the gate.

### 2.5 CI (`conformance-ci.yml`)
Mirror `foundation-ci.yml` triggers (`push`/`PR` on `main` + `mmo-rpg/**`), `permissions: contents: read`. One job: checkout → `setup-go 1.25` → `go test ./...` (runner unit tests) → `go run ./cmd/conformance` (real catalog; `projection-coverage` runs in-CI = pass, `publisher-smoke` = notrun, no stack) → upload JSONL artifact. Green because notrun ≠ fail.

---

## 3. PLAN — build steps (TDD order)

1. **Scaffold** `tests/conformance/go.mod` (module `loreweave.dev/conformance`, go 1.25) + dir tree + `README.md` stub.
2. **`verdict/`** — `Verdict` enum + `Result` struct + JSONL marshal. **Test first:** round-trip + enum stringer.
3. **`catalog/` (internal)** — YAML schema struct + `Load(dir)` (walk, parse, validate unique ids). **Test first:** valid load, duplicate-id error, malformed-yaml error.
4. **`runner/`** — precondition gate (`requires`/`skip_when` evaluation against an injected environment probe), `exec` case, exit-code→verdict map, summary + exit-code logic. **Test first:** the §2.3 mapping table (0/1/2/2-fail-closed), requires-unmet→notrun, skip_when→skip, summary any-fail→non-zero.
5. **`expunge/`** — load `expunge.yaml`, `Downgrade(results)` fail→skip-expunged. **Test first:** expunged fail → skip, non-expunged fail stays fail, gate-break only on real fail.
6. **`cmd/conformance/main.go`** — wire load → run → expunge-downgrade → emit JSONL → summary → exit.
7. **Real catalog cases** — `catalog/generic/projection-coverage.yaml` (lint, requires:[]) + `catalog/generic/publisher-smoke.yaml` (live-probe, requires:[docker]); empty `expunge.yaml` with header comment + 1 example DEFERRED-ref row commented.
8. **`conformance-ci.yml`** — per §2.5.
9. **`.gitignore`** — add `tests/conformance/results/`.

### Test plan (acceptance #8) — all in `tests/conformance/`
verdict round-trip · catalog load(valid/dup/malformed) · mapping table 0/1/2/2-fc · requires→notrun · skip_when→skip · expunge downgrade · summary exit-code · (integration) run real catalog → assert projection-coverage=pass, publisher-smoke∈{pass,notrun}.

### VERIFY gate (phase 6)
- `cd tests/conformance && go test ./...` → green (paste output).
- `go run ./cmd/conformance --catalog ./catalog` locally → inspect JSONL: `projection-coverage=pass`; `publisher-smoke=notrun` (no stack) or `pass` (stack up). Paste summary.
- `language-rule-lint.sh` + `foundation-ci.yml` lints still PASS (O3).
- Live-smoke token: not a ≥2-service change (test tooling) → `"live infra unavailable: foundation-dev stack not booted at dev time"` unless the stack is bootable, in which case run `publisher-live-smoke.sh` through the runner for a real pass-path.

---

## 4. Risks & open items

**Risks**
- **R1 — new `go.mod` under `tests/`.** The repo already runs every `go.mod` (`foundation-ci.yml:52` finds all). `conformance-ci.yml` runs its own; confirm the foundation-ci find-loop building this module is harmless (it has no service deps). 
- **R2 — Windows dev.** Runner shells `bash scripts/*.sh`; local VERIFY on Windows needs Git Bash/WSL. CI is ubuntu (fine). Note in README.
- **R3 — catalog format bikeshed.** Chose YAML to match `_registry.yaml`/`language-rule.yaml`; schema-versioned via a top-level `version:` (O2).

**Open items (carry into BUILD, do not block)**
- **O1** — CI service-container (Postgres/Redis) to exercise a smoke's pass-path on CI vs `notrun`-on-CI. **Recommend:** notrun-on-CI for S1; graduate at S5/S8.
- **O2** — catalog schema `version:` field + migration discipline.
- **O3** — verify `language-rule-lint.sh` does not flag the `tests/conformance` Go module as an unmapped service (it gates `services/`); if it does, add a tests/ exclusion (small lint edit, tracked).
- **O4** — results JSONL retention: CI artifact (start) vs committed history. Start artifact.

---

## 5. Deferred-Items to add at COMMIT
- **D-CONFORMANCE-FLEET-MIGRATION** — fold the remaining ~26 lints + ~4 live-smokes into the catalog incrementally (S1 ships 2). Target: rolling, post-S1.
- **D-CONFORMANCE-CI-LIVE** (O1) — service-container pass-path for live-probes in CI. Target: S5/S8.
