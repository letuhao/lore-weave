# RUN-STATE — Generation SSOT

**Spec:** [`docs/specs/2026-07-31-generation-ssot.md`](../specs/2026-07-31-generation-ssot.md)
**Started:** 2026-07-31 · **Branch:** `feat/frontend-tools-mcp-migration` · **Size:** XL

> **After every compaction: re-read THIS FILE first, then `git log`, then continue.**
> Never re-litigate a sealed decision from memory — re-read §Decisions.

---

## The commitment

Eleven slices that turn PLAN and PROSE from two disjoint toolchains into one spine.
**Acceptance test (spec §6 item 7):** the Mị Đế chapter-1 defect — scene 1's prose killing
Tô Thanh Dao, whom the plan has alive in scene 2 — is caught by **a gate**, not by a human
reading the prose.

### ▶ THE ACTIVE GOAL (set 2026-08-02) — re-read this after every compaction

Author's framing, and it changes what "good" means for this stretch: *"chúng ta sẽ còn bước audit
sau khi hoàn thành nên việc chúng ta đang thực hiện chỉ đơn giản là tăng tốc độ thôi, bước audit
đó mới là thứ quan trọng và cực kỳ mất thời gian."* ⇒ **the job here is THROUGHPUT that leaves an
auditable trail.** A later audit will read this transcript and this file; evidence that is not
written down does not exist for it.

**Condition set with the human:** drive the board to completion in sealed order —
`[budget-seam rot = S7 slice 4] → S6(+UI) → S11 → S3 → S4 → S9 → S5 → S13` — with KG/extraction
PARKED throughout. **No turn bound** (author's explicit choice: *"Không giới hạn lượt, chỉ dừng khi
board sạch"*).

⚠ **What that costs, recorded so it is not a surprise.** The `/goal` evaluator reads the transcript
only — it cannot run a command or read a file, so it is satisfied by a *claim* that a check passed.
A turn bound was the one brake that layer had, and it is deliberately off. **The compensation is
that the other two enforcement layers now carry the whole load:**

1. **This file's slice board** — a slice is not done until its row here says so, with its evidence
   string. Update it in the same commit as the code. If the transcript and this file disagree,
   **this file is right.**
2. **The gates** (`scripts/*-gate.py`, `.githooks/pre-commit`, `scripts/workflow-gate.py`) — these
   are mechanical and cannot be talked past. Run them; paste them.
3. **The drift log** — an empty drift log at the end of a stretch this long is not clean, it is
   dishonest. Append near-misses as they happen, not in a sweep at the end.

**Stop and ask the human only for:** a destructive or irreversible action, or a sealed decision in
this file turning out to be wrong. Everything else — park it in the register and keep moving.

## Invariants that must hold at every commit

1. No guard reports clean without having checked something (`verdict is None` unless `CHECKED`).
2. No model is silently its own judge.
3. No integer `max_tokens` literal at an LLM call site.
4. Provider-gateway invariant unbroken — no new direct SDK import, no hardcoded model name.
5. Every slice ships a gate **proven red-able by injecting the defect**, and the injection is
   undone by re-editing from memory — **never** `git checkout <file>` (it discards real work in
   that same file).
6. S11 is additive-then-switch: no existing `loreweave_context` consumer changes behaviour until
   its own measurement says it may.

## PHASE 0 — live bugs. **CLOSED 2026-07-31: 8/8.**

| id | outcome |
|---|---|
| B5 | FIXED — ownership 503; gate red = `201 Created` on an unverified project |
| B2 | FIXED — 2 guide-bypass sites; gate red on 3 injection payloads |
| B1 | FIXED — `cl100k` → `o200k` + fallback chain; VN 1.98 → 2.94 chars/budget-token |
| B6 | FIXED — coverage + `filter_status` ride the result; **plus** a ZeroDivision in the extracted `compute_filter_kept` |
| B7 | FIXED, wider than stated — POCs deleted; the GATE was the real bug (half a rule enforced, blind to every local model family, and running only as an opt-in hook) |
| B4 | PARTIAL — `judge_distinct` tri-state on the wiki judge; severity walked back (internal-token gated, not attacker-selectable) |
| B3 | CORRECTED IN DOCS + §S12 gate built (wiring was never an available option) |
| B8 | **CLOSED — NOT A BUG.** The harness is a CLI that prints the fallback count; `src/http/` does not use it |

**Residue is tracked in spec §3.1** — 13 carry-forward rows, each assigned to an owning slice.
**ROT-1 CLOSED** — all 159 executed. auth (36) and provider-registry (54) clean; three reds, **all
stale tests, not product bugs** (a migration list missing the migration written for it; a test
predating a lease guard; a free-tier assertion colliding with an unrelated daily cap). Sealed with
`scripts/test-dsn-coverage-gate.py`, which compares gating variables against what CI arms — and on
its first run found a **tenth** gap the manual sweep missed (9 Redis-gated scheduler tests; the
sweep had grepped Go only). **There is no ROT-2.**

## ROT-0 — the skip audit (2026-07-31, author-requested: *"coi chừng degraded bugs"*)

**SEALED.** Audited every skipped test in the services touched so far, then every DB-gated suite in
the repo against the workflows that claim to run them.

| finding | resolution |
|---|---|
| composition 383 skips (`TEST_COMPOSITION_DB_URL`) | ✅ already covered by `python-integration-tests.yml`, trigger `push` on all branches |
| campaign 20 skips (`TEST_CAMPAIGN_DB_URL`) | ✅ same workflow |
| composition `test_route_403_when_grant_below_view` | ❌ **skipped on every run since written** — `GrantLevel` is `NONE=0 < VIEW=1` with nothing between, so its `below` list is always empty. Rewritten to assert the `InsufficientGrant → 403` mapping directly. 19 passed, **0 skipped**. |
| **jobs-service, 13 tests** (`JOBS_TEST_PG_DSN`) | ❌ **no workflow set the var.** All 13 pass on a fresh DB (112 passed / 0 skipped). Added to the `python-integration-tests` matrix. |
| **PIIKMS family, 28 Go tests / 16 files** (`PIIKMS_TEST_PG_URL`) | ❌ **no workflow set the var.** Covers PgKEKManager, PII erasure, admin-cli erasure/archive/drift, meta-worker's erased-writer, breach-notifier, meta-outbox relay. New `meta-db-smoke` job in `domain-db-smoke.yml`. |

**One real defect found on first execution — D-METAOUTBOX-DRAIN-TEST-ISOLATION.**
`TestLive_PgSource_DrainAndMark` seeded 2 rows and called `Begin(ctx, 10)`. The drain is FIFO
(`ORDER BY enqueued_at ASC LIMIT $1`), the family shares one throwaway DB, and sibling suites leave
pending rows — measured **17 pending**, so the batch returned ten *other* rows and the seeded pair
never appeared. Its failure message could not say so: `got[id]` on a map returns `""` for both
"empty topic" and "absent row", and the meta-only assertion passed **vacuously** under the same
condition. Fixed by sizing the batch from the live pending count and asserting presence separately
from value. Verified stable across two consecutive runs on a dirty DB.

Everything else in the family passed — the suites had not rotted, they had simply never been asked.

## ▶ THE RUN ORDER + THE PER-SLICE PROTOCOL (2026-08-01 — author-set)

Author: *"phải ép chất lượng QC và giữ độ tập trung để tránh bị drift … cần thêm bước audit
lại những gì đã làm ở mỗi slice và hướng đi tiếp theo … chỉ dừng lại sau khi hoàn thành plan."*

**Order.** `S10 ✅` → `D-GENERATED-FACT-HAS-NO-HOME ✅` → `[CI-RED sweep] ✅` → `S1 ✅` → `S2 ✅` → `S8 ✅` → `S12 ✅` →
`[budget-seam rot] ✅ → S7 ✅` → `S6(+UI) ✅` → `S11 ✅` → `S3 ◐` → `S4 ✅` → **`S9`** → `S9 → S5 → S13`.

> **2026-08-02 — author-set, after an overview.** The KG/extraction thread is **PARKED**, and
> that includes `docs/specs/2026-08-01-entity-identity-under-qualitative-extraction.md`. It is a
> real diagnosis and it points at a large refactor; it is **not** what to do next.
> *"tôi không khuyến khích lao đầu vào KG ngay bây giờ … cách làm đúng bây giờ nên là làm phần
> 'Budget seam rot' trước và rồi resume slice 7 và các slice còn lại."*
> Pay the budget-seam rot down first, then finish S7, then the board in its sealed order.

---

## ▶ WHERE THE RUN STANDS — the overview (2026-08-02)

Written because the slice board alone gives a **false** reading: it shows the run parked at S7,
when in fact most of the last two days went into defect work that was never on the board.

### The board — 7 closed, S7 open, 6 untouched

| slice | state | note |
|---|---|---|
| `S10` the eval instrument | ✅ | a real build slice, not a formality |
| `D-GENERATED-FACT-HAS-NO-HOME` | ✅ | inserted before S1 as the root of both continuity failures |
| `[CI-RED sweep]` | ✅ | **3 roots**, not the 1 the handoff claimed; one was a production bug |
| `S1` one honest verdict shape | ✅ | `GuardReport` · `CheckStatus` · `verdict` |
| `S2` one cast-liveness SSOT | ✅ | both directions |
| `S8` the pack's diagnostics ride the job | ✅ | |
| `S12` every declared enforcement site resolves | ✅ | the gate went green on its own example 3× before it was real |
| **`S7` one output budget** | **✅ CLOSED 2026-08-02** | slices 1·2·3 ✅ · slice 4 (budget-seam rot) ✅ — 28 no-signal sites → 9, and the 9 are named |
| `S6` no model silently its own judge | ✅ CLOSED 2026-08-02 | the affordance shipped; 7 hand-rolled copies → one policy; the skip states now differ |
| `S11` one context compiler | ✅ CLOSED 2026-08-02 | allocation layer + composition flipped (no-op ≥16K) · translation's estimator converged (it under-counted CJK/vi by a third) · the contract's two closed sets now machine-checked both ways |
| `S3` one `Finding` | ◐ slice 1 ✅ | one closed `skip_reason` vocabulary (the docs were false and omitted the member a consumer reads); the `locator` union is untouched |
| `S4` the plan half onto the spine | ✅ CLOSED 2026-08-02 | the gate was reading COMMENTS as behaviour (both directions); SCAN_DIRS 4→10 services surfaced 8 untracked modules, 7 in translation |
| `S9` the shared guard SDK | ☐ | **inverted** — converge three services first, extract after |
| `S5` one heal loop | ☐ | |
| `S13` cite the exemplars | ☐ | mostly documentation |

**The join nobody had made:** what this session called *"155 — 28 budget call sites carrying no
adaptive signal"* **IS S7 slice 4's unbuilt scope.** Spec §S7 already specifies the gate as
*"red on an int default in any signature that reaches an LLM call (~31 of ~40 are defaults)"*, and
the measurement found **26 of 28 are exactly that** — `max_tokens: int = max_tokens_for("kind")`,
evaluated once at import, unreachable by any per-call signal. It was named as new work because it
was found from the other end.

### What was NOT on the board — and is most of the elapsed effort

Since the POST-RUN REVIEW, ~13 items, none of them a slice: the review's own 3 defects (the publish
gate rounding up to a pass · `loreweave_guard` having zero production consumers · `plan_status` with
no producer) · closing the run's acceptance test (detection half) · the plan-liveness judge tier
advisory → **HARD** · building the prevention half · measuring it and finding it **does not work** ·
chapter paths declaring their gap instead of looking like a pass · A/B v2 (detector **11/11** on real
drafts) · a mute judge no longer reading as one that declined · wiring the budget seam + its ratchet ·
the FE finally saying **why** the guard is amber (+17 locales) · the planned-lens leaking **40
synopses from 14 chapters** into every scene · `POST /entities` honouring its own contract · the
**canon flywheel** (2 commits — a book written from scratch now reaches the graph its guard checks) ·
the entity-identity architecture review.

Not waste — most were real defects, several surfaced by the author's questions. But the board does
not reflect them, so reading the board alone understates the run and overstates the stall.

### De-rot

| | state |
|---|---|
| **ROT-0** skip audit | ✅ SEALED — **200 tests that had never run** (41 reported first; a full sweep found 159 more). jobs 13 + PIIKMS 28 Go tests wired into CI. One real defect found on first execution. |
| Test parallelisation | ✅ composition **508s → 107s (4.7×)** — per-worker DBs + a fingerprinted migration memo |
| Suite restoration plan | ◐ **written and measured, NOT executed** — knowledge still **561 skips**, and `-n auto` is still *unsafe* there (12 failed + 118 errors). [`docs/plans/2026-08-01-test-suite-restoration.md`](2026-08-01-test-suite-restoration.md) |
| **Budget seam rot** | ◐ found, gate ratcheted, **26 sites unswept** ⇒ **this is what comes next** |
| CI-RED | ✅ |

### The three concrete loose ends

1. **S7-4 / budget-seam rot** — 26 functions whose budget is frozen at import. Mechanical, with an
   in-repo pattern to copy (`judge_plan_conflict`), but each needs a judgement about its real size
   driver. **Next.**
2. **S6 is blocked by an affordance, not by code** — no surface sets a critic; `critic_model_ref`
   lives only in `work.settings` JSONB. So today's self-graded fraction is *100% minus hand-edited
   JSONB*. The spec is explicit: ship the UI in the same slice or the label is noise.
3. **Suite restoration** — fully measured, unexecuted.

---

`D-GENERATED-FACT-HAS-NO-HOME` is inserted BEFORE S1 because it is the root of both continuity
failures this session measured: a fact the generator invents (a character's gender, a name, a
new object) has no path into anything authoritative, so the next scene's spec can contradict it
and nothing reconciles them. `exit_state` exists for exactly this and is authored-only, never
written back from what was generated. S1 (GuardStatus unification) will have to carry whatever
shape this produces, so doing it after S1 means migrating twice.

### Every slice ends with the same four things, in this order

| # | step | what makes it real |
|---|---|---|
| 1 | **VERIFY** | run the tests + the gates and **PASTE the output**. A claim that they pass is not evidence. |
| 2 | **LIVE** | for anything on a generation path: a real run on a **throwaway** book, with the numbers pasted. Mock-green has hidden a cross-service bug four times in this repo. |
| 3 | **AUDIT** | the block below, written out. Not "looks good" — the four questions answered. |
| 4 | **COMMIT + RUNSTATE** | code and the slice board move in the same commit. |

### The AUDIT block — write it verbatim, every slice

```
AUDIT <slice>
  BUILT      — what exists now that did not before, in one sentence
  PROVEN     — the evidence, quoted: test counts, gate lines, live numbers
  NOT PROVEN — what I claimed or assumed but did not measure. NEVER "nothing".
  DRIFT      — what I nearly did wrong, or a bar I nearly lowered. NEVER "none".
  NEXT       — the next slice, and what about this one changes its shape
```

`NOT PROVEN` and `DRIFT` are the anti-drift mechanism and they are **required to be non-empty**.
This session produced seven drift entries and four retractions; a slice that reports neither has
not been audited, it has been rubber-stamped. If a slice genuinely has nothing, the honest entry
is *what I did not check*, which is never nothing.

### ✅ D-GENERATED-FACT-HAS-NO-HOME — CLOSED 2026-08-01

```
AUDIT D-GENERATED-FACT-HAS-NO-HOME
  BUILT      — a drafted scene now RECORDS the people it named into `outline_node.exit_state.cast`
               (`source='generator'`), the next scene's prompt carries them as a protected,
               uncompressible `carries=` line, and the seam check compares against that record
               instead of re-reading the prose.

  PROVEN     — unit: `3303 passed, 58 warnings in 28.81s` (was 3272 at HEAD; +31).
               integration on a throwaway PG: `33 failed, 353 passed, 8 skipped` — and the HEAD
               baseline MEASURED by stashing the slice was `33 failed, 347 passed, 8 skipped`.
               Same 33, +6 = the new repo tests. The 33 are pre-existing rot, not assumed so.
               gates: `ai-provider-gate (full): OK` · `db-safety-gate: PASS (exit 0)` ·
               `[language-rule] PASS` · `composition eval-gate: PASS — 5 seeded defect class(es)`.
               Deployed image verified by whole-file sha256 against source (5 files, all MATCH).

               LIVE, gemma-4-26b via lm_studio ($0), two throwaway Vietnamese books:
                 SEEDED (characters named)        CONTROL (nobody named)
                 exit_state_record  recorded, 2   no_cast_extracted, 0
                 DB exit_state      Lục Hàn—he;   NULL
                                    Thanh Dao—she
                 carries= in prompt PRESENT       ABSENT
                 earlier_source     recorded      extracted
                 linked / clean     2 / true      0 / false
                 words              811 + 878     883 + 898
               Every field differs in the expected direction; neither half is vacuous.

  NOT PROVEN — that any of this makes the PROSE better. The fact reaching the prompt is measured;
               "a scene with `carries=` contradicts less often" is not, and needs an A/B over many
               scenes. The anchor→Scribe case (unnamed on both sides) is still NOT detected —
               only prevention improves there, and prevention was not measured either.
               Also unmeasured: the `name` slot on any model but gemma-4-26b (n=2 runs); the whole
               live path on an ENGLISH book (unit tests only); the MCP authoring merge live (unit
               only); and the INLINE router branch, which is wired but never executed — the shipped
               compose has `COMPOSITION_WORKER_ENABLED=true`, so only the worker branch ran.

  DRIFT      — five, and two were nearly shipped.
               1. The protected-segment gate went GREEN with `protected=False` injected. It passed
                  because the `carries=` line is SMALL, not because it was protected — the budget
                  drops largest-first and stops early. Rewritten to squeeze into `over_budget`,
                  where protection actually decides. Caught only by injecting the defect.
               2. Wrote "can never fail a generate" while calling `get_pool()` OUTSIDE the guard.
                  Four router tests reddened; the promise was false on the path that made it.
               3. Accepted the FIRST live run because the status field said `recorded, cast_size=10`.
                  The payload was ten Vietnamese pronouns and common nouns — including *Ánh mắt họ*,
                  "their gaze". A green status over garbage data; I nearly stopped at the status.
               4. Fixed that in the recorder and left the SAME bug in `compare_people`'s fallback.
                  The control then reported `linked=2, clean=true` on a scene where nobody is named.
                  An empty `name` is an ANSWER, not a missing value to fall back from.
               5. Called the 33 integration failures pre-existing before measuring. Then measured.
               Plus: a defensive `try/except` referencing a `logger` this module does not define,
               on a branch JSONB makes unreachable — it could only ever have fired as a NameError.

  NEXT       — S1 (GuardStatus unification) inherits `exit_state_record` and `cross_scene.
               earlier_source` as two more per-guard status fields on an envelope now assembled in
               FOUR places, which is exactly what S1/S2 exist to collapse. Two findings feed it:
               the INLINE generate branch has no cross-scene check at all, and `exit_state_record`
               had to be added to both branches by hand — the parity problem is the slice.
```

**Found while doing it, NOT part of this slice — tracked so it cannot be forgotten:**

| finding | disposition |
|---|---|
| **CI is RED** (measured 2026-08-01 via `gh run list`): `python-integration-tests`, `python-unit-tests`, `domain-db-smoke` all `failure` on this branch | → the CI-RED sweep, next |
| the INLINE generate branch (`COMPOSITION_WORKER_ENABLED=false`) runs no cross-scene check | → S1/S2 (envelope consolidation) |

## ✅ CI-RED sweep — 2026-08-01

Three roots, not one. The first diagnosis ("33 failures, one rename") was **wrong on both counts**
— it was the shape I could see from one error message, and I wrote it into the handoff before
reading the other two workflows.

**1 · `app.routes` stopped being flat (fastapi 0.139 / starlette 1.3).** Measured inside the
shipped image: `{'Route': 4, '_IncludedRouter': 35, 'Mount': 1}` — 202 real paths, 5 visible to
the old idiom. Six tests across knowledge- and composition-service raised
`AttributeError: '_IncludedRouter' object has no attribute 'path'`; the contract-parity test
reported **31 real, served endpoints as "declared but not served"**. Two call sites used
`getattr(route, "path", "")` and would have gone **quietly empty** instead — a parity assertion
over an empty set is a test that cannot fail. Fixed with `loreweave_obs.routes`
(`iter_routes`/`route_paths`/`route_ops`), duck-typed on `include_context` rather than importing
the private class name, with a depth cap so a malformed graph is a failure and not a hang.

⚠ **My local suite could not have caught this.** The dev box runs fastapi 0.136 where the old
idiom still works — 3303 green locally while CI was red on the same commit. The SDK test is
therefore written to pass on BOTH versions and asserts `naive < full` **strictly** on the new
one; it was executed on fastapi 0.139.2 inside the container (`6 passed, 0 failed`).

**2 · `-e ../../sdks/python` resolved outside the checkout.** pip resolves a relative editable
against the **CWD**, not the requirements file's directory, and both workflows ran the install
from the repo root. lore-enrichment's whole install step aborted, so its entire suite never ran
— a red job whose cause was two directory levels. Fixed by giving the install step a
`working-directory`.

**3 · `language` → `original_language` (MOTIF-I18N / ARC-I18N).** The identity key changed —
*one motif = one row*, other languages live in `motif_translation` — and **8** test files still
asserted the removed behaviour. Both the mechanical part (SQL columns on `motif` +
`arc_template`, `MotifCreateArgs` kwargs, `retrieve(language=)` → `display_language=`) and the
SEMANTIC part (two tests asserted "same code + different language = 2 rows", which is exactly
what the i18n migration deleted) are fixed against the rule as written in `migrate.py` + spec
`2026-07-29-motif-i18n.md` — **not** against whatever the code currently does.

