# Cycle 11 — Pending Proposals inbox (FE) — live smoke evidence

## Live Playwright smoke: RESOLVED (D-C11-INBOX-LIVE-SMOKE)

Date: 2026-06-15. Stack UP (gateway :3123, FE :5174 prod build, glossary :8211,
knowledge :8216). Logged in as `claude-test@loreweave.dev`.

**Token:** `live smoke: proposals inbox aggregates 3 review queues read-only +
deep-link navigates`

### What ran

Opened the C6 project-detail shell **Proposals** sub-tab for a project on book
`019eb60e-9f37-7198-b512-b526f1969ab9` (万古神帝) — route
`/knowledge/projects/{projectId}/proposals`. The inbox is **book-scoped** (G6:
`bookId = project.book_id`), so it renders identically for any project on that
book; used derivative project `019ec734-3f0d-7c37-b777-ab6112a68fdd` (the
original `019eb683-…` project is no longer in the test user's project list — only
4 dị bản projects on this book remain, all book `019eb60e`).

### The unified inbox rendered all 3 source groups (screenshot `inbox-live.png`)

| Source group | Count | Rows | Per-origin label | Deep-link |
|---|---|---|---|---|
| **Glossary AI drafts** | **3** | 紫怡偏殿 · 玉漱宫 · 九天明帝经 | "Glossary draft" | `/books/019eb60e-…/glossary` |
| **Wiki suggestions** | **1** | 池瑶 ("AI regeneration") | "Wiki edit" | `/books/019eb60e-…/wiki` |
| **Lore-enrichment proposals** | **0** | — graceful empty-state | — | `/books/019eb60e-…/enrichment` |

**2 sources populated + 1 gracefully empty** → exercises BOTH populated rows AND
graceful-degrade in one run. The enrichment group is a healthy-but-empty source
(`GET /v1/lore-enrichment/proposals?book_id=…&review_status=proposed|author_reviewing`
both return **200, 0 items**) — it shows the per-group empty copy
*"No pending proposals. New AI suggestions will appear here as they're produced."*
WITHOUT blanking the inbox or erroring. The two populated groups still render in
full alongside it (graceful per-source degrade confirmed).

### Deep-link navigation (screenshot `inbox-deeplink-landing.png`)

Clicked the **紫怡偏殿** glossary-draft row → navigated to
`/books/019eb60e-9f37-7198-b512-b526f1969ab9/glossary` — the book's existing
Glossary review surface (the "AI suggestions **3**" review badge + entity list).
The inbox is read-only: rows are `<Link>` navigations into each source's OWN
review UI, no accept/reject/edit control in the inbox itself. **Deep-link
navigates: confirmed.**

### Seed note (data setup via an existing production endpoint, NO feature-code change)

The 3 ai-suggested glossary entities (九天明帝经, 紫怡偏殿, 玉漱宫) had been
promoted to `status=active` by later cycles (C9/C10/C24), so the source filter
`status=draft & tags=ai-suggested` returned 0 at smoke time. To restore the
draft-review precondition that C11's glossary source consumes, they were flipped
`active→draft` via the existing `POST /v1/glossary/books/{id}/entities/bulk-status`
production endpoint (the same activate/draft control the glossary UI uses), the
inbox was captured with rows, then they were **flipped back to `active`**
(verified 0 drafts remaining) — the book's data is left exactly as found. No
feature code was modified.

### Console

No errors originating from the inbox render or the deep-link nav. (Pre-existing
unrelated noise: a `notifications/stream` 500 SSE; plus 401/404 entries from this
session's own exploratory `fetch` probes using a cookie-credential and a
wrong-guessed `/v1/enrichment/…` path — the real FE path `/v1/lore-enrichment/proposals`
returns 200.)

## Unit evidence (still valid — 11 vitest green)

`proposalsInbox.test.ts` (6) + `ProposalsInboxTab.test.tsx` (5): 3-source merge,
exact per-source filters (glossary `status=draft&tags=ai-suggested`, wiki
`status=pending`, enrichment two exact-match `review_status` calls), graceful
degrade, route-scoping (G6 bookId from `project.book_id`), read-only `<Link>`
rows. `verify-cycle-11.sh` exit 0.
