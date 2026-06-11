# Plan — D-WIKI-P2B-COST-ESTIMATE (wiki batch-regenerate cost estimate)

**Date:** 2026-06-11 · **Branch:** `wiki/phase2-change-control` · **Size:** L (cross-service)

## Goal
Show a precise `~N × $per_article ≈ $total` estimate in the wiki Generate dialog
(which the change-feed batch-regenerate opens), where N = the distinct selected
entities. PO: flat per-article × N (matches the cost model the budget-cap charges);
surfaced in the dialog only. Token-precise pricing stays D-WIKI-M6-PRECISE-COST.

## Cost basis
The only pre-flight number is knowledge-service config `wiki_gen_cost_per_article_usd`
(default 0.05) — the same flat estimate the orchestrator's budget gate charges, so
the shown estimate and the live `cost_spent_usd` agree. It is knowledge-owned and
must reach the FE via the glossary proxy (FE-only-talks-to-glossary invariant); no
duplication of the constant in glossary or the FE.

## Changes

### Backend — knowledge-service
- `app/routers/internal_wiki.py`: `WikiGenConfig{cost_per_article_usd: Decimal}` +
  `GET /internal/knowledge/wiki/gen-config` (internal-token, reads `settings`). Global
  (not book-scoped) — the value is a flat config.

### Backend — glossary-service
- `internal/api/knowledge_client.go`: `getWikiGenConfig(ctx)` → GET the knowledge
  endpoint, PROPAGATE status+body (mirrors `getWikiGenJob`; errors if knowledge unset).
- `internal/api/wiki_jobs.go`: `getWikiGenConfig` handler — `requireUserID` +
  `verifyBookOwner` (book in path, owner-gated like the sibling wiki proxies) → proxy.
- `internal/api/server.go`: register `r.Get("/gen-config", s.getWikiGenConfig)` under
  the book `/wiki` group.

### Frontend
- `features/wiki/types.ts`: `WikiGenConfig { cost_per_article_usd: number | string }`.
- `features/wiki/api.ts`: `getGenConfig(token, bookId)` → GET
  `/v1/glossary/books/{bookId}/wiki/gen-config`.
- `features/wiki/components/GenerateWikiDialog.tsx`: `useQuery` for the config (enabled
  when `open && isLlm` && have token+bookId); compute + render an estimate line under
  the spend-cap. **Regen mode** (N known): `~N × $x ≈ $total`. **Batch/fresh mode**
  (N unknown pre-flight): show the per-article rate only (`~$x per article`). Needs
  `bookId` passed into the dialog (currently it isn't) — thread it from `WikiTab`.
- i18n ×4 `wiki.json`: `gen.estimate.{forN, perArticle, loading}`.

## Tests
- Go (no DB): `getWikiGenConfig` client test (URL `/internal/knowledge/wiki/gen-config`
  + internal-token + body propagation), not-configured error, and a route-auth 401
  (mirrors `wiki_jobs_test.go`).
- Knowledge: a small endpoint test if the router test client is cheap; else rely on the
  glossary client test + live-smoke.
- FE vitest: GenerateWikiDialog renders `forN` estimate in regen mode and `perArticle`
  in batch mode; hidden for the deterministic (non-LLM) path.

## VERIFY
Cross-service (knowledge + glossary) → needs a live-smoke token, or
`LIVE-SMOKE deferred to D-WIKI-P2B-COST-ESTIMATE-LIVE-SMOKE`. go build/vet + glossary
api pkg + knowledge pytest + FE vitest/tsc + i18n parity ×4.

## Out of scope
Token-precise pricing (D-WIKI-M6-PRECISE-COST); a fresh-generation exact N (needs a
pre-flight entity count by kind).