**…and it turned up a PRODUCTION bug.** `_ARC_RETRIEVE_COLS` in
`app/db/repositories/motif_retrieve.py` still selected `language` from `arc_template`, so
`retrieve_arcs` — the arc-suggestion read — **500s on the shipped schema**. Its sibling
`_RETRIEVE_COLS` (motif) had been renamed; the arc one was missed. It was caught by
`test_retrieve_arcs_projects_renamed_columns_via_alias`, a guard-by-EFFECT test written for
exactly this class, whose docstring says the unit test *"mocks the pool with rows already shaped
… so it CANNOT catch an unaliased column"*. The guard worked; nobody had run it.
A schema-scoped sweep of `app/` found no other stale reference (the remaining hits are inside
the i18n migration files themselves, which must name the pre-rename column).

### ⛔ Still failing, root FOUND, deliberately not fixed here

`tests/integration/db/test_motif_retrieve_db.py` — **8 tests**. Not a rename: `retrieve()` was
re-designed on 2026-07-17 into **two embedding spaces** (a caller's private motifs rank in their
own BYOK U-space, everything shared in the platform P-space). A row whose vector is in the wrong
space is *queued and skipped in the cosine path*, so with `motif_embed_model_ref` unset every
seeded row is skipped and retrieve returns **∅** — which is what all 8 assertions see.

Setting the env is **not** the fix: it turns the config error into a live provider call and the
run hangs (measured — killed at 600 s). Fixing it properly means seeding vectors in the space the
new design expects, which needs that design read. Deferred under gate #1 (different track) and
#2 (needs the design, and writing assertions to match current behaviour is the self-witness
anti-pattern this repo has paid for five times).

```
AUDIT CI-RED sweep
  BUILT      — `loreweave_obs.routes` (a route enumeration that survives fastapi 0.139), both
               python workflows install from the service directory, 8 motif/arc test files
               moved onto the post-i18n schema and identity rule, and ONE production SQL fix:
               `_ARC_RETRIEVE_COLS` was selecting a column the ARC-I18N migration dropped.

  PROVEN     — composition integration on a FRESH throwaway PG:
                 before  `33 failed, 347 passed, 8 skipped`
                 after   `8 failed, 378 passed, 8 skipped`
               composition unit `3303 passed, 58 warnings in 28.30s`.
               knowledge-service, the 5 edited files: `67 passed in 2.53s`.
               lore-enrichment `test_api_contract.py`: `7 passed in 1.56s`.
               SDK `test_routes.py`: `6 passed` on the dev box (fastapi 0.136) AND
               `fastapi 0.139.2: 6 passed, 0 failed | paths 202 | ops 246` executed INSIDE the
               shipped image — the version where the old idiom breaks, which is the only run
               that proves anything. Both workflow YAMLs re-parsed clean with the new
               `working-directory` on the install step.
               gates: `ai-provider-gate (full): OK` · `db-safety-gate: PASS (exit 0)` ·
               `[language-rule] PASS`.

  NOT PROVEN — that CI is now GREEN. I fixed what the last run's log named plus what a fresh-DB
               run reproduces; the next push is the only thing that can confirm it, and
               `domain-db-smoke` (also red) was never diagnosed at all — I read two of the three
               failing workflows. The `-e` fix is reasoned from pip's resolution rule and a
               YAML re-parse, NOT from a CI run. `route_ops` includes `HEAD`, which is fine for
               the forward-parity check that consumes it and untested for anything else. And
               no browser/live smoke ran for the `retrieve_arcs` fix — the integration test
               issues the real SELECT against the real renamed schema, which is the right proof
               for a SQL typo, but it is not the same as the endpoint being exercised.

  DRIFT      — I wrote "33 failures, ONE root, a mechanical sweep" into the session handoff
               after reading ONE traceback. It was three roots; the rename half needed a
               semantic rewrite because the identity key had changed too; and my file list came
               from a terminal that had truncated 13 of the 33 rows — the missing rows held two
               more files and the production bug. I also nearly shipped a `_sub()` fallback
               that would have emitted every sub-route at the WRONG path (no prefix) the moment
               FastAPI renamed `include_context` — losing routes is caught downstream,
               inventing plausible wrong ones is not.

  NEXT       — S1 (GuardStatus unification). Nothing here changes its shape; the one carry-over
               is that this sweep proves the repo has stale-test rot in tracks the SSOT run
               does not touch, so a red integration suite is no longer a safe proxy for "my
               change broke something" — measure the baseline before believing a delta.
```

## ✅ S1 · one honest verdict shape — CLOSED 2026-08-01

```
AUDIT S1
  BUILT      — `loreweave_guard` (CheckStatus + GuardReport: per-check statuses, a DERIVED
               headline, and `verdict` as a PROPERTY that returns None unless the report is
               CHECKED). Adopted by the canon guard additively — `status` keeps its legacy
               strings because SQL reads them — plus `guard_status` on all six envelope sites,
               a fail-safe publish-gate clause, `contracts/generation-paths.yaml`, and
               `scripts/generation-guard-gate.py` wired into foundation-ci with its teeth test.

  PROVEN     — sdks/python `22 passed`; composition unit `3311 passed` (3303 before, +8);
               publish-gate integration `17 passed` on a fresh throwaway PG;
               `scripts/test_generation_guard_gate.py` + gate-teeth `32 passed`.
               gates: `generation-guard-gate: PASS — 8 generation paths enumerated across 3
               languages; 4 guarded, 4 tracked-unguarded` ·
               `gate-teeth-gate: PASS — 56 CI-invoked gate(s) … 9 carry a red-ability proof`
               (it FAILED first at "grew to 48 (baseline 47)", which is what forced the teeth
               test rather than a baseline bump) · enforcement-claims OK · ai-provider OK ·
               db-safety PASS · language-rule PASS.
               `loreweave_guard` PROVEN present in the built image, not assumed — the
               pyproject include-list trap that silently dropped `loreweave_crypto`.

               LIVE, $0 gemma-4-26b, two throwaway books:
                                     no cast bound           cast bound (control)
                 canon.status        skipped_no_cast         checked
                 canon.guard_status  no_subject              checked
                 canon.checks        canon_cast=no_subject   canon_cast=checked
                                     name_grounding=checked  name_grounding=checked
                 canon.resolved      True                    True   ← identical, the point
                 words               497                     475

               GATE PROVEN RED-ABLE by five injections, each run against the real contract and
               then removed by re-editing: a phantom file; a symbol that appears ONLY in a
               comment (the S12 shape, which greened that gate three times); a `guarded` claim
               whose coverage field is never emitted; an untracked `unguarded` gap; and the
               model-gateway caller count growing. All five reddened; the file returned to PASS.

  NOT PROVEN — the registry is NOT complete and does not claim to be. 93 files call a model
               gateway; 8 paths are enumerated. The uncovered surface is measured and prevented
               from GROWING, which is a different and weaker guarantee than covering it — I did
               not classify the other 85 and will not pretend a curated list is a denominator.
               Nothing verifies that a `guarded` path's coverage field is CORRECT, only that it
               is emitted. The four `unguarded` rows are recorded, not fixed: composition's two
               SSE generators still stream user-visible prose with no guard at all. And no
               adopter outside composition moved — wiki verify, translation's two tiers and the
               Go/Rust paths still carry their own scalar shapes.

  DRIFT      — I wrote the discovery baseline (`rust: 25`) from a shell grep typed at a prompt
               while the GATE's own detector counts 24. That single-digit gap would have masked
               one new Rust caller forever. A baseline is only a guard if the thing that checks
               it produced the number — the same "derive it from the SSOT" rule I had just
               written into the file's own comment, violated four lines below.
               Second: my first publish-gate test asserted `canon_blocked is True` for an
               unchecked scene. That was my ASSUMPTION about the design; the code blocks only
               on confirmed contradictions, by a written decision, because blocking on
               unchecked would fire on nearly every real book. I nearly "fixed" working code to
               match a test I had just invented.

  NEXT       — S2 (one cast-liveness SSOT, both directions). It inherits `CheckStatus`
               directly: its per-entity resolution is `unknown` + `source="none"` when the
               snapshot has no status row for THAT entity, which is `NO_RULES` computed on the
               entity's own corpus — the exact distinction this slice's primitive now carries.
               S2 also owes `scenes_covered` and `unresolved_refs`, the two fields S10's eval
               declares BLIND on.
```

## ✅ S2 · one cast-liveness SSOT, both directions — CLOSED 2026-08-01

```
AUDIT S2
  BUILT      — `resolve_cast_liveness` in `loreweave_canon_check`: per-ENTITY status WITH the
               layer that answered (KG → plan → none). The canon guard now carries
               `cast_liveness` + `unresolved_refs` on every scene envelope, and reports
               `canon_cast = NO_RULES` when a POPULATED graph has no status row for any of the
               scene's cast — an empty corpus for that check, not a pass. The eval class
               `unresolved_cast_reference` is UN-BLINDED with a live seeder.

  PROVEN     — composition unit `3315 passed` (3311 before, +4); sdks/python `32 passed`
               (+10 for the liveness SSOT).
               `composition eval-gate: PASS — 5 seeded defect class(es) … 4 SCORABLE · 1 blind`
               (was 3 SCORABLE · 2 blind; `MIN_SCORABLE` ratcheted 3 → 4 so it cannot fall back).
               gates: ai-provider OK · db-safety PASS · language-rule PASS ·
               generation-guard-gate PASS · gate-teeth-gate PASS.

               LIVE, $0 gemma-4-26b, throwaway books, the newly-scorable class:
                 `ok unresolved_cast_reference   seeded=fired  control=quiet`
               Recorded into `app/eval/baseline.json` alongside the other three:
                 length_target_unmet         seeded=fired  control=quiet
                 structured_output_truncated seeded=fired  control=quiet
                 gone_cast_asserted_active   seeded=error  control=quiet   (the known
                   knowledge-service gap: the entity anchors but no EntityStatus{gone} is
                   visible at the scene position — unchanged by this slice)

               THE FIXTURE IS THE POINT, and the spec said so: the failing case is a NON-EMPTY
               snapshot with no row for the subject. An empty snapshot passes against the
               BROKEN implementation too, so the unit tests carry both and label the weak one
               as a control rather than letting it stand in for the real one.

  NOT PROVEN — `scenes_covered` is still BLIND and this slice did not touch it. Emitting a
               constant 1 would have made its detector permanently quiet, which is worse than
               declared blindness, so it stays declared. The plan→KG direction is
               UNIMPLEMENTED in practice: `resolve_cast_liveness` accepts `plan_status` and
               composition passes nothing, so the cascade's middle rung is tested but not fed —
               "both directions" is half-built and the half that exists is the KG one. Nothing
               outside composition adopted it: knowledge-service has the same
               everything-not-gone-reads-as-alive shape and still has it. And `unresolved_refs`
               counts ids, not NAMES — a cast bound to the wrong entity id resolves fine.

  DRIFT      — I checked whether `_uuid` was imported by searching for the string
               `import uuid as _uuid`. It matched — at line 277, INSIDE another method, where
               it is a local. My check answered a different question from the one I asked, and
               the new seeder would have died on `NameError` at its first live run. Caught by
               re-reading the grep output, not by the test suite, because no test drives the
               seeder without a stack.
               Second: I recorded a baseline with `gone_cast = error/error` and nearly committed
               it. Both halves failed because MY SHELL lacked `INTERNAL_SERVICE_TOKEN` and then
               because the seeder's internal URLs default to docker hostnames. Committing that
               would have written a WORSE baseline into the repo and blamed the engine for my
               environment — the "host-env drift masquerades as a code bug" shape, one step
               removed. Re-run with `GLOSSARY_INTERNAL_URL=http://localhost:8211
               KNOWLEDGE_INTERNAL_URL=http://localhost:8216`.

  NEXT       — S8. S2 leaves it two things: `plan_status` is a live parameter with no producer,
               so whichever slice owns the plan-side cast roster should feed it; and the
               `NO_RULES`-on-empty-corpus rule now has a second worked example, which is the
               shape S8's own coverage reporting should copy rather than re-invent.
