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
- [x] **R2** — **✅ CONFIRMED GREEN IN CI, not merely locally.** The `dp-clippy` job's
  `run-lint.sh --self-test` step now prints all six OK lines on the runner: it fires on a raw
  `sqlx::PgPool` import, is silent on a crate with no kernel client, exempts a declared
  `dp-crate`, reds the SAME crate without the marker, fires on exactly the 3 discards and not
  the 2 legitimate uses, and loads the library with both lints registered. The job is still
  red, but one step LATER — at `dp-clippy-gate.py`, which is D7 and a decision.

- [x] **R2 (original text)** — **the self-test is FIXED and verified under CI's own environment. The step behind it
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

- [x] **R6** - **DONE. `Domain DB round-trips` was an ALIAS read as a canonical code, and my
  first fix was WRONG.** I blamed a `created_at` tie (Postgres `now()` is transaction-start, so
  rows written in one tx share a byte-identical timestamp) and added `, id DESC`. The red SURVIVED.
  - 🔴 **The refutation came from LOOPING the test, not from re-reading it.** 2 failures in
    25 runs, and the second pair named the mechanism: `faction`->`organization` beside
    `generic`->`terminology`. Both alias->canonical. `loadKindMap` folds `entity_kind_aliases` into
    the same map, so its keys are a MIXTURE - and **Go randomises map iteration**, so the test
    failed on exactly the runs that landed on an alias key.
  - ✅ **Confirmed in the DATABASE, not by reading code:** `organization` and `terminology`
    are real `book_kinds` rows; `faction` and `generic` exist ONLY in `entity_kind_aliases`. The
    production path was correct throughout - the entity moved, and the payload carried that kind's
    canonical code. The expectation resolves from the target ID now: 0 of 30 after. The `, id DESC`
    stays (the tie is real and latent) but its comment no longer claims to explain this failure.

