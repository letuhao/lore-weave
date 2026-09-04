# CI red, case by case — the 26 checks standing between this branch and `main`

Reconciles: Non-Vacuity (NV-1..6) · Foundation Lint Catalog (L1.K) — every row here ends in a
gate's verdict, and the failures it triages are mostly gates that reported a colour they had
not earned; L1.K is the catalogue those gates belong to.

PR [#219](https://github.com/letuhao1994/lore-weave/pull/219) · base `main` · head `refactor/kal-and-mcp-runtime`
· `mergeable: MERGEABLE` (no conflicts) · **`mergeStateStatus: UNSTABLE`**

Follows [`2026-09-04-gui-parity-triage-loop.md`](2026-09-04-gui-parity-triage-loop.md), whose board is
closed. This is the last thing before the merge.

---

## 0. The correction this plan opens with

I reported earlier that *"none of the failures appear to be mine"*. That was scoped to **this
session's commits** (`742fd34b0..HEAD`), where it is true — zero Rust, zero knowledge-service files.

Scoped to **the branch**, it is false, and the branch is what merges:

| failing area | files changed vs merge-base `df18e9049` |
|---|---:|
| `scripts/` | **616** |
| `services/knowledge-service/` | **414** |
| `crates/` | **166** |
| `services/glossary-service/` | **103** |
| `services/world-service/` | 64 |
| `services/meta*` | 20 |
| `crates/meta-rs/` | 12 |
| `crates/dp-control-plane/` | 7 |

**3,768 files** changed in total. And the three gates that crash inside `all-gates` —
`event-order-collision-gate.py`, `test_a_measured_turn_reaches_its_tool_gate.py`,
`test_synonym_spelling_variants_gate.py` — are all **files this branch added**. The branch owns them.

🔴 **`main`'s green is not a baseline.** Its last successful run for 7 of these 8 workflows is
**2026-08-09**, nearly a month ago against a tree 3,118 commits behind. "It was green on main" cannot
attribute anything here. The one workflow with a fresh main run — `conformance-ci`, 2026-09-04
11:59 — is **failing on main too**, which is the only pre-existing verdict that is actually measured.

---

## 1. What is red, measured 2026-09-04 from run `2a5cd293b`

**106 checks: 69 SUCCESS · 26 FAILURE · 11 SKIPPED.** The 26 are **22 distinct jobs** — the `gates`
workflow runs twice (push + pull_request), so its 4 failures are counted 8 times.

⚠️ **4 of the 26 do not block.** `dep-vuln`'s four audit jobs are `continue-on-error`: their checks
read FAILURE while the workflow conclusion is SUCCESS. **18 blocking job failures** is the real number.

| # | class | checks | blocking |
|---|---|---:|---|
| **C1** | Rust toolchain + workspace build | 6 (10 w/ dup) | yes |
| **C2** | `all-gates` — 10 red gates of 188 | 1 (2 w/ dup) | yes |
| **C3** | Go modules — glossary-service | 1 | yes |
| **C4** | knowledge-service python, unit + integration | 2 | yes |
| **C5** | DB round-trips + live-smoke | 4 | yes |
| **C6** | conformance-ci | 3 | yes |
| **C7** | agentruntime falsification + membrane | 2 | yes |
| **C8** | dep-vuln audits | 4 | **no — advisory** |

---

## 2. The evidence already in hand, so no row starts from zero

**C1 — one root cause may account for the whole class.** `rust-toolchain.toml` pins `1.89.0`; the
`gates` job reports:

    error: the 'cargo' binary, normally provided by the 'cargo' component,
    is not applicable to the '1.89.0-x86_64-...' toolchain

That is a **runner provisioning fault, not code** — and it is why `dp-aggregate-gate` and
`crate-purity-gate` (`cargo metadata` failed) are red. But `dp-clippy` installs
`nightly-2025-09-12` separately, and `foundation-ci`'s `cargo build --workspace` dies on something
else entirely:

    error: failed to run custom build command for `dp-control-plane v0.1.0`

**So C1 is at least two faults, not one.** Prove which checks share a cause before fixing any of them.

**C2 — the 10 named red gates**, out of 188 discovered (`gate-wiring-gate: OK — 188 gate(s)
discovered, 6 exempt, 0 tracked-red`):

| gate | first line of its failure | reading |
|---|---|---|
| `dp-aggregate-gate.py` | cargo not applicable to 1.89.0 | C1 |
| `crate-purity-gate.py` | `cargo metadata` failed | C1 |
| `dp-oracle-bite-gate.py` | doc/code pair, broken | likely C1 |
| `dp-slice5c-bite-gate.py` | gRPC guards, each removed | likely C1 |
| `gate-number-visibility-gate.py` | `MAX_COLLIDING_PAIRS = 51 never reaches the output` | **one-line fix** |
| `test_a_measured_turn_reaches_its_tool_gate.py` | `Traceback` | **branch-added, crashes** |
| `test_synonym_spelling_variants_gate.py` | `Traceback` | **branch-added, crashes** |
| `agentruntime-membrane-gate.py` | selftest OK, then fails | real finding |
| `phase0-reconcile-gate.py` | SELFTEST PASS, then fails | real finding |
| `graph-tenancy-coupling-gate.py` | `traversal_filters_project=False` | real finding |

⚠️ **A crashing gate is not a passing gate and not a failing one** — it is a gate with no verdict.
Two of them are this branch's own files, which makes them the same defect class as `UNTRIAGED`.

⚠️ `gate-number-visibility-gate` fails over **`event-order-collision-gate.py`**, also branch-added:
its ratchet `MAX_COLLIDING_PAIRS = 51` is never printed on the pass path. Print it or declare it in
`SILENT_BY_DESIGN` — the same ratchet-visibility rule this branch has already applied twice.

**C3 — the one that looks like a genuine merge regression.** `go module failed:
./services/glossary-service`, on two separate points:

    entity_lifecycle_ledger_test.go:154: the chokepoint no longer writes the ledger
    recalc_restore_test.go:43: chain has no step "0060_glossary_recalc_restore"

The first is **the exact hazard the merge plan predicted** — `executor.py:632 silently disables FE's
P7 chokepoint`. The second says a migration step vanished from the chain, which on this repo is the
`DDL-in-an-applied-ledger-step` family. Neither is infra. Treat C3 as the highest-severity row even
though it is one check.

**C6 is red on `main` today.** Its `S7/F2 perf micro-bench gate` fails at `install benchstat` — a
network step. Attribute before touching.

---

## 3. Board

- [x] **T1** — **DONE. C1 was never one class: it was FOUR unrelated faults, and one member is not
  even Rust.** Rule 7 earned its place on the first row.
  - **A — `protoc` is installed by NO workflow in this repo.** `crates/dp-control-plane` is a
    workspace member whose build.rs runs tonic-build, so `cargo build --workspace` died at BUILD and
    everything downstream of it was dark, not passing. Added to `foundation-ci/rust` and `dp-clippy`.
  - **B — `all-gates` had no Rust toolchain at all.** The three `rust-toolchain@` uses in gates.yml
    are all in the *other* jobs; `ubuntu-latest` ships rustup, so cargo resolved and then died on the
    `1.89.0` pin. All four cargo gates pass locally against 1.89.0 — pure provisioning. Provisioned
    rather than skipped, so four real static gates stay in CI.
  - **C — `lints/dp-clippy/run-lint.sh` was mode `100644` in git.** `./run-lint.sh` → Permission
    denied, exit 126. One `git update-index --chmod=+x`.
  - **D — `rust-mutations` and `reality-layer-mutations` were not infra, and the second is Go.**
    Both were reporting *dead pointers as findings about the code*:
    - `rust-mutations`: 1 of 26 survived — `NOTEST … selected nothing`. The row named
      `actor::tests::existence_…` with `--lib`, but the test is an INTEGRATION test in
      `tests/hub.rs`. Now `26/26 RED, 0 NOTEST`, exit 0.
    - `reality-layer-mutations`: 4 bites unproven — one anchor matching **2x**, one matching **0x**
      (the code was refactored out from under it), and two naming tests **that do not exist anywhere
      in this repository**. Now `all 37 guards proved load-bearing (15 go + 16 rust + 6 meta)`.
  - 🔴 **The mechanism defect behind D, which is the real finding.** `go test -run <nonexistent>`
    exits **0** and prints `[no tests to run]`, so the harness reported a missing test as
    `[VACUOUS] … stayed GREEN with the guard broken` — *the guard is weak* — when the truth was
    *the bite never ran*. The Rust branch of that same file has guarded against this since it was
    written; the Go branches never got it. Carried across as `[NOTEST]`, and three GDPR erasure
    obligations that had read as measured for their whole existence now have tests
    (`scrubber_obligations_test.go`).
- [x] **T2** — **DONE for 9 of 10; the 10th (`agentruntime-membrane-gate`) is adjudicated in T7,
  where its other CI home is.** Not one of the nine was "a gate finding a bug in the code". Every
  one was a gate reporting a colour it had not earned, and **four of them were GREEN on a dev box
  and RED in CI** — the shape gates.yml's own PyYAML comment already warns about.
  - **Four (`dp-aggregate`, `crate-purity`, `dp-oracle`, `dp-slice5c`)** were T1's fault B. All pass
    locally against cargo 1.89.0; `dp-oracle` 19/19 bitten, `dp-slice5c` 7/7.
  - 🔴 **Two `Traceback`s exposed a much larger hole.** `gate-wiring-gate` invokes gates as
    `python <file>`, and a pytest module has no `__main__` — so the call **defines its test
    functions and exits 0 having asserted nothing**. Seven were in the run list; **21** were being
    invoked this way in total. Four reported **GREEN over 29 assertions that never ran**. The two
    REDs were the only honest ones, and only by accident: they end their import guard with
    `pytest.skip(..., allow_module_level=True)`, which raises outside a pytest run. The file's own
    comment already said these "get EXEMPT rows" — two of twenty-one had one. Now COMPUTED from the
    structure (`test_*.py` with no `__main__`), not listed, so a pytest gate written tomorrow is
    exempt the day it lands and one that grows a `__main__` returns to scope. Their real home is
    foundation-ci's `gate red-ability proofs` step, which runs all of them properly.
  - **`gate-number-visibility-gate` was the wrong diagnosis, not a one-line fix.** It reported
    `MAX_COLLIDING_PAIRS = 51 never reaches the output` for a gate that is in `NEEDS_STACK` — CI has
    no AGE store, so it never printed anything, while a dev box runs it and the finding evaporates.
    The repair it demanded would have fixed nothing. Live-stack gates are now reported **UNVERIFIED**
    on both paths (2 of them, incl. `causal-coverage-gate`, which was also passing on an
    unsupportable verdict), reading `NEEDS_STACK` from gate-wiring-gate as the SSOT.
  - **`graph-tenancy-coupling-gate` had stopped calling the function it exists to call.**
    `id_is_project_scoped=None` in CI, `True` locally: importing `loreweave_extraction.canonical`
    runs the package `__init__`, which pulls httpx, pydantic, bs4 and three opentelemetry
    distributions. Now falls back to a package-init-free load (both modules are stdlib-only), so CI
    calls the real function instead of degrading to `None`.
  - **`phase0-reconcile-gate` was right, and I was one of the four offenders.** All four plan docs
    missing a `Reconciles:` line were written in this session; the fifth failure was a wrapped
    `Reconciles:` whose continuation line became a phantom row. Now 61 specs checked, all green.
- [x] **T3** — **DONE, and the severity call was wrong in the safest direction.** I ranked this
  highest because `the chokepoint no longer writes the ledger` reads like the merge hazard the
  merge plan predicted at `executor.py:632`. It is not a regression: **both failures are stale
  tests, and the production code is correct and better than what the tests describe.** Worth
  saying plainly — the alarm was loud, specific, and wrong, and only reading the code showed it.
  - **The migration three** named `0060_glossary_recalc_restore`. Nothing was lost: the merge
    **renumbered** the pair to `0067`/`0068` (`0060` is now `0060_seed_genre_kind_attributes` from
    the other side), and a second repair pair `0069`/`0070` was added when 0067 turned out to have
    been reverted on the running database. Renumbering on merge is this ledger's normal practice —
    it carries three MERGE notes saying so. Re-anchored on the **function and the order** instead
    of the number, so the next renumber cannot break them *or* hide a real removal. Bitten both
    ways.
  - 🔴 **The chokepoint test was reading a 214-character alias through a 3,000-character window.**
    T28 moved the SQL and its `glossary.entity_status_changed` emission together into
    `setEntityStatusCore`; `bulkSetEntityStatusCore` survives as a wrapper that "deliberately holds
    no SQL of its own". The old guard read `src[i : i+3000]` from the wrapper, found nothing, and
    reported a lost audit trail. The guarantee is now the same **TRANSACTION** rather than the same
    **STATEMENT** — stronger, and enforced in a signature: `appendLifecycleLedgerTx` takes a
    `pgx.Tx` and no pool, so its row cannot commit independently. Every property the old test
    asserted still holds (`FOR UPDATE` kept; `IS DISTINCT FROM` is now the Go `continue`).
  - ⚠️ **Two guard-shape defects fixed while here**, both of which fail quietly: the fixed-size
    window (it measures the file's layout, not the function, and reads the *next* function's code
    when the target shrinks), and CRLF. This package is **mixed** — `entity_handler.go` is
    1780/1780 CRLF while the other two files are pure LF — so a source guard that is not
    line-ending agnostic silently covers whichever half it was written on.
  - Evidence: `go test ./...` in glossary-service — **10 packages ok, 0 FAIL**. Five bites, each
    red for its own reason and none via a build failure, all restored byte-exact.

- [x] **T1b** — **the two follow-ons the first CI re-run exposed.** Fixing a check does not always
  make it green; sometimes it just lets it fail further along, and that is progress worth naming.
  - **`dp-clippy` got past `Permission denied` and died on the next line.**
    `BUILD PRODUCED NO CDYLIB: nothing matched target/debug/dp_clippy.{dll,so,dylib}` — that is the
    **Windows** spelling, and the only platform this script had ever run on. Linux emits
    `libdp_clippy.so`. The `lib` prefix is now carried through to the destination too, because
    dylint builds the name it searches for from the platform convention and a library it cannot
    see fails as `No libraries were found.` with **exit 0** — the exact silent pass `assert_loaded`
    exists to refuse.
  - 🔴 **`Secret scan (gitleaks)` went red, and it is NOT one of the original 26.** It was SUCCESS
    at `2a5cd293b`. **All 10 findings are false positives and none is from this session** (commits
    dated 2026-08-05 … 2026-08-23): a self-describing test JWT
    (`test_secret_at_least_32_chars_long_xx`, ×3 spec files), a `dev_internal_token` header shown
    against `http://localhost:28216` in the isolated-stack runbook, and — four times over, once per
    agent-config directory — **a security checklist's own counter-example**,
    `const API_KEY = "sk_live_abc123";` sitting under the heading *"❌ Secrets in code"*.
    Allowlisted as three **exact literals**, never by path: a path entry for
    `services/knowledge-gateway/test/` or `.claude/skills/` would blind the scanner to a real
    secret committed there tomorrow.
- [ ] **T4** — **C4, knowledge-service.** Unit fails outright; integration fails **building the
  Postgres image** (PG18 + pgvector + pgvectorscale + AGE) — separate faults, so separate verdicts.
- [ ] **T5** — **C5, the four DB jobs.** Three round-trip jobs plus `create meta smoke DB`. If one
  migration or one image explains all four, that is one fix; prove it rather than assuming it.
- [ ] **T6** — **C6, conformance-ci.** 🔴 Red on `main` today — attribute each of the three before
  fixing. `install benchstat` is a network step and probably not ours.
- [ ] **T7** — **C7, agentruntime.** Falsification + membrane. ⚠️ The two untracked
  `contracts/agentruntime-*-verdict.json` files in the working tree are evidence to read first, and
  a falsification verdict can be vacuous — check its bar before believing either colour.
- [ ] **T8** — **C8, the advisory four.** Non-blocking by construction. Either fix or record why
  shipping with them red is acceptable, so the next reader does not re-open this.
- [ ] **D3** — **STOP.** `platform_models` is empty, so the model story is BYOK. Is BYOK-only the
  intended first-release posture? Owner's call, carried over unanswered.
- [ ] **D4** — **STOP.** One cloud-model run; everything so far is proven on one local model. Costs
  money, needs an explicit yes and a stated call count. Carried over unanswered.
- [ ] **D5** — **STOP.** Merge with C8 advisory-red, or block on it? Owner's call.

---

## 4. What "resolved" means, so the row cannot be ticked cheaply

A row closes when every check in its class is **GREEN**, or **declared** with a reason a stranger can
audit: a `KNOWN_RED` row naming a tracked deferral, an advisory job's accepted-risk note, or a
measured attribution to runner infrastructure. **A red check with no verdict is the failure this plan
exists to end**, and it is the same defect as an `UNTRIAGED` parity row.

🔴 **Re-run before believing a fix.** A green local run proves the fix compiles here; only the PR's
own checks prove it in CI. And re-run the FULL workflow — a subset run hides the regression you
just shipped.

**RESUME: T1 — separate the Rust faults, the class that is 6 of the 18 blocking failures**

---

```goal-prompt
goal: every one of the 26 red checks on PR 219 carries a verdict - fixed, or declared with a reason a stranger can audit - and the branch is fit to merge to main
po_decisions: [D3, D4, D5]
rules: |
  1 $0. Local models only. A PAID run needs an explicit yes and its CALL COUNT stated first. platform_models is EMPTY - keep it that way.
  2 main's green is NOT a baseline: its last pass for 7 of 8 workflows is 2026-08-09, 3118 commits behind. Never attribute by "it was green on main".
  3 Attribute a red thing BEFORE fixing it. The branch changed 3768 files and touches every failing area, so "not mine" needs the BRANCH diff, not the session diff.
  4 A crashing gate (Traceback) has NO verdict - neither pass nor fail. Same defect class as UNTRIAGED.
  5 A check that stays red leaves with a KNOWN_RED row naming a tracked deferral, or an accepted-risk note. Never silently.
  6 dep-vuln's 4 checks are continue-on-error and do NOT block. 18 blocking failures is the real number; do not pool the 26.
  7 Two Rust errors that look alike may be different faults. Prove a shared root cause before applying one fix to a class.
  8 Re-run the FULL workflow to confirm a fix. A local green proves it compiles here, not in CI; a subset run hides the regression you shipped.
  9 conformance-ci is red on main TODAY - the only measured pre-existing verdict. Everything else needs its own attribution.
  10 Never merge or push to main without an explicit yes. Merging is outward-facing and the owner's call.
discipline: |
  A pipe to head/tail reports the PIPE's exit, not the command's. Capture to a file when the exit code matters.
  sed -i rewrites every line ending on this repo's CRLF files - edit with Python or Edit, and check cmp AND git diff --stat after a bite.
  Verify the pointer before declaring evidence missing, and grep for the route before blaming a service.
  A falsification verdict can be vacuous - check what its bar actually asserts before believing either colour.
  Numerator and denominator must measure the same population - stratify before pooling.
stop: |
  a write would touch a non-throwaway book or database
  a run would call a model that is not local
  a merge or push to main is about to happen
  a product decision is owed: D3, D4, D5
```
