# RUN-STATE — Work Assistant autonomous build

> ## 📌 READ THIS FILE FIRST after any compaction, and at every checkpoint.
> This file — not my memory of the conversation — is the source of truth for the run.
> Context is lossy. Disk is not.

**Started:** 2026-07-11 · **Branch:** `feat/context-budget-law` · **Mode:** long autonomous run, self-checkpointing.
**Spec set:** [`docs/specs/2026-07-11-work-assistant-mode/`](../specs/2026-07-11-work-assistant-mode/README.md) ·
**Sealed decisions:** [`DECISIONS-SEALED.md`](../specs/2026-07-11-work-assistant-mode/DECISIONS-SEALED.md) (binding) ·
**Plan:** [`implementation-plan`](2026-07-11-work-assistant-implementation-plan.md)

---

## 1. The goal (one sentence)

**Ship the Work Assistant end to end — Phase 0 → Phase 5 — with every slice `/review-impl`-clean, every
deferred item closed before "done", and no silent lowering of the bar.**

## 2. Autonomy contract (agreed with PO 2026-07-11)

| | Rule |
|---|---|
| **Don't stop** | Work continuously. Solve deferred items until closed. Do not pause for approval between slices or phases. |
| **Self-checkpoint** | I checkpoint myself (commit + update this file). No human gate at checkpoints. |
| **Auto-compact** | Session compacts at the limit; **on resume, re-read this file first.** |
| **`/review-impl` per phase** | **Mandatory.** Findings fixed in the same phase, not deferred. |
| **I decide** | All ordinary technical decisions are mine. Record them in §6. |
| **STOP only if** | (a) **dangerous** — destructive/irreversible, security-critical, or data-loss risk; or (b) **needs redesign** — a sealed decision turns out to be wrong. Then: stop, write it up, ask. |
| **Blocked ≠ stop** | If I cannot solve something: **park it in §7, move to other work, keep going.** PO reviews parked items and decides. Never block the run on one problem. |
| **Final audit** | At the end: decisions · drift · debt · deferred · completeness (§6–§10). Built incrementally so the audit is a *byproduct*, not archaeology. |

## 2b. The `/goal` condition (the human↔agent commitment — durable copy)

The human sets this with `/goal` (a built-in CLI command; **the agent cannot set it**). Recorded here so it
survives compaction and can be re-set verbatim. ⚠️ The `/goal` evaluator **reads the transcript only — it
cannot run commands or read files**, so the condition is deliberately written to force proof *into* the
transcript.

```
/goal Phase 0 of docs/plans/2026-07-11-work-assistant-implementation-plan.md is COMPLETE. Done means ALL of: (1) every slice WS-0.1..WS-0.9 is marked ✅ in docs/plans/2026-07-11-work-assistant-RUN-STATE.md §5 with a real evidence string; (2) the transcript contains the ACTUAL PASTED OUTPUT of the test runs and the live-smokes from §5 of docs/specs/2026-07-11-publish-independent-kg-indexing.md — specifically: a draft chapter that is never published gets indexed into the KG; autosave triggers ZERO extraction jobs; a single index click leaves the other 199 chapters' extraction_leaves intact; the whole-book rebuild enumerates draft-indexed chapters; and composition's index_stale is false after publish@A + index-draft@B; (3) /review-impl has been run on the phase and every finding is FIXED (not deferred), with the fixes committed; (4) the transcript shows `git log --oneline` with the commits; (5) RUN-STATE §6-§9 registers are updated. Claiming a check passed without pasting its output does NOT satisfy this condition. If you cannot solve something, park it in RUN-STATE §7 and continue with other slices — do not stop. Stop and ask ONLY if an action is destructive/irreversible or a sealed decision turns out to be wrong. Or stop after 60 turns.
```

**Subsequent phases:** re-set `/goal` per phase, same shape (evidence pasted into the transcript, findings
fixed not deferred, registers updated, turn-bounded).

## 3. Standing invariants (the bar — never lower these silently)

These are the things that *feel* skippable at 2am and must not be:

1. **A slice is DONE only when its evidence string exists in §5.** Not when the code compiles. Not when tests
   are green. **Evidence = the behavior was observed.**
