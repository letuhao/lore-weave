# Cycle 20 — World container (book-service) live-smoke evidence

**Date:** 2026-06-14
**Service:** book-service (Go/Chi) on :8205, rebuilt + `up -d` (fresh image, no stale false-green).
**Token:** `live smoke: create world → bible chapter exists (sort_order 0) → attach book → world lists books; null-world books unaffected`

## Stack
- book-service `/health` = 200 (rebuilt image, migration applied at startup).
- gateway :3123 `/health` = 200; auth login via `POST /v1/auth/login` (claude-test).
- DB `loreweave_book` on `infra-postgres-1`.
- NOTE: the NestJS gateway does not (yet) proxy `/v1/worlds` (FE wiring is C21, out of scope);
  the live-smoke calls book-service directly per the brief ("real API round-trip on a stacked-up book-service").

## Migration round-trip (real PG — up → down → re-up)
1. **up** (container startup): `worlds` table created; `books.world_id` = nullable, FK `ON DELETE SET NULL`;
   `chapters.is_bible` = NOT NULL DEFAULT false. Verified via `information_schema` + `\d worlds`.
2. **down** (`WorldsDownSQL` applied via psql): dropped `books.world_id` column BEFORE `worlds` table (FK ordering).
   Confirmed: `to_regclass('public.worlds') IS NULL` = t, `world_id` column gone = t. Clean, no orphaned FK.
3. **re-up** (container restart re-runs `migrate.Up`): `worlds` table back = t, `world_id` column back = t.
   Idempotent + reversible. **migration_roundtrip = true.**

## Live-smoke round-trip
1. **CREATE WORLD** `POST /v1/worlds {"name":"C20 Live Smoke World"}` → 201, `book_count=1`
   (the auto-provisioned bible book), `world_id=019ec675-66b2-7f10-b2de-233511dacfd0`.
2. **BIBLE CHAPTER** (SQL join on the world's bible book): exactly one chapter,
   `sort_order=0`, `is_bible=t` (hidden), title "World Bible", `lifecycle_state=active`.
3. **ATTACH BOOK** `POST /v1/worlds/{id}/books {"book_id":"019eb60e-…"}` (万古神帝) → 200.
4. **LIST WORLD BOOKS** `GET /v1/worlds/{id}/books` → total=2 (bible book + 万古神帝).
5. **NULL-WORLD BOOKS UNAFFECTED:** standard `GET /v1/books` library list still returns its normal
   total (72 active); world_id distribution across the owner = **2 with world_id set**, **275 standalone
   (world_id=NULL)** — standalone books behave exactly as before (no backfill, list filter unchanged).
6. **DELETE WORLD → SET NULL (not cascade):** `DELETE /v1/worlds/{id}` → 204; the attached book
   万古神帝 **survived** (`active`, `world_id IS NULL` = t, returned to standalone); world gone.
   No cascade book delete.
7. **OWNER-SCOPE:** `GET /v1/worlds/{random-uuid}` = 404 (no existence oracle); no-token list = 401.
8. **IDEMPOTENT bible chapter:** every `is_bible` book has EXACTLY one `sort_order=0` chapter
   (the HAVING <> 1 check returned zero rows) — no double-insert.

## Adversary M1 fix — re-smoke (post code-review)
Adversary found the auto-created "World Bible" *container book* leaked into the user's
normal library, `listWorldBooks`, and `book_count` (only the chapter was hidden, not its book).
Fix: added `books.is_bible` flag; bible book inserted with `is_bible=true`; excluded from
`listBooksByLifecycle`, world `book_count`, and `listWorldBooks`; `moveBookIntoWorld` refuses to
re-parent a bible book (`AND is_bible=false`). Re-smoke on a rebuilt image:
- Library total = **72 before AND after** world creation (bible book no longer leaks).
- New world `book_count: 0` (bible book excluded); after attaching 万古神帝, world list = **only 万古神帝** (total 1), bible book absent.
- Bible chapter still provisioned hidden at sort_order 0 (`chap_bible=t`, `book_bible=t`).
- Delete world → 204, attached book survives `active` (SET NULL intact).

## Result
All assertions pass. World grouping is additive, book-service-only; lore DBs untouched; existing
standalone books unchanged; world deletion SET-NULLs member books; bible chapter hidden at sort_order 0,
idempotent. verify-cycle-20.sh exits 0; migration round-trip clean on real PG.
