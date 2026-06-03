# LOOM — Track Charter & Session Handoff

> **Track:** **LOOM** — the lore-grounded **co-writer** + its **Canon Model** foundation.
> **Last updated:** 2026-06-03 · **Branch:** `feat/composition-service` · **HEAD:** `bad7acda` (design-checkpoint) · **Session:** LOOM-00 (design-lock)
> **Workflow:** 12-phase **v2.2 human-in-loop** (PO checkpoint at CLARIFY-end + POST-REVIEW). `/amaw` **opt-in** for: CM1 (schema/migration), CM3 (cross-service contract cutover), composition M1 (schema), M5 (authz/isolation).
> **Isolated from** the `lore-enrichment/*` track — LOOM **never touches `services/lore-enrichment-service/`** (siblings, not deps).

## What LOOM is
The name = LoreWeave's **loom**. The **Canon Model** is the **warp** (the fixed structural threads: *published* canon, in-world/reading order, provenance); the AI **co-writer** weaves the **weft** (new prose) through it. Spoiler-safety = you can only weave with threads already laid down (no future-canon leak). LOOM turns a book into living canon, then co-writes grounded in it.

Two parts, built in order:
1. **Canon Model (Cycle 0, prerequisite)** — fixes pre-existing platform bugs B1–B7 that composition surfaced (NOT composition scope). 4 primitives: editorial lifecycle · canon=published · dual-order populated · provenance (aligned with enrichment H0, no enrichment edits).
2. **Composition (V0)** — lore-grounded co-writer + visual planning, built on the Canon Model.

## Design SSOT (locked 2026-06-03, commit `bad7acda`, after 4 adversarial review rounds)
- Canon Model: [spec](../../specs/2026-06-03-canon-model.md) · [Cycle-0 plan](../../plans/2026-06-03-canon-model-cycle0.md) (§8 = corrected/authoritative)
- Composition: [design](../../specs/2026-06-02-composition-design.md) (§12 contract-review, §13 ops-benchmark) · [V0 plan](../../plans/2026-06-02-composition-service-v0.md)

## Locked decisions
- Full **event-driven** extraction rework (coalescing per-project drainer over `extraction_pending`, respects the one-active-job/project index; retract-before-reextract; pinned-revision).
- **canon = published** (extract on `chapter.published` at the pinned revision; `chapter.saved` no longer canonizes).
- **CM-FE (publish UI) in Cycle 0** (else KG/passages stale platform-wide).
- **chapter-gate publish** — composition publishes a chapter only when ALL its scenes are `status='done'`.
- **dual-order:** reading-order (`event_order` from `sort_order`) is the dense V0 spoiler axis; `chronological_order` (from `event_date_iso`) is best-effort/sparse for CJK corpus.
- **enriched-lens deferred** to composition's final phase (glossary has no structured enrichment-content read yet).
- Boundary: touches book/worker-infra/knowledge/worker-ai/SDK + FE; **lore-enrichment never**.

## Build order
**Cycle 0 (Canon Model):** CM1 (book lifecycle + `/publish` + migration) → CM3a (revision_id event + internal revision-text endpoint) → CM2 (relay confirm — no-op) → CM3b (knowledge queue + worker-ai coalescing drainer + pinned-revision + retract-before-reextract + B7 fix) → CM3c (passage-ingest + manual-rebuild gating) → CM4 (dual-order + backfills) → CM-FE (publish affordance) → CM5 (provenance).
**Then Composition V0:** M0 skeleton → M1 schema → M2 repos → M3 clients/prose-source → M4 packer → M5 isolation → M6 engine+critic → M7 contract+gateway → M8 FE tab → M9 OI-1 publish wiring.

## ▶ NEXT SESSION (LOOM-01)
**Start CM1 — book-service editorial lifecycle** (12-phase v2.2; `/amaw` for the schema/migration). CLARIFY first (PO checkpoint at end):
- `chapters.editorial_status` (`draft`|`published`; drop `in_review` — YAGNI) + `published_revision_id` (FK ON DELETE SET NULL).
- Migration backfill: existing chapter → `published` + pointer=latest revision; revision-less chapter stays `draft`.
- `POST …/publish` (idempotent, `draft_version`-guarded, emits `chapter.published {book_id,chapter_id,revision_id}` in-tx).
- Verify gate: migrate up/down/up clean; publish snapshots a revision + emits event; backfill proven.

## Deferred / watch
- L5 long-term-summary lens (no HTTP read endpoint) — future knowledge surface.
- `chronological_order` quality for non-ISO in-world dates — extraction-quality follow-up; reading-order is the fallback.
- Composition V1/V2 (branches/takes, autonomous loop, consistency sweep, 同人) — post-V0.
