# Enrichment UI — component architecture (proposal)

> Review the two HTML mockups first: `enrichment-review.html` (the ④ author
> approval/promote screen — the core + what the e2e drives) and
> `enrichment-gaps-sources.html` (the trigger side). This doc is WHERE the code goes
> and WHAT each piece is. Follows the repo's React-MVC rules (hooks=logic,
> components=view, context=shared state, api.ts=API, types.ts=types) and the existing
> `features/glossary/` pattern.

## Where it plugs into the app — DECIDED: a book-workspace TAB (not a sidebar item)
Enrichment is per-book + book-owner (review proposed lore for THIS book → promote
into THIS book's glossary canon). The two most analogous features — **Glossary and
Wiki** — are ALSO book tabs (`pages/BookDetailPage.tsx:20-27`), NOT sidebar items;
the sidebar holds only cross-book/global surfaces (Books/Chat/Knowledge/Browse). A
sidebar entry would force a context-switch away from the book mid-edit. So:

- **Tab registration** (`pages/BookDetailPage.tsx`): add
  `{ key: '/enrichment', labelKey: 'detail.tabs.enrichment' }` to the `tabs` array
  **right after `/glossary`** (it feeds glossary canon), and render
  `<EnrichmentTab bookId={bookId} />` in `BookTabContent` using the same
  `visited` + `display:none` no-unmount idiom the other tabs use.
- **Tab entry**: `pages/book-tabs/EnrichmentTab.tsx` — mirrors `GlossaryTab`/`WikiTab`;
  a thin wrapper that mounts `EnrichmentProvider` + the feature shell (`EnrichmentView`).
- **Route**: `/books/:bookId/enrichment` (URL-suffix, same scheme as `/glossary`,
  `/wiki`). No new top-level route, no gateway change (`/v1/lore-enrichment/*` already
  proxied).
- **i18n**: add `detail.tabs.enrichment` to `books.json` in all 4 locales
  (en/vi/ja/zh-TW); feature strings under a new `enrichment` namespace.
- **Reuse shared components**: the **book's** `PageHeader` is already there (the tab
  renders below it); reuse `StatusBadge`, `ConfirmDialog`, `FilterToolbar`,
  `EmptyState`, `AttrCard` idiom — do NOT reinvent. The mockup's 4 panels become a
  **secondary tab strip inside** the Enrichment tab (same nesting Glossary uses).

## File layout — `frontend/src/features/enrichment/`
```
features/enrichment/
  api.ts          — enrichmentApi (all /v1/lore-enrichment calls via apiJson)
  types.ts        — Proposal, ReviewStatus, Technique, VerifyStatus, VerifyFlag,
                    Gap, Source(+license), Job, Provenance
  context/
    EnrichmentContext.tsx   — book scope (bookId) + selectedProposalId + activePanel
                              (stable); volatile vs stable split per the re-render rule
  hooks/                    — "controllers": own logic + react-query, no JSX
    useProposals.ts         — list proposals (filters: status/technique/verify) + getOne
    useProposalActions.ts   — beginReview / approve / promote / reject / edit / retract
                              (mutations + invalidate + sonner toast); author-only guard
    useGaps.ts              — detectGaps + autoEnrich (enqueue background job)
    useEnrichmentSources.ts — list / register / ingest corpus
    useEnrichmentJobs.ts    — poll job status (resume-worker)
  components/               — "views": render only, data via props/context
    EnrichmentView.tsx      — feature shell: H0 chip + secondary tab strip
                              (Proposals/Gaps/Sources/Jobs). The book's PageHeader is
                              already above it, so this owns only the inner strip + body.
    ProposalsPanel.tsx      — two-pane: ProposalList (left) + ProposalDetail (right)
    ProposalList.tsx        — FilterToolbar + scrollable list of ProposalCard
    ProposalCard.tsx        — one summary: entity · TechniqueBadge · StatusBadge ·
                              VerifyBadge · H0Marker · content preview (line-clamp)
    ProposalDetail.tsx      — full view: H0Banner + DimensionList + VerifyPanel +
                              ProvenancePanel + ProposalActionBar
    DimensionList.tsx       — per-dimension generated lore (历史/地理/文化/…) in AttrCards
    VerifyPanel.tsx         — contradiction/anachronism/injection/regurgitation results
                              (✓ clean or flag evidence); reads canon_verify provenance
    ProvenancePanel.tsx     — grounding sources (+license badge), recook attribution (②),
                              technique/model_ref, origin/confidence
    ProposalActionBar.tsx   — Promote / Approve / Edit / Reject (author-only); sticky
    PromoteDialog.tsx       — ConfirmDialog wrapper: the ④ gate (promote→canon, H0 note)
    H0Marker.tsx            — the "dị bản · enrichment" chip (reused in card + detail)
    TechniqueBadge.tsx      — P1 retrieval / P2 fabrication / P3 recook pill
    VerifyBadge.tsx         — verified_clean / needs_review / quarantined / degraded /
                              auto_rejected pill (maps to StatusBadge variants)
    GapsPanel.tsx           — detected-gaps table + auto-enrich config (technique/model/
                              cost-cap) → enqueue
    SourcesPanel.tsx        — corpus cards (license badge, recook-OK/refused) + register
    JobsPanel.tsx           — job list + status + resume
```
> Book-tab entry lives OUTSIDE this dir: `pages/book-tabs/EnrichmentTab.tsx`
> (mirrors `GlossaryTab`/`WikiTab`) → mounts `<EnrichmentProvider><EnrichmentView/></…>`.

## Component inventory — what each is (one-liners)
| Component | Role |
|---|---|
| `EnrichmentTab` (book-tab entry) | thin wrapper: mounts provider + `EnrichmentView` |
| `EnrichmentView` | feature shell: secondary tab strip + H0 chip; owns only layout |
| `ProposalsPanel` | the review workspace (list ⇄ detail) — the e2e target |
| `ProposalCard` | scannable summary; click → select (no unmount, CSS-driven) |
| `ProposalDetail` | the full draft + the ④ action bar |
| `VerifyPanel` | surfaces C12/C3 + regurgitation(③) results → trust signal |
| `ProvenancePanel` | source/license/attribution → the ©-safety story is visible |
| `PromoteDialog` | the explicit author act (④) — confirm copy spells out H0 + responsibility |
| `H0Marker` / `TechniqueBadge` / `VerifyBadge` | the small, reused trust chips |
| `GapsPanel` / `SourcesPanel` / `JobsPanel` | the trigger + corpus + job-status surfaces |

## Data flow (per the rules)
- `EnrichmentContext` holds `bookId/projectId`, `selectedProposalId`, `activeTab`
  (stable) — split any streaming/job-poll state into a volatile context if added.
- Hooks own all react-query + mutations + toasts; components receive data + callbacks.
- No `useEffect` for actions (promote/approve are explicit handlers, per the rule).
- Auth token via `useAuth()`; calls via `apiJson('/v1/lore-enrichment/...', {token})`.

## Decisions (RESOLVED 2026-06-03)
1. **Placement** → **book-workspace TAB** (after Glossary), NOT a sidebar item.
   Rationale: enrichment is per-book + book-owner; Glossary/Wiki (the analogues) are
   tabs; a sidebar entry breaks the in-book edit→review flow. (See top section.)
2. **Scope of v1** → **FULL** — all 4 panels (Proposals/Gaps/Sources/Jobs) now. The
   review/promote gate (④) is the load-bearing copyright-safety layer, so it ships
   complete, not partial.
3. **i18n** → **YES** — labels via existing i18n; `detail.tabs.enrichment` +
   `enrichment` namespace across en/vi/ja/zh-TW.