- [x] **R7** - **DONE. `Foundation lints` was 9 live tool descriptions pointing at RETIRED tools -
  and fixing it revealed a second gate demanding the OPPOSITE.**
  - **Attributed first:** the same scan exits 0 against `origin/main`, so all nine arrived with
    this branch. `DEAD_TO_DEAD_BASELINE` held at exactly 9 throughout.
  - 🔴 **My first fix replaced the names with PROSE, and six tests went red saying "name the
    tool".** `Go modules`, `Domain DB round-trips`, `all-gates` and `translation-service (pytest,
    unit)`. Two gates, opposite demands, and **neither is wrong**: naming a tool the model cannot
    see sends it into a discovery loop; naming none leaves it with no move.
  - ✅ **The way out was in the retired tools' own registrations.** Four declare a successor -
    `book_list_chapters` -> `book_list with kind=chapters`, `glossary_book_patch` ->
    `glossary_ontology_upsert`, `glossary_propose_kinds` -> `glossary_propose_batch`. Source AND
    tests moved to the successor, so each assertion keeps its meaning while naming a tool that is
    actually on the surface.
  - 🔴 **The scan never told me those successors existed, and that is its own defect.** It
    reported "NO replacement declared" because its regex stops at the first comma inside a nested
    `WithSupersededBy(WithVisibility(NewToolMeta(...)), "successor")`. Its own header calls
    under-reporting *"the dangerous failure for this tool: a missed finding looks exactly like a
    clean scan"*. **Not fixed - RECORDED.** Every affected site is handled and the scan is green.
  - 🔴 **One of the nine I got wrong on the merits, and reverted.** `glossary_user_restore`
    has NO successor, and `ontology_delete_summary_test` carries a MEASURED correction: it revives
    the row (status `restored`, `deleted_at` cleared) and is the only thing that does. My edit said
    *"there is no restore tool to find"* - false, and false in the direction that tells a user
    their delete is permanent when it is not. The description now names it AND says it is
    DEPRECATED with no successor: true, what the caller needs, and it satisfies the scan through
    the exemption it ALREADY has for a description carrying its own deprecation pointer. **No gate
    was modified to make this pass.**
  - **BITE:** change that one `DEPRECATED` to `retired` and the scan exits 1, naming line 70 /
    `glossary_user_restore`. Restored byte-exact (`cmp` clean, diff 3/2).

- [x] **R8** - **DONE. The step CI had never REACHED: `gate red-ability proofs`, 19 failures.**
  Hidden behind the deprecated-tool-scan failure by the job's `set -euo pipefail`. Rule 6 again.
  - 🔴 **The dominant cause is that the INVESTIGATION FINISHED.** 68 deferred questions: 64
    answered, 4 withdrawn. 222 defects: 185 fixed, 28 withdrawn, 8 cannot_reproduce, 1 superseded.
    **Nothing is open** - and nine guards asserted that open work exists. One borrowed a live open
    row to mutate and its `next(...)` raised `StopIteration`, taking FIVE proofs down with it. Each
    is re-anchored on its invariant and CROSS-DERIVED so it still cannot pass vacuously: the
    generator, the raw ledger and the queue must independently agree on zero.
  - ✅ **A real SDK defect found on the way.** The Python kit registered `task_id: str` bare,
    so FastMCP advertised a schema with a title and a type and NO description - the model told a
    value is mandatory and nothing about where to get one. The catalogue shows the split exactly:
    Go-kit tools carry `description`, Python-kit tools carry `title`. One fix repairs both
    `composition_task_provide_input` and `translation_task_provide_input`.
  - 🔴 **The stall bar fired correctly, and I investigated BEFORE touching it.** The whole
    101->71 drop is ONE scenario: recomputed at `df190598a`, the commit that SET the bar,
    `composition-motif-bind-edit` was **0/30 - perfectly clean** - and is now 13/53. Its 13 errors
    are three ALL-OR-NOTHING batches on a single day, 2026-09-01, all carrying the same upstream
    error, while a fourth batch that same day ran 0/10 clean. The floor was scenario-partitioned,
    so one bad day deleted 30 clean runs at a stroke; it is RUN-level now (173 at the bar, 213
    today), monotone in new evidence. Fixing it revealed a second bar sized to "the top TWO"
    scenarios - the concentration had NOT broken up (3 of 10 hold 48 of 49 errors, 98%), the
    window was just too narrow.
  - ✅ **19 -> 1 on an undisturbed tree: 901 passed.** The survivor is LOCAL-ONLY:
    `test_it_really_reads_the_LOG_and_not_just_the_store` needs a chat session inside a 6h log
    window and the newest here is 15h52m old. CI has no `infra-postgres-1`, so it SKIPS there.
  - 🔴 **A measurement I threw away.** A falsification run reporting 79/402 was MY OWN
    contamination - I ran a mutation harness in the same worktree while committing and stashing.
    Re-run in an isolated worktree: **402/402, 0 NOT FALSIFIABLE.** The same race invented 20
    phantom red-ability failures; the clean run has 19, so one of the 20 was pure noise.

- [x] **R9** - **DONE. My own seed helpers widened a seam `all-gates` is closing.**
  `channel-id-adoption-gate` read 6 `ChannelId::unverified` call sites in `recovery.rs` against a
  baseline of 4 - mine, because the helpers took `ch: ChannelId` and forced the caller to build two
  more. The newtype bought nothing: these are row ids being INSERTED into `channels`, so there is
  no channel to resolve yet. They take `i64` now, matching the siblings in `failover.rs` and
  `epoch_activation_live.rs`. **A genuine narrowing, not a baseline edit** - back to 4, "matches
  the baseline exactly", nothing added to any allowlist. `gate-wiring-gate`: OK, 188 gates
  discovered, all wired or exempted, 0 tracked-red.

- [x] **R3** — **✅ SETTLED at 402/402, 0 NOT FALSIFIABLE.** The 8 real findings each got a
  case that exercises the mutated path, and the harness was re-run in an ISOLATED WORKTREE
  (a run in the main tree, racing my own commits, reported a meaningless 79/402 that is
  recorded and discarded in R8). Original text follows.

- [x] **R3 (original text)** — **`lint-foundation` → `agentruntime-falsification`: CI says 13, the harness's own
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
- [x] **R10** - **DONE. `Secret scan (gitleaks)` - and the finding is that the EARLIER GREENS WERE
  PARTIAL SCANS.**
  - 🔴 Two consecutive `pull_request` runs on the SAME branch scanned different ranges: the
    green one narrow, the red one **1,569 commits**. Nothing new was committed - the scanner
    looked further back. A check that flips because its SCOPE moved, not because the code did.
  - Both findings sit in old branch history (`021550e46`, `70315044c`), which is also why editing
    the files at HEAD cannot clear them: gitleaks reads the COMMIT RANGE, not the worktree. An
    allowlist entry or a history rewrite are the only two options, and a rewrite is destructive
    and not mine to authorise.
  - ✅ **Neither is a credential.** One is a composition confirm token in a recorded HTTP 400
    against `http://localhost:8217` - local dev server, single-use, and **TRUNCATED**: its base64
    decodes to JSON that ends mid-string at char 118 because the error text cut the URL. The other
    is two model UUIDs in explanatory PROSE (`llm_model=<uuid>`), matched by the
    `generic-api-key` heuristic; a model id is a public identifier the catalogue hands out.
  - Added as **exact literals**, per the rule the config already states - a path entry for
    `docs/eval/toolloop/` would blind the scanner to a real credential captured in a recorded run
    tomorrow. Verified none contains a regex metacharacter and each self-matches.
  - 🔴 **FLAGGED, NOT BURIED:** if the owner reads that truncated localhost token
    differently, the entry should come out and the token should be scrubbed from history instead.

