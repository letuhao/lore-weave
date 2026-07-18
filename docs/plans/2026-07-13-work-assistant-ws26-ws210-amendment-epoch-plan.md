# WS-2.6 (D17 memory amendment) + WS-2.10 (employment epoch) — implementation plan

**Date:** 2026-07-13 · **Track:** Work Assistant · **Phase:** 2 (the two remaining slices) · **Status:** PLAN (pre-build) ·
**Specs:** [`09-settings-consent-privacy.md`](../specs/2026-07-11-work-assistant-mode/09-settings-consent-privacy.md) §Q (D17 verbs, T18 epoch) · [`00-overview.md`](../specs/2026-07-11-work-assistant-mode/00-overview.md) §D17 · [`07-recall-search.md`](../specs/2026-07-11-work-assistant-mode/07-recall-search.md) §Q5 · **SEALED:** D17 promoted early (revert = the amendment primitive; auto-accept can't ship before D17).

> These are the last two Phase-2 slices. They were parked gate-#2 because D17 is a **foundational primitive**
> ("build once — T4/T10/T24/T25 collapse into one tested path") and both entangle with the parked P-12
> erasure/encryption goal. This plan decomposes them into buildable slices and draws the P-12 boundary
> **before** any code, so the cross-store cascade isn't half-built (the incomplete-cascade privacy hole).

---

## 1. D17 in one sentence (the spec's core claim)

**Supersede a fact · correct a memory · forget a person · merge a renamed entity are all the SAME three-legged
write:** **(1) amend the PG SSOT (the diary entry revision) → (2) re-index (`chapter.kg_indexed`) → (3)
reconcile the derived graph.** *Anything that stops at leg 3 is a lie* — today `memory_forget` invalidates one
Neo4j fact and never touches PG, so the diary text stays wrong and a KG rebuild **resurrects** the "corrected"
fact. **Leg 1 is the missing piece.**

## 2. Substrate audit (what exists vs. what's missing)

| Leg / piece | State | Where |
|---|---|---|
| **Leg 1** — amend the PG diary-entry revision | ◐ partial — the write seam `UPDATE chapters … chapter_drafts … chapter_revisions` REPLACES a **draft**; a **kept** entry 409s (must supplement). An explicit amend-a-kept path is missing. | `book-service/diary_entry_handler.go` |
| **Leg 2** — re-index `chapter.kg_indexed` | ✅ built (WS-0.4/0.8) — the index action + the consumer that pins `extraction_pending` at the indexed revision. | book-service + knowledge consumer |
| **Leg 3 (facts)** — invalidate a superseded fact | ✅ built — `invalidate_fact` sets `valid_until` (bi-temporal); `delete_facts_with_zero_evidence`. | `knowledge/neo4j_repos/facts.py` |
| **Leg 3 (entity cascade)** — delete ONE entity across stores | ◐ partial — glossary has `glossary_entity_delete` (Tier-W propose→confirm **soft-delete** + `bookDeleteCascadeRows`); KG merge does `DETACH DELETE`; `delete_entity_status_with_zero_evidence` exists. **No single "forget this entity" cascade + no event type** ties them together. | glossary `action_confirm*.go` · knowledge `entities.py` |
| **Diary-span redaction** — remove a name from the user's prose | ❌ missing — an NLP/text op on the entry body. | — |
| **Pending-fact reject tombstone** | ✅ built (WS-2.2) — reject writes `knowledge_rejected_facts`. | knowledge |

**Takeaway:** the *facts* half of leg 3 and legs 2 are done. The genuine new work is **leg 1 (amend a kept
entry)** + the **entity cascade + event type** + **diary-span redaction**.

## 3. Slice decomposition

### WS-2.6a — the D17 primitive + "correct a memory" (BUILD FIRST — tractable, closes the headline gap)
The three-legged write for the simplest verb: the user corrects a fact stated in an entry.
- **Leg 1:** an **amend endpoint** on the diary entry (`PATCH /internal|/v1/books/{id}/diary/entries/{chapter_id}`)
  that writes a new `chapter_revisions` row + updates the draft body + (if kept) records the amendment without
  silently clobbering `diary_kept_at` (amend is an explicit correction, not a re-distill clobber — different
  from the write-seam's 409).
- **Leg 2:** the amend emits/triggers `chapter.kg_indexed` at the new revision (reuse WS-0.4).
- **Leg 3:** invalidate the superseded fact(s) via `invalidate_fact` (`valid_until`), so recall returns the
  corrected value and a rebuild does not resurrect the old one.
- **Acceptance:** amend "Minh froze the budget" → "Alice froze the budget"; recall now says Alice; the old
  `:Fact` has `valid_until` set; a re-extract of the amended revision does NOT re-create the Minh fact.

### WS-2.6b — "supersede a fact" (small — mostly leg 3, rides WS-2.6a)
A newer fact contradicts an older one. Same write; leg 3 invalidates the old fact and asserts the new (the
temporal-recall path from WS-2.4 already reads `valid_from_ordinal`/`valid_until`). Recall says *"it changed"*
(spec 07 §Q5), not pick-one.

### WS-2.6c — "forget a person" (the CROSS-STORE CASCADE — see §4; candidate to fold into P-12)
Cascade one entity: glossary entity (soft-delete + `bookDeleteCascadeRows`) → KG `:Entity` + its `:Fact`/
`:ABOUT`/`:Event` + evidence + passages + embeddings → pending facts (+ tombstone so it can't re-propose) →
**redact the diary spans that name them** → emit a new **`entity.forgotten`** event type (there is none today)
so every derived consumer reconciles. **This is a scoped erasure worker.**

### WS-2.6d — "merge a renamed entity" (substrate mostly exists)
Entity A renamed to B: reuse the glossary `merge_candidate` path (soft-deletes the loser) + KG merge
(`DETACH DELETE` / re-point `:ABOUT`). Leg-1 amend only if an entry names the old form.

### WS-2.10 — employment epoch (T18) — STRUCTURAL (export-then-purge folds into P-12)
- **WS-2.10a — epoch model + close-epoch:** an `epoch` marker (on the assistant project or a per-user epoch
  row); on a job change, `invalidate_fact`-style `valid_until` on the current epoch's facts (bulk).
- **WS-2.10b — fresh project + diary volume:** provision a new assistant project + diary volume for the new
  job (mirrors WS-1.4 provisioning, epoch-scoped).
- **WS-2.10c — recall defaults to current epoch:** the recall read filters to the active epoch by default (the
  D16 exclusion + WS-2.4 temporal read gain an epoch predicate); cross-epoch recall is explicit.
- **WS-2.10d — export-then-purge:** export the old epoch, then purge it. **= the erasure worker → P-12.**

## 4. 🔴 The P-12 boundary (draw it before coding)

Forget-person's cascade (WS-2.6c) and epoch export-then-purge (WS-2.10d) **are** the erasure worker (D18),
scoped to an entity / an epoch instead of an account. The spec's own Phase-2 (`09 §Q10`) lists **D18 erasure +
D17 forget-person + epoch** together, and D18's worker is exactly what's human-parked as **P-12 (D-R24)**.

**Decision (this plan):** build the **cross-store cascade primitive once, in P-12's erasure worker**, and have
WS-2.6c / WS-2.10d **call it with a scope (entity | epoch | account)**. Building three separate cascades now
would (a) duplicate the delete fan-out and (b) risk the incomplete-cascade hole fixed earlier this session
(erase left `:Fact`/`:Entity` behind). So:
- **In Phase 2 now:** WS-2.6a (correct), WS-2.6b (supersede), WS-2.6d (merge) — no new cross-store cascade.
- **Deferred to P-12 (with a tracked row):** WS-2.6c forget-person cascade + diary-span redaction, and
  WS-2.10d export-then-purge — built on the shared scoped-erasure primitive. WS-2.10a/b/c (epoch model, fresh
  project, recall-default) can land in Phase 2 without the purge.

## 5. Build order + gates

1. **WS-2.6a** correct-a-memory (leg1 amend + leg2 re-index + leg3 invalidate) — TDD, real-DB tests, `/review-impl`.
2. **WS-2.6b** supersede-a-fact — rides 2.6a's leg 3.
3. **WS-2.6d** merge-a-renamed-entity — reuse merge substrate.
4. **WS-2.10a/b/c** epoch model + close-epoch + fresh project + recall-default (NO purge).
5. **Tracked to P-12:** WS-2.6c forget-person cascade + diary-span redaction + WS-2.10d export-then-purge.
- Every slice: consumed-by-EFFECT tests (a rebuild does NOT resurrect a corrected/invalidated fact — the exact
  D17 failure mode), live-smoke on the ≥2-service legs (book amend → knowledge reconcile).

## 6. Acceptance (D17's honesty bar)
- **Leg-1-exists proof:** after any amendment, the PG entry revision reflects the correction (not just the KG).
- **No-resurrection proof:** a KG rebuild of the amended revision does NOT re-create the superseded fact — the
  test that would have caught today's `memory_forget` lie.
- **Recall reflects it:** temporal recall returns the corrected/current value; "it changed" for a supersede.
- **Epoch:** recall defaults to the current epoch; the old epoch's facts carry `valid_until`.

## 7. Open questions for the human (before/at build)
- **Q-a — amend UX vs. re-distill:** does "correct a memory" edit the entry text in place (leg 1 = a manual
  revision), or re-run the distiller on a corrected transcript? Recommend **in-place revision** (cheaper, no LLM,
  and the user's correction is authoritative) with re-index handling leg 2/3.
- **Q-b — confirm the P-12 fold:** OK to move forget-person cascade + epoch-purge into P-12's erasure worker
  (this plan's §4 recommendation), rather than build three cascades now?
