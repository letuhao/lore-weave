# Plan — Enrichment review UI + book-scoping (2026-06-03)

> Branch `lore-enrichment/foundation`. Size **XL** (full-stack: additive backend
> migration + new FE feature + e2e + Suite C). Not legal advice — the ④ gate is a
> reputational/IP-safety layer; release still needs counsel.

## Corrected domain model (locked with PO)

- **`project_id` is a GENERAL scope** (knowledge-service notion) — a project may
  exist with no book at all. NOT the book anchor.
- **Enrichment is a BOOK-bound feature** — its GUI lives inside the book workspace
  (beside Glossary), so **`book_id` is ALWAYS present** when enriching. The backend
  simply never persisted it (the gap). `book_id` is the natural primary anchor;
  `project_id` is a secondary dimension.
- A book's enrichment *may* span multiple general `project_id`s → offer a **project
  filter/picker**, but only when >1 is actually present.

## Backend (additive, low-risk — this branch IS the enrichment workstream)

Join approach (minimal): `book_id` on `enrichment_job` only; proposals filter via a
join. Runner / `build_proposal_fields` / resume-worker request **untouched**.

1. **Migration** (`app/db/migrate.py`): `ALTER TABLE enrichment_job ADD COLUMN IF
   NOT EXISTS book_id UUID;` (nullable, same idempotent pattern as canonical_name)
   + `idx_enrichment_job_book ON enrichment_job(user_id, book_id, created_at DESC)`.
   Down-migration unchanged (column drops with the table).
2. **Persist** (`app/jobs/proposal_store.py`): `create_job(..., book_id: str|None=None)`
   on the Protocol + Pg (`INSERT ... book_id`) + InMemory stores.
3. **Wire create-paths**: `api/jobs.py` `create_job` → pass `book_id=str(body.book_id)`;
   `api/gaps.py` `auto_enrich` → pass `book_id=str(body.book_id)`.
4. **List by book_id**:
   - `services/review.py` `ProposalsRepo.list(book_id: UUID|None=None)` — conditional
     `JOIN enrichment_job j ON j.job_id = p.job_id` + `j.book_id = $n`; columns
     `p.`-prefixed to avoid ambiguity. `ProposalRow`/`as_dict` unchanged (book_id is a
     filter, not echoed — the FE already knows the book; each proposal still carries
     its own `project_id` for per-proposal actions).
   - `api/proposals.py` `list_proposals`: add `book_id: Optional[UUID]`, make
     `project_id` Optional, require ≥1 (400 otherwise). Back-compatible.
   - `api/jobs.py` `list_jobs`: add `book_id` filter (project_id optional, ≥1);
     `_job_row` echoes `book_id`.
5. **GUI default**: GUI-initiated detect-gaps/auto-enrich pass `project_id := book_id`
   (the book's default enrichment scope). Real general-project selection = DEFERRED.
6. **Tests**: book_id persisted on job; list-proposals by book_id returns the book's
   rows across project_ids; list-jobs by book_id; project_id-only still works.

## Frontend (`features/enrichment/`, book-scoped — React-MVC)

Per the locked architecture doc (`design-drafts/enrichment-ui-architecture.md`):
- **Tab**: `pages/book-tabs/EnrichmentTab.tsx` (mirrors GlossaryTab/WikiTab) →
  registered in `BookDetailPage.tsx` `tabs` array after `/glossary`; rendered in
  `BookTabContent` with the `visited`+`display:none` no-unmount idiom.
- `api.ts` (book-scoped calls via `apiJson`), `types.ts`, `context/EnrichmentContext`,
  hooks (`useProposals`/`useProposalActions`/`useGaps`/`useEnrichmentSources`/
  `useEnrichmentJobs`), components (`EnrichmentView` + `ProposalsPanel`/`ProposalList`/
  `ProposalCard`/`ProposalDetail`/`DimensionList`/`VerifyPanel`/`ProvenancePanel`/
  `ProposalActionBar`/`PromoteDialog`/`H0Marker`/`TechniqueBadge`/`VerifyBadge` +
  `GapsPanel`/`SourcesPanel`/`JobsPanel`).
- **Project picker** = client-side filter chip over the book-scoped list, shown only
  when distinct `project_id`s > 1 (no extra endpoint).
- **Render sources**: `content` (per-dimension summary) + `provenance_json.dimensions`
  (the 历史/地理/文化… map) + `provenance_json.canon_verify` (verify flags) +
  `source_refs_json` (grounding/license). The ④ PromoteDialog spells out H0 + author
  responsibility.
- **i18n**: `detail.tabs.enrichment` + an `enrichment` namespace across en/vi/ja/zh-TW.

## e2e (Playwright)
Login test user → book → Enrichment tab → review a P2/P3 proposal → **Promote** →
assert it became glossary canon (the real ④ flow). Needs a seeded passing eval-gate
row (Mode-A) + LM Studio gen+embed to have produced proposals.

## Suite C (backend robustness, parallelisable)
injection / contradiction / anachronism / regurgitation TRUE-positive auto-reject,
live (gen+embed loaded) — proves C12/C3 + ③ fire on real egregious input.

## Deferred
- **D-ENRICH-PROJSEL** — real general-project selection at enrich time (pick an
  existing knowledge-service project instead of `project_id := book_id`). v1 uses the
  book-default scope; the picker already handles >1 if external tools create others.
- Backfill `book_id` on pre-existing demo jobs (NULL → invisible under book filter).
  v1 re-runs enrichment to produce book-tagged rows; backfill is optional.
