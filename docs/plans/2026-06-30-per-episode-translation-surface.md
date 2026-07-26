# Per-episode translation surface (KAL §7 read) — implementation plan

**Branch:** feat/temporal-knowledge-architecture · **Date:** 2026-06-30
**Spec:** `docs/specs/2026-06-29-incremental-temporal-knowledge-architecture.md` §6B (translation = bounded units keyed by validity) + §7.6 (FE temporal surface).
**Mandate:** production-ready, NO new defers (the branch must be usable everywhere on merge).

## Decision (CLARIFY)

The §7 "per-episode translation" surface shows the entity's **as-of-N folded canonical, translated on-demand into the reader's display language**, cached **immutable per (content, language)** ("translated exactly once" — §6B). Chosen over (a) name/aliases-only and (b) name+appearances. The user picked the on-demand LLM-translated snapshot.

**Language source:** the existing per-book display-language (`useGlossaryDisplayLanguage`, server-persisted under `glossary_display_lang_by_book`, already shared with the glossary browser + embedded chat). The Temporal tab reuses it → stays in lockstep with the glossary browser. When the selected language is the book's original/as-authored, the panel shows the **original** as-of canonical (no LLM call); only real target languages hit the translate path.

## Architecture (mirror of KG-TL M3)

Glossary owns `canonical_snapshot`, so it owns the translation cache — exactly as knowledge-service owns `:Event` text + its `event_text_translations` cache. The LLM call goes through **translation-service `/internal/translation/translate-text`** (→ `translate_text_core` → provider-registry; BYOK model resolved from the user's `user_translation_preferences`). Glossary never imports a provider SDK (provider-gateway invariant). KAL federates; the FE talks only to the KAL via the BFF.

Flow (user-mode): FE → BFF `/v1/kal/*` (JWT passthrough) → KAL (dual-auth + grant, pins `X-User-Id`) → glossary `/internal/.../canonical-translation` → (cache hit ⇒ return) | (miss ⇒ single-flight claim + background fill calling translation-service).

**Non-blocking read-through + FE poll** (robust, no long-held HTTP, single-flight prevents double-spend):
- `status: ready` → translated `content`.
- `status: translating` → original `content` + the FE polls (`refetchInterval` while translating).
- `status: failed` → original `content` + `error_code` (FE shows a friendly message; `no_model` → "set a translation model").
- `status: original` → selected lang is the source/as-authored ⇒ original canonical, no translate.
- `status: unbuildable` → canonical empty (degrade-safe).

**Tenancy:** the canonical snapshot is **book-tier** (shared, read-only to collaborators, written by the fold). Its translation is an equally book-tier derived artifact → the cache key is `(entity_id, attr_scope, language_code, source_content_hash)` (NO user_id in the key); `minted_by_user_id` is audit only. First authorized viewer mints; collaborators reuse ("exactly once"). Grant-gated at the KAL.

## Build layers

### L1 — glossary-service (Go)
1. **Migration 0050** `canonical_snapshot_translations` (PK above; `status pending|ready|failed`, `error_code`, `attempts`, `value`, `as_of_ordinal`, `book_id`, `minted_by_user_id`, ts). Register `{"0050_canonical_snapshot_translations", UpCanonicalSnapshotTranslations}` in `ledger.go`.
2. **`config.go`**: add `TranslationServiceURL` (env `TRANSLATION_SERVICE_URL`, optional — unset ⇒ snapshot translation returns `failed/unconfigured`, rest of service unaffected, mirrors `KnowledgeServiceURL`).
3. **`translation_client.go`**: `translateText(ctx, userID, text, srcLang, tgtLang) (string, errCode, httpStatus)` — POST to translation-service `/internal/translation/translate-text` with `X-Internal-Token`; dedicated `http.Client` with a long (~120s) timeout (LLM call); map 422→`no_model`, 402→`quota`, else→`provider`.
4. **`canonical_translation_handler.go`** + helper `getCanonicalContent` (refactor the snapshot read out of `internalGetCanonical`). `GET /internal/books/{book_id}/entities/{entity_id}/canonical-translation?as_of=&lang=`: entityInBook guard; fetch canonical; empty⇒unbuildable; require `lang` + `X-User-Id`; `content_hash = md5(content)`; cache lookup; single-flight claim (`INSERT … ON CONFLICT DO NOTHING`, re-claim `failed` while `attempts<budget`); background goroutine (`context.Background()` + timeout) fills via `translateText`, UPDATE to ready/failed.
5. **Route** in `server.go` internal group.
6. **Tests** (`canonical_translation_handler_test.go`): unbuildable, missing-lang 422, ready hit, pending passthrough, failed+error_code, claim idempotency (one fill), original short-circuit.

### L2 — KAL (TypeScript)
7. **`kal.v1.yaml`**: add the read path + `CanonicalTranslation` schema.
8. **`kal-read.controller.ts`**: `getCanonicalTranslation` under `KalAuthGuard`; `downstream.ts` glossary GET with `ctxFromReq` (pins `X-User-Id`); pass `as_of`+`lang`.
9. **Jest**: shape coercion + auth-guard coverage.

### L3 — BFF
No change (the new sub-path rides the existing `/v1/kal/*` proxy).

### L4 — FE
10. **`types.ts`** `CanonicalTranslation`; **`api.ts`** `getCanonicalTranslation`; **`hooks/useTemporalReads.ts`** `useCanonicalTranslation` (userId-prefixed key; `refetchInterval` while `translating`).
11. **`EpisodeTranslationPanel.tsx`** rewrite: `useGlossaryDisplayLanguage(bookId, bookOriginalLanguage)`; compact language selector (write-through the hook); if selected lang is original/as-authored ⇒ `useCanonical` (original), else `useCanonicalTranslation`; states original/translating/ready(+cached badge)/failed/unbuildable; remove the degrade pending-note.
12. **Tests** updated.

### L5 — wiring + verify
13. `infra/docker-compose.yml`: `TRANSLATION_SERVICE_URL` on glossary.
14. Build + test every layer; live-smoke the FE→BFF→KAL→glossary→translation chain with the test account's BYOK chat model.

## Invariants checked
- **INV-KAL**: new KAL read endpoint; glossary reads its OWN canonical (owner-allowed); translate-text is NOT a bi-temporal knowledge read ⇒ HTTP-surface lint clean.
- **Provider gateway**: LLM via translation-service→provider-registry only; glossary adds no provider SDK; `TRANSLATION_SERVICE_URL` is a service URL (like `BOOK_SERVICE_URL`), not a model/key config.
- **No hardcoded model**: model resolved from `user_translation_preferences`.
- **Tenancy**: book-tier cache, grant-gated, no user-mutable shared row.
