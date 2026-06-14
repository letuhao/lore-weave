# Cycle 11 — Pending Proposals inbox (FE) — smoke evidence

## Live Playwright smoke: DEFERRED — live infra unavailable

At VERIFY time the local stack was not bootable:

- `infra-api-gateway-bff-1`, `infra-glossary-service-1`, `infra-book-service-1`,
  `infra-frontend-1`, `infra-ai-gateway-1` — all `Exited (255)` (~15h prior).
- `infra-knowledge-service-1` — crash-looping (`Restarting (3)`); root cause is a
  startup DB-connection failure (`asyncpg.create_pool` → TargetServerAttributeNotMatched
  against its Postgres), an infra/db-bootstrap problem.
- No listener on the gateway (:3123), FE (:5174), or knowledge (:8216).

Bringing the stack up requires repairing a crash-looping knowledge-service DB
bootstrap — an infra escalation outside cycle-11 (FE-only) scope. The inbox's 3
sources (glossary · wiki · lore-enrichment) all live behind the gateway, which is
down, so an authenticated Playwright capture of populated rows + a deep-link
landing was not possible. Tracked as **D-C11-INBOX-LIVE-SMOKE**.

## Unit evidence standing in (11 vitest green, PowerShell runner)

`proposalsInbox.test.ts` (6) + `ProposalsInboxTab.test.tsx` (5):

- **3-source merge**: glossary AI-suggested drafts + wiki suggestions + lore-enrichment
  proposals merge into one list; each row carries its `origin` + the correct
  per-origin deep-link URL (`/books/{bookId}/glossary|wiki|enrichment`).
- **Exact source filters (LOCKED)**:
  - glossary → `listAiSuggestions` (encodes `status=draft&tags=ai-suggested`).
  - wiki → `listSuggestions` with `status='pending'` (the review queue — corrected
    from the prior partial's nonexistent article `status='stub'`).
  - lore-enrichment → `listProposals` fetched as TWO exact-match calls
    (`review_status=proposed` AND `review_status=author_reviewing`) — the BE filters
    review_status by exact equality, so a single `proposed|author_reviewing` would match neither.
- **Graceful degrade**: one source erroring (wiki 503) still renders the others +
  a per-source error chip; an empty-but-healthy source shows a per-group empty
  state; all-empty shows the global empty state.
- **Route-scoping (G6)**: bookId comes from the route project's `book_id`
  (`ProposalsInboxTab bookId={project?.book_id ?? null}` in the C6 shell); no-book
  state when unlinked; no project select-box.
- **Read-only**: rows are `<Link>` navigations only — no accept/reject/edit control
  in the inbox (integrate, don't duplicate; verify-cycle-11.sh grep-asserts this).

`verify-cycle-11.sh` exit 0. tsc + eslint clean. i18n parity across en/vi/ja/zh-TW (12 keys each).
