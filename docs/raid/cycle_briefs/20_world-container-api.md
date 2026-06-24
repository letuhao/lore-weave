# Cycle 20: World container — model + API (book-service)

## 🎯 TL;DR (30 seconds — TOP critical info)
- **Scope:** Add an **additive** world-grouping layer in **book-service**: a new `worlds` table (`id, owner_user_id, name, description`) + a **nullable `world_id` FK on `books`** (default NULL = standalone). CRUD for worlds + a **move-book-into-world** op (set/clear `books.world_id`) + list-books-in-world. **ARCH-REVIEW FIX (LOCKED):** on world creation, **auto-create a hidden "world bible" chapter at `sort_order 0`** in the world's bible book, so the chapter-keyed lore machinery (glossary `chapter_entity_links.chapter_id` NOT NULL, knowledge chapter-keyed extraction, composition outline) works prose-less. **Zero schema change to glossary/knowledge/composition** — additivity preserved.
- **Acceptance gate:** `scripts/raid/verify-cycle-20.sh` exits 0
- **Top 3 LOCKED decisions consumed:** G1 (world container), World-container locks, Architecture-review "world bible chapter" lock
- **DPS count:** 3
- **Estimated wall time:** ~4h

## Dependencies (must show DONE in CYCLE_LOG.md)
- Cycles: C0
- Files expected to exist (grep-able paths): `services/book-service/internal/` (server, models, store), book-service migrations dir, C0's shared FE foundation (not consumed by this BE cycle but C0 is the gate).

## Scope (IN)
- **Migration (up + down):** create `worlds` table (`id`, `owner_user_id`, `name`, `description`, timestamps); add nullable `world_id` column on `books` (FK → `worlds.id`, `ON DELETE SET NULL`, **default NULL**). No backfill. Down-migration drops the column then the table, clean round-trip.
- **World CRUD API** (book-service, app-validated owner scoping like existing book routes): `POST /v1/worlds` (create), `GET /v1/worlds`, `GET /v1/worlds/{id}`, `PATCH /v1/worlds/{id}`, `DELETE /v1/worlds/{id}`.
- **Move-book-into-world:** `PATCH /v1/books/{book_id}` (or dedicated `POST /v1/worlds/{id}/books`) sets/clears `books.world_id`; clearing returns the book to standalone.
- **List books in a world:** `GET /v1/worlds/{id}/books`.
- **Auto bible-chapter on world creation:** world creation provisions the world's **bible book** + a **hidden chapter at `sort_order 0`** (e.g. title "World Bible", a `hidden`/`is_bible` flag). This chapter is the anchor lore links to. Idempotent — re-create paths don't double-insert sort_order 0.
- `scripts/raid/verify-cycle-20.sh` (acceptance gate runner creates it).

## Scope (OUT — explicitly)
- **NO schema change to glossary-service, knowledge-service, or composition-service.** Lore stays `book_id`/`chapter_id`-keyed; it rolls up to a world via its books. Do NOT add a `world_id` column to any lore DB.
- **NO world-level sharing/grants** — grants stay per-book (LOCKED deferred). Do not touch sharing-service.
- **NO FE** — that is C21. No worldbuilding entry screen here.
- **NO living-world view / dị bản** — C28 / C23–C27.
- No backfill of existing books into worlds; existing `world_id=NULL` books must behave exactly as today.

## Acceptance criteria (CI gates — exit code 0 = pass)
- Tests pass: book-service unit/integration suite for worlds CRUD + move-book + list-books + bible-chapter auto-creation (real-PG where the harness supports it).
- Lints pass: book-service Go lint/vet clean.
- **Migration round-trip:** `up` then `down` runs clean on a real PG; re-`up` succeeds (idempotent/reversible).
- **CROSS-SERVICE live-smoke (REQUIRED — CLAUDE.md VERIFY rule):** evidence string contains `live smoke: create world → bible chapter exists (sort_order 0) → attach book → world lists books; null-world books unaffected`. A real API round-trip on a stacked-up book-service (rebuild the image first — stale images = false-green). If un-bootable: `live infra unavailable: <reason>` is the only allowed substitute.

