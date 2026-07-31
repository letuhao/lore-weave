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