2. **Live-smoke for any slice touching ≥2 services.** Unit-green has hidden cross-service bugs 4× in this repo.
3. **Consumed-by-effect** — every flag/guard/setting gets a test asserting the *behavior*, not the stored value.
4. **Fail-closed** — every privacy/spend toggle defaults off and fails closed.
5. **No silent success** — a success status with no work done is a **bug**. Every skip logs a reason.
6. **Erasure tests assert ABSENCE** (row gone, node gone, rebuild doesn't resurrect) — never "invisible".
7. **Never `git add -A`** — enumerate files (concurrent sessions share this checkout).
8. **Grep before trusting a list.** The red team found "canon = published" in 6+ places after I'd found one.
   *Assume my enumeration is incomplete.*

**Mechanical enforcement:** use `scripts/workflow-gate.py` (+ the pre-commit hook) — it blocks phase jumps and
commits without VERIFY/POST-REVIEW evidence. If I find myself wanting to bypass it, that **is** the drift.

## 4. Phase board

| Phase | Status | `/review-impl` | Notes |
|---|---|---|---|
| **0 — Publish-independent KG indexing** | ⬜ not started | ⬜ | Prereq. 4 services. Red team: "do not build as written" (v1) → v2 fixed |
| **1 — Assistant MVP + diary-lite** | ⬜ | ⬜ | WS-1.0 (encryption) ships FIRST |
| **2 — Facts · erasure · amendment · spend** | ⬜ | ⬜ | D18 erasure = release requirement (PO-4) |
| **3 — Scheduler & proactive** | ⬜ | ⬜ | |
| **4 — Voice parity** | ⬜ | ⬜ | |
| **5 — Coaching** | ⬜ | ⬜ | Gated on 4 prerequisites (R4) |

## 5. Slice board — the only place "done" is defined

`⬜ todo · 🔵 in progress · ✅ done (evidence recorded) · 🅿️ parked (see §7)`

| Slice | Status | Evidence (required for ✅) |
|---|---|---|
| WS-0.1 chapter-scoped cache invalidation | ✅ | **unit 3780 passed** (`-n auto --dist loadgroup`, 0 failed). **Integration 7/7 vs REAL Postgres** (`test_extraction_leaves_chapter_scope.py`): `test_delete_by_chapter_spares_the_other_199_chapters` PASSED (seed 200 chapters × 4 ops = 800 leaves → invalidate 1 → **796 survive**, exactly the other 199); `..._does_not_leak_across_books`; `..._is_idempotent_on_replay`; `..._respects_op_filter`; `test_delete_by_book_still_wipes_everything` (the `/invalidate-cache` route keeps book-wide semantics); `test_migration_backfills_chapter_id_from_scene_id_on_legacy_rows` (reconstructs the pre-WS-0.1 shape, runs the **real** `migrate.DDL`, asserts `chapter_id == scene_id`, rolls back); `test_chapter_id_is_not_null_so_a_forgetful_writer_fails_loudly`. **`test_migrations_idempotent` PASSED** (real double-run vs live PG, `-rs` confirms ran-not-skipped). Live schema verified: `chapter_id` `is_nullable=NO`. |
| WS-0.2 columns + backfill | ⬜ | |
| WS-0.3 all six writers + hygiene test | ⬜ | |
| WS-0.4 index action + `chapter.kg_indexed` | ⬜ | |
| WS-0.5 sweeper full re-key + unpublish | ⬜ | |
| WS-0.6 generalize the publish gate in every reader | ⬜ | |
| WS-0.7 composition mirror + canon-markers | ⬜ | |
| WS-0.8 knowledge consumer + canon flag + retraction | ⬜ | |
| WS-0.9 FE "Add to knowledge" + indexed indicator | ⬜ | |
| *(Phase 1+ slices appended as phases open)* | | |

## 6. Decision register (every call I make, so the audit is free)

| # | Decision | Why | Reversible? |
|---|---|---|---|
| **D-R1** | `delete_by_chapter` keys on a **new `extraction_leaves.chapter_id` column**, not on the existing `scene_id`. | The spec said "the event already carries `chapter_id`" but the *table* has no such column — it has `scene_id`, which production writes as `scene_id := chapter_id`, an explicit **placeholder** (`pass2_orchestrator.py`: *"placeholder until per-scene fanout"*, D-P2-PER-SCENE-FANOUT). A delete keyed on `scene_id` passes every test today and silently matches **zero** rows the day real per-scene fanout lands → a stale extraction cache the graph then re-derives from → **correctness** bug, not a cost bug. An explicit column survives the fanout. Backfill `chapter_id := scene_id` is correct by construction for every existing row. | Yes (drop column) — but don't; the placeholder coupling is the trap. |
| **D-R2** | `chapter_id` is **NOT NULL**, enforced after the backfill. | A leaf written without a chapter_id is unreachable by *any* chapter-scoped invalidation — a permanently-stale cache entry, silently. NOT NULL converts latent corruption into a loud failure at the write. (Repo class: `add-column-if-not-exists-never-revisits-a-bad-default`.) | Yes |
| **D-R3** | An event with an unusable `chapter_id` **widens to book-scope + WARNs** — it does **not** skip. | Over-deleting costs an LLM re-extract; under-deleting leaves a stale cache → the graph re-derives from a scene index that no longer exists. **When the scope is unknown, spend money rather than corrupt the graph.** The WARN means the degradation can't rot unnoticed (no-silent-success). | Yes |
| **D-R4** | Taught `test_p2_block_is_idempotent` that `ALTER COLUMN … SET NOT NULL` is inherently idempotent, rather than dropping the guard. | The guard greps every P2 `ALTER TABLE` for `IF NOT EXISTS`; Postgres has **no such spelling** for `SET NOT NULL`, so the *syntactic* proxy can't express a statement that *is* re-runnable. The **semantic** guarantee is already proven by effect (`test_migrations_idempotent` runs the real DDL twice vs live PG) — so I narrowed the static backstop with a documented exception instead of weakening the real gate. | Yes |

## 7. Parked problems (blocked ≠ stopped — PO reviews these)

| # | Problem | What I tried | Why parked | Blocks what? |
|---|---|---|---|---|
| *(appended as I go)* | | | | |

## 8. Debt register (things I knowingly did the cheap way)

| # | Debt | Where | Cost of leaving it | Pay-off trigger |
|---|---|---|---|---|
| **DBT-1** | WS-0.1 has **no cross-service live-smoke**: the real loop is book-service emits `chapter.scenes_reparsed` → knowledge invalidates one chapter. I proved the consumer half against real SQL, and the handler wiring by unit test, but never ran a real producer→consumer round trip. | knowledge-service (consumer proven) ↔ book-service (producer untouched this slice) | Low **for this slice** (the producer is unchanged), but the repo has been burned 4× by mock-only cross-service coverage. The honest statement: the *contract* is unproven end-to-end. | **WS-0.8 / Phase-0 exit smoke** — where the index action exists and the whole loop is real. Acceptance §5.4 covers exactly this. **Do not let the phase exit without it.** |

## 9. Drift log (bar-lowering, caught and corrected)

Anything where I *nearly* skipped a gate, or where a spec turned out to be wrong. **Recording these is the
point** — a run with an empty drift log is either perfect or dishonest, and it is never perfect.

| # | Drift | Caught by | Corrected how |
|---|---|---|---|
| **DR-1** | **The spec was wrong, and its wording invited the lazy fix.** §3.3 says *"add `delete_by_chapter(chapter_id)` … (the event already carries `chapter_id`)"* — which reads as a trivial re-key. But the **table has no `chapter_id` column**. The available column is `scene_id`, which production sets to the chapter id. Keying the delete on `scene_id` would have passed every test I wrote, shipped clean, and silently deleted **zero** rows the day per-scene fanout landed. | Reading `pass2_orchestrator.py:706` before writing the query — the line is literally commented *"placeholder until per-scene fanout"*. **The spec's own phrasing would have led me straight past it.** | Added a real `chapter_id` column (D-R1) + NOT NULL (D-R2). **The spec's §3.3 is now factually wrong and must be corrected** (done — see the spec edit in this commit). |
| **DR-2** | **I nearly shipped a fake backfill proof.** I ran `SELECT count(*) FILTER (WHERE chapter_id = scene_id)` against the live DB, got a clean result, and was about to record "backfill verified". The table had **0 rows** — the query proved *nothing*. This is precisely the `env-gated-tests-skip-and-the-green-suite-lies` class, self-inflicted. | Checking `total_leaves` before writing the evidence string, instead of after. | Wrote `test_migration_backfills_chapter_id_from_scene_id_on_legacy_rows`: reconstructs the legacy shape, runs the **real imported `migrate.DDL`** (not a paraphrase that could drift), asserts `chapter_id == scene_id`, rolls back. Evidence string now cites *that*, not the vacuous count. |

## 10. Completeness ledger (the definition of "done" for the whole run)

- [ ] Every phase built, `/review-impl`-clean
- [ ] Every parked problem (§7) resolved or explicitly accepted by PO
- [ ] Every debt (§8) paid or converted to a tracked defer with a gate reason
- [ ] Every sealed decision (DECISIONS-SEALED) still true — or amended with a review-record line
- [ ] The 5 "most likely to go wrong" items in the plan each have a passing test
- [ ] `docs/sessions/SESSION_HANDOFF.md` updated
- [ ] Final audit written: decisions · drift · debt · deferred · completeness

---

## 11. If you are me, resuming after a compaction — do this

1. Read this file (you just did).
2. `git log --oneline -10` — what actually landed.
3. Read §5 for the current slice; §7 for what's parked.
4. Re-read the slice's spec section **before** touching code (do not trust a remembered summary of it).
5. Continue. Do not re-litigate a sealed decision.
