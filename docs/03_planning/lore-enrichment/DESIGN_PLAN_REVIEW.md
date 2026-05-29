# Lore-Enrichment — DESIGN + PLAN Review (adversarial)

> **Date:** 2026-05-30 · **Reviewer perspective:** Lead + adversary (find what's wrong before BUILD).
> **Scope:** [SERVICE_DESIGN.md](SERVICE_DESIGN.md) v2 · [PLAN.md](PLAN.md) · [CYCLE_DECOMPOSITION.md](../../plans/2026-05-30-lore-enrichment/CYCLE_DECOMPOSITION.md) · [OPEN_QUESTIONS_LOCKED.md](../../plans/2026-05-30-lore-enrichment/OPEN_QUESTIONS_LOCKED.md).
> **Verdict:** Plan is structurally sound and the bottom-up correction was right, BUT 3 HIGH correctness gaps must be resolved before RAID runs (they invalidate the write-back path / scoping as currently written).

---

## HIGH — must resolve before/early in BUILD

### H1 — Write-back → KG propagation is NOT automatic (Q2 is wrong as written)
Q2 says: write canonical via glossary `extract-entities` → `glossary_sync` propagates to Neo4j. **Verified:** `bulkExtractEntities` emits **no event**; `glossary_sync.py` docstring says propagation is driven by **worker-ai `scope='glossary_sync'` jobs** / a startup reconciler / a *future* K14 event pipeline — i.e. **not triggered by the write itself**. → enriched entities would land in glossary but **not reach the KG layer** until an out-of-band sync runs.
- **Fix:** after write-back, enrichment must explicitly trigger the glossary→Neo4j sync (enqueue the worker-ai `glossary_sync` job, or call the internal sync endpoint C12c-a referenced in the docstring). Amend Q2 + add a sub-task to C10. Verify the exact trigger mechanism in C1.

### H2 — Scoping conflict: per-user/project enrichment vs shared glossary SSOT (Q3 unverified)
Q3 locks **per-user/project**, but enrichment writes **canonical** entities to glossary. The `glossary_sync` comment says "glossary entities are **shared across a user's projects** when the underlying book is shared." Glossary entity scoping (per-user? per-book? per-project?) **could not be verified** (migrations not at the expected path). If glossary is book-level/shared, per-user enrichment writing canonical entities risks **cross-user/project contamination** of the authored SSOT.
- **Fix:** verify glossary entity ownership model (C1 / PRE_FLIGHT). Likely resolution: enriched content stays in **enrichment's own per-project proposal store**; only human-**approved** items promote to glossary, written with the correct ownership/scope. Make "what scope does an approved entity get" an explicit locked answer.

### H3 — No renderer for rich wiki content (the "feeds existing machinery" claim is half-wrong)
**Verified:** glossary `generateWikiStubs` only inserts **empty-body** stub articles. Rich wiki **content** generation (knowledge-service D4-03 "wiki-from-KG") is **planned, likely unbuilt**. → enrichment's wiki output has **no existing renderer**.
- **Fix:** decide scope — either (a) enrichment **owns** wiki-body generation (write full article body via glossary wiki write, not just stubs), or (b) explicitly depend on D4-03 and confirm it exists. Default to (a) for the demo. Update SERVICE_DESIGN §2/§3 and DESIGN v2's "feeds wiki-generation" note.

## MEDIUM — design soundness

- **M1 — Gap-detection is underspecified (and it's the core novel value).** "graph-stats + templates → gaps" glosses the hard part: the canonical **dimension set per entity-kind**, how partial coverage is detected, and gap **ranking**. Recommend a short design spike before C4 (or split C4 into C4a *gap model/spec* + C4b *engine*). This is the product's crux — under-specifying it is the biggest risk.
- **M2 — Canon-verify can't verify correctness, only contradiction.** Filling a gap means there is no canon to check against; verify can detect *contradiction* + *anachronism* but not *truth*. Cultural-faithfulness needs external corpora actually loaded. State verify's real scope explicitly; rely on provenance + human gate for correctness. Avoid false-confidence framing.
- **M3 — Output language unaddressed.** Multilingual platform, Chinese source — what language is enriched lore written in (per-user locale? book locale?)? Add to locked questions. knowledge-service already regenerates summaries per `users.preferred_locale` — align.
- **M4 — Cross-service code reuse may not be importable.** "Reuse knowledge-service injection-defense + CJK splitting" assumes they're a shared Python package (`loreweave_extraction`?). If service-internal, enrichment can't import them → must extract to a shared lib or reimplement. Verify in C1/C7/C9; affects effort.
- **M5 — Eval-harness cost not in the cost model.** Per-proposal adversarial multi-check (C12) can balloon LLM cost; the cost-cap currently scopes technique generation, not eval. Fold eval cost into the per-job cap.
- **M6 — No idempotency / re-run dedup / retraction.** Re-running a job could duplicate proposals; no defined path to retract an approved-but-wrong enriched entity. Glossary has `recycle_bin_handler` — leverage it. Specify dedup (against existing glossary + open proposals) and rollback.

## LOW — plan / sizing / hygiene

- **L1 — Decomposition is largely serial** (C4→C5→C6→C7→C8→C9→C10→C11 is a chain) → limited DPS parallelism, blunting RAID's throughput advantage. Parallelizable: {C1,C2,C3} after C0; {C13,C14}; C15 alongside C12+. Acknowledge and exploit.
- **L2 — Uneven cycle sizing.** C8 (gen + repair + provenance), C10 (review API + write-back + sync-trigger), C11 (orchestration + events + cost-cap) are heavy; C3 is light. Consider splitting the heavy ones at brief time.
- **L3 — Port 8093/8217 unverified free** (knowledge=8092/8216 adjacent). Confirm in PRE_FLIGHT.
- **L4 — Doc path errors:** actual write API is `POST /internal/books/{book_id}/extract-entities` (behind `requireInternalToken`), not `/books/...`; wiki route is `generateWikiStubs` (confirm exact path). Fix CLARIFY/DESIGN/PLAN strings.

## What's solid (keep)
- Bottom-up correction (knowledge-service is real) — prevented building a duplicate extraction pipeline. Highest-value decision.
- Reuse-infra mapping (confidence/quarantine, pending_facts pattern, job state machine, per-project embedding) is sound.
- Phased-by-cost rollout + human-gate-first + provenance/confidence is prudent and differentiated.
- 16-cycle bottom-up, evidence-gated structure is RAID-appropriate.

## Recommended actions before `/raid`
1. **Amend OPEN_QUESTIONS_LOCKED** for H1 (explicit sync trigger), H2 (approved-entity scope), H3 (enrichment owns wiki body), M3 (output language). 
2. **Add C1 verification sub-tasks**: confirm glossary scoping, the glossary→Neo4j sync trigger, and whether injection-defense/CJK are importable.
3. **Split C4** into gap-model spec + engine (M1).
4. Fix doc path strings (L4); confirm port (L3).

---

## Resolution status (2026-05-30 — applied)

- **H0 (NEW — core invariant, raised by author):** enriched ≠ canon, source_type='enriched'+quarantine, author-promote-only, permanent origin marker. → **LOCKED** in OPEN_QUESTIONS_LOCKED H0; baked into SERVICE_DESIGN principle #3 + data model; enforced in C2/C11/C13.
- **H1 (sync) → RESOLVED by building K14 event pipeline** (C4) — automatic glossary→KG propagation, platform-wide.
- **H2 (scoping) → C1 verification sub-task** + H0 resolves contamination (enriched stays quarantined, not canon, until promote).
- **H3 (wiki renderer) → RESOLVED by building D4-03 wiki-from-KG** (C5).
- **M1 (gap-detection) → split into C6 (gap-model spec) + C7 (engine).**
- **M2 (canon-verify limits) → C12 scoped to contradiction+anachronism;** correctness rests on human gate.
- **M3 (output language) → added to locked defaults** (align to `users.preferred_locale`, as knowledge-service does). *(confirm exact locale source in C6.)*
- **M4 (importability) → C1 verification sub-task.**
- **M5 (eval cost) → folded into C14 cost-cap.**
- **M6 (idempotency/retraction) → C13 retraction via glossary recycle-bin;** dedup against existing glossary + open proposals.
- **L1 (serial) → parallelism note added** ({C1,C2,C3}; platform {C4,C5}∥core; {C16,C17}; C18).
- **L2 (sizing) → split at brief time** (C6/C7 split done).
- **L3 (port) → PRE_FLIGHT item.** **L4 (paths) → corrected** (`/internal/books/{book_id}/extract-entities`; wiki = `generateWikiStubs`→replaced by D4-03).
- **Scope:** task raised XL → **XXL** (19 cycles C0–C18) by pulling in K14+D4-03 (Option B). `task_config.py validate` → exit 0.
