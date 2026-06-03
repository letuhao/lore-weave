# LOOM — Track Charter & Session Handoff

> **Track:** **LOOM** — the lore-grounded **co-writer** + its **Canon Model** foundation.
> **Last updated:** 2026-06-04 · **Branch:** `feat/composition-service` · **HEAD:** CM1+CM3a (see latest commit) · **Session:** LOOM-02 (CM1+CM3a built)
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

## ✅ CM1 DONE (LOOM-01, 2026-06-04) — book-service editorial lifecycle
Shipped (book-service only, additive): `chapters.editorial_status` (draft|published) + `published_revision_id` (FK ON DELETE SET NULL) + `canon_model_migration` marker table + marker-gated one-time `backfillSQL`; `publishChapter`/`unpublishChapter` handlers + routes; `chapter.published{book_id,chapter_id,revision_id}` / `chapter.unpublished` events; import → published + pinned revision; editorial fields on `getChapterByID` + `getInternalBookChapter`. 12-phase v2.2 + `/amaw`: design adversary R1 BLOCK→R2 APPROVED_WITH_WARNINGS, code adversary R1 APPROVED_WITH_WARNINGS — all folded (down-migration gate, publish RETURNING+FOR UPDATE, import NULL-pointer + error-check, marker-gated backfill, stable tiebreak). `go build` + `go test` (migrate/api/config) green. CLARIFY PO: import=published · /unpublish ships · edit-after-publish stays published · always-snapshot · publish-empty→404 · no in_review.

## ✅ CM3a DONE (LOOM-02, 2026-06-04) — internal revision-text endpoint
Shipped (book-service only): `GET /internal/books/{book_id}/chapters/{chapter_id}/revisions/{revision_id}/text` under `requireInternalToken`; IDOR-guarded (`rv.id+rv.chapter_id+c.book_id+lifecycle=active` → cross 404); plain-text projection (`->>'_text'`, ordered, null-safe). 12-phase v2.2 (S, self-review) + **/review-impl** (0 HIGH; folded MED-2 caller-gate contract comment, LOW-2 trim `body` from response, MED-1 tightened the live-smoke to require the IDOR-negative case; accepted LOW-1 body_format='json' / LOW-3 projection-swallow). `go build`+`go vet` green. **Contract:** serves ANY revision by id — canon=published depends on CM3b passing `chapters.published_revision_id`.

## ▶ NEXT SESSION (LOOM-03)
**CM2 — worker-infra relay confirm (no-op)** then **CM3b** (the load-bearing one). `/loom CM2` then `/loom CM3b`.
- **CM2:** verify `chapter.published`/`chapter.unpublished` reach `loreweave:events:chapter` (relay is generic by `aggregate_type` — `outbox_relay.go:149-205`; expect zero code change, just confirm). Quick.
- **CM3b** (⚠️ `/amaw` — the cutover): knowledge `chapter.published`→queue `extraction_pending`(+revision_id col); worker-ai **per-project coalescing drainer** (respect the one-active-job/project unique index — NO job-per-event), single-chapter scope, fetch pinned revision via **CM3a's endpoint**; **wire `remove_evidence_for_source`+`cleanup_zero_evidence` before re-extract** (canon-drift fix, closes D-CM1-UNPUBLISH-RETRACT on `chapter.unpublished`); fix B7 chat-drainer `aggregate_type` filter. See plan §8.2/§8.3 CM3b.
- Then CM3c → CM4 → CM-FE → CM5.

## Deferred / watch
- **D-CM1-UNPUBLISH-RETRACT** — `/unpublish` flips status but does NOT retract already-extracted KG facts; **CM3b** wires `remove_evidence_for_source` on `chapter.unpublished`. Until then: temporary canon drift on unpublish.
- **D-CANON-CYCLE0-LIVE-SMOKE** — book-service has no DB-backed Go test harness; CM1 publish/unpublish tx + backfill one-time property + NULL-pointer scan + **CM3a revision-text endpoint** are string/build-tested only → need a live-smoke at stack-up, OR keep deferred. **Required assertions:** publish→revision pinned→event; re-publish; backfill double-run; unpublish; **CM3a: revision-text returns the published revision's text AND a cross-book/cross-chapter revision_id → 404 (the IDOR-negative, review-impl MED-1 — not just happy path).** (Also CM3b proves publish→extraction end-to-end.)
- L5 long-term-summary lens (no HTTP read endpoint) — future knowledge surface.
- `chronological_order` quality for non-ISO in-world dates — extraction-quality follow-up; reading-order is the fallback.
- Composition V1/V2 (branches/takes, autonomous loop, consistency sweep, 同人) — post-V0.