```

## ✅ S8 · the pack's diagnostics ride the job — CLOSED 2026-08-01

```
AUDIT S8
  BUILT      — `PackedContext.diagnostics()`: ONE method, called from all four envelope
               assembly sites plus the three worker results, carrying the eight numbers the
               pack already measured and then discarded. Only `grounding_available` and
               `reinjected_promise_count` used to reach a job.

  PROVEN     — composition unit `3322 passed` (3315 before, +7).
               gates: ai-provider OK · db-safety PASS · language-rule PASS ·
               generation-guard-gate PASS.
               LIVE, $0 gemma-4-26b, throwaway book, the job result now carries:
                 {"warnings": ["grounding_unavailable: no knowledge-graph data for this
                  scene/project (C3a)"], "over_budget": false, "token_count": 16,
                  "dropped_count": 0, "grounding_available": false,
                  "l4_dropped_no_position": 0, "recent_floor_compressed": 0,
                  "reinjected_promise_count": 0}   · 559 words drafted
               That warning previously had nowhere to go — it was raised, and then the request
               ended.

               THE SEMANTICS v1 INVERTED, pinned against the REAL budget pass rather than my
               description of it: `enforce_budget` produces `over_budget=True, dropped_count=0`
               (protected floor alone over budget — nothing lost) AND
               `over_budget=False, dropped_count=2` (the trim SUCCEEDED by discarding content).
               An alarm keyed on `over_budget` fires on the first and is silent on the second,
               which is exactly backwards.

  NOT PROVEN — no live control on a GROUNDED book. The run above is a bare throwaway, so
               `dropped_count`/`l4_dropped_no_position`/`recent_floor_compressed` were all 0 and
               only the unit tests show them non-zero; `warnings` being non-empty is the one
               live signal that these are not constants. Nothing CONSUMES the block yet — no FE
               surface, no gate, no eval class reads it, so this slice makes a fact available
               rather than acted upon. And the two SSE paths still carry no result envelope at
               all, so they carry no diagnostics either.

  DRIFT      — my first fixture for "content lost while the budget reads fine" used a protected
               floor of 401 tokens against a 200-token budget, so BOTH halves were over-budget
               and the test asserted the opposite of its own name. It failed loudly, which is
               the only reason I noticed: had I written the assertion the other way round it
               would have passed and pinned the inversion this slice exists to correct.

  NEXT       — S12 (every declared enforcement site must resolve to a real call site). S8 hands
               it a worked example of the same shape one level down: a number that is computed,
               documented, and read by nobody. S12's gate should treat "no consumer" the way
               this slice treats "no field".
```

## ✅ S12 · every declared enforcement site must resolve — CLOSED 2026-08-01

```
AUDIT S12
  BUILT      — `enforcement-claims-gate` generalised from the 12 machine-contract rows to
               EVERY path the 125-row standards index names, in any section — and given the
               teeth test it had shipped without since Phase 0.

  PROVEN     — `enforcement-claims-gate: 12 registered contract(s) · 2 declared NOT WIRED ·
               91 path(s) named across the whole index; 0 do not exist`.
               `gate-teeth-gate: PASS — 56 CI-invoked gate(s) … 10 carry a red-ability proof;
               46 held at baseline` (was 9/47; the meta-gate ASKED for the ratchet).
               scripts suite `41 passed`. generation-guard-gate PASS · ai-provider OK ·
               db-safety PASS · language-rule PASS.
               RED-ABLE, by injection into a copy of the index: a named gate script that does
               not exist → reported; a broken markdown link → reported; a missing glob
               directory → reported; prose naming a directory → correctly NOT reported.

  NOT PROVEN — existence is not correctness. The gate cannot tell whether a named script DOES
               what its enforcement cell claims, only that it is there — the B3 defect was a
               crate with zero call sites, which this would still miss if the crate file
               existed. Sections A/C/D/E/F are covered only insofar as they NAME a path; a row
               whose enforcement cell is prose ("planned perf-nightly p95 assertion") is
               deliberately unchecked and therefore uncounted. And the index remains the only
               input: a standard that exists in the repo but has NO row here is invisible to
               this gate entirely.

  DRIFT      — my first version of the generalisation matched only repo-relative link targets.
               This index lives at `docs/standards/`, so nearly all its links are
               `../../contracts/x.yaml` — it found 43 paths and reported "0 missing" while
               never looking at a single doc link. Fixing it took the count to 91. I had
               written a checker that silently halved its own input and printed the smaller
               number as though it were the set, INSIDE the gate whose docstring already
               records that exact failure two paragraphs up. The teeth test caught it, and only
               because I wrote the broken-link case before I trusted the number.

  NEXT       — S7 (one output budget). It is the largest remaining mechanical slice — ~40
               `max_tokens` sites of which ~31 are signature defaults, plus ABSENT budgets in
               glossary's Go tools and tilemap, plus zero `finish_reason == "length"` checks
               service-wide in glossary. The spec is explicit that it must SPLIT: `prose` is
               mechanical, the JSON kinds each need their own sizing model.
```

## ◐ S7 · one output budget — MEASURED, not yet built (2026-08-01)

Checkpointed at a risk boundary with the survey done, so the next run starts from numbers
instead of from the spec's prose — which is falsified in one place below.

**The existing gate already covers more than the spec assumed.**
`llm-budget-ssot-gate: PASS — 92 LLM call site(s) scanned · 18 traced to call_budget() · 29 held
at baseline (8 literal, 21 unattributed, **0 signature defaults**) · 45 built off-site.`
It explicitly does NOT scan `raw POST /internal/llm/stream` (chat, lore-enrichment, video-gen).

**⚠ SPEC CORRECTION — “two SDK sites clamp and two do not” is wrong as written.** Measured, all
six real `call_budget(` sites (word-boundary matched; a naive grep also catches
`per_call_budget` and the stale `sdks/python/build/lib/` copy, which is how I first counted 4):

| site | clamps? | verdict |
|---|---|---|
| `composition/app/llm_budget.py` | yes | correct — threads `context_length` through `budget_for` |
| `translation/app/llm_budget.py` ×3 | no | **CORRECT, not a bug.** All three are `OutputKind.MIRROR`, and `call_budget` short-circuits MIRROR before every clamp on purpose: applying a window share would turn a deliberate “no cap” into a cap. |
| `sdks/loreweave_llm/budget.py` ×2 | 1 of 2 | the definition + its own MIRROR branch |

So there is no unclamped `call_budget` adopter. **The real asymmetry is where the spec's own
example pointed — worker-ai — and it is a call site that never reaches `call_budget` at all:**

- `worker-ai/app/decoupled_extract.py:318,475,566` resolves `context_length` and threads it.
- `worker-ai/app/distill_job.py:68` — `max_tokens: int = DISTILL_MAX_TOKENS`, a SIGNATURE
  DEFAULT, never clamped against the window.
- and `worker-ai/app/distill_consumer.py:104` **already resolves `ctx_len`** — it uses it to
  size the INPUT window (`resolve_distill_window`) and then does not use it for the OUTPUT
  budget. The value is in hand at the call site and dropped.

The fix threads `ctx_len` consumer → `distill_and_write` → `make_distill_llm` and resolves the
output through `call_budget(..., context_length=…)`. Multi-hop across a service this run has
not otherwise touched, which is why it is checkpointed here rather than started at 91% context.

**The other three S7 sub-goals, unstarted and unmeasured beyond the spec's claims:** an ABSENT
`max_tokens` (glossary's Go tools, tilemap), zero `finish_reason == "length"` checks anywhere in
glossary, and the JSON kinds each needing their own sizing model (the spec is explicit that
`prose` is mechanical and the rest are not — v1's “mechanical once the function exists” was wrong).

### ✅ S7 slice 1 — the distill window and the distill cap were two numbers for one decision

```
AUDIT S7-1
  BUILT      — `OUTPUT_RESERVE_TOKENS` and `DISTILL_MAX_TOKENS` are now ONE constant.
               `distiller.py` owns it (`distill_job` already imports from there — the reverse
               is a measured `ImportError: partially initialized module`), and `distill_job`
               re-exports rather than restating it.

  PROVEN     — worker-ai `504 passed` (502 before, +2).
               The overflow, computed for both versions:
                 ctx      OLD(reserve=2048)          NEW(reserve=4096)
                 8192     win=4096  tot=10240 OVER   win=2048  tot=8192  ok
                 16384    win=12000 tot=18144 OVER   win=10240 tot=16384 ok
                 32768    win=12000 tot=18144 ok     win=12000 tot=18144 ok
               An 8k-context BYOK model was budgeted chunk+prompt+output = 10240 against an
               8192 window — exceeding it by 2048, which is the exact overflow
               `resolve_distill_window` was written to prevent, on exactly the models it names.

  NOT PROVEN — ctx=4096 STILL overflows (tot=7144) and this slice does not fix it:
               `MIN_WINDOW_TOKENS = 1000` floors the chunk, so a 4k model cannot fit
               prompt+output+a-usable-chunk at all. The floor deliberately wins ("a tiny model
               gets the largest chunk that fits, floored") — the honest statement is that a
               4k-context distill model is unsupported, and nothing SAYS that anywhere.
               No live run: this is a constant-arithmetic fix on a path that needs a real
               diary-distill job to exercise, and the arithmetic is pinned by a test that
               derives from the constants instead of restating them.

  DRIFT      — the existing test asserted `8_000 - 2_048 - 2_048`, restating both constants.
               When the reserve changed it went red — for PINNING THE BUG. I nearly read that
               red as "my fix is wrong" instead of "the test hardcoded the defect", which is
               the same shape as the motif tests that asserted the removed i18n behaviour, two
               slices ago, in this same session.

  NEXT       — S7 slices 2-4, still untouched and unmeasured: ABSENT `max_tokens` (glossary's
               Go tools, tilemap), ZERO `finish_reason == "length"` checks anywhere in
               glossary, and per-kind sizing models for the JSON kinds.
```

### ◐ S7 slices 2-3 — measured; one was ALREADY DONE, the other needs a Rust cycle

```
AUDIT S7-2/3 (survey)
  BUILT      — nothing. Both sub-goals were MEASURED against code, and the measurement changed
               what each of them is.

  PROVEN     — S7-2, "glossary-service has ZERO FinishReason checks service-wide": FALSE, and
               stale rather than wrong-in-principle. `grep` finds 10 hits; the guard is
               `llmbudget.Truncated(res.FinishReason)` at BOTH of glossary's LLM call sites
               (`action_plan_tools.go:228`, `entity_doc_extract_tools.go:245`), backed by a
               dedicated `internal/llmbudget` package whose own docstring records the bug the
               spec is describing — *"`llm.StreamRequest` with NO MaxTokens and never looked at
               `res.FinishReason`"*. It was closed by the LLM-BUDGET SSOT M1-M3 work EARLIER IN
               THIS SAME SESSION. The third file that matches `MaxTokens`
               (`select_for_context_handler.go`) is not an LLM call at all — its `MaxTokens` is
               a context-PACKING budget for entity selection, so it has no finish_reason to
               check.

               S7-3, tilemap: CONFIRMED, and it is the `l4_retry.rs` shape exactly.
                 `max_tokens|max_output_tokens` in `services/tilemap-service/src`: **0 hits**.
                 `finish_reason`: captured at `harness/mod.rs:142`, carried at :220, and
                 PRINTED at :240 — and compared to nothing. Grepping for a comparison against
                 `"length"` near finish/truncat returns EMPTY.
               So tilemap sends no output cap, receives the truncation signal, records it, and
               treats a cut-off narration as a narration.

  NOT PROVEN — I did not run glossary's Go suite or tilemap's cargo tests, so "already done"
               rests on reading the call sites, not on executing them. I also did not check
               whether `llmbudget.Truncated` is reached on every BRANCH of those two handlers
               — only that it is present in each file. And tilemap's 0-hit `max_tokens` count
               is over `src/`; if a cap is set in a config or passed by a caller outside the
               crate, this survey would not see it.

  DRIFT      — THIRD spec claim falsified by measurement in this slice alone ("two SDK sites
               unclamped" → they are MIRROR; "33 CI failures, one root" → three roots;
               "glossary has zero FinishReason checks" → it has ten). I have been treating the
               spec's §S7 bullets as a work list rather than as hypotheses, which is exactly
               what the red team already caught this spec doing to itself. Every remaining
               bullet gets measured before it gets built.

  NEXT       — tilemap is a Rust crate this run has not opened; the fix (send a cap, make
               `finish_reason == length` a first-class outcome instead of a printed field)
               needs a cargo build/test cycle that does not fit the remaining context. It is
               recorded here with exact line numbers so the next window builds rather than
               re-surveys.
```

### ◐ S6 · no model silently its own judge — SURVEYED; the affordance gap is worse than stated

```
AUDIT S6 (survey)
  BUILT      — nothing. Measured first, per the rule this run added after three spec claims
               were falsified by measurement in a single slice.

  PROVEN     — the spec says *"No surface sets a critic: `critic_model_ref` lives in
               `work.settings` JSONB and `CompositionSettingsView` contains no `critic`
               string."* Measured, it is CORRECT and SHARPER than that:
                 · `frontend/src/features/chat-ai-settings/types.ts:41` DOES declare
                   `ModelRole = 'chat'|'composer'|'planner'|'embedding'|'rerank'|'critic'` —
                   so the role exists in the type system.
                 · the literal `'critic'` appears NOWHERE else in that feature: no picker, no
                   option row, no write path.
                 · `critic_model_ref` appears in `frontend/src` in **`__tests__` FILES ONLY** —
                   `ChapterAssembleView.test.tsx:124,127`,
                   `CompositionSettingsView.test.tsx:41,45`,
                   `useChapterAssembly.test.tsx:33`. Zero production readers or writers.
               So the FE suite is GREEN on a configuration no user can produce: the fixtures
               hand components `{critic_model_ref: 'x'}` and assert the behaviour that follows,
               while the only way to reach that state in the product is hand-editing JSONB.
               That is the affordance-gate shape one level down — tests supplying a value the
               product cannot.

  NOT PROVEN — I did not check the MCP/agent surface or `chat-ai-settings`' server-side write
               endpoint; a critic may be settable by an agent tool even with no GUI, which
               would change "100% self-graded" to "100% minus whatever agents set". I also did
               not measure the actual self-graded FRACTION on real jobs — the spec asserts
               "100% minus hand-edited JSONB" and I have confirmed the affordance is absent,
               not counted the jobs. And I did not verify the five other S6 corrections
               (`purpose` discriminator, enforce-at-write-time, move to provider-registry,
               compare RESOLVED provider models, the static gate's shape).

  DRIFT      — I nearly recorded "the spec is wrong again, `ModelRole` has 'critic'" on the
               strength of one grep hit. The type member exists and is unreachable; stopping at
               the hit would have inverted the finding. Three falsifications in a row had
               primed me to expect a fourth, which is its own bias — the measurement has to be
               allowed to CONFIRM as well as refute.

  NEXT       — S6 cannot close without the UI slice: shipping the label without the affordance
               produces a warning the author has no way to clear, which is the permanent-amber
               failure S1 exists to prevent. The FE work (a critic row in the model-role picker,
               writing `critic_model_ref` through the existing settings path) is the gating
               piece and it is a frontend cycle this window cannot start.
```

### ✅ S7 slice 3 — the Rust surface had no way to set an output cap at all

```
AUDIT S7-3
  BUILT      — `ChatStreamRequest::with_max_tokens` in the Rust SDK (it did not exist), and
               tilemap's L3 harness now sends `L3_MAX_OUTPUT_TOKENS = 8192`.

  PROVEN     — `cargo test -p loreweave_llm --test budget_contract`:
                 `test result: ok. 5 passed; 0 failed` — including
                 `the_builder_can_actually_SET_the_budget_it_normalises ... ok`
               `cargo test -p tilemap-service`: `test result: ok. 5 passed; 0 failed`
               `cargo check -p loreweave_llm -p tilemap-service`: `Finished dev profile`
               gates: `ai-provider-gate (full): OK` ·
               `llm-budget-ssot-gate: PASS — 92 LLM call site(s) scanned` · `[language-rule] PASS`

               THE FINDING IS WIDER THAN TILEMAP. `max_tokens` was declared on
               `ChatStreamRequest` (models.rs:106), defaulted to `None` (:147), and `normalize`
               already coerced `Some(0)` → `None` (:171) — the conversion stood ready for a
               value nothing could supply, because there was no builder. Measured: NO Rust
               service in the repo set an output cap. The whole Rust surface sent uncapped.

               The new test carries its CONTROL in the same body: an un-built request asserts
               `max_tokens.is_none()` first, so the positive assertion is about the builder and
               not about a default — and it re-checks after `normalize`, because a builder
               whose value `normalize` silently dropped would be worse than no builder.

  NOT PROVEN — 8192 is a RUNAWAY GUARD, not a sizing model. The tool returns a bounded array
               of zone classifications whose real size is the zone count; I did not measure
               what a fixture actually produces, so the number is "far above anything
               plausible" rather than derived. Sizing it per-kind is S7-4 and remains undone.
               No live run: tilemap's harness needs an lmstudio L3 measurement, and the cap's
               EFFECT (a long generation stopping at the cap rather than running on) is
               therefore unobserved — I proved the value reaches the wire, not that the wire
               honours it. And the other Rust services remain uncapped; this slice added the
               ability and used it in ONE place.

  DRIFT      — I nearly claimed a bug that is not there. `tool_use_success:
               classifications_parsed > 0` looked like "a truncated run reads as success", and
               I started writing it up that way — but the classifications ARE parsed, so the
               field is literally true, and the render already prints `finish_reason`. The real
               defect was the plainer one underneath: no cap was ever sent. Reaching for the
               more dramatic reading of code I had just met is how B4 and B5 got their severity
               walked back on this same project.

  NEXT       — S7-4: per-kind sizing for the JSON kinds. The spec is explicit that `prose` is
               mechanical and the rest are not (`cast_plan`'s 4000 is rows × per-row tokens;
               `motif_conformance`'s 512 is a 20-word reason), so 8192 above is a placeholder
               that S7-4 should replace with a derived number.
```

### ✅ S7 slice 4 (tilemap) — the cap now tracks what it caps

```
AUDIT S7-4 (tilemap)
  BUILT      — `l3_output_budget(zones)` replaces the flat 8192 S7-3 shipped as a placeholder:
               `zones × L3_TOKENS_PER_ZONE`, floored at 512 and ceilinged at 8192. Derivation
               and runaway guard are now two separate jobs.

  PROVEN     — `cargo test -p tilemap-service --lib s7_budget`:
                 `test result: ok. 3 passed; 0 failed; 0 ignored; 0 measured; 464 filtered out`
               `cargo test -p tilemap-service --lib`:
                 `test result: ok. 467 passed; 0 failed` (464 before, +3)
               gates: `ai-provider-gate (full): OK` ·
               `llm-budget-ssot-gate: PASS — 92 LLM call site(s) scanned` ·
               `[language-rule] PASS` · `enforcement-claims-gate: OK`

               Each of the three tests carries its counterweight rather than only its claim:
               "tracks the zone count" is paired with "a 1-zone call still gets the envelope"
               (sizing PURELY by count would starve it) and with "a hostile list cannot ask for
               the moon" — which also pins `saturating_mul`, because a wrapping multiply would
               turn `usize::MAX` zones into a SMALL budget, the failure being silent.

  NOT PROVEN — `L3_TOKENS_PER_ZONE = 128` is REASONED from the tool's shape (one small JSON
               object per placeholder: an id, some enum-ish fields, a short reason), NOT
               measured against a real completion. The right number comes from a live L3 run's
               `output_tokens / zones`, which needs lmstudio and a fixture; until then it is a
               better-shaped guess than 8192, not a measured one. And this is tilemap ONLY —
               S7-4's real scope is the JSON kinds in `call_budget` (`cast_plan`'s 4000 as rows
               × per-row, `motif_conformance`'s 512 as a 20-word reason), which is untouched.

  DRIFT      — I nearly folded the ceiling INTO the derivation — one constant doing both jobs.
               That is exactly the S7-1 bug I fixed four commits ago, where the distill window's
               output reserve and the request's cap were one decision expressed as two numbers
               that then disagreed. Here it would have been the inverse: two decisions collapsed
               into one number, so a raised ceiling would silently re-size every request.

  NEXT       — S7-4 proper: per-kind sizing inside `call_budget` for the JSON kinds. Then S6,
               which is surveyed and blocked on the critic picker row.
```

### ✅ S7 slice 2 — EXECUTED, not just read

```
AUDIT S7-2
  BUILT      — nothing new. The gap the spec describes was closed earlier in this session by
               the LLM-BUDGET SSOT M1-M3 work; what this entry adds is the EVIDENCE, because
               the first version of it said "already done" on the strength of reading two call
               sites, and a claim is not a measurement.

  PROVEN     — `go -C services/glossary-service test ./internal/llmbudget/...`
                 `ok  github.com/loreweave/glossary-service/internal/llmbudget  0.417s`
               and the named tests that back the specific claim:
                 `--- PASS: TestTruncatedFinishReasonMatchesTheContract`
                 `--- PASS: TestStructuredTruncationIsFatalMatchesTheContract`
                 `--- PASS: TestTheTruncationMessageMakesSenseForAnUncappedRow`
                 `--- PASS: TestTruncationErrorNamesTheCauseAsCapacityNotMalformedOutput`
               Plus the two production call sites: `llmbudget.Truncated(res.FinishReason)` at
               `action_plan_tools.go:228` and `entity_doc_extract_tools.go:245`. The spec's
               "glossary-service has ZERO FinishReason checks service-wide" is FALSE.

  NOT PROVEN — the package's own tests pass; I did not execute glossary's FULL Go suite, and I
               did not verify that `Truncated` is reached on every BRANCH of those two handlers
               — only that each file calls it. A handler that returns early before the check
               would still satisfy everything measured here.

  DRIFT      — I wrote "already done" and moved on. It took the goal's own condition — "saying
               a check passed without pasting its output does NOT satisfy this" — to send me
               back for the four PASS lines. The rule caught me on the one claim in this whole
               run that I had not measured, which is exactly the claim it was written for.

  NEXT       — S7-4's real scope (`call_budget`'s JSON kinds), then S6.
```

### ◐ S6 survey v2 (2026-08-02) — the two questions the first survey left open, answered

The first survey's NOT PROVEN list named two things it had not checked: the MCP/agent surface,
and the server-side write endpoint. Both measured now, and the gap is **wider** than recorded.

| surface | can it set a critic? |
|---|---|
| **FE GUI** | **No.** `MODEL_ROLES` in `ChatAiSettingsPanel.tsx` is `chat · composer · planner · embedding · rerank` — no `critic` row. `critic_model_ref` appears in `frontend/src` in `__tests__` files ONLY. |
| **Agent / MCP** | **No.** Every `critic` hit in `frontend_tools.py` and `contracts/frontend-tools.contract.json` is the panel id `quality-critic` — the critic OUTPUT view. No tool sets a model role. |
| **`settings.model_roles`** | **No — and this is the new finding.** It has **one reader** (`internal_model_settings.py`, feeding chat-service's effective-settings Book tier) and **ZERO writers repo-wide**. |

So the map that "wins if present" is never present, and the Book tier of the Chat & AI settings
cascade resolves a key nothing in the repo can write. Same no-producer shape as `plan_status`,
which the POST-RUN REVIEW found and fixed one layer up — except this one is a whole scope tier.

⇒ S6's affordance is not "a missing picker row". The write path does not exist at any layer, and
the surface that would consume it (`model_roles`) is a read-only contract with no producer. That
is what the slice has to build, and it is why shipping the label alone would produce a warning
the author has no way to clear.

### ✅ S4 — the injection gate was reading COMMENTS as evidence about behaviour

```
AUDIT S4 (injection-coverage-lint)
  BUILT      — `_code_lines()`: the lint's three signals now match against source with
               COMMENT and DOCSTRING lines blanked (regular string literals kept — a prompt
               template IS code). `SCAN_DIRS` widened from 4 services to 10. Two stale
               BASELINE rows deleted, 8 newly-surfaced ones added. A stale-row NOTE so the
               baseline can shrink. Nine teeth tests, wired into foundation-ci.

  PROVEN     — I FOUND THIS BY TURNING THE GATE RED MYSELF. `injection-coverage-lint` exits 1
               on `engine/compress.py`, and the marker is the word "passage" at line 170 —
               inside a COMMENT I wrote in commit 767f2fe2f (S7 slice 4). The gate is in CI.
               I had not run it, because the gate set I had been pasting as "the gates" is a
               SUBSET of what CI runs.

               MEASURED, where the markers actually live, per file:
                 compress.py            comment 1 · docstring 0 · CODE 0  ← flagged on prose
                 canon_reflect.py       comment 1 · docstring 1 · CODE 0  ← BASELINE'd on prose
                 wiki/generate.py       comment 1 · docstring 0 · CODE 0  ← BASELINE'd on prose
                 select.py              comment 11 · docstring 1 · CODE 2  ← real, stays
               Two BASELINE rows called their modules "genuine gaps — composition-service has
               no sanitizer anywhere" on the strength of a comment. `select.py`'s own row
               already records this happening once: a feature gave it the word "passage" in
               prose and the row was written rather than rename the word to dodge the regex.
               That was the right call for the wrong reason — the regex should not have been
               reading prose.

               AND THE DANGEROUS DIRECTION, which nobody had looked at: `SANITIZER_REF`
               matched raw text too, so a module whose ONLY mention of `neutralize(` was in a
               comment counted as PROTECTED. Measured: **0 files** exploit this today — but
               nothing prevented it, and a security gate silenced by a sentence is worse than
               no gate because it reports coverage. Now closed and pinned by two tests.

               WIDENING FOUND REAL SURFACE: 8 modules never scanned — 7 in
               translation-service, 1 in worker-ai. translation is the one that should have
               been in `SCAN_DIRS` first: it builds prompts from IMPORTED third-party book
               text, the least trusted bytes on the platform, and references no sanitizer
               anywhere. Baselined with notes + a Debt row, not silently cleared.

               gates: `injection-coverage-lint (full): OK — every retrieved-text
               prompt-assembly module routes through the sanitizer (22 baselined)` ·
               `gate-teeth-gate: PASS — 57 CI-invoked gate(s), every one able to return
               non-zero. 12 carry a red-ability proof; 45 held at baseline` (ratcheted 46→45,
               the meta-gate ASKED for it) · `ai-provider-gate OK` ·
               `generation-guard-gate PASS` · `enforcement-claims-gate OK` ·
               `db-safety-gate exit 0` · `llm-budget-ssot-gate PASS` · `[language-rule] PASS`.
               scripts suite `340 passed`; the new teeth `9 passed`, none skipped.
               RED-ABLE, and it discriminates: injecting a REAL code-level hole
               (`passage = body` folded into a message, no sanitizer) reds with
               `FAIL … services/composition-service/app/engine/compress.py`, exit 1, while
               the prose-only marker stays green. Restored by re-editing.

  LIVE       — live infra unavailable: a lint has no runtime path. Its behaviour is proven by
               the six-case probe (real hole · comment-only marker · docstring-only marker ·
               sanitizer-in-comment · real sanitizer · template string) rather than by a run.

  NOT PROVEN — the 8 new rows are TRACKED, NOT FIXED. translation-service still folds imported
               book text into prompts with no sanitizer; this slice makes that visible and
               guards against a ninth, and it does not close one of them. Routing them through
               `neutralize_injection` is a separate change with a real risk of its own — a
               sanitizer that mangles source text is a TRANSLATION-FIDELITY bug, which is
               precisely why those rows are `OutputKind.MIRROR` elsewhere.
               The Go and Rust surfaces the spec also names (glossary, tilemap) are still
               unscanned: this lint is Python-only and making it polyglot is a rewrite.
               The spec's two structural classes — SECOND-ORDER ECHO (model output replayed
               into the next turn) and DECLARED-BUT-UNIMPLEMENTED FENCING (tilemap's prompts
               promise `<author_text>` tags its builders never emit) — are untouched; module
               -level coverage cannot see either.
               And the detector's real limit is now pinned rather than glossed: an UPPERCASE
               marker inside a prompt template (`"PASSAGE:\n" + x`) does not register, because
               `RETRIEVED_TEXT` matches identifier-shaped names.

  DRIFT      — three, and the first is about my own process.
               1. I turned a CI gate RED with a comment and shipped it, because the gate set I
                  had been running and pasting all run — ai-provider, generation-guard,
                  enforcement-claims, db-safety, llm-budget, language-rule — is a SUBSET of
                  what CI runs. Six gates is not "the gates". Every VERIFY block before this
                  one asserted its evidence honestly and against an incomplete list.
               2. My first red-ability injection used `_retrieved_passage = body` and the gate
                  stayed green. I was one step from writing up "the prose fix blinded the
                  detector" — the regex needs a word boundary and `_` is a word character, so
                  the NAME was wrong, not the gate. Measuring the regex directly settled it.
               3. My teeth-test probe asserted an uppercase `"PASSAGE:"` template MUST flag.
                  It does not, and never did — before or after my change. I had begun treating
                  it as a regression I caused; checking the pre-fix behaviour showed it was
                  always the boundary. Recorded as a known limit rather than "fixed" by
                  widening a security regex on the strength of my own assumption.
               Plus: my first stale-baseline test guarded on `hasattr(inj, "iter_files")` — a
               name that does not exist — so it SKIPPED, and a skipped test reads as passing.
               ROT-0 audited 200 tests for exactly that shape.

  NEXT       — S9, which the spec INVERTS: do not extract a fourth guard SDK. Its entry
               criterion is mechanical — three services carrying a structurally identical
               `GuardReport` with no service-specific fields, proven by a test that imports
               all three — and only composition has one today.
```

### ◐ S3 slice 1 — one `skip_reason` vocabulary. The docs were already false.

```
AUDIT S3-1 (skip_reason vocabulary)
  BUILT      — `app/engine/finding.py`: `SkipReason`, a closed `StrEnum` adopted by both heal
               pipelines, plus an `ast` guard that reds on any raw string assigned to a
               `.skip_reason`.

  PROVEN     — measured across the two producers, three defects in four lines of comment:
                 self_heal.Finding      # not_located | overlap | edit_failed | edit_expanded
                 plan_heal.PlanFinding  # not_found   | edit_failed | edit_expanded
               1. `not_located` and `not_found` are ONE concept under two names — "the quoted
                  text could not be located in the thing being edited".
               2. The declared list is INCOMPLETE and the omission is load-bearing: `self_heal`
                  also writes `refuted` and `noop`, and `worker/operations.py` counts
                  `f.skip_reason == "refuted"` — the one member the documentation never named.
               3. Both are free `str`, so a typo produces a finding that is silently
                  un-countable: `refuted: 0` on a run where every finding was refuted.

               NOT merged, deliberately: `glossary_build`'s `skip_reason` is a free-text
               sentence shown to a human and persisted in a `TEXT` column ("the glossary
               already has an entry with this name"). Same spelling, different concept — the
               same call made for lore-enrichment's billing estimator in S11-2.

               composition `8 failed, 3919 passed, 8 skipped` (was 3917; the 8 are the tracked
               test_motif_retrieve_db rows).
               gates: `ai-provider-gate OK` · `generation-guard-gate PASS` ·
               `enforcement-claims-gate OK` · `db-safety-gate exit 0` ·
               `llm-budget-ssot-gate PASS` · `[language-rule] PASS`.
               RED-ABLE: re-introducing `f.skip_reason = "not_found"` fails BOTH the raw-string
               guard (`[(180, 'not_found')] == []`) and the duplicate-name guard. Restored by
               re-editing.

               LIVE, $0 gemma-4-26b, deployed service AND worker hash-verified:
                 findings 6 · located 6 · proposals 1 · skip_reasons seen [] ·
                 OUTSIDE vocabulary []
                 deterministic arm, all six members through the DEPLOYED module:
                   not_located · overlap · edit_failed · edit_expanded · refuted · noop
                   members whose str() != value : []

  NOT PROVEN — the live run's vocabulary check was VACUOUS on both attempts: the model
               produced no skips, and an empty set is trivially inside any vocabulary. That is
               why the deterministic arm exists, and it is worth saying plainly that the
               interesting half of that live run proved nothing. A run that actually exercises
               `refuted` needs the verify tier enabled with a model that refutes.
               This is S3 SLICE 1, and it is the SMALL half. The spec's actual S3 is one
               `Finding` with a `locator` union (`span | scene_index | node_id`, with
               `trace_span_id` reserved), and that is untouched: five composition finding types
               still carry five different locators — char offsets, chapter+scene, seam pairs,
               block ids. Nothing was unified except the outcome vocabulary.
               `MergedFinding`, `_RepetitionFinding`, `_OverResolveFinding` and `CanonViolation`
               have no `skip_reason` at all and were not touched.

  DRIFT      — I shipped a regression and only the LIVE run caught it. `class SkipReason(str,
               Enum)` satisfies `== "refuted"` and JSON-serialises to `"noop"`, so all six unit
               tests passed — but `str()` and f-strings return `"SkipReason.NOOP"`. Any
               consumer that FORMATS rather than compares would have started emitting the
               member path. The live probe printed `skip_reasons seen: ['SkipReason.NOOP']`
               and that is the only reason it was found; `StrEnum` fixes it. Every test I had
               written used `==`, which is precisely the shape that cannot see this.
               Second: my first duplicate-name guard scanned raw FILE TEXT for `not_found` and
               reddened on my own comment explaining that `not_found` was removed. Prose is not
               usage — the same distinction the deferral registry's stripper had to learn, met
               from the other side. Rewritten over the AST's string constants.

  NEXT       — S4 (the plan half onto the spine). Its gate already exists
               (`scripts/injection-coverage-lint.py`); the work is widening `SCAN_DIRS` and
               putting an expiry on the 15-row permanent baseline that today exempts every
               composition engine module.
```

### ✅ S11 slice 3 — the contract's two closed sets were never checked. S11 CLOSES.

```
AUDIT S11-3 (context-trace contract)
  BUILT      — `phases` and `tiers` added to `contracts/context-trace.contract.json`, sourced
               from `loreweave_context` rather than restated; `TraceTier` closed on the TS side
               (it was a bare `string`); bidirectional parity tests on both sides, mirroring
               the discipline `breakdown_categories` already had; and a producer-side test that
               every emitted span's phase/tier is IN the closed set.

  PROVEN     — the spec's namespacing item was MEASURED FIRST and turned out not to be the
               work. `chat.*`/`composition.*` namespacing exists to let composition extend the
               category vocabulary — and composition emits NOTHING into the trace: the only
               `TraceAccumulator` consumers in the repo are chat-service's `stream_service`,
               `compact_service` and `token_budget`. Namespacing now would be a vocabulary
               with no second surface to separate, i.e. the zero-consumer ceremony S8 and S12
               both exist to reject. Recorded in Debt with what un-parks it.

               What IS wrong today is the spec's other sentence, and it is worse than stated:
                 · `phase` — closed on BOTH sides (`PHASES` in Python, `'planner' | 'compiler'`
                   in `TraceSpanFrame`) and cross-checked by NOTHING. A rename on either side
                   would not red the other.
                 · `tier` — `TIERS` in Python, and in TypeScript the literal declaration
                   `tier: string; // T0..T6`. The COMMENT carried the constraint and the type
                   carried none, so the Inspector would render `"T9"`, or any string at all,
                   exactly as happily as a real tier. A closed-set value typed `string` on the
                   consuming side is the defect the Frontend-Tool Contract exists to prevent —
                   sitting inside the contract-checked payload itself.
               `breakdown_categories` had the both-ways parity test all along; these two had
               none, because the contract did not carry them to compare against.

               suites: chat-service `1963 passed` · chat FE `74 files, 656 passed` ·
               `tsc --noEmit` exit=0 · context-trace contract `13 passed`.
               gates: `context-inspector-trace-gate --selfcheck: SELFCHECK PASS — contract
               parses (13 frame fields, 6 span fields), 5 turns declared` ·
               `ai-provider-gate OK` · `generation-guard-gate PASS` ·
               `enforcement-claims-gate OK` · `db-safety-gate exit 0` ·
               `[language-rule] PASS` · `i18n-completeness-gate OK`.
               RED-ABLE: widening `TraceTier` back to `string` fails `tsc --noEmit` with
               `src/features/chat/types.ts(250,7): error TS2322: Type 'boolean' is not
               assignable to type '["S11: this union was widened to `string` and is no longer
               closed", "TraceTier"]'`. Restored by re-editing.

  NOT PROVEN — no LIVE trace was captured. The gate's live half needs a stack on :8090 plus
               `JWT_SECRET`, and it said so rather than pretending: `Live half NOT run here`.
               So the vocabulary is proven consistent across three declarations and one
               producer, not proven against a frame a real turn emitted.
               The parity is over the SET, not the MEANING: nothing checks that FE `T5` renders
               what BE `T5` intends. `category` and `action` remain free strings on both sides
               and are deliberately untouched — `category` overlaps `breakdown_categories`
               without being the same vocabulary, and reconciling them is its own measurement.
               And composition still emits no trace, so "one context compiler" remains true of
               the BUDGET math (slices 1-2) and not of the TELEMETRY.

  DRIFT      — I wrote a `@ts-expect-error` test for the closed union and it was INERT.
               `tsconfig.json` excludes `src/**/__tests__` and `*.test.tsx`, so no test file is
               ever type-checked: the annotation could neither pass nor fail, and it reads
               exactly like enforcement. I caught it only because I widened the type to prove
               red-ability and `tsc` came back exit 0 — the injection I nearly skipped because
               the change looked too simple to need one. The assertion now lives in `types.ts`,
               which tsc does compile. Fifth check-that-cannot-fail this run, and the first one
               I wrote INTO a test file rather than found in someone else's code.
               Second, smaller: my first instinct was to build the `chat.*`/`composition.*`
               namespacing because the spec listed it. Grepping for `TraceAccumulator` took a
               minute and showed there is no second surface to namespace FOR.

  NEXT       — S3 (one `Finding`). Deliberately sequenced after S11, and slice 3 sharpens why:
               the repo has ≥9 finding/verdict types, and this slice just demonstrated the cost
               of a vocabulary declared in three places with no machine check between them.
```

### ◐ S11 slice 2 — the estimators. "Four copies" was a hypothesis, and it was wrong.

```
AUDIT S11-2 (token estimators)
  BUILT      — translation-service's `chunk_splitter.estimate_tokens` now IS the kernel's
               (`loreweave_context.estimate_tokens`), and `split_chapter` derives its
               chars-per-token from that same estimator instead of a separate pair of
               constants. Three assertions that restated the old constants were rewritten
               against tiktoken as ground truth.

  PROVEN     — THE SLICE'S PREMISE WAS FALSIFIED FIRST. "Converge the four `estimate_tokens`
               implementations" assumes four copies of one thing. Measured, they are four
               DIFFERENT intents, and one of them must not be touched:
                 · SDK `loreweave_context` — script-aware pre-send projection (the kernel).
                 · knowledge-service — real tiktoken `o200k_base`. The most accurate, and the
                   ground truth the others should be judged against.
                 · lore-enrichment — a deliberate OVER-estimate mirroring provider-registry's
                   billing math. Measured **3.05x** tiktoken on Vietnamese, by design, because
                   a spend guardrail must err high. The spec already says the 2 billing
                   conventions stay separate; merging it would be a BILLING correctness change.
                 · translation — a two-class local heuristic, and the only genuine duplicate.
               So this is the FOURTH spec bullet in this run falsified by measurement.

               THE DUPLICATE WAS ALSO A LIVE BUG. translation's estimator, against tiktoken:
                 text          chars   tiktoken   translation   ratio
                 Vietnamese      205         73            51   0.70x
                 Chinese          35         34            23   0.68x
                 English         134         28            33   1.18x
               Under-counting by a third, on the two scripts this service exists to translate.
               Its docstring claimed to have fixed *"the ~2.3x underestimation bug for CJK
               text that caused context window overflow and hallucination"* — it had closed
               two thirds of that gap and stopped. A chunk it believed was 2000 tokens reached
               the model at ~2900. Vietnamese was worse for a structural reason: the module had
               no Vietnamese class at all, so it was counted at the LATIN ratio.

               THREE TESTS WERE PINNING THE UNDER-COUNT, and the arithmetic is exact:
                 fixture           tiktoken   OLD (asserted)   NEW
                 "中" x150              150      100  (-33%)   158
                 "中" x3000            3000     2000  (-33%)  3150
               `test_estimate_tokens_cjk_3000_chars` even documented the history — v1's 857 was
               "catastrophically underestimated", v2's 2000 was pinned as the answer — while
               the real number was 3000 the whole time. `test_estimate_tokens_mixed` computed
               its `expected` FROM the module's own constants, so it would have passed for any
               value they produced.

               suites: translation `1139 passed` (was 1136) · SDK `1187 passed, 9 skipped`.
               gates: `llm-budget-ssot-gate PASS` · `ai-provider-gate OK` ·
               `generation-guard-gate PASS` · `enforcement-claims-gate OK` ·
               `db-safety-gate exit 0` · `[language-rule] PASS` ·
               `sdk-duplication-gate (full): OK — no new SDK-tier duplications`.
               RED-ABLE: re-inlining the old two-class arithmetic fails FIVE tests, including
               `test_the_estimator_IS_the_kernels_not_a_local_copy` (asserted by EFFECT across
               scripts, so an edit that keeps the import and re-inlines the maths still reds)
               and `test_vietnamese_is_no_longer_counted_at_the_LATIN_ratio`. Restored by
               re-editing.

               LIVE, deployed translation-service AND worker, both hash-verified (MATCH):
                 text          chars  est tok  chunks  max chunk tok  OVER BUDGET
                 Vietnamese     5800     1642       4            492            0
                 Chinese        1400     1422       3            498            0
                 English        5400     1350       3            490            0
               budget 500/chunk, `chars_preserved=True` on every row. Zero over-budget chunks
               is the property the old splitter could not hold.

  NOT PROVEN — no live TRANSLATION was run. The chunking is proven on deployed code over real
               prose; that smaller chunks produce better translations, or even that a
               previously-overflowing chapter now succeeds, is not measured. The failure this
               fixes (overflow → hallucination) is named in the module's own docstring, not
               observed by me.
               COST MOVED and nobody measured it: counting ~40% more tokens on CJK/Vietnamese
               means ~40% more chunks, i.e. ~40% more LLM calls per chapter for exactly the
               books this platform is for. That is the safe direction for correctness and the
               expensive one for spend, and it is a real product consequence shipped without
               a number.
               The kernel estimator is itself 0.78x tiktoken on my Vietnamese sample — better
               than 0.70x, still UNDER. The spec cites a 2026-07-07 eval claiming the
               script-aware heuristic tracks o200k within 3-6%; my three-sentence sample
               disagrees and is far too small to overturn a real corpus measurement, so I am
               recording the tension rather than re-tuning the kernel on n=3.
               knowledge-service and lore-enrichment are UNTOUCHED. The first is the ground
               truth and needs no change; the second must not be changed. So "one estimator"
               is not what shipped — what shipped is one PROJECTION estimator, with the
               measurement and the billing convention deliberately beside it.

  DRIFT      — I introduced a two-convention bug WHILE removing one, and it passed the suite.
               Swapping `estimate_tokens` for the kernel left `split_chapter` sizing its
               window from the old `_CJK_CHARS_PER_TOKEN = 1.5`, so a 100-token budget still
               cut 150 CJK chars that the new estimator counts as 158 — 58% over the budget
               the caller asked for, inside the module I was fixing for exactly this. The
               suite stayed green because the test asserting chunk COUNT was itself derived
               from the old constant. Caught by reading `split_chapter` after the swap, not by
               a test.
               Second: I ran the module docstring's claim ("CJK at ~1.5 chars/token") straight
               past me twice while editing the function underneath it. Stale prose describing
               behaviour that no longer exists is how the next reader re-derives the wrong
               model — the same shape as the `cross_scene_check` row whose `why` describes a
               call that does not exist.

  NEXT       — S11 slice 3: the `context-trace.contract.json` `breakdown_categories`
               namespacing (`chat.*` / `composition.*`). It is asserted on BOTH sides
               (BE ⊆ FE and FE ⊆ BE), so extending it is a consumer-visible shape change and
               cannot be done additively the way slices 1 and 2 were.
```

### ◐ S11 slice 1 — the allocation layer the spec said "does not exist and must be written"

```
AUDIT S11-1 (allocation layer)
  BUILT      — `loreweave_context.allocate_context` → `ContextAllocation`, and composition's
               `pack_budget_for` composing it with `scale_by_window`. Composition's three
               pack-budget call sites now ask how much grounding FITS, not merely how much
               they would like.

  PROVEN     — the defect is arithmetic, and it was never a subtle one:
                 `scale_by_window(6000, window)` as a share of the window it must fit inside
                   window 4096 → 6000 = 146.5%   ← the block alone exceeds the whole context
                   window 8192 → 6000 =  73.2%   ← before the prompt, and before any output
               `scale_by_window`'s contract is *"Never smaller than flat_default … this only
               ever grows"*, which is right for the flat-constant problem it was written for
               and wrong for an allocator, whose entire job is being able to say LESS.

               THE COMPOSITION IS THE POINT, and getting it wrong in the other direction was
               the trap: `allocate_context` alone CAPS at the default, which would have
               revoked `scale_by_window`'s growth for a 1M-window model — fixing a
               small-window bug by introducing a large-window one. So `scale_by_window`
               answers "how much would we like" and `allocate_context` answers "how much
               fits", and a test pins the 1M case at 30000.

               MEASURED, which is what RUN-STATE invariant 6 REQUIRES before a consumer may
               switch — `no existing loreweave_context consumer changes behaviour until its
               own measurement says it may`:
                 window    before   after   effect
                   None      6000    6000   unchanged  (unresolved window ⇒ caller's number)
                   4096      6000     512   REDUCED
                   8192      6000    1444   REDUCED
                  16384      6000    6000   unchanged
                 200000      6000    6000   unchanged
                1000000     30000   30000   unchanged  (the growth survives)

               LIVE, on deployed code, both images rebuilt + hash-verified (budget.py and
               engine.py MATCH in service AND worker):
                 resolve_context_length → 200000 (live provider-registry)
                 THE MODEL THIS STACK SERVES: before 6000 · after 6000 · clamped=False ·
                   fits=True · source=window  ⇒ NO-OP (identical)
                 counterfactual on the same deployed code:
                   window  4096 → 512  clamped=True  fits=False
                   window  8192 → 1444 clamped=True  fits=True
                   window 16384 → 6000 unchanged
               and the clamp is NOT silent — the run printed
               `pack budget CLAMPED to the model's window: grounding 512 (wanted 6000) ·
                window=4096 · output_reserve=4700 · fits=False`.

               suites: composition `8 failed, 3911 passed, 8 skipped` (was 3900; +11 — the 8
               are the tracked test_motif_retrieve_db rows) · SDK `1187 passed, 9 skipped`
               (was 1174; +13).
               gates: `llm-budget-ssot-gate PASS` · `ai-provider-gate OK` ·
               `generation-guard-gate PASS` · `enforcement-claims-gate OK — 103 path(s)` ·
               `db-safety-gate exit 0` · `[language-rule] PASS` ·
               `context-budget-defaults-lint` clean.
               RED-ABLE: passing `None` as the window inside `pack_budget_for` (so every
               allocation degrades to flat) fails exactly the three small-window tests and
               leaves the no-op ones green — which is the right signature, because a
               regression here should look like "the fix stopped working", not like
               "everything changed". Restored by re-editing.

  NOT PROVEN — `PACK_OUTPUT_RESERVE_TOKENS = 4700` is REASONED (1000 words × 2.6 vi
               tokens/word × the PROSE headroom), NOT measured against real scene replies. It
               is also used because the TRUE output budget cannot be known at allocation
               time: `scene_output_budget` needs the profile's language, and the profile comes
               out of the pack this budget is sizing. That ordering is worked around, not
               resolved.
               `DEFAULT_OVERHEAD_SHARE = 0.25` is likewise read off the packer's segment list
               rather than measured against real prompts.
               NO LIVE GENERATION on a small-window model. The 4096/8192 rows are the deployed
               code computing against those numbers, not a draft produced by an 8K model — so
               "the request now fits" is arithmetic, not an observed success. A BYOK model
               with a small window is the case that matters and this stack has none.
               And this is S11 SLICE 1 only. The slice's other parts are untouched: FOUR
               `estimate_tokens` implementations still exist (SDK, knowledge, lore-enrichment,
               translation), the `context-trace.contract.json` `breakdown_categories`
               namespacing (`chat.*` / `composition.*`) is not started, and the plan half's
               cl100k-calibrated budget in `plan_forge/existing_state.py` is unchanged.

  DRIFT      — I nearly adopted `allocate_context` on its own at the three call sites. It
               reads as the obvious switch, it passes every small-window test, and it would
               have silently capped a 1M-context model at 6000 where it had been getting
               30000 — a regression invisible to exactly the tests I had just written, because
               they were all about windows being too SMALL. Caught by running the numbers at
               1M before editing, not by a test.
               Second: my first `pack_budget_for` returned a bare int. That would have thrown
               away `clamped` and `fits` at the moment of use, which is the S8 defect verbatim
               — a number the pack computed, documented, and handed to nobody — inside the
               slice about composing budgets honestly.

  NEXT       — S11 slice 2: the four `estimate_tokens` copies. The spec's crux is already
               settled (the script-aware heuristic tracks o200k within 3-6%; cl100k is the
               outlier and tiktoken cannot be a kernel dependency), so that slice is
               convergence work, not a measurement.
```

### ✅ S6 — no model silently its own judge. The affordance shipped WITH the label.

```
AUDIT S6
  BUILT      — `app/engine/critic_policy.py` (`resolve_critic` → `CriticResolution` carrying a
               four-member `CriticStatus`), adopted at all SEVEN sites in `routers/engine.py`;
               a per-status author-facing message map; and the UI row that makes any of it
               reachable — a Critic model select in `CompositionSettingsView` writing
               `critic_model_ref` + `critic_model_source` through the existing (merging) Work
               PATCH, plus an inline warning when the chosen critic IS the drafter.

  PROVEN     — the rule was hand-rolled SEVEN times: six copies of
               `distinct = bool(c_ref and c_src and str(c_ref) != str(body.model_ref))` and a
               seventh written INVERTED as the critique endpoint's guard. Six stayed in
               lockstep; the seventh is where the defect grew — it collapsed TWO states into
               one sentence, *"critique skipped: no distinct critic model configured"*,
               returned both when no critic was ever set and when the author had set the model
               already writing the prose. Different problems, different fixes, identical text.
               The two existing route tests asserted `"skipped" in warning`, which is true of
               BOTH, so nothing could see the conflation.

               LIVE, on deployed code, both images rebuilt + hash-verified (critic_policy.py
               and engine.py MATCH in service AND worker):
                 no critic set      → not_configured  · "no critic model is set … Set one in
                                                        Composition → Settings → Critic model."
                 critic == drafter  → same_as_drafter · "the SAME model that wrote this
                                                        passage … Choose a different model."
                 ref without source → incomplete      · "a model was recorded without its
                                                        provider … Re-select."
                 DISTINCT critic    → configured      · the critique RUNS
                 `distinct statuses across the four arms: 4 — PASS (they differ)`

               suites: composition `8 failed, 3900 passed, 8 skipped` (was 3883; +17 — the 8
               are the tracked test_motif_retrieve_db rows) · frontend composition
               `155 files, 1057 passed` · `tsc --noEmit` exit=0.
               gates: `llm-budget-ssot-gate PASS` · `ai-provider-gate OK` ·
               `generation-guard-gate PASS` · `enforcement-claims-gate OK — 103 path(s)` ·
               `db-safety-gate exit 0` · `[language-rule] PASS`.

               RED-ABLE, restored by re-editing: pointing SAME_AS_DRAFTER's message at
               NOT_CONFIGURED's text fails BOTH guards — the route test
               (`both states still share one sentence`) and the uniqueness test
               (`two statuses share a message — the conflation is back`).
               An `ast` guard also reds if anyone re-inlines a critic identity comparison in
               `engine.py`, and it carries a CONTROL proving the detector sees that pattern —
               without it, an empty-list assertion passes just as well when the scan is broken.

  NOT PROVEN — THE COMPARISON IS ON `user_model_id`, NOT ON THE RESOLVED PROVIDER MODEL. Two
               BYOK rows can point at the SAME underlying model, so a user with two gemma
               credentials gets `CONFIGURED` and a model grading its own prose — the precise
               failure this slice is named for, one level below where it now looks. No route
               exposes the underlying model for a `user_model_id` (provider-registry has
               `/context-window` and nothing equivalent), so closing it needs a new
               cross-service contract plus a caching decision on a per-generation hot path.
               Tracked in Debt; deferred under gate #2, not waved through.
               The live run is POLICY-level on deployed code, not a book-scoped HTTP run: the
               four arms exercise the real deployed `resolve_critic` and the real message map,
               while the endpoint's `critic_status` field is proven by route tests rather than
               by a browser. No browser smoke on the new select at all, so the i18n keys are
               asserted as chosen, not as rendering well in Vietnamese.
               The FE `criticIsDrafter` warning compares against `default_model_ref`, the
               book's DEFAULT drafter — a session that overrides the model per call can still
               reach SAME_AS_DRAFTER without the UI predicting it. The server is the authority
               and does refuse it; the UI is an early warning, not the check.
               And `model_roles` still has ZERO writers: this slice writes the legacy scalars,
               which the dual-read consumes, so the newer map remains a read-only contract with
               no producer.

  DRIFT      — I nearly shipped the UI row alone. The spec's requirement is the affordance, and
               a select that writes `critic_model_ref` satisfies it literally — but the state
               the author would most often land in is "I picked the model I already use", which
               the server silently refuses. Shipping the picker without the same-as-drafter
               warning would have produced a setting that looks applied and does nothing: the
               permanent-amber shape S1 exists to end, re-created by the slice meant to close it.
               Second: my first pass at replacing the six copies matched on `\r\n` and reported
               `8-indent copies: 0 · 4-indent copies: 0` — a clean no-op that printed like a
               successful run. Had I not printed the remaining count in the same breath I would
               have moved on believing the refactor had landed.

  NEXT       — S11 (one context compiler), the largest remaining slice. S6 hands it nothing
               structural, but the `signal_inert`/`CriticStatus` pattern is now used twice in
               two days — a row or a state DECLARING what it cannot do, checked by a probe
               rather than trusted — and S11's additive-then-switch rule needs exactly that
               shape to prove no existing `loreweave_context` consumer changed behaviour.
```

### ✅ S7 slice 4 — the budget-seam rot. The ratchet was measuring the wrong thing.

```
AUDIT S7-4 (budget-seam rot)
  BUILT      — the 28 frozen budgets are gone, and the number that tracked them now means
               something. Three parts:
               1. `max_tokens: int = max_tokens_for("kind")` → `max_tokens: int | None = None`
                  resolved AT THE CALL, at 20 sites. A default argument is evaluated once at
                  IMPORT, so it could never see a roster, a chapter or a candidate list —
                  which is the whole defect, independent of whether the number moves.
               2. `CallProfile.signal_inert` in BOTH registries, for rows where NOTHING can
                  size the call (translation's three MIRROR rows short-circuit before the
                  sizing model runs). Declared, not assumed: a two-directional PROBE test in
                  each service fails if the flag disagrees with `call_budget` either way.
               3. `llm-budget-ssot-gate` now scores a kwarg only if the KIND READS it, and
                  learned the sentinel shape so it stops punishing the migration it enforces.
               Plus one production bug the live run found — see PROVEN.

  PROVEN     — THE RATCHET WAS SATISFIABLE WITH THEATRE, and that is the finding. `language`
               is consulted ONLY on the PROSE and VERDICT branches; STRUCTURED sizes on
               `target * 220` and EDIT on `target / 3`, and neither reads it. So adding
               `language=` to a STRUCTURED call site cleared it from the backlog and changed
               no budget, ever. Injected exactly that into `propose_cast` — the OLD gate
               counts `{language}` as signal and goes GREEN; the new one FAILs, naming the
               site and its kind. Restored by re-editing.

               `llm-budget-ssot-gate: PASS — 94 LLM call site(s) scanned …
                 19 traced to call_budget() · 29 held at baseline (8 literal, 21
                 unattributed, 0 signature defaults) · 46 built off-site
                 adaptive signal: 18/31 budget calls carry one that their KIND reads ·
                 4 declared signal_inert (nothing can size them) · 9 held at baseline`
               28 → 9, and the attribution axis held at EXACTLY its 29 baseline — the
               conversion is attribution-neutral, which is what says the drop is real work
               and not a widened detector.

               NON-VACUITY, measured per site (BEFORE = the old frozen default):
                 propose_edits_direct  20k-char chapter   3000 → 13333   4.44x
                 propose_cast          40-name roster     4096 → 24750   6.04x
                 propose_world         full roster        4096 → 32768   8.00x
                 score_promise_coverage 18 promises       4096 →  9900   2.42x
                 judge_prose           30 rules, vi       1536 →  5202   3.39x
                 plan_character_arcs   12 characters      4096 →  6600   1.61x
               10 of 18 realistic cases resolve to a DIFFERENT number; 8 still land on the
               floor and are LISTED as such rather than counted as wins.

               suites: composition `8 failed, 3883 passed, 8 skipped` — the 8 are the tracked
               `test_motif_retrieve_db` rows (earlier audits said 11; three were the
               duck-typed stubs fixed in 9e346a439) · translation `1136 passed` · SDK
               `1174 passed, 9 skipped` · gate teeth `19 passed`.
               gates: `llm-budget-ssot-gate PASS` · `ai-provider-gate OK` ·
               `generation-guard-gate PASS` · `enforcement-claims-gate OK — 103 path(s)` ·
               `db-safety-gate exit 0` · `[language-rule] PASS`.

               LIVE, $0 gemma-4-26b, both images rebuilt and hash-verified (7 files, MATCH in
               service AND worker — the run before this one verified only the service and the
               drift log already carries that mistake once):
                 resolve_context_length → 200000, live from provider-registry
                                    BLANK roster        ESTABLISHED roster
                 propose_cast  wire       4096                24750
                 propose_world wire       4950                32768
                 cast parsed                 6                    7
                 world parsed                9                   10
               Same code, same model, same premise — only the roster differs. The budget
               reaching the WIRE differs 6x. That is the control that makes this a statement
               about the signal and not about the fixture.

               …AND THE LIVE RUN FOUND A DEAD PRODUCTION PASS. `propose_world` parsed **0**
               entities in both arms. Not truncation: `finish_reason=stop`, 2864 characters of
               valid JSON. `_WORLD_SCHEMA` requires `{"items": [...]}` — added when WORLD_KINDS
               moved to decoder enforcement — and `parse_world` still read a bare array, so
               `isinstance(arr, list)` was False and the pass degraded to `[]` on every
               grammar-honouring provider. Pass 3 returns `[]` on any failure, so a DEAD PASS
               and a premise with no world in it were indistinguishable from outside. Fixed,
               with an ambiguous-wrapper case refused rather than guessed; live after the fix:
               0 → 9 and 0 → 10.

  NOT PROVEN — the live run is NOT book-scoped. `propose_cast`/`propose_world` take a premise
               and write nothing, so there is no throwaway book and no debris — but neither is
               there evidence about the planning ORCHESTRATION, only about the two calls.
               The window clamp is UNEXERCISED in production: the dev model reports a 200k
               window, so its half-share (100000) is above every budget here. The clamp is
               proven only by unit test (8192 → 4096, with the unclamped control). A
               small-window BYOK model is the case that matters and it was not run.
               `_INVENTED_CAST_ALLOWANCE = 5` and `_INVENTED_WORLD_PER_KIND = 3` are READ OFF
               the prompts' own wording, not measured against what models return. And
               `_TOKENS_PER_ITEM = 220` is the SDK's generic per-item cost; a world entity is
               plausibly half that, which is why a full roster reaches the 32768 runaway
               ceiling. Nobody has measured a real per-item cost.
               The 9 remaining no-signal sites are argued, not proven, to be unsizable.
               The `cross_scene_check` ROW is mislabelled: its `why` describes "a contradiction
               list … each entry quotes both sides", and its only two call sites emit a cast
               ROSTER. The row documents a call that no longer exists, and VERDICT's
               `truncation_is_fatal=False` is wrong for a roster, where a clipped response
               silently drops people. Recorded as debt, not fixed — changing the kind changes
               the budget and needs its own measurement.

  DRIFT      — four, and the first would have shipped inside the slice written to stop it.
               1. I marked `compress` `signal_inert` on an argument that felt airtight —
                  `ceiling == floor == 512`, ceiling applied last, therefore nothing can move
                  it. The PROBE reddened immediately: the window clamp also runs after the
                  floor and pushes DOWN, so `context_length=8` resolves it to 4. A ceiling
                  bounds ONE direction. Marking it inert would have excused a call site from a
                  signal it is entitled to — the exact rot this slice pays down, re-created by
                  its own exemption mechanism, in the first row I applied it to.
               2. My first `_ssot_local_names` bound names MODULE-wide, and quietly cleared
                  three sites this slice never touched — including `self_heal._chat`, a helper
                  fed a flat `400` by one of its callers. The name matched, so a literal would
                  have been laundered into `attributed` by an assignment 400 lines away. I was
                  looking at a backlog that had dropped 29 → 26 and had to stop and ask which
                  three, rather than bank it.
               3. I nearly deleted the explicit `max_tokens=max_tokens_for("plan_forge_chat")`
                  from five repair sites as redundant restatement of a default. They are
                  load-bearing overrides: `LMStudioClient.chat` declares 8000 against the
                  row's 12000. Deleting them would have cut a plan JSON by a third, and the
                  registry says a clipped plan comes back unparseable, not short. Checking the
                  Protocol is what stopped it — and it turned up the real version of the same
                  bug: `_parse_with_repair`'s own `8000` default, which only `materialize`
                  overrode, so `analyze` and `refine_spec` had been running a third under the
                  declared row all along.
               4. I read `MISMATCH` on all seven image hash checks and had started treating it
                  as a stale build. Git Bash was rewriting `/app/...` into
                  `C:/Program Files/Git/app/...`. Host-env drift wearing a deployment bug's
                  clothes — a lesson this repo already has written down, which I applied only
                  after generating the false report.

  NEXT       — S6 (no model silently its own judge). It is surveyed and BLOCKED on an
               affordance, not on code: no surface sets a critic, `critic_model_ref` lives
               only in `work.settings` JSONB, and the FE suite is green on a configuration no
               user can produce. The spec is explicit that the UI ships in the same slice or
               the label is noise. Nothing in S7-4 changes its shape; the one carry-over is
               that `judge_plan_conflict` and `judge_canon` now size on candidate count, so a
               critic that IS configured gets a budget that tracks its workload.
```

### ✅ POST-RUN REVIEW — the author-requested audit of S1/S2, and what it found

The author stopped the run and asked for a quality review before continuing: *"nên đánh giá
chất lượng của những gì chúng ta vừa làm trước khi tiếp tục — chạy goal dài thường có chất lượng
không cao."* Reading the CODE rather than the audit blocks found three real defects, all in
work this run had already recorded as done. The instinct was right.

```
AUDIT POST-RUN REVIEW
  BUILT      — three fixes + one consolidation the fixes exposed:
               1. HIGH · `chapter_scene_gate`'s unchecked clause gets a THIRD COALESCE arm.
                  `COALESCE(guard_status, status) <> 'checked'` reads as fail-safe and is not:
                  a result with NO `canon` key makes both arms NULL, `NULL <> 'checked'` is
                  NULL, and FILTER does not count a NULL — so a scene nothing verified read as
                  verified. S1 closed the enumerated-list version of this bug and left the
                  missing-envelope version IN THE SAME QUERY, under a comment claiming
                  fail-safe.
               2. MED · `loreweave_guard` had ZERO production consumers for its core:
                  `GuardReport` and `check_over` existed only in their own tests, while
                  `guard_status` and `coverage` were hand-rolled restatements of `.status` and
                  `.covered`. `check_over` now owns its one real call site; `ReflectResult`
                  derives both from a `GuardReport`; and `verdict` (`resolved` AND
                  something-checked) is a field rather than a conjunction each caller repeats
                  — `CanonGatePanel` was restating it in TypeScript, where no Python test holds.
               3. MED · `plan_status` got a PRODUCER. `resolve_cast_liveness` has taken the
                  argument since S2 and nothing ever passed one, so the middle rung of a
                  three-rung cascade was unreachable. `OutlineRepo.plan_liveness_after` asserts
                  `alive` for any entity the plan places in a LATER scene of the chapter.
               4. `canon_envelope()` — the `result.canon` projection existed in SIX
                  hand-written copies, which is exactly why `guard_status` reached all six and
                  `verdict` reached none. Plus `test_there_is_no_FIFTH_hand_built_canon_envelope`,
                  which found two of the six the first sweep had missed.
               Also: the FE read the LEGACY scalar. S1 added `guard_status` to the envelope and
               to the gate SQL and left `CanonGatePanel` on `canon.status` — so a run whose
               name-grounding degraded drew a green all-clear.

  PROVEN     — composition full suite, on the final tree:
                 `11 failed, 3789 passed, 8 skipped in 508.36s`
               The 11 are pre-existing and were MEASURED at HEAD, not assumed: with the whole
               change stashed (`git stash push -u -- services/composition-service`),
               `tests/test_worker_jobs.py` gives `3 failed, 27 passed` — the same three. The
               other 8 are the tracked `test_motif_retrieve_db` rows.
               sdk: `996 passed, 9 skipped` · frontend composition: `1043 passed` (155 files)
               · `tsc --noEmit` exit=0
               targeted (publish-gate + plan-liveness + guard-report): `35 passed`
               the gate's OWN teeth: `13 passed` (`scripts/test_generation_guard_gate.py`,
               3 of them new — one per branch of the `via` hop, each asserting the REASON
               rather than the exit code, because the first draft of one reddened on the
               OTHER branch while claiming to test its own)
               gates: `ai-provider-gate (full): OK` · `llm-budget-ssot-gate: PASS — 92 LLM call
               site(s)` · `generation-guard-gate: PASS — 8 paths, 4 guarded, 4
               tracked-unguarded` · `enforcement-claims-gate: OK — 91 path(s)` ·
               `db-safety-gate: OK` · `[language-rule] PASS`

               MEASURED ON THE REAL CORPUS (`loreweave_composition`, SELECT only), because the
               finding was a claim about live data and not about a fixture:
                 127 scenes with a latest completed job · 23 of them with NO canon envelope
                 counted unchecked BEFORE: 93 · AFTER: 116
               The sources are current, not historical: every completed `continue` (14/14) and
               `plan_pass` (103/103) job carries no canon envelope, and so do 26 of 163
               `draft_scene` rows.

               LIVE, on a throwaway book, both images rebuilt and hash-verified against source:
                 scene 1 (a later scene exists) — 378 words, `cast_liveness =
                 {"32a33d57…": {"source": "plan", "status": "alive"}}`, `unresolved_refs=0`,
                 `checks={"canon_cast":"checked","name_grounding":"checked"}`,
                 `guard_status='checked'`, `verdict=True`
                 scene 2 CONTROL (last scene, nothing after it) — 454 words,
                 both cast ids `{"source":"none","status":"unknown"}`, `unresolved_refs=2`,
                 `guard_status='no_rules'`
                 persisted: `generation_job.result` reads `checked|true|{…"source":"plan"…}`
                 for scene 1 and `no_rules||{…"source":"none"…}` for scene 2
                 the gate on that chapter: `canon_unchecked_scenes: 1`
               Same code, same book, different position → different answer. That is the control
               that makes it a statement about the plan rung and not about the fixture.

               EVERY new check proven RED-ABLE by injection, restored by re-editing (never
               `git checkout`):
                 · drop the third COALESCE arm → the two new gate tests fail `assert 0 == 1`,
                   the control stays green
                 · cut `plan_status=` out of the `resolve_cast_liveness` call → exactly the
                   wiring test fails, `source: none` instead of `plan`
                 · rename the emitted `"guard_status"` key → generation-guard-gate FAILs on all
                   four guarded rows
                 · remove every `canon_envelope(` call from `routers/engine.py` → "the hop is
                   claimed, not taken"

  NOT PROVEN — the plan rung's REACH is measured only as an upper bound. On the real corpus,
               37 cast references across 20 scenes are ones the plan CAN now speak to; how many
               of those the KG already answered is not measured, because that needs a live
               knowledge snapshot per scene. The number is "what the layer can say", not "what
               it adds".
               `plan_liveness_after` is wired into TWO call sites (the scene worker and the
               inline router) and deliberately NOT into the chapter-level paths, which have no
               single scene position to be "after" — so chapter single-pass and stitch still
               run a KG-only cascade and nothing says so in their envelope.
               The plan layer only ever emits `alive`; a plan that has not been updated after
               an author kills someone will keep asserting it, and the KG outranking it is the
               only thing that saves that case.
               And the acceptance test is STILL NOT CLOSED: this makes the cascade's middle rung
               reachable, it does not make the guard COMPARE prose-death against plan-alive.
               `scenes_covered` remains blind, and composition's two SSE paths remain unguarded.

  DRIFT      — four, and two would have shipped:
               1. I verified the composition-SERVICE image against source, concluded the plan
                  rung was broken, and started writing it up — the job had run in the WORKER,
                  which is a SEPARATE image I had not rebuilt. The live probe's first run was a
                  measurement of stale code that I very nearly recorded as a code defect.
               2. My own FE fix reintroduced the bug it fixed: `canon.verdict ?? canon.resolved`
                  treats an explicit `null` — the server saying *nothing verified this* — as
                  "absent" and falls back to `resolved`. The operator that reads as safe.
                  Caught only because I wrote the `verdict: null` test before trusting it.
               3. My first `via`-hop check in generation-guard-gate PASSED its own injection,
                  twice: first because a substring test matched the property DEFINITION, then
                  because an `or f"{field}=" in body` escape hatch matched a DOCSTRING. A gate
                  that survives its own defect, inside the gate written to enforce that rule.
               4. I counted the hand-built envelopes by eye and wrote "FOUR" into the docstring.
                  The test I wrote in the same commit immediately found two more.

  NEXT       — unchanged: S7-4's `call_budget` JSON kinds, then S6. The acceptance test needs
               `scenes_covered` and a comparison step, neither of which this review touched.
```

### ✅ THE ACCEPTANCE TEST IS CLOSED — prose-death vs plan-alive is caught by a gate

```
AUDIT PLAN-LIVENESS (detection half)
  BUILT      — the check the run was written for. `app/engine/plan_conflict.py` (pure: normalise,
               index the cast by name+alias, intersect) + `_check_plan_liveness` in
               `canon_reflect` + `GlossaryClient.entities_by_ids` + a `plan_liveness` entry in
               `checks` + `unlinked_gone_refs` on the envelope.

               THE SHAPE, and it is the point: the model is asked ONLY to fill a slot — *who
               does this passage say died* — using `status_effects`, an extractor that already
               existed and was already prompt-taught. It is never asked whether that
               contradicts the plan. That comparison is set intersection, in code, with tests.

  PROVEN     — LIVE, two ISOLATED throwaway books, both images rebuilt + hash-verified:
                 CONTROL (no death, 439w) — `checks={canon_cast:checked, plan_liveness:checked,
                   name_grounding:checked}` · PLAN-LIVENESS VIOLATIONS: none ·
                   `unlinked_gone_refs=[]`
                 DEATH (404w) — same three checks `checked`, and
                   `[{"kind":"plan_liveness_conflict","name":"Tô Thanh Dao",
                     "entity_id":"019fbc0f-66b2…","confirmed":null}]`
               Same model, same cast, same prompt shape — the ONLY difference is whether the
               prose kills her. Before this slice both scenes returned `guard_status='checked'`
               with no violation at all.

               The POC that preceded it, on the same two books:
                 CONTROL → 2 events (travel, dialogue), `status_effects []`
                 DEATH   → 1 event  (death),             `status_effects [('Tô Thanh Dao','gone')]`

               tests: `24 passed` (15 comparison + 9 wiring) · `3352 passed` for
               `tests/unit` + `test_canon_reflect.py` · composition full suite below.
               gates: `ai-provider-gate (full): OK` · `llm-budget-ssot-gate: PASS — 92 LLM call
               site(s)` · `generation-guard-gate: PASS` · `enforcement-claims-gate: OK` ·
               `db-safety-gate: OK` · `[language-rule] PASS`

  NOT PROVEN — THE JUDGE TIER IS NOT BUILT. Every conflict is `confirmed=None`, i.e. ADVISORY,
               so it flags and does NOT block publish. The author's decision was *judge
               confirms ⇒ HARD, no judge ⇒ advisory*; only the second half exists. A feint, a
               dream, a prophecy and a body that turns out to be someone else all look
               identical to `status_effects`, which is exactly why promoting without a judge
               would be wrong — but until it exists the gate warns rather than gates.
               The extraction runs with NO `context_budget`, so it takes the SDK's default
               (4096 output, 15-paragraph chunks). Measured only on ~400-word scenes; a
               3000-word scene will CHUNK, i.e. cost more than one call, and nothing has
               measured that.
               `plan_liveness` is wired on the two SCENE paths only — the chapter-level
               single-pass and stitch still pass no plan rung and their envelope does not say so.
               And the check inherits the plan rung's own limit: chapter-scoped, so a death in
               the last scene of chapter 1 is not compared against a cast chapter 2 needs.

  DRIFT      — the fixture failed THREE times before it could measure anything, and each
               failure was mine, not the code's:
               1. cast were bare UUIDs pointing at nothing → the drafter wrote "Tô Thanh Dao"
                  as a FORTRESS ("những lớp giáp đá vĩ đại"), so "did it detect a CHARACTER
                  death" was unanswerable — and the control, generated after the death scene in
                  the same chapter, inherited the killing through `<recent>`.
               2. both scenes hand-set to `story_order 10` in different chapters → their
                  synopses landed in each OTHER's prompt and the two drafts swapped. I was one
                  step from writing this up as a cross-chapter spoiler leak in
                  `gather_structural` before measuring the stride.
               3. then the opposite error: having found the stride, I began "fixing"
                  `plan_liveness_after` to scan project-wide — which under the mixed convention
                  the data actually has would have been the bug. Its chapter scope is right.
               Plus: the first version of the wiring passed `trace_id=` and `source_language=`
               to `extract_events`, which accepts NEITHER. Every stubbed test stays green on
               that; only a live call raises. `test_the_extractor_is_called_with_kwargs_it_
               actually_accepts` now asserts against the real signature.

  NEXT       — the judge tier (advisory → HARD), then the PREVENTION half: carry liveness and
               a "must survive this scene" line into the drafter's prompt, which today contains
               nothing about who may die.
```

### ✅ PLAN-LIVENESS judge tier — advisory → HARD, and it blocks publish

```
AUDIT PLAN-LIVENESS (judge tier)
  BUILT      — `judge_plan_conflicts` + its own prompt + its own budget key
               (`judge_plan_conflict`). A DISTINCT judge is now the ONLY thing that can set
               `confirmed=True` on a `plan_liveness_conflict`, and a confirmed one flips
               `result.resolved = False` — which is what the publish gate actually reads.

               Its own prompt, not `judge_canon`'s: that judge asks "this character is already
               gone — is the passage treating them as present?"; this one asks "the passage
               appears to END this character — is that real and permanent, here, now?".
               Borrowing one prompt would ask the wrong question for whichever check borrowed it.

  PROVEN     — LIVE, a real local judge model, three passages differing ONLY in the nature of
               the death, `why` returned in Vietnamese:
                 REAL  → confirmed=True  · "mô tả trực tiếp… kiếm xuyên qua ngực, cô ngã xuống"
                 DREAM → confirmed=False · "chỉ xảy ra trong giấc mơ… cô ấy vẫn đang sống"
                 FEINT → confirmed=False · "né tránh kiếm và vẫn đứng vững, không hề chết"
               3/3, at zero cost. The unit tests script the judge, so they prove the wiring and
               prove NOTHING about the prompt — this is the half that could only be measured.

               tests `31 passed` (15 comparison + 16 wiring, 8 of them the judge tier) · suite
               `11 failed, 3821 passed, 8 skipped in 106.04s` (the same 11 pre-existing) ·
               gates: `llm-budget-ssot-gate: PASS — 93 LLM call site(s)` (92 before: the new
               judge call is budget-declared) · `ai-provider-gate (full): OK` ·
               `generation-guard-gate: PASS` · `enforcement-claims-gate: OK` ·
               `db-safety-gate: OK` · `[language-rule] PASS`
               red-able: cut `result.resolved = False` → exactly the HARD test fails; restored
               by re-editing.

  NOT PROVEN — the judge was measured on THREE hand-written passages, not on a corpus. 3/3 is
               an existence proof that the prompt works in vi, not a false-positive rate. A
               feint written more ambiguously than mine is unmeasured.
               The judge runs only when the work has a DISTINCT critic configured; with none,
               the finding stays advisory forever and nothing tells the author that the tier
               that could block is switched off. That is S6's axis and it is still open.
               No live END-TO-END run with a critic configured: the probe called
               `judge_plan_conflicts` directly. The path from `distinct` → judge_source/ref →
               HARD → publish-gate 409 is covered by unit tests, not by a stack.
               A confirmed conflict does NOT trigger a re-revise — `reflect_revise` has already
               run by then. The author gets a red row with a Revise affordance; the loop does
               not fix it for them.

  DRIFT      — my judge STUB invented the job-result shape from what the code looked like it
               wanted: `{"content": …}`. The real one is `result["messages"][0]["content"]` —
               `extract_judge_text` calls that LOAD-BEARING in its own docstring, and this
               repo already has a lesson row for it. Both judge tests failed for a reason that
               had nothing to do with the code under test.
               Then a second one: I asserted `verdict is False` on a fixture whose
               `packed_prompt` was empty, so name-grounding was NO_RULES, `guard_status` was
               not `checked`, and `verdict` was None BY THE RULE I wrote this morning. I was
               one keystroke from "fixing" the honesty rule to make my test pass.

  NEXT       — the PREVENTION half: the drafter's prompt still says nothing about who may die.
```

### ✅ PLAN-LIVENESS prevention half — the drafter is finally TOLD

```
AUDIT PLAN-LIVENESS (prevention)
  BUILT      — `gather_must_survive` + `LensBundle.must_survive` + a render in
               `build_segments`. The names the plan still needs after this scene now reach the
               prompt as a PROTECTED `canon` segment: *"These characters must still be alive
               and present at the end of this scene… Do not kill, destroy, or permanently
               remove them."*

               `canon`, not `present`, and protected on purpose. `present` DESCRIBES who is in
               the scene; this FORBIDS an outcome, and InkOS F5 says do not compress what the
               next step must OBEY — a constraint the budget may trim is one that vanishes on
               exactly the long scenes where the drafter most needs it.

               Names come from the `present` lens, not a second glossary read: pack has already
               paid for them, and an id the drafter never saw a name for is one it cannot obey
               a constraint about anyway.

  PROVEN     — LIVE on the real stack, both images rebuilt + hash-verified, WITH a control:
                 scene that HAS a later scene → `CONSTRAINT: These characters must still be
                   alive and present at the end of this scene, because the plan places them in
                   a later scene: Lạc Viên, Tô Thanh Dao. Do not kill, destroy, or permanently
                   remove them.`
                 LAST scene of the chapter → `(absent — correct: nothing comes after it)`
               Same book, same cast, different position → different prompt.

               tests `8 passed` (`test_must_survive_constraint.py`) · suite
               `11 failed, 3829 passed, 8 skipped in 110.48s` — the same 11 pre-existing ·
               gates: `ai-provider-gate (full): OK` · `llm-budget-ssot-gate: PASS — 93` ·
               `generation-guard-gate: PASS` · `enforcement-claims-gate: OK` ·
               `db-safety-gate: OK` · `[language-rule] PASS`

  NOT PROVEN — THE BEHAVIOURAL EFFECT IS UNMEASURED, and it is the thing the slice is FOR.
               I proved the constraint reaches the prompt; I did not prove it changes what the
               model writes. The obvious experiment is a trap: my death-forcing synopsis says
               "kill her" while the constraint says "don't", so a run would measure which of
               two conflicting instructions wins — not prevention. The real scenario is a
               NEUTRAL synopsis where the drafter drifts into a death on its own, and I have
               no corpus of those. Until that exists, this is a prompt change with a live
               render proof and no efficacy number.
               It also fires ONLY on the scene paths (the chapter-level ones have no single
               position), and it inherits the plan rung's chapter scope.

  DRIFT      — I asserted `seg.kind == "canon"` from memory. The field is `block`. Small, and
               the test caught it — but it is the same "wrote what I expected the shape to be
               instead of reading it" that produced the judge-stub `{"content": …}` an hour
               earlier, twice in one session.

  NEXT       — a neutral-synopsis A/B to put a number on prevention; the chapter-level paths;
               and the three defects the POC surfaced.
```

### ⚠ PREVENTION efficacy — CORRECTED. The first write-up was wrong twice.

```
AUDIT PLAN-LIVENESS (prevention efficacy) — REVISED after the author asked
                                            "is the measurement even right?"

  WHAT HELD     — the manipulation DID reach the model, and this was verified against the
                  string the drafter actually received, not the one an endpoint rebuilds:
                    `generation_job.input->>'packed_prompt'` LIKE '%must still be alive%'
                    constrained 5/5 · free 0/5
                  And the scoring was right: reading all ten drafts by hand, nobody dies. The
                  extractor and I agree.

  WHAT WAS WRONG — two things, and the second is the one that voids the experiment.

                  1. THE INFERENCE. I wrote "this drafter did not spontaneously kill a named
                     cast member". The prose says something else: it never RESOLVES THE FIGHT
                     AT ALL. Ten out of ten end at the decisive moment — "ranh giới giữa sự
                     sống và cái chết chỉ còn mỏng manh", "cú đâm quyết định" — and stop,
                     although the synopsis said the fight "đi tới hồi kết". Against the earlier
                     POC at the SAME target_words, where a synopsis naming the death produced
                     one immediately, the honest statement is: this drafter commits to an
                     outcome when TOLD the outcome, not when told there is one.

                  2. THE SAMPLE. n=1 per arm, not 5. I re-ran the SAME node five times, so the
                     exit-state write-back from each run landed in the next run's prompt:
                       run 1 → no `leaves=cast=` · runs 2-5 → `leaves=cast=[Lạc Viên, Tô Thanh
                       Dao]`, i.e. a "this scene LEAVES these two" signal, in BOTH arms.
                     It cannot manufacture a difference between arms, but the runs are not
                     independent samples and both arms were nudged toward survival.

  ALSO WORTH SAYING — the packs were 226–602 characters. The fixture books have no bios, no
                  canon rules, no prior prose, so `<present>` is two bare names and the
                  constraint is ~40% of the constrained arm's entire prompt. Whatever this
                  measured, it was not the product's real prompt conditions.

  STILL NOT PROVEN — prevention's efficacy. Unchanged, and now for better-understood reasons.
                  A valid experiment needs: a FRESH node per run (or exit_state cleared between
                  them), a synopsis whose conclusion this drafter will actually write, and a
                  pack resembling a real book's.

  DRIFT         — I reported a flat 0-vs-0 as "no power because the synopsis wasn't lethal
                  enough" and moved on. I had a lesson row for exactly this shape — *verify the
                  varied input reached the model before trusting a flat measurement* — and I
                  applied only half of it: I checked the constraint reached the prompt and
                  never checked whether the SAMPLES were independent or read what the prose
                  actually did. The author asking "is the measurement right?" is what produced
                  both findings, not my own re-reading.

  NEXT          — the three POC defects. This experiment gets redesigned before it is rerun,
                  and until then prevention ships as reasoned, unmeasured insurance.
```

### ✅ CHAPTER paths — the gap is DECLARED instead of looking like a pass

```
AUDIT PLAN-LIVENESS (chapter paths)
  BUILT      — `plan_supported: bool` on `run_canon_reflect`, passed False by the four
               chapter-level call sites (worker single-pass + stitch, router single-pass +
               stitch). They report `plan_liveness = NO_POSITION` instead of NOT_APPLICABLE.

               The two are DIFFERENT and were indistinguishable on the envelope: a scene with
               nothing after it has genuinely nothing to check (NOT_APPLICABLE, no amber), while
               a chapter path covers many scenes at once, has no single position to be "after",
               and simply DID NOT RUN the check (a GAP). Collapsing them is the exact
               conflation the per-check vocabulary was added to end.

  PROVEN     — tests `42 passed` across the three plan-liveness files (3 new: the chapter
               status, the scene CONTROL that must stay NOT_APPLICABLE, and a mechanical
               no-omission guard) · suite `11 failed, 3832 passed, 8 skipped in 112.29s`, the
               same 11 pre-existing · gates: `ai-provider-gate (full): OK` ·
               `llm-budget-ssot-gate: PASS — 93` · `generation-guard-gate: PASS` ·
               `enforcement-claims-gate: OK` · `db-safety-gate: OK` · `[language-rule] PASS`
               red-able: deleting one `plan_supported=False` fails the guard.

  NOT PROVEN — the chapter paths still do not CHECK anything; they now say so. Whether a
               chapter-level rung is even definable is unanswered: `story_order` has two
               conventions live in one project (stride vs 1..N), so "the cast a LATER chapter
               needs" cannot be computed reliably today. That is finding (A)'s root, and this
               slice does not touch it.

  DRIFT      — the no-omission guard PASSED ITS OWN INJECTION. Written as a regex over call
               bodies, it caught 2 of 3 calls in `routers/engine.py` and one match ran to
               19,993 characters, having swallowed the next call whole — so the flag I deleted
               from one site was still found inside another's blob. Rewritten with `ast`, it
               reds. That is the THIRD gate this session to survive its own defect on the first
               attempt (generation-guard-gate's via-hop did it twice). The pattern is mine, not
               the tooling's: I reach for a regex where the structure is a parse tree.

  NEXT       — the three defects the POC surfaced, (A) first: `gather_structural` injects 809
               foreign-chapter synopses across 41/41 scenes of the dogfood book.
```

### ✅ A/B v2 — the detector is 11/11 on real drafts, and PREVENTION DOES NOT WORK

```
AUDIT PLAN-LIVENESS (efficacy, v2)

  DESIGN     — v1 leaked through four channels; v2 closes each and VERIFIES the closure per
               run against `generation_job.input.packed_prompt`, the string the drafter really
               received:
                 · ONE BOOK per run (chapters share `gather_recent`; projects share
                   `gather_structural`'s planned lens — a book is the only boundary nothing
                   crosses). 12 books.
                 · each scene generated EXACTLY ONCE → `leaves=cast=` absent in 12/12, so no
                   run inherited another's exit state. v1 had it in 8 of 10.
                 · a synopsis this drafter will CONCLUDE — v1's produced ten unresolved fights.
                 · bios on both characters, so the constraint is not 40% of the prompt.
               `INVALID RUNS: 0` — constraint present iff the arm intended it, 6/6 and 0/6.

  MEASURED   — deaths, scored by the same `status_effects` extractor the detector uses:
                 constrained 6/6   who = [Lạc Viên]
                 free        6/6   who = [Lạc Viên, Tô Thanh Dao]   (both died in 2 of 6)

               PREVENTION FAILED. The constraint NAMES BOTH characters and Lạc Viên died 6/6
               anyway. The only hint of an effect is that Tô Thanh Dao died 0/6 constrained vs
               2/6 free — two events, n=6. That is a hint, not a result.

               DETECTION IS 11/11 on real, unforced drafts:
                 6/6 true positives  — v2 constrained: a needed character died, the violation
                                       fired, `plan_liveness = checked`, every time
                 5/5 true negatives  — v1 constrained: plan rung ACTIVE, extractor found no
                                       death, ZERO violations raised
                 0 false positives · 0 false negatives observed

  WHAT I GOT WRONG AGAIN — and it is the same mistake in a new place. I fixed v1's
               no-resolution problem by making the synopsis COMMAND a terminal outcome ("one of
               the two falls and does not rise"), which RECREATED the conflicting-instructions
               trap I had written v1 specifically to avoid. So v2 does not cleanly isolate
               prevention either: it measures what happens when the author's synopsis demands a
               death and the plan forbids it. The synopsis wins, 6/6.

               That is still worth knowing — arguably more than the clean number would have
               been — but it is not the experiment I set out to run, and calling it one would
               be the third framing error in this thread.

  WHAT IT MEANS FOR THE ARCHITECTURE — prevention is advice a model may ignore, and here it
               ignored it completely. DETECTION is the gate that actually holds. The two halves
               are not redundant and the ordering of trust between them should be: detect,
               then judge, then block; prevention is cheap insurance with no demonstrated
               effect under conflict.

  STILL NOT PROVEN — prevention under NO conflict, i.e. a synopsis that neither forbids nor
               demands a death, on a drafter that still resolves the scene. v1 and v2 bracket
               that case without landing on it. It needs a synopsis whose ending is terminal
               but not fatal-by-instruction.

  NEXT       — the three POC defects, (A) first.
```

### ✅ A MUTE JUDGE NO LONGER READS AS A JUDGE THAT DECLINED

```
AUDIT PLAN-LIVENESS (judge truncation)
  BUILT      — `judge_plan_conflicts` returns `(candidates, judged)`. The flag is necessary
               because the candidates CANNOT carry the fact: an unjudged candidate and a
               judge-declined one are both `confirmed=None`. `_check_plan_liveness` maps
               `judged=False` to `CheckStatus.UNPARSEABLE` — the enum member written for exactly
               this ("the judge answered and the answer could not be used").

  PROVEN     — MEASURED on real 500-word drafts through PRODUCTION code
               (`judge_plan_conflicts`), not a hand-rolled probe:
                 `job.status = completed` · `finish_reason = length`
                 `raw len = 5684` · `parsed verdicts = {}`
               The judge model reasoned aloud in Vietnamese past the output cap and never
               emitted the JSON. Every candidate stayed `confirmed=None`, which is
               byte-identical to a judge that looked and declined — so the BLOCKING TIER HAD
               SILENTLY STOPPED EXISTING and the envelope said nothing.

               The earlier 3/3 live judge validation used THREE-SENTENCE excerpts. It passed
               for that reason. Fixture length was the difference between a validated tier and
               a dead one.

               tests `22 passed` in the wiring file (3 new: the truncated judge, the CONTROL
               that must stay `checked`, and a signature check) · suite
               `11 failed, 3835 passed, 8 skipped in 108.21s`, the same 11 pre-existing ·
               all six gates PASS · red-able: dropping the `judge_unusable` branch fails
               exactly the truncation test, with the diagnostic log line visible.

  NOT PROVEN — WHY the model overruns. `build_judge_request` already sends the strong disable
               (`reasoning_effort:"none"` + `chat_template_kwargs:{thinking:False,
               enable_thinking:False}`), so "the flag does not work for this model" was MY
               guess and I did not verify it. It could equally be the 1536-token budget being
               too small for a Vietnamese verdict, or this judge model simply being verbose in
               visible output. This slice makes the failure VISIBLE; it does not diagnose it,
               and the fix for the cause is a separate measurement.
               Nothing yet surfaces the UNPARSEABLE status to the AUTHOR — it rides the
               envelope and the FE does not render it.

  DRIFT      — I asserted a cause ("the thinking-disable flags are not effective for this
               model") from one observation, and the author corrected me: the POC had diverged
               from the platform's own call path, so a POC-shaped conclusion was being applied
               to production. Checking `build_judge_request` showed it sends the STRONGER
               disable, not a weaker hand-rolled one — the opposite of what I had claimed. The
               observation (truncation kills the tier silently) survived; the explanation did
               not, and I had already written the explanation down as if it had.

  NEXT       — per the author: stop POCing, the finding is wired. Then the three POC defects.
```

### ✅ THE BUDGET SEAM WAS NEVER WIRED — 28 of 30 call sites passed nothing

```
AUDIT LLM-BUDGET (adaptive signal)
  BUILT      — three things, in the order that keeps them honest:
               1. VERDICT gets a REAL sizing model. It was `base = 0.0` with the comment
                  "bounded by construction, the floor IS the model", which made `target` and
                  `language` provably inert for the kind — so no judge call could ever carry
                  signal. Now `target` verdicts x (30 reason-words x the language's tokens/word
                  + 24 envelope). Measured: 25 verdicts → en 2812 / vi 3825, against a flat
                  1536 before.
               2. Both judges pass `target=len(candidates), language=source_language`.
               3. `llm-budget-ssot-gate` gains a SECOND axis, ratcheted at 28: a budget call
                  that passes no `target`/`language`/`reasoning`/`context_length`.

  PROVEN     — the author asked "is there a hard gate against this rot yet?" and the answer,
               measured, was no: the existing gate checks ATTRIBUTION, so a call resolving
               through `call_budget` counts as correct while returning the same number every
               time. `llm-budget-ssot-gate` PASSes with 93 sites — and 28 of 30 budget calls
               passed no signal at all.

               THE SEAM DID NOT ROT. It shipped unwired, hours after being built, and the two
               sites that DO carry signal are the two judges I fixed this hour. That is not
               drift over time; the gate simply could not see the axis it was written for.

               registry no-downgrade test `31 passed` · sdk `996 passed, 9 skipped` ·
               composition `11 failed, 3835 passed, 8 skipped in 110.87s` (the same 11
               pre-existing) · gate teeth `13 passed` · all six gates OK ·
               `adaptive signal: 2/30 budget calls pass one (28 held at baseline)`
               red-able: reverting one judge to `max_tokens_for("judge_plan_conflict")` makes
               the gate FAIL and name the site; restored by re-editing.

  NOT PROVEN — THIS DOES NOT FIX THE TRUNCATION THAT FOUND IT. My case was ONE candidate, and
               the floor (1536) still dominates below ~15 verdicts, so the number my judge got
               is unchanged. What it fixes is multi-candidate under-budgeting, which is a real
               bug nobody had hit yet. The observed overrun is a verbose judge model, and the
               UNPARSEABLE status is what makes it visible — a budget cannot fix a model that
               ignores "do not think aloud".
               `_VERDICT_REASON_WORDS = 30` is REASONED from the prompt's own "why" field, not
               measured against real verdicts.
               The ratchet freezes 28 sites; nothing schedules paying them down.

  DRIFT      — I answered the author's rot question with "the mechanism exists and my call
               ignores it", which put the fault on my call site. Counting first showed 28 of 30
               did the same, and that VERDICT could not have carried signal if I had passed it.
               I had reached for the explanation that made it a local mistake before measuring
               whether it was a systemic one.

  NEXT       — the three POC defects (A/B/C), and surfacing UNPARSEABLE to the author.
```

### ✅ THE AUTHOR CAN NOW SEE WHY THE GUARD IS AMBER

```
AUDIT PLAN-LIVENESS (surfacing)
  BUILT      — `CanonGatePanel`'s unchecked reason derives from `guard_status`, with a case per
               status and a fallback that NAMES the status; plus a `(which_check)` suffix from
               `canon.checks`.

  PROVEN     — two defects, both measured by reading the component rather than the envelope:
               1. the reason chain keyed on `canon.status` — the SAME legacy scalar `checked`
                  was moved off this morning. So every status added since (`no_rules`,
                  `no_subject`, `unverified_input`, `unparseable`) fell through.
               2. what they fell through TO asserts *"the canon service was unavailable"* for
                  anything unrecognised. A truncated judge is not an outage. The panel was
                  telling the author to go look at a healthy service — a cause it cannot know,
                  which is the same class as the explanation the author corrected me on an hour
                  earlier, this time shipped in the UI.

               `19 passed` in the panel file (6 new) · `1049 passed` across composition FE ·
               `tsc --noEmit` exit=0
               red-able: reverting `reasonKey` to the legacy scalar fails exactly the
               truncated-judge test; restored by re-editing.

  NOT PROVEN — no browser smoke. The tests use the i18n mock, so they assert the KEY is chosen,
               not that the rendered Vietnamese sentence reads well — and `canonUncheckedOther`
               interpolates a raw enum member (`unparseable`) into author-facing copy, which is
               developer vocabulary leaking into the UI.
               The `(plan_liveness)` suffix names the check with its INTERNAL key for the same
               reason. Both are honest and neither is finished copy.
               No translations added — only `defaultValue`s, so a vi reader sees English until
               the locale files catch up.

  DRIFT      — I shipped `guard_status` to the SQL gate and the `checked` flag this morning and
               left the reason chain on the old field, in the same component, in the same edit.
               Then I recorded "the FE renders nothing for UNPARSEABLE" as the gap — which was
               wrong in the more embarrassing direction: it rendered something, and what it
               rendered was a fabricated cause.

  NEXT       — the three POC defects (A/B/C).
```

### ✅ (A) THE PLANNED LENS WAS LEAKING FUTURE CHAPTERS INTO EVERY SCENE

```
AUDIT POC-DEFECT A (cross-chapter synopsis leak)
  BUILT      — `gather_structural`'s planned-synopsis lens is scoped to the scene's OWN chapter.
               One `if`, and the reason it was not there is the interesting part.

  PROVEN     — MEASURED on the dogfood project, which holds TWO `story_order` conventions AT
               ONCE: five chapters numbered 1,2,3,4 and the rest chapter*1000+i (2000-2002,
               3000-3001, 4000-4002). The lens filtered on `n.story_order <= my_order` over
               `list_tree(project_id)` — the WHOLE project — so it was comparing numbers from
               incompatible schemes.
                 one scene at story_order 10002 pulled in 40 synopses from 14 chapters
                 chapter-scoped, the honest answer is 2
                 across all 41 scenes: 850 injections BEFORE, 41 AFTER (-95%)

               THIS IS A SPOILER LEAK, not prompt bloat. Any chapter on the small convention
               sorts below every 4-digit order, so a scene early in the book was shown the
               unwritten synopses of chapters ten ahead of it. The lens whose job is "what is
               planned BEFORE me" was reliably showing what comes after.

               tests `5 passed` (new file) · suite `11 failed, 3840 passed, 8 skipped in
               108.65s` — the same 11 pre-existing · all six gates OK
               red-able: removing the chapter bound fails exactly the two-convention test.

  NOT PROVEN — the CROSS-chapter signal is now gone entirely, not fixed. "What is planned
               earlier in the BOOK" needs the chapter's own sort_order, which this lens does
               not have; the narrow answer is correct while the numbering is unreliable, but it
               IS a narrowing and no test asserts the wider behaviour we gave up.
               Nothing repairs the two conventions themselves — the project still holds both,
               and every other consumer comparing `story_order` across chapters has the same
               bug. I did not audit who else does.
               No live regeneration to show the prose improved; the 95% is a count of what
               reaches the prompt, not a quality measurement.

  DRIFT      — my POC note recorded "809 foreign synopses". The real number is 850, and I had
               written the smaller one down from a query I did not re-run before quoting it.
               Small, and exactly the kind of number that gets repeated into a report.

  NEXT       — (B) POST /entities dropping documented fields, then (C).
```

### ✅ (B) POST /entities NOW HONOURS THE FIELDS ITS CONTRACT DOCUMENTS

```
AUDIT POC-DEFECT B (create drops documented fields)
  BUILT      — `createEntity` accepts `display_name`, `status` and `tags`. The request struct
               carried NONE of them, so `json.Decode` discarded all three in silence and the
               route answered 201. `display_name` seeds the NAME ATTRIBUTE VALUE (the name is
               not a column), `status` is enum-validated on write (422, not a CHECK-constraint
               500), `tags` persists.
               Plus a fix to the PP-4 seed helper — see DRIFT.

  PROVEN     — 3 new tests, all asserting the READ-BACK and never the status code: 201 proved
               nothing here for as long as the bug existed.
                 `--- PASS: TestCreateEntity_HonoursTheFieldsItsContractDocuments`
                 `--- PASS: TestCreateEntity_DefaultsAreUnchangedWhenTheFieldsAreOmitted`
                 `--- PASS: TestCreateEntity_RejectsAStatusOutsideTheClosedSet`
               plus the pre-existing `TestCreateEntity_ValidatesBookTierKind` and
               `TestCreateEntity_MultiGenreKeepBothValues` — five RUN, none skipped.
               `TestOpenAPIRouteConformance` ok (contract-first holds).
               red-able: disabling ONLY the seed (keeping the struct field so it compiles)
               fails on `cached_name: want "Tô Thanh Dao", got ""`.

               FULL PACKAGE, three runs, because the first one lied:
                 with my change, run 1 : 2 failed  (TestEnrichments_RefusesAColleagueEntity_PP4,
                                                    TestWikiGenDelegate_ExcludesColleague_PP4)
                 at HEAD, stashed      : 0 failed, ok 651.606s
                 with my change, run 2 : 0 failed, ok 679.913s
               So the two PP-4 failures are FLAKY, not mine.

  NOT PROVEN — the flake's trigger. The mechanism is identified (see DRIFT) but I did not
               reproduce it deliberately, so "poisoned `book_kinds` row" is the best
               explanation and not a demonstrated one. The new guard turns it into a clear
               message when it next fires; it does not stop it firing.
               No live smoke: the fields are proven through the handler against a real DB, not
               through the gateway from the UI.

  DRIFT      — I had already written "the two PP-4 failures ARE caused by my change" and was
               about to hunt the cause. HEAD was green once; my branch failed once; that is
               n=1 on each side, and I have been burned by exactly that three times today.
               Re-running settled it in the opposite direction.
               The flake deserves its own note because of HOW it fails: `seedEntityOfKind`
               reuses an existing `book_kinds` row without checking its `is_person`, and the
               shared database keeps that row forever (cleanup deletes the entity, not the
               kind). When they disagree the enrichment guard correctly returns 200 and the
               assertion reports **"PP-4 BREACH"** — a privacy hole in production. A test that
               misattributes its own state to a product defect costs more than the bug it was
               written for, so the helper now fails with "FIXTURE STATE, NOT A PRODUCT DEFECT".

  NEXT       — (C) is a product decision, deferred as 157. The parked test-suite work.
```

### ✅ THE CANON GUARD WAS CHECKING AGAINST A GRAPH NOTHING EVER FILLED

```
AUDIT FLYWHEEL (canon path)
  BUILT      — `plan_canon_dispatch` + the approve route's canon branch. An approved chapter of
               a NON-derivative Work now extracts into its OWN knowledge project.

               A SEPARATE decision, not a loosening of `plan_flywheel_dispatch`, whose
               invariants are LOCKED and exist to stop a DERIVATIVE writing into its SOURCE's
               graph. A canon book writing into its own project is not that leak. The C23
               null-scope guard is kept for the new path (`unscoped_project` refuses).

  PROVEN     — the finding first, because it reorders the whole backlog. MEASURED 2026-08-01:
                 `extract-item` has exactly ONE caller in the repo — the derivative branch of
                 `approve_chapter`, behind `if not decision.dispatch: return dispatched=false`
                 · `:EntityStatus` across the live graph: 17 gone + 3 active, on 4 projects
                 · on the DOGFOOD book: 15 chapters, 4 published, a knowledge project that
                   exists and SHARES the composition project's id — and **0** EntityStatus
               So for a book written from scratch the knowledge graph is permanently empty, and
               the canon guard, the LLM judge and the publish gate all check every scene
               against nothing. The plan rung built earlier today is a COMPENSATION for that.

               `plan_flywheel_dispatch`'s docstring says a greenfield Work "uses the
               event-driven path". There is no event-driven path. I grepped every caller.

               tests `21 passed` (approve-router + delta-flywheel), 2 new · suite
               `11 failed, 3841 passed, 8 skipped in 120.65s` — the same 11 pre-existing ·
               all six gates OK
               red-able: disabling the canon branch fails exactly the 2 new tests (and the
               pre-branch one, which shares the branch).

  NOT PROVEN — NO LIVE RUN. Nothing has been extracted end-to-end through this path yet: it
               dispatches a real LLM extraction, and doing that on the dogfood book would
               mutate the author's real graph and spend real tokens. It needs a throwaway book
               with one approved chapter, and that is the next step, not a done one.
               APPROVAL is the trigger. Whether that is the right threshold (vs publish, vs an
               explicit author action) is the author's call and was decided as "approve" today
               — but a low-quality approved chapter now becomes canon, and nothing walks that
               back.
               The 15 already-written dogfood chapters stay unextracted; this fires on the NEXT
               approval only. A backfill is a separate decision.
               Cost is unmeasured: one full Pass-2 extraction per approved chapter.

  DRIFT      — `test_approve_canon_work_is_clean_no_op` was GREEN and was PINNING THE DEFECT.
               It asserted `extract_calls == []` with the comment "canon partition untouched" —
               true, and the bug. I have spent a day hunting guards that report clean without
               checking; this was a test doing it, and it read as a deliberate invariant
               because it was written like one.

  NEXT       — a live end-to-end on a throwaway book. Then 155/156 (mechanical) while suites run.
```

### Standing quality bars — a slice is NOT done if any of these is skipped

- **A new check ships with its CONTROL run and pasted.** A detector that answers the same on a
  seeded defect and on its control cannot fail; this session shipped one and caught it only by
  running the control.
- **A guard reports its COVERAGE.** "Nothing found" and "nothing was checked" must be
  distinguishable in the output, not inferrable from a status string.
- **No measurement is trusted at n=1** when it decides a design. Three probes this session
  reversed on the second run.
- **Verify the input reached the system** before concluding anything from an output.
- **A verifier must not share its source of truth with the thing it verifies.**

## SSOT slices — after Phase 0 seals

`S10 → S1 → S2 → S8 → S12` · `S7 → S6(+UI) → S11 → S3 → S4` · `[translation+knowledge adopt] → S9 → S5`
See spec §4/§6 for each slice's **corrected** shape — v1's versions of S1/S2/S6/S7/S8/S9/S10/S11 were
all wrong in ways the red team named.

## Decisions (sealed — re-read, do not re-derive)

| date | decision |
|---|---|
| 2026-07-31 | Full scope, spec first, repo-wide — **not** composition-only. |
| 2026-07-31 | **Merge the two context-budget systems (S11)**, chosen over "keep separate, borrow the trace". |
| 2026-07-31 | S6 ships label-then-tighten; a hard refusal on day one would fail every default-configured job. |
| 2026-07-31 | Audit F2 (`chapter_index`) and F3 (control-plane i18n) stay OUT — adjacent tracks. |
| 2026-07-31 | Order puts S11 **before** S4: migrating the plan half twice is the avoidable cost. |
| 2026-08-02 | **KG/extraction identity is PARKED, not next.** Budget-seam rot → finish S7 → the rest of the board in sealed order. The entity-identity spec is a diagnosis to return to, not a work item to start. Author, verbatim: *"tôi không khuyến khích lao đầu vào KG ngay bây giờ."* |
| 2026-08-02 | **The budget-seam rot and S7 slice 4 are the SAME work**, approached from two ends. Do not track them as two items. |
| 2026-08-02 | **A budget kwarg counts as signal only if its KIND reads it.** `language` on a STRUCTURED or EDIT row is discarded by `call_budget`, so a gate that greps kwargs can be turned green without changing a single budget. Enforced by the gate; the per-kind read-set lives in `_KIND_READS`. |
| 2026-08-02 | **A row where nothing can size the call DECLARES it (`signal_inert`) instead of accumulating fake signal at its call sites.** The declaration is probed against the mechanism in each service's registry test, two-directionally, so it cannot drift into a comment. Same move as `OutputKind.MIRROR`: make silence and intent distinguishable. |

## Measured facts (do not re-measure; cite these)

> ⚠️ The v1 figures that used to sit here were the ones the red team falsified. They are struck
> rather than deleted, because "the number I first believed" is the artefact worth keeping.

| measure | ~~v1~~ | **verified** |
|---|---|---|
| services with LLM generate/grade paths | ~~4~~ | **13** + 6 shared SDKs + Go + Rust |
| `build_*_messages` in composition | ~~~30~~ | **23–25**; **~41** counting `*_prompt` builders |
| LLM callers bypassing the packer | ~~24, "all planning"~~ | **18**, and ≥10 are prose-side or neither |
| flat `max_tokens` in composition | ~~~21~~ | **~40 / 19 values**, ~31 of them **default params**, not call-site literals |
| self-grading call sites | ~~5 / 2 services~~ | **17+ / 8 services** |
| finding/verdict types | ~~6, no shared base~~ | **≥9**; `CanonViolation` already extends a shared base |
| token/count conventions | ~~2~~ | **4** (+2 billing, which must stay separate) |
| never-run DB-gated tests | ~~41~~ | **209** — ROT-0 cleared 41, ROT-1 the other 159, the gate found 9 more |

**Token measurements (real Vietnamese prose from the dogfood book).** At a 6000-token pack budget,
characters of grounding that survive: English **29,756** · Vietnamese under cl100k **11,777** (40%)
· Vietnamese under o200k **17,636** (59%). cl100k over-counts Vietnamese by **1.50×**. The remaining
gap is real — Vietnamese tokenizes denser — and is a product question, not a bug.

**Baseline prose:** Mị Đế ch.1, 5 scenes, 3,124 words, one known defect invisible to the stack.

**~~Clean, verified~~ — BOTH claims were falsified:**
- ~~all 11 composition judges de-bias to `source_language`~~ → `plan_heal` takes the parameter and
  never reads it; `motif_mine` has none; `arc_conformance`/`tension_conformance` call no LLM at all.
- ~~the provider path is genuinely single~~ → two POC files called Ollama directly over httpx
  (deleted), and the gate that was supposed to catch them enforced half its own rule.

## Parked

| date | item | why parked, and what un-parks it |
|---|---|---|
| 2026-08-02 | **The whole KG/extraction identity thread** — [`docs/specs/2026-08-01-entity-identity-under-qualitative-extraction.md`](../specs/2026-08-01-entity-identity-under-qualitative-extraction.md) | **Author's call**, explicit: do not dive into KG now. The diagnosis stands (all 21 `:EntityStatus` rows in the graph are unreachable by the guard's FK lookup; identity is `hash(name, kind)` over LLM output), and its own §5 says step **C — measure the fork** must come before anything else. Un-parked when the board reaches a natural stop, or when the author calls it. **Consequence to state plainly: the dead-character feature does NOT work end-to-end while this is parked.** The store fills; nothing reads it. |
| 2026-08-02 | **`:EntityStatus` / dead-cast guard, end-to-end** | **Author, 2026-08-02: the root is that there has never been a real ENTITY LIFECYCLE** — *"ngay từ đầu chúng ta đã sai vì không có lifecycle thực sự cho entity"*. So this is not "correct code blocked by a parked join": `alive`/gone was built on a model that was never designed, and the FK unreachability documented in the entity-identity spec is a symptom, not the disease. **Do not attempt to fix it by repairing the join.** It belongs to a larger refactor that **already has its own document**; the author will name the starting point when it begins. Nothing to look up or design in the meantime. |
| 2026-08-02 | **Backfill of the 15 already-written dogfood chapters** | The canon flywheel catches from the next approval forward. Backfilling is a separate decision (irreversible-into-canon, unmeasured per-chapter cost) and is not blocking the board. |
| 2026-08-01 | **Test-suite restoration execution** — [`docs/plans/2026-08-01-test-suite-restoration.md`](2026-08-01-test-suite-restoration.md) | Plan written and every number in it measured; execution is a separate run. knowledge's 561 skips are a *local-dev* gap, not a CI coverage hole (CI arms every gated suite), which is why it does not block. |

## Debt taken on

| date | debt | the honest cost |
|---|---|---|
| 2026-08-01 | The **prevention** half of plan-liveness ships with its efficacy **disproven**, not merely unmeasured. A/B v2 showed the detector at 11/11 and prevention not holding. | The drafter is told who the plan still needs, and it does not reliably obey. The *detector* is what is load-bearing today. Do not describe prevention as working. |
| 2026-08-01 | The dogfood book carries **16 scenes on a second `story_order` convention** (book slots 11-15, numbered 1,2,3 — so on the global axis they sort *before chapter 1*). Written by this session's own eval/POC runs via the authored `create_node` path. | Position-gated lenses under-serve those 5 chapters. `resync_reading_order` is the right repair but is parent-keyed and those scenes are parentless, and its only caller is the chapter-reorder route. 16 rows. |
| 2026-08-01 | The authored `create_node` path takes a caller-supplied `story_order` and never derives it from the chapter's slot. | This is the *writer* that produced the debt above; not fixing it means the drift recurs. |
| 2026-08-01 | Smoke debris: throwaway book `019fbd8f-008c-7cef-bf81-1d53a808361d` and its knowledge project `019fbd90-…` | Deliberately a throwaway (never the dogfood book), but it is real rows in the dev stack awaiting purge. |
| 2026-08-02 | The `cross_scene_check` registry row is MISLABELLED. Its `why` describes "a contradiction list across one scene seam"; its only two call sites (`compress._cast_state`, `cross_scene_check._extract_one`) emit a cast ROSTER. | The row documents a call that does not exist, and the kind is wrong in a way that matters: VERDICT carries `truncation_is_fatal=False`, but a clipped roster silently DROPS PEOPLE — the same class as the `propose_world` dead pass. Not fixed here because changing the kind changes the budget (VERDICT 2048 → STRUCTURED 4096) and needs its own measurement. |
| 2026-08-02 | `_TOKENS_PER_ITEM = 220` (SDK, generic) is what makes a full-roster `propose_world` reach the 32768 runaway ceiling. A world entity is plausibly half that. | Every STRUCTURED budget is sized off a per-item cost nobody has measured against a real completion. The right number is `output_tokens / items` from a live run; until then the big-roster budgets are over-generous rather than wrong. |
| 2026-08-02 | **translation-service folds IMPORTED third-party book text into prompts with no sanitizer** — 7 modules, surfaced by widening `injection-coverage-lint`'s SCAN_DIRS in S4. Plus 1 in worker-ai. | The least-trusted bytes on the platform, in the service that exists to process them, never scanned until now. Baselined with notes rather than fixed: routing them through `neutralize_injection` risks a TRANSLATION-FIDELITY bug (a sanitizer that mangles source text), which is the same reason those rows are `OutputKind.MIRROR`. Needs its own measurement, not a sweep. |
| 2026-08-02 | **The `chat.*` / `composition.*` trace namespacing is NOT built** — composition emits nothing into the context trace (the only `TraceAccumulator` consumers are chat-service's `stream_service`, `compact_service`, `token_budget`). | Namespacing a vocabulary with no second surface to separate would be zero-consumer ceremony. **Un-parks when composition first emits a trace span** — at that moment `breakdown_categories` becomes a shared vocabulary asserted BOTH ways on the chat side, so extending it is a consumer-visible shape change and must be namespaced in the same commit. |
| 2026-08-02 | **S11-2 moved COST and nobody measured it.** Counting ~40% more tokens on CJK/Vietnamese means ~40% more chunks per chapter, i.e. ~40% more LLM calls — for exactly the books this platform is for. | The safe direction for correctness (no window overflow) and the expensive one for spend. Shipped without a number. A real per-chapter cost delta needs one translation run before/after on a real chapter. |
| 2026-08-02 | **The kernel estimator is itself ~0.78× tiktoken on Vietnamese** (my n=3 sample), where the spec cites a 2026-07-07 eval claiming the script-aware heuristic tracks o200k within 3-6%. | Under-counting is the direction that overflows a window. My sample is far too small to overturn a real-corpus measurement, so the tension is recorded rather than acted on — re-tuning the kernel's `_F_VIETNAMESE` on n=3 would be the "generalised from one prompt formulation" mistake this run already has twice. Needs the eval corpus re-run. |
| 2026-08-02 | **The distinct-critic rule compares `user_model_id`, not the RESOLVED provider model.** Two BYOK rows can point at the same underlying model. | A user with two gemma credentials picks one as drafter and one as critic, gets `CONFIGURED`, and a model grades its own prose — the exact failure S6 is named for, one level below where the check now looks. Closing it needs a provider-registry route exposing the underlying model for a `user_model_id` (only `/context-window` exists) plus a caching decision on a per-generation hot path. Gate #2 — cross-service contract. |
| 2026-08-02 | `settings.model_roles` still has ZERO writers. S6 writes the legacy `critic_model_ref`/`_source` scalars, which the dual-read consumes. | The newer map remains a read-only contract with no producer, so the Book tier of the Chat & AI cascade still resolves a key nothing writes. Not blocking — the dual-read means the critic setting works — but the map is dead weight until something writes it or it is retired. |
| 2026-08-02 | The output-budget window clamp is unexercised in production. | The dev model reports a 200k window, so the half-share never binds. It is proven only by unit test. The case that matters — a small-window BYOK model getting a 24750-token cap — has never been run. |

## Drift log — near-misses, wrong turns, bars I nearly lowered

> A run that ends with an empty drift log is not clean; it is dishonest. Append as they happen.

| date | what nearly shipped, or did |
|---|---|
| 2026-07-31 | **Built a database column on a broken measurement.** Read "output uncorrelated with the ask" three times, each reading more confident, and shipped `draft_beats` + a migration + a design rationale on the third. `select_draft` simply had no `target_words` parameter — the ask was never sent. A flat curve across a wide input range means the input never arrived, far more often than it means a ceiling. |
| 2026-07-31 | **Explained the inversion with a story instead of reading the output.** Wrote that a 4000-word ask "pushes the model toward summarising the span". The drafts open with an explicit refusal; the word counts partly count it. Committed the wrong explanation, corrected it an hour later by reading the prose. |
| 2026-08-01 | **Called an invented name "wrong" using an inference I had just deleted for being unreliable.** Judged "Mira" a corruption of "Mina" by 1-edit distance, minutes after removing that exact claim from the code because `Weaver's Lane`→`Vane` proved it false. Without ground truth you can check self-contradiction, not correctness. |
| 2026-08-01 | **Shipped a check that could not fail, and nearly reported its silence as a clean result.** `cross_scene_check` v1 returned 0 on the seeded defect AND on its control. Caught only because I ran the control. Fifth instance of the self-witness shape this session — the first four I found in other people's code. |
| 2026-08-01 | **Built a verifier on the generator's own input.** `name_grounding` compared drafts against the packed prompt and reported as though it had verified. The author asked "if there is no glossary entity, on what basis do you say the model generated wrongly?" and the answer was: none. Now it names its `truth_source`. |
| 2026-08-01 | **Generalised from one prompt formulation, twice.** Concluded coreference linking was impossible from a stripped-list probe; a passage-based probe then worked. Nearly built on THAT — the controls showed it was not reproducible, and that the model resolves coreference by gender agreement, so the defect and the linking signal are the same thing. |
| 2026-08-01 | **Ran an attribution test that could not answer its own question.** The probe chapter's `<memory>` carried the earlier run's chapters, where the answer was already written. Re-ran on a fresh book with a different world before claiming anything. |
| 2026-08-01 | **Shipped a "gate" that stayed GREEN with its own defect injected — again.** The protected-segment test squeezed the budget until the prose dropped and asserted `carries=` survived. With `protected=False` injected it still passed, because the line is 25 characters and the budget drops largest-first then stops. It was testing SIZE, not protection. Second time this session a check could not fail; the first was `cross_scene_check` v1. |
| 2026-08-01 | **Accepted a green STATUS over garbage DATA.** The first live run returned `{'status': 'recorded', 'cast_size': 10}` and I read it as the feature working. The ten rows were Vietnamese pronouns and common nouns — *Anh ta*, *ngươi*, *Ánh mắt họ* ("their gaze"). All ten would have been injected into the next scene's prompt as facts about the cast. `_NOT_A_NAME` is an English word list and filtered none of them. |
| 2026-08-01 | **Fixed that bug in one consumer and left it in the other.** The recorder got a strict name key; `compare_people`'s fallback kept using the same broken one, so the CONTROL run reported `linked=2, clean=true` on a scene where nobody is named — a false green in the guard, reached through my own fix. An empty `name` from the extractor is an ANSWER, not a missing value to fall back from. |
| 2026-08-01 | **A green test was pinning the stub.** `test_approve_canon_work_is_clean_no_op` asserted that approving a canon chapter dispatches NO extraction, commented “canon partition untouched”. True, and the defect: it is why a book written from scratch never reached the knowledge graph the canon guard checks against. It read as a deliberate invariant because it was written like one. |
| 2026-08-01 | **I deferred five items and four did not clear the gate.** The author pushed back that the reasons were not legitimate and that deferring makes the product a stub. Re-grading against the repo's own rule: 155 is breadth not depth, 156's audit half is a grep I refused to run, 158 and 159 are experiments I had already designed. Only a data migration was genuinely large. |
| 2026-08-01 | **Wrote “this regression is mine” from one run against one run.** A full glossary package failed twice on my branch and passed at HEAD — n=1 each way. Re-running my branch came back clean: the two PP-4 tests are flaky. I had already drafted the attribution and would have gone hunting a bug that does not exist. |
| 2026-08-01 | **Quoted a number I had not re-run.** The POC note said 809 leaked synopses; measuring properly gave 850. The figure had been carried forward from a one-off query into a defect list as if it were established. |
| 2026-08-01 | **Moved a component off the legacy scalar and left half of it behind.** `checked` was switched to `guard_status`; the unchecked-REASON chain in the same file kept keying on `canon.status`, so every new status fell through to a branch that asserts “the canon service was unavailable”. I then wrote the gap up as “the FE renders nothing”, when it rendered a fabricated cause. |
| 2026-08-01 | **Blamed my own call site before counting the others.** Asked whether the budget seam had rotted, I said the mechanism existed and my new call ignored it. Counting showed 28 of 30 call sites passed no signal, and that the VERDICT kind was hardcoded `base = 0.0` so no judge call COULD have carried any. A local explanation reached for before a systemic measurement. |
| 2026-08-01 | **Asserted a CAUSE from one observation, in a probe that had drifted off the platform's own call path.** I wrote that the thinking-disable flags “do not work for this model”; `build_judge_request` in fact sends the STRONGER disable. The author caught it. The observation — a truncated judge silently kills the blocking tier — held; the explanation I had already committed to prose did not. |
| 2026-08-01 | **Validated a judge on three-sentence excerpts and called the tier proven.** The 3/3 real/dream/feint result was real and useless as evidence for production: on 500-word drafts the same judge overruns its budget and returns nothing. Fixture LENGTH was the difference between a working tier and a dead one. |
| 2026-08-01 | **Fixed one confound by recreating the one I had explicitly set out to avoid.** v1 failed because the drafter never resolved the fight; I fixed that by having the synopsis COMMAND a terminal outcome — which is the conflicting-instructions trap v1 was designed around. v2 measures synopsis-vs-constraint, not prevention. The result is valuable; the framing would have been wrong for the third time if I had not checked. |
| 2026-08-01 | **Called a flat A/B “no power” without checking my own samples were independent.** Re-running the same node five times fed each run's exit-state into the next one's prompt, so n was 1 per arm, not 5 — and the prose showed the drafter never resolved the fight at all, which is a different finding from the one I reported. I had the lesson row for this and applied half of it. |
| 2026-08-01 | **A third gate that passed its own injection — same cause each time.** The chapter-path no-omission guard used a regex over call bodies; it matched 2 of 3 calls and one match ran 19,993 chars, swallowing the next call, so a deleted flag was still found inside another's blob. `ast` reds correctly. I keep reaching for a regex where the structure is a parse tree. |
| 2026-08-01 | **Nearly scored an A/B with a column that cannot differ.** The `free` arm has no plan rung, so its `plan_violations` is 0 by construction — an arm that killed everyone would still read 0. I caught it while writing the scorer, not while designing the experiment. |
| 2026-08-01 | **Wrote a field name from memory instead of reading it — twice in one session.** `seg.kind` (it is `block`), after the judge stub's `{"content": …}` (it is `messages[0].content`). Both were caught by a failing test, and both were the same habit: asserting the shape I expected rather than the shape the producer defines. |
| 2026-08-01 | **Invented a fixture's shape from the consumer instead of the producer.** My judge stub returned `{"content": …}`; the gateway's job result puts it at `messages[0].content`, which `extract_judge_text` calls LOAD-BEARING in its own docstring and which this repo already has a lesson row for. Two tests failed for a reason that had nothing to do with the code. |
| 2026-08-01 | **Nearly ‘fixed’ the honesty rule to make my own test pass.** I asserted `verdict is False` on a fixture with an empty `packed_prompt`, so name-grounding was NO_RULES, `guard_status` was not `checked`, and `verdict` was None — exactly as the rule I wrote hours earlier requires. The fixture was wrong, not the rule. |
| 2026-08-01 | **Built a fixture three times before it could measure anything.** Bare-UUID cast made the drafter write a character as a fortress; a same-chapter control inherited the death through `<recent>`; two scenes at the same `story_order` swapped each other's synopsis. Every failure was the fixture, and every one of them would have produced a confident wrong answer if I had not read the prose. |
| 2026-08-01 | **Nearly wrote up a cross-chapter spoiler leak that isn’t one — then nearly ‘fixed’ correct code into a bug.** `gather_structural` scans project-wide; I called it a leak before finding `STORY_ORDER_CHAPTER_STRIDE`. Then, having found it, I started widening `plan_liveness_after` to match — which under the mixed convention the data really has would have broken it. Both directions were caught by measuring, not by thinking harder. |
| 2026-08-01 | **Passed two kwargs the callee does not accept.** `extract_events` takes neither `trace_id` nor `source_language`. Every test that stubs the extractor stays green; only a live call raises — and the degrade-safe `except` would have swallowed it into a permanent DEGRADED status nobody would have questioned. |
| 2026-08-01 | **Verified ONE of two images and drew a conclusion about the path that ran in the other.** Rebuilt `composition-service`, hash-checked it, ran the live probe, saw the plan rung silent and began writing up a code defect. The job runs in `composition-worker` — a separate image, still stale. The measurement was of code I had not deployed. |
| 2026-08-01 | **My fix for the null-swallowing bug swallowed a null.** `canon.verdict ?? canon.resolved` treats an explicit `null` — *nothing verified this* — as absent and falls back. `undefined` and `null` mean OPPOSITE things there. The `??` operator reads as the safe one, which is why it got through. |
| 2026-08-01 | **Wrote a gate that passed its own injection — twice — inside the gate whose job is that rule.** The `via`-hop evidence check first matched the property DEFINITION, then matched a DOCSTRING through an `or field=` escape hatch I added for generality. Only the third version went red on the renamed key. |
| 2026-08-01 | **Counted copies by eye and wrote the number into a docstring.** “SIX places” was first written as “FOUR”; the mechanical test written in the same commit found the other two immediately. The wrong count came from the same eyeballing that let the copies exist. |
| 2026-08-01 | **Wrote a diagnosis into the handoff from ONE error message.** Told the next session "CI red = 33 failures, one root, `language`→`original_language`, a mechanical sweep". There were **three** roots — a fastapi 0.139 `app.routes` change across two services, a pip editable path resolving outside the checkout, and the rename — and the rename half needed a SEMANTIC rewrite because the identity key had changed too. I had read one traceback and generalised, which is the §1.4 mistake the red team already caught me making twice. |
| 2026-08-01 | **Wrote “already done” instead of running the tests.** S7-2 rested on reading two call sites. The goal's own clause — *saying a check passed without pasting its output does NOT satisfy this* — is what sent me back for the four PASS lines. It caught the single claim in this run I had not measured. |
| 2026-08-01 | **Nearly collapsed two decisions into one constant — the inverse of the bug I had fixed four commits earlier.** I almost let tilemap's runaway ceiling double as its sizing model. S7-1 was one decision written as two numbers that disagreed; this would have been two decisions written as one, so raising the ceiling would silently re-size every request. |
| 2026-08-01 | **Reached for the dramatic reading of code I had just met.** `tool_use_success: classifications_parsed > 0` looked like “a truncated run reads as success” and I began writing it up — but the classifications ARE parsed and the render already prints `finish_reason`. The real defect was plainer: no cap was ever sent, anywhere in Rust. Same shape as B4/B5, whose severity this project already walked back. |
| 2026-08-01 | **Three falsifications in a row primed me to expect a fourth.** On the first grep hit (`ModelRole` includes `'critic'`) I nearly recorded “the spec is wrong again”. The type member exists and is unreachable — the spec was RIGHT, and sharper than it knew. A measurement has to be allowed to confirm as well as refute. |
| 2026-08-01 | **Treated the spec's §S7 bullets as a work list instead of as hypotheses — three of them falsified by measurement in one slice.** “two SDK sites unclamped” (they are MIRROR, where clamping is the bug) · “33 CI failures, one root” (three roots) · “glossary has ZERO FinishReason checks service-wide” (it has ten, and the gap was closed earlier in this same session). This is the exact habit the red team already caught the spec doing to itself. |
| 2026-08-01 | **Nearly read a red test as “my fix is wrong” when it was pinning the bug.** `test_window_shrinks_for_a_small_context_model` restated `8_000 - 2_048 - 2_048`; raising the output reserve to match the request cap made it fail. Same shape as the motif tests asserting the removed i18n behaviour, two slices earlier in this same run. |
| 2026-08-01 | **Counted `call_budget` call sites with a regex that also matched `per_call_budget` and a stale `sdks/python/build/lib/` copy** — 4 “unclamped” sites, all four phantom. Then read the two real ones and found the spec's claim (“two clamp, two do not”) was itself wrong: the unclamped ones are `OutputKind.MIRROR`, where clamping would be the bug. Nearly “fixed” correct code on the strength of a spec sentence. |
| 2026-08-01 | **Wrote a checker that silently halved its own input — inside the gate whose docstring records that exact failure.** The S12 generalisation matched only repo-relative markdown link targets; the standards index lives at `docs/standards/` so nearly all its links are `../../…`. It found 43 paths and printed “0 missing” while never examining a single doc link. The fix took it to 91. |
| 2026-08-01 | **Wrote a fixture that asserted the opposite of its own name.** The “content lost while the budget reads fine” case used a 401-token protected floor against a 200-token budget, so both halves were over-budget. It failed loudly — the only reason I noticed. Written the other way round it would have PASSED and pinned the very semantic inversion S8 exists to correct. |
| 2026-08-01 | **Wrote a check that answered a different question from the one I asked.** Verified `_uuid` was imported by grepping for the string — it matched, at line 277, INSIDE another method where it is a local. The new eval seeder would have died on `NameError` at its first live run, and no test drives a seeder without a stack. |
| 2026-08-01 | **Nearly committed a WORSE baseline and blamed the engine for my shell.** Recorded `gone_cast = error/error` twice — once because my shell had no `INTERNAL_SERVICE_TOKEN`, once because the seeder's internal URLs default to docker hostnames that do not resolve from the host. Both times the honest reading was *my environment*; the committed file would have said *the engine*. |
| 2026-08-01 | **Trusted a local green that could not have been the CI green.** 3303 tests passed on my box while CI was red on the same commit, because the dev box is on fastapi 0.136 and CI installs `>=0.139`. I only found it by reading the CI log, not by running anything. A suite is only evidence for the environment it ran in, and I never checked that mine matched. |
| 2026-08-02 | **I turned a CI gate RED with a comment, shipped it, and did not notice for four slices — because the gate set I kept pasting as "the gates" is a SUBSET of what CI runs.** The word "passage" in a comment I added in S7-4 made `injection-coverage-lint` exit 1 on `compress.py`. Six gates (ai-provider, generation-guard, enforcement-claims, db-safety, llm-budget, language-rule) is not the CI gate set. Every VERIFY block before S4 asserted its evidence honestly against an incomplete list. |
| 2026-08-02 | **Nearly wrote up "the prose fix blinded the detector" when my injected NAME was wrong.** `_retrieved_passage = body` did not red the gate; the regex needs a word boundary and `_` is a word character. Measuring the regex directly settled it in a minute. Same reach-for-the-dramatic-reading shape as the tilemap `tool_use_success` near-miss. |
| 2026-08-02 | **Asserted a security detector MUST catch something, on my own assumption, and started treating the mismatch as a regression I had caused.** An uppercase `"PASSAGE:"` inside a prompt template does not register — before or after my change. Checking the pre-fix behaviour showed it was always the boundary. Recorded as a known limit instead of widening a security regex to match what I had guessed. |
| 2026-08-02 | **Shipped a regression six unit tests could not see, and only the LIVE run caught it.** `class SkipReason(str, Enum)` satisfies `== "refuted"` and JSON-serialises correctly, so every test passed — but `str()` and f-strings return `"SkipReason.NOOP"`, so any consumer that FORMATS a skip_reason would emit the member path. The live probe printed `skip_reasons seen: ['SkipReason.NOOP']`. Every test I wrote used `==`, which is exactly the shape blind to it. `StrEnum` fixes it; the lesson is that comparison-only tests do not cover a value that leaves the process by three different routes. |
| 2026-08-02 | **A guard that reddened on the comment explaining what it forbids.** My duplicate-name check scanned raw file text for `not_found` and failed on my own note recording that `not_found` had been removed. Prose is not usage — the distinction the deferral registry's stripper had to learn, met from the other side. Rewritten over the AST's string constants, where comments do not exist. |
| 2026-08-02 | **I wrote a check that could not fail, into a test file, in the slice about machine-checking a contract.** A `@ts-expect-error` asserting `TraceTier` rejects `"T9"` — inert, because `tsconfig.json` excludes `src/**/__tests__` and `*.test.tsx`, so no test file is ever type-checked. It reads exactly like enforcement. Found ONLY because I widened the type to prove red-ability and `tsc` returned exit 0 — the injection I nearly skipped as unnecessary for a change this simple. Fifth check-that-cannot-fail this run, and the first I authored rather than found. |
| 2026-08-02 | **Introduced a two-convention bug WHILE removing one — and the suite stayed green.** Swapping translation's `estimate_tokens` for the kernel left `split_chapter` still sizing its window from the old `_CJK_CHARS_PER_TOKEN = 1.5`, so a 100-token budget cut 150 CJK chars the new estimator counts as 158: 58% over, inside the module I was fixing for exactly that. It passed because the test asserting chunk COUNT was itself derived from the old constant. Caught by reading the function below the one I edited, not by a test. |
| 2026-08-02 | **Edited a function twice while its module docstring described the behaviour I had just removed.** `chunk_splitter`'s header still advertised "CJK at ~1.5 chars/token" after the body became the kernel's. Stale prose is how the next reader re-derives the wrong model — the same shape as the `cross_scene_check` row whose `why` describes a call that no longer exists. |
| 2026-08-02 | **Nearly shipped the S6 picker without the warning that makes it honest.** The spec asks for an affordance, and a select writing `critic_model_ref` satisfies that literally. But the state an author most often lands in is "I picked the model I already use", which the server silently refuses — so the setting would look applied and do nothing. That is the permanent-amber shape S1 exists to end, re-created by the slice written to close it. |
| 2026-08-02 | **A refactor that did nothing, reported like a run that worked.** My first replacement of the six hand-rolled `distinct` copies matched on `\r\n` and printed `8-indent copies: 0 · 4-indent copies: 0` — a clean no-op with a tidy summary. Only because the same command also printed the REMAINING count did I see it had changed nothing. A script that reports what it looked for, not what it changed, reads as success. |
| 2026-08-02 | **Applied the new exemption to the wrong row, first try, inside the slice written to stop exactly that.** I marked `compress` `signal_inert` because `ceiling == floor == 512` and the ceiling is applied last. The probe reddened at once: the window clamp ALSO runs after the floor and pushes DOWN, so `context_length=8` gives 4. A ceiling bounds one direction. The flag would have excused a call site from a signal it is entitled to — the rot this slice pays down, re-created by its own exemption mechanism. Only the two-directional assert caught it; a one-directional one would have passed. |
| 2026-08-02 | **Widened the detector and nearly banked the smaller number.** My first `_ssot_local_names` bound names module-wide, and the unattributed backlog fell 29 → 26 — three sites this slice never touched, including `self_heal._chat`, a helper one of whose callers passes a flat `400`. The name matched, so a literal would have been laundered into `attributed` by an assignment four hundred lines away. Shrinking a backlog by loosening the thing that measures it is how a ratchet stops meaning anything, and it presents as progress. |
| 2026-08-02 | **Nearly deleted five load-bearing overrides as redundancy.** The plan-forge repair sites restate `max_tokens_for("plan_forge_chat")`, which looked like duplication of the client default — but `LMStudioClient.chat` declares **8000** against the row's **12000**, so removing them would have cut a plan JSON by a third, and a clipped plan comes back unparseable rather than short. Reading the Protocol before editing is what stopped it, and it exposed the genuine version of the bug: `_parse_with_repair`'s own `8000` default, overridden only by `materialize`, so `analyze` and `refine_spec` had been running a third under the declared row. |
| 2026-08-02 | **Reported a deployment failure that was my shell.** Seven image hash checks came back `MISMATCH` and I had begun treating the build as stale. Git Bash rewrites `/app/...` into `C:/Program Files/Git/app/...`; with `MSYS_NO_PATHCONV=1` all seven MATCH. The repo already has this lesson written down. I applied it only after producing the false report — which is the failure mode, not the path mangling. |
| 2026-08-01 | **Built the fix list from a TRUNCATED terminal, then called it complete.** The failure list printed 20 of 33 rows; I swept the 6 files I could see and reported "one root, six files". The other 13 rows held two more files with the same root — and one of them was a PRODUCTION bug (`retrieve_arcs` selecting a dropped column, 500 on the shipped schema). Same shape as the ROT-1 miss: a denominator taken from what I happened to see rather than from the full set. |


- **2026-07-31 · caught in review of my own proposal.** My first S1–S5 proposal was scoped to
  composition-service and missed five axes, one of which (S7) was a defect I created last session:
  I wrote `scene_output_budget` and left 20 of its 21 sibling call sites as flat literals. The
  author's question *"đã đủ triệt để chưa?"* is what surfaced it — I had stopped auditing at the
  boundary of the file I had most recently edited.
- **2026-07-31 · I repeated the exact mistake the red team had just caught me making, one day later.**
  §1.4 was falsified because I counted inside the files I had read and stated it for the repo. Then
  ROT-0 swept the two DSN variables I happened to be looking at, found 41 never-run tests, and I
  reported "41" as the answer. Sweeping *every* `*_TEST_*` var afterwards found **159 more** — auth,
  usage-billing and provider-registry among them. **200 total, 41 reported.** It surfaced only
  because the author asked "did the un-cleared items get into the spec, or were they forgotten?"
  They were being forgotten. The lesson is not "sweep harder" — it is that a count is a claim, and a
  claim needs its denominator derived from the SSOT, not from what I happened to touch.
- **2026-07-31 · the S12 gate went green on its own motivating example three times.**
  Once because the crate reads the contract (and nothing calls the crate); once because a doc
  comment and a workspace-membership list mention the crate name (membership is not linkage); and
  once because the gate ITSELF names the contracts in its docstring, so it satisfied its own check
  by discussing the problem. Each was caught only by re-injecting the original fiction and watching.
  **A gate that has never been observed to fail is not a gate.**
- **2026-07-31 · the red team falsified my own falsifiability section.** §1.4 existed to be
  disprovable and both its claims were wrong. Root cause, both times: I counted inside the file I
  had just read and stated the result for the repo. Scope was off ~3× (4 services → 13 + 6 SDKs +
  Go + Rust); two of four stated root causes were wrong paths; four slices would have broken
  working code. **Four cold-start agents on disjoint corpora found what I could not, because they
  could not see my reasoning.**
- **2026-07-31 · a gate that went red for the wrong reason.** B5's first version reddened on a
  `TypeError` from an unstubbed repo, not on the security property. Re-stub the downstream and the
  defect sails through. Fixed by asserting `create_campaign.assert_not_called()` — the property
  itself — after stubbing the write path exactly as the neighbouring success test does.
- **2026-07-31 · I fabricated dataclass fields in a test** (`density=`/`pace=` on `BookProfile`).
  It failed for its own reason and proved nothing. The repo already has this lesson written down:
  derive test inputs from the producer schema, never from memory of it.
- **2026-07-31 · two "bugs" that needed the severity walked back.** B4's endpoint is
  internal-token gated (401) — not attacker-selectable from outside. B5's fail-open had a written
  justification; the bug was that the justification (*"the dispatch path re-verifies"*) was
  **fiction** — `verify_project_owner` has one call site, the one making the claim. Same class as
  B3. Accepting the red team's framing unverified would have mis-ranked both.
- **2026-07-31 · nearly asserted a bug that was not there.** I proposed a "cast-liveness check" as
  missing. It exists (`canon_check.gone_cast_in_draft`), and `ReflectResult.status` already carries
  honesty states. The real gaps were narrower and different: one missing *direction*, one missing
  *status*, and the checker pointed at the empty SSOT. Reading the code before proposing the fix
  changed the fix.