## DPS parallelism plan
- DPS 1: **Migration + model layer** — `worlds` table migration (up/down), `world_id` column on `books`, store/repo methods (insert/get/list/update/delete world; set/clear book.world_id; list books by world). (return budget: 1500 tokens summary)
- DPS 2: **HTTP handlers** — world CRUD routes + move-book + list-books-in-world, wired to DPS-1 store; owner-scoping middleware reuse. (seam-stub the store interface first.)
- DPS 3: **Bible-chapter provisioning** — auto-create hidden `sort_order 0` chapter on world creation; reuse existing chapter insert path; idempotency guard. Depends on DPS-1 shapes.
- **Serial tail (Raid Leader):** migration round-trip + cross-service live-smoke + `verify-cycle-20.sh`.

## Adversary review focus (cold-start sub-agent — return budget 2000 tokens)
- **Additivity breach:** any schema/code change reaching into glossary/knowledge/composition DBs — LOCKED violation. World grouping is book-service-only.
- **Non-nullable / backfill regression:** `world_id` must be nullable with default NULL; existing `world_id=NULL` books' list/scoping queries must be unaffected (verify the `server.go` list filter still returns standalone books).
- **Missing bible chapter:** world created without a `sort_order 0` hidden chapter → breaks the chapter-keyed lore machinery the ARCH-REVIEW lock exists to fix. Confirm it is created AND hidden.
- **sort_order 0 collision / double-insert:** re-running world provisioning must not create two sort_order-0 chapters.
- **FK delete behavior:** deleting a world must `SET NULL` on member books (return them to standalone), not cascade-delete books.
- **Migration down dirtiness:** down-migration must drop column + table cleanly with no orphaned FK; round-trip must re-up.
- **Owner-scope bleed:** world CRUD must scope by `owner_user_id` — no cross-user world read/move.
- **Mock-only false-green:** confirm the live-smoke token reflects a real stacked-up call, not a mocked one.

## Scope Guard CLEAR criteria (cold-start sub-agent — return budget 500 tokens)
CLEAR iff: only book-service code + migrations + `scripts/raid/verify-cycle-20.sh` changed; ZERO edits to glossary/knowledge/composition/sharing service code or DBs; `world_id` nullable/default-NULL; bible chapter auto-created hidden at sort_order 0; migration up/down round-trips clean; cross-service live-smoke token present; `verify-cycle-20.sh` exits 0. Otherwise BLOCKED.

## Cross-references (for deep-read IF Raid Leader needs to FOCUS mode)
- Row: `docs/plans/2026-06-13-creation-unblock/CYCLE_DECOMPOSITION.md` — C20 row + Notes (additive substrate, cross-service live-smoke list).
- LOCKED: `docs/plans/2026-06-13-creation-unblock/OPEN_QUESTIONS_LOCKED.md` — §G1 (additive `world_id` grouping in book-service), World-container locks, Architecture-review locks (world bible chapter, sort_order 0, NOT-NULL chapter_id rationale).
- Spec: `docs/specs/2026-06-13-writer-persona-use-cases-scenarios.md` §4A (worldbuilder use case).
- Spec: `docs/specs/2026-06-13-derivative-works-living-world-plan.md` (world = shared substrate for living-world view C28).

## ⚠️ REMINDERS (BOTTOM — re-stated critical info, anti-lost-in-middle)
- 🔴 **G1 LOCKED:** additive only — `worlds` table + nullable `world_id` FK on `books` (default NULL = standalone). NO schema change to the 3 lore services.
- 🔴 **ARCH-REVIEW LOCKED:** world creation MUST auto-create a hidden "world bible" chapter at `sort_order 0` — glossary `chapter_entity_links.chapter_id` is NOT NULL, knowledge extraction is chapter-keyed, composition outline forbids scenes without a chapter. A prose-less world with no bible chapter breaks all three.
- 🔴 **World-container LOCKED:** world-level sharing is deferred — grants stay per-book; do NOT touch sharing-service. Deleting a world SET NULLs member books (no cascade book delete).
- 🔴 **Acceptance MUST include:** CROSS-SERVICE live-smoke token `live smoke: create world → bible chapter exists → attach book → world lists books; null-world books unaffected` AND migration up/down clean + round-trip. Rebuild the book-service image before smoke (stale = false-green).
- 🔴 **Do NOT touch:** glossary/knowledge/composition/sharing service code or DBs; FE (C21 owns it); existing standalone-book (`world_id=NULL`) behavior must be unchanged.
- 🔴 **Fresh session reminder:** this is a new `/raid 20` invocation; no carry-over from prior cycles. Read CYCLE_LOG.md + this brief + LOCKED file ONLY.
