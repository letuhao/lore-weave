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

## PHASE 0 — live bugs. Fix · live-smoke · seal. `done` is an evidence string.

| id | bug | status | evidence |
|---|---|---|---|
| B5 | campaign-service ownership fail-open | **SEALED** | gate red = `201 Created` on an unverified project + `create_campaign` called; green = 503 `CAMPAIGN_OWNERSHIP_UNVERIFIABLE` + `created.assert_not_called()`. Suite **184 passed / 20 skipped**. |
| B2 | `guide` sanitized in pack, re-appended RAW by the wrapper | **SEALED** | 2 bypass sites fixed (`build_messages`, `build_selection_messages`); gate red on 3 payloads; green 9/9. Composition suite **3076 passed / 384 skipped**. |
| B1 | composition `cl100k` → VN books trimmed to ~56% | in progress | |
| B4 | judge model caller-selected, no distinctness record | pending | *severity corrected: the endpoint is internal-token gated — NOT externally attacker-selectable. Real defect = a self-graded score persists indistinguishably from an independent one.* |
| B3 | `YamlGuardrail` — 0 call sites, 2 docs claim it gates every write | pending | needs a decision: wire the crate, or correct both documents |
| B6 | worker-ai unjudged⇒keep, coverage discarded | pending | |
| B7 | `poc_v2_*` direct Ollama + hardcoded model, unallowlisted | pending | |
| B8 | tilemap fallback narration returned as `Ok` | pending | |

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

- 43% disagreement between the repo's two token estimators on 2,275 chars of real Vietnamese prose
  (`estimate_tokens` 665 · `tiktoken cl100k_base` 1,159), measured 2026-07-31.
- ~30 `build_*_messages` in composition-service; 24 LLM-calling modules bypass the packer (17 build
  a prompt); 6 finding types; 2 self-heal implementations; ~21 flat `max_tokens` literals;
  5 self-grading call sites across 2 services.
- Baseline prose: Mị Đế ch.1, 5 scenes, 3,124 words, one known defect invisible to the current stack.
- **Clean, verified:** all 11 composition judges de-bias to `source_language`; the provider path is
  genuinely single (`clients/llm_client.py`).

## Parked

*(empty)*

## Debt taken on

*(empty)*

## Drift log — near-misses, wrong turns, bars I nearly lowered

> A run that ends with an empty drift log is not clean; it is dishonest. Append as they happen.

- **2026-07-31 · caught in review of my own proposal.** My first S1–S5 proposal was scoped to
  composition-service and missed five axes, one of which (S7) was a defect I created last session:
  I wrote `scene_output_budget` and left 20 of its 21 sibling call sites as flat literals. The
  author's question *"đã đủ triệt để chưa?"* is what surfaced it — I had stopped auditing at the
  boundary of the file I had most recently edited.
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
