# The last three, and the guards that do not guard

Reconciles: Non-Vacuity (NV-1..6) · Foundation Lint Catalog (L1.K) — the rows below are gate
verdicts, and the two that remain are a gate whose message could not name its own fault and a
falsifier set whose count means different things in different environments.

Continues [`2026-09-04-ci-red-triage-before-main.md`](2026-09-04-ci-red-triage-before-main.md),
whose board is closed. That plan took PR [#219](https://github.com/letuhao1994/lore-weave/pull/219)
from **26 red checks to 7**.

---

## 0. Where it actually stands, measured 2026-09-05

`gh pr checks 219` — **124 checks: 58 SUCCESS · 7 FAILURE · 11 SKIPPED · 48 still running.**

| workflow | state |
|---|---|
| `Game subtree CI`, `deploy`, `lint` | **green** |
| `python-unit-tests` | 16 green, 3 running |
| `python-integration-tests` | 10 green, 4 running |
| `foundation-ci` | 5 green, 4 running |
| `lint-foundation` | 5 green, 4 running, 21 queued |
| `conformance-ci` | 3 green, 6 skipped, 6 running |
| **`domain-db-smoke`** | 2 green, **1 RED** |
| **`gates`** | 4 green, **`dp-clippy` RED** |
| **`dep-vuln`** | **4 RED — advisory, non-blocking** |

⚠️ **48 checks have not settled**, so this board is a floor and not a total. Every fix in the
previous plan revealed the next failure behind it — the image build that unblocked the tests that
then failed on AGE, the exec bit that unblocked the lint that then failed on a cdylib name. Assume
that continues.

---

## 1. Board

- [x] **R1** — **DONE. TWO tests, not one, and the nil-pointer panic was a red herring.** That
  `panic="runtime error: invalid memory address or nil pointer dereference"` is a *recovered* panic
  logged by an unrelated handler; the actual failures were two assertions. Both are **pre-existing
  and were invisible** — `f_dbsmoke` shows neither, because the book-service test T5 fixed failed
  first and the job's `set -euo pipefail` never reached the glossary step. Rule 6, fourth time.
  - **A stale vocabulary.** `TestStatusChangeAppendsToTheLifecycleLedger` asserted
    `op == "status_change"`; the code writes `"status_changed"`. **Two vocabularies**:
    `status_change` is the confirm-token / propose-tool action (`descStatusChange`), while the
    LEDGER's op is fixed by migration 0063's own column comment — *"`status_changed` /
    `kind_reassigned`. Deliberately the same vocabulary as the outbox event's `op`, so a ledger row
    and its event can be read side by side without a mapping table that would itself drift."* The
    event is `glossary.entity_status_changed`. The code was right. Bitten: flipping the production
    op reds the test with a message naming the distinction.
  - 🔴 **A flake with a guaranteed tie, not a race.** `TestReassignKind_EmitsUpdatedCarryingTheNewKind`
    passed in one CI run and failed the next on the same commit, and passes locally every time.
    Three reads in that file take `LIMIT 1` off `ORDER BY created_at DESC` with **no tiebreaker** —
    and `outbox_events.created_at` defaults to `now()`, which in Postgres is **transaction-start**
    time, so rows written in one transaction are byte-identical. Measured: two rows inserted 50ms
    apart in one tx → `distinct_created_at=1`. Reproduced the CI failure verbatim on a scratch
    table: `WITHOUT tiebreaker -> terminology` (the OLD kind, exactly what CI reported) and
    `WITH tiebreaker -> generic`. `id` is `uuidv7()` and therefore time-ordered, so `, id DESC` is
    a real monotonic tiebreaker — which `entity_command_parity_test.go` in the same package was
    already using.
  - ⚠️ **One local-only failure, attributed and left alone.**
    `TestSystemAttrDescriptions_SeedsDescriptionsAndRefreshesHash` fails here
    (`pre-migration empty descriptions = 3, want 93`) and appears **nowhere** in the CI log for
    this job. It drives migration step functions directly, which is the ApplyOnce-bypass shape;
    it is my environment, not a CI row, and inventing a fix for it would be work nobody asked for.
  - Evidence: `go -C services/glossary-service test ./internal/api/... -count=1` **exit 0** and
    `go -C services/book-service test ./internal/api/... -count=1` **exit 0** — CI's exact
    commands, each against a fresh throwaway database.
- [~] **R2** — **the self-test is FIXED and verified under CI's own environment. The step behind it
  is a real architectural finding and becomes D7.**
  - 🔴 **The whole difference was ANSI colour.** Every verdict in `run-lint.sh` is a `grep`, and
    the R-6 leg *counts* lines matching `^error: \`.`. The runner exports
    `CARGO_TERM_COLOR: always`, so in CI those lines begin with an escape sequence and the anchor
    matched nothing. Measured on this tree, same pinned nightly, one variable changed:
    **without colour → 3** (correct), **`CARGO_TERM_COLOR=always` → 0** (what CI counted). Forced
    to `never` inside `lint()` — one place, and it makes every leg deterministic instead of
    dependent on whoever set the environment. Self-test now exits **0 under both** environments.
  - ⚠️ **And my own diagnostic from the previous cycle was wrong in an instructive way.** It keyed
    the build-failure branch on `could not compile` — which is *exactly what a firing lint
    produces*, because dylint reports each finding as an `error:` and cargo then says "due to 3
    previous errors". So the branch written to tell a dead fixture from a weak rule announced the
    rule's **success** as a build failure. It now keys on `error[E####]`, a code only rustc emits.
  - 🔴 **D7 — the step after it.** With the self-test passing, `dp-clippy-gate.py` finally runs,
    and the ratchet refuses:

        WORSE: `commit-service` went 3 -> 4 DP-R3 finding(s).
        WORSE: `world-service`  went 5 -> 12 DP-R3 finding(s).

    All 12 are `sqlx::PgPool` held directly in a non-SDK crate. **7 of those 12 files do not exist
    at the merge-base** — exactly the 5→12 increase — so this branch is introducing them. This
    session touched **zero** files in either service. `world-service` already depends on the dp SDK
    (`dp::RealityId`) while constructing and holding its own pool, which is the precise question
    DP-R3 asks, and `server/db.rs` is pool construction carrying a connection guard. That is an
    architecture change, not CI triage.
- [x] **R5** — **DONE. `DB live-smoke` was six suites taking a writer lease on a channel that
  did not exist.** 23503 on `channel_writer_state_channel_fk`, and the tests were not broken by
  a test-only detail: they were writing the exact row `0027_channel_writer_state_fk` exists to
  forbid. It is a `NOT VALID` ratchet — history unscanned, every NEW write enforced — and its
  own header calls the orphans it found *"the DEFECT the key exists to prevent"*. So: seed the
  channel, never weaken the key.
  - 🔴 **A bare `ON CONFLICT DO NOTHING` made the seed a silent no-op, and that was my first
    attempt.** `channels_root_single` is UNIQUE (reality_id) WHERE parent IS NULL, so a bare
    clause swallows a *second root in the same reality* — the conflict it eats is not the one
    you meant. Narrowed to `ON CONFLICT (reality_id, id)`. `failover.rs`'s two multi-channel
    tests then needed 10 as the root and 11 as its **child**, which is the shape the constraint
    was telling me about all along.
  - ✅ **Proven load-bearing, not assumed.** With the four seed calls removed,
    `epoch-activation` returns the identical 23503 the CI log shows. Restored byte-exact
    (`cmp`), never with `git checkout --`.
  - ✅ **`live-suites.py`: 25 passed of 27.** The two not-passed are `world-embedding` and
    `world-provisioner-reentry`, both failing to apply `0008_pgvector_setup` because the LOCAL
    postgres image has no pgvector. CI's image does — **not** a CI failure, and the row is not
    closed on that basis but on CI going green. Pushed as `dbbc7e795`.

- [ ] **R3** — **`lint-foundation` → `agentruntime-falsification`: CI says 13, the harness's own
  run says 2.**
  - 🔴 **I WITHDREW A CORRECT FINDING, AND THE MEASUREMENT PUT IT BACK. Both corrections stand
    here.** The original reading was *"5 environment and 8 real"*. I withdrew it after the
    harness's own `--run --force` appeared to say **two** — and it did not. I read `tail -3` of
    that run and took the last two lines for the whole list. The full log has **eight**, and they
    are exactly the eight the probe named. The probe was right; the withdrawal was a truncated
    read, which is the failure my own notes call *"a pipe to tail reports the PIPE's exit"* wearing
    different clothes.
  - **Now measured both ways, and the arithmetic is exact:**

    | environment | falsifiers reddening | NOT FALSIFIABLE |
    |---|---|---|
    | Postgres reachable | 400/408 | **8** |
    | Postgres unreachable | 395/408 | **13** |
    | **CI** | **395/408** | **13** |

    The no-Postgres run reproduces CI **exactly** — same ratio, same 13 names. And
    `13 − 8 = 5`, those five being precisely the DB-gated rows in `tests/test_cp0_merge_db.py`,
    with the 8 a strict subset of the 13. Nothing is left unaccounted for.
  - ✅ **The 5 are handled.** Moved out of `FALSIFIERS` into the unproven backlog, which the
    script's own note prescribes: a falsifier row for a DB-gated test *"would read GREEN and be
    filed as `the guard requires nothing`, which is a lie about a guard that works"*. Partition
    kept exact — 798 = 403 + 2 + 393.
  - 🔴 **The 8 are real, and they are the row's remaining work.** They reddened nothing with a
    Postgres present *and* absent, and `_apply` raises on a stale anchor, so the edits landed and
    the guards did not notice. Each needs a case that exercises the mutated path — e.g.
    `test_THE_UNION_DERIVES_COMPLETELY`'s falsifier makes derivation skip a tool with no name, and
    the test has no nameless-tool case. That is test-authoring, one analysis per guard.
  - ⚠️ **The count in the script's note was a trap in both directions.** It said "THE 13 ROWS FROM
    `tests/test_cp0_merge_db.py`" while that file has 20 tests and exactly 5 falsifier rows.
    Reading the note forward closes 8 real findings as environment; reading a truncated log
    backward withdraws them. Header corrected.
- [ ] **R4** — **The 48 unsettled checks.** Not a wait: a row. When they land, triage anything new
  the same way — attribute before fixing, and expect a fix to reveal the next failure rather than
  end the chain. `conformance-ci`, `foundation-ci`, `lint-foundation` and
  `python-integration-tests` all carry fixes pushed but never yet observed green.
- [ ] **D3** — **STOP.** `platform_models` is empty, so the model story is BYOK, and the UI says so
  at the point of failure and the point of repair. Is BYOK-only the intended first-release
  posture? Owner's call, carried unanswered since 2026-09-04.
- [ ] **D4** — **STOP.** One cloud-model run; everything is proven on one local model. Costs money,
  needs an explicit yes and a stated call count. Carried unanswered.
- [ ] **D5** — **STOP.** Merge with `dep-vuln` advisory-red, or block on it?
- [ ] **D7** — **STOP. `world-service` and DP-R3: adopt, declare, or record.** The branch adds 7
  new files holding a raw `sqlx::PgPool` in a non-SDK crate, taking the ratchet 5 → 12 (plus
  3 → 4 in `commit-service`). The ratchet is doing its job; the question is which answer is right.
  **(a) Adopt** — route world-service's data access through the dp SDK. The correct answer by
  DP-R3's own wording, and a real refactor of a service's data layer across 12 files, with its own
  test cycle. **(b) Declare** — give world-service `[package.metadata.dp] dp-crate = true`, the
  marker that exempts a crate legitimately holding a client. Cheap, and honest *if* world-service
  is meant to be part of the data plane — which is exactly the design question, not a formality.
  **(c) Record** — raise the baseline to 12/4 with the reason written in, so the debt is visible
  and can only shrink. ⚠️ (c) weakens a ratchet without doing the work it exists to force, which
  this repo's own convention warns against; it is listed because a permanently-red check on an
  otherwise-ready merge is its own cost.
- [ ] **D6** — **STOP. The first release's security posture.** Real advisories in all four
  ecosystems, none blocking: `rsa` (Marvin Attack, key recovery via timing — **no patched
  release**), `google.golang.org/grpc` (GO-2026-6061), `h2`, `quinn-proto`, `crossbeam-epoch`, 21
  JS findings, and `datasets 2.21.0` (PYSEC-2026-3716, fix is a 2.x→5.x major). Three ways:
  **(a)** bump everything now and take the regression risk on a branch 3,100+ commits ahead;
  **(b)** only what is cheap and safe — move `datasets` to `requirements-test.txt`, where its own
  comment says it belongs and which drops ~500MB–1GB from the runtime image; **(c)** accept,
  record, and schedule the bumps as their own change with their own test cycle.

---

## 2. What "cleared" means here

A row closes when its check is **GREEN in CI** — not locally — or when it carries a verdict a
stranger can audit: a `KNOWN_RED` row naming a tracked deferral, or an accepted-risk note.

🔴 **The two habits that did the work last time, kept.** Every fix was reproduced *before* it was
written and bitten *after*, restoring byte-exact; and every "obvious cause" was checked against a
control that could refute it. That is what caught a drift test being pointed at a table its own
migration drops, a route walk verified against the wrong FastAPI, and a `latest` image that turned
out to still carry the file it was blamed for losing.

**RESUME: R1 — the ledger panic, the only non-advisory red that is not a gate reporting on itself**

---

```goal-prompt
goal: the last three red checks on PR 219 are green in CI or carry an auditable verdict, and the 48 unsettled ones are triaged as they land
po_decisions: [D3, D4, D5, D6]
rules: |
  1 $0. Local models only. A PAID run needs an explicit yes and its CALL COUNT stated first. platform_models is EMPTY - keep it that way.
  2 GREEN IN CI closes a row, not green locally. Three defects last cycle passed on this machine and failed on Linux: file-locking scope, a lib prefix, a FastAPI version never installed here.
  3 Reproduce BEFORE fixing and BITE after, restoring byte-exact. A test you watched fail is evidence; one you wrote is not.
  4 Chase the control that refutes you. It caught a table that migration 0018 DROPS, a route walk checked against the wrong version, and a `latest` image that still had the file it was blamed for.
  5 A matching COUNT is not a matching population - 13 findings, 13 rows in a note, and only 5 were the same 5.
  6 Expect a fix to reveal the next failure rather than end the chain. That happened four times last cycle.
  7 dep-vuln's 4 are continue-on-error and do NOT block. They are D6, not a row to fix quietly.
  8 A check that stays red leaves with a KNOWN_RED row naming a tracked deferral, or an accepted-risk note. Never silently.
  9 Never merge or push to main without an explicit yes.
discipline: |
  A pipe to head/tail reports the PIPE's exit, not the command's. Capture to a file when the exit code matters.
  sed -i rewrites every line ending on this repo's CRLF files, and this tree is MIXED even inside one package - edit with Python or Edit.
  Don't build source containing \n or \t through a heredoc'd python; it ate the escapes three times.
  testsafe refuses a DB whose name carries no test/smoke/scratch/tmp marker, and pg_isready answers during initdb's TEMPORARY server - wait for the second "ready to accept connections".
  A guard that cannot name its own fault sends the next reader at the wrong thing.
stop: |
  a write would touch a non-throwaway book or database
  a run would call a model that is not local
  a merge or push to main is about to happen
  a product decision is owed: D3, D4, D5, D6
```
