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
- [ ] **R2** — **`gates` → `dp-clippy`.** Five of six self-test legs pass; `R-6` reported
  `MISCOUNTED: 0 finding(s), expected 3` while the same leg passes locally on the same pinned
  nightly. The last commit taught that branch to separate *the lint found nothing* from *the
  fixture never built* and to print the compiler output, so **read the new CI run before touching
  anything** — the answer should now be in the log rather than inferred.
- [ ] **R3** — **`lint-foundation` → `agentruntime-falsification`: CI says 13, the harness's own
  run says 2.**
  - 🔴 **A CORRECTION I AM CARRYING FORWARD RATHER THAN QUIETLY DROPPING.** The previous plan
    recorded "5 environment and 8 real", from an ad-hoc probe I wrote that drove the falsifiers
    one at a time through `_apply`/`_run_one` on a single shared mirror. The harness's **own**
    `--run --force`, finished afterwards, disagrees:

        400/408 falsifiers red the guard they name
        NOT FALSIFIABLE  test_the_CALL_SITE_arms_what_the_refusal_named
        NOT FALSIFIABLE  test_the_DIRECTIVE_for_this_arm_claims_nothing_it_did_not_measure

    **Two, not eight.** My probe over-reported by six — it reuses one mirror across every test
    while the harness manages its own lifecycle. The harness is authoritative and the probe is
    withdrawn. Both survivors were in the probe's list, so the six extra were the probe's fault,
    not a shrinking set.
  - **So the real split is unknown and must be measured, not inferred.** CI (no Postgres) reports
    13; this machine (Postgres reachable) reports 2. The 5 in `tests/test_cp0_merge_db.py` are
    DB-gated and explain part of the gap, but **5 + 2 ≠ 13** — six are still unaccounted for, and
    guessing which is what produced the withdrawn finding. The measurement that settles it is the
    harness's own run in an environment with no Postgres.
  - **What is safe to do now, independent of that count:** move the 5 DB-gated rows out of
    `FALSIFIERS` into the unproven backlog. The script's own note says a falsifier row for a
    DB-gated test "would read GREEN and be filed as `the guard requires nothing`, which is a lie
    about a guard that works", and a fix commit (`73b3189a8`) added them anyway.
  - 🔴 **The count is a trap, and it caught me once already.** The note says "THE 13 ROWS FROM
    `tests/test_cp0_merge_db.py`" and CI reports 13 findings — but only **5** live in that file.
    A matching count is not a matching population, in either direction.
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