- [x] **R11** - **DONE. A SKIP GUARD THAT COULD NEVER SKIP. `Foundation lints`, 22 failures.**
  - 🔴 Every one said only *"there is no stack here"* - `could not read NEO4J_PASSWORD from
    infra-knowledge-service-1`, `SnapshotUnavailable: loreweave_jobs`, `httpx.ConnectError`,
    `psql failed`. They ran on the runner because both guards test a PROXY that is TRUE in CI:

        skipif(not (ROOT / "infra").exists())   # `infra/` is COMMITTED - always there
        skipif(docker ps returncode != 0)       # every GitHub runner HAS docker

    They passed here only because I run the `infra-*` containers - the same environment gap in the
    opposite direction from the log-window test - and stayed invisible until R7 let the job REACH
    the step that runs them.
  - ✅ `scripts/live_stack.py` gives ONE answer and does not invent a second: it imports
    `gate-wiring-gate.stack_reachable` (a TCP connect to 127.0.0.1:25556, the store those gates
    default to) and **fails CLOSED**. Its selftest pins that the SSOT is readable, so it cannot rot
    into "always skip". Eleven files repointed, including two forms the first pass missed.
  - **BITE, both directions:** probe forced False -> **34 passed, 64 SKIPPED, 0 failed** (34 static
    assertions still run, so this is not green-by-absence); stack up -> 97 passed. Byte-exact
    restore, `cmp` clean.
  - 🔴 **Then 4 survived, and it was the same mistake one layer in.**
    `test_toolloop_seed_assert_preflight` skipped on `if not bad` - but an unreachable database is
    NOT silent, it returns `db_query failed ... no such container: infra-postgres-1`. Non-empty,
    so the skip never fired and the assertions failed for not finding "column" in a message about
    docker. Guarded on the probe rather than on the error TEXT, because matching a wrapped error
    by substring is how this class of guard rots. Scoped to the two LIVE classes: the static class
    must keep running, or the file goes green by absence. BITE: 5 skipped, **2 still passed**.

- [x] **R12** - **DONE. `all-gates`: one missing package, and I had caused it.**
  `agentruntime-census` copies the tree and runs the chat-service suite to establish a GREEN
  BASELINE before injecting anything. Without `pytest-asyncio` every async fixture errors at
  setup - *"requested an async fixture 'conn', with no plugin or hook that handled it"* - and the
  census reports `SELFTEST FAIL: the suite is not green before any injection`. It is RIGHT to: a
  verdict measured against an already-red baseline is the vacuous measurement it exists to refuse.
  - `pytest-asyncio` is declared in `requirements-test.txt`, not `requirements.txt`. The step that
    installed only the runtime half is one **I added earlier in this same session**. The standalone
    census job already got this right, and its own comment records the lesson being learned once
    before: *"requirements.txt HAS NO PYTEST, so the first version of this job could never..."*.
  - **BITE:** `pytest -p no:asyncio` on that file reproduces CI's sentence verbatim - same test,
    same fixture, same words. With the plugin: 19 passed.
  - Also closed the last LOCAL red: the log-window test asserted a 6h container-log read against a
    stack whose newest chat message was 20.2h old, and reported *"the reader is looking at the
    wrong stream"* - a defect that is not there. It now asks for the age in the same query and
    skips saying which it was.

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

**RESUME: D7 — `dp-clippy` is the LAST non-advisory red, and it is a STOP, not work**

Every other row is closed. R1 and R5-R9 are fixed and pushed. R2's self-test is GREEN IN CI
(all six checks print OK on the runner). R3 is settled at **402/402, 0 NOT FALSIFIABLE**,
measured in an isolated worktree after a contaminated run had to be thrown away. R4 is the CI
confirmation of the last push. What remains is a decision, not work: **D3, D4, D5, D6, D7**.

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
