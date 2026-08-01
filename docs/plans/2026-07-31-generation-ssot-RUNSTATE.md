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
`S7 → S6(+UI) → S11 → S3 → S4` → `S9 → S5`.

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

*(empty)*

## Debt taken on

*(empty)*

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
