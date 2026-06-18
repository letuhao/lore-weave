# Glossary Kind/Attribute Tiering — Epic Master Plan (SS-4 → SS-7 + T1-lock)

> **Date:** 2026-06-19. **Phase:** PLAN (epic kickoff). **Size:** XL, multi-slice, **multiple DB migrations → /amaw + rollback plan per slice**. **Mode:** full epic in one continuous multi-session run (PO, 2026-06-19). Sequences the four Approved detailed designs (docs [93](../03_planning/93_SS4_USER_KIND_CRUD_DETAILED_DESIGN.md)/[94](../03_planning/94_SS5_BOOK_KIND_CRUD_DETAILED_DESIGN.md)/[95](../03_planning/95_SS6_KIND_SYNC_COMPARE_DETAILED_DESIGN.md)/[96](../03_planning/96_SS7_KIND_INTEGRATION_DETAILED_DESIGN.md)) + the supplement plan [89](../03_planning/89_MODULE05_SUPPLEMENT_DETAILED_DESIGN_PLAN.md), and adds the T1-lock + orphan-kind migration this plan decides.

## Why (root cause)
`entity_kinds` (glossary) is the ONLY kind table — global, `UNIQUE(code)`, **user-mutable** (`POST/PATCH/DELETE /v1/glossary/kinds*`). A user editing a "kind" mutates the shared row for **every** user — a multi-tenancy defect (see CLAUDE.md → "User Boundaries & Tenancy"; the agent's early self-hosted≠single-user misconception). Users have nowhere to put custom kinds except the global table, so they corrupt it.

## Target model (system → per-user → per-book = T1 → T2 → T3)
| Tier | Table | Writes | Read scope |
|---|---|---|---|
| **T1 system** | `entity_kinds` + `attribute_definitions` (existing) | **admin only** (seed + admin endpoints) | everyone, read-only |
| **T2 per-user** | `user_kinds` + `user_kind_attributes` (SS-4) | the owning user | that user |
| **T3 per-book** | `book_kinds` + `book_kind_attributes` (SS-5) | book owner + E0 grantees | owner + grantees |

**Resolution (lowest-precedence first):** System → Per-user → Per-book; higher tier shadows lower by `code`. A book-scoped kind list = system defaults + that user's kinds + that book's kinds, deduped by code (book wins, then user, then system).

## Slices (dependency-ordered; each = one /loom cycle, /amaw for the migration)
- **SS-4 — T2 user kinds + T1-LOCK + orphan migration** (L). Per doc 93: `user_kinds`/`user_kind_attributes` (soft-delete + recycle bin), 9 CRUD endpoints, clone-from-T1, `UserKindsPage`. **PLUS this plan's additions:**
  - **T1-lock:** gate `POST /kinds`, `PATCH /kinds/{id}`, `DELETE /kinds/{id}`, `PATCH /kinds/reorder`, `POST /kind-aliases` to **admin only** (require an admin/system role, not a regular JWT). Regular users lose write access to `entity_kinds`; reads stay open. Decide the admin signal (auth-service admin role / a platform-admin claim — check what exists; book-service/auth already has admin-JWT issuance).
  - **Orphan migration (PO decision):** the 3 live `is_default=false` global kinds have no `owner_user_id`. For each, resolve the books whose entities use it (`glossary_entities.kind_id` → `book_id` → book-service `owner_user_id`), copy the kind + its attribute_definitions into each such owner's `user_kinds`, repoint those owners' entities (deferred to SS-7's polymorphic ref — until then the entities keep the T1 kind_id but the per-user copy exists), then mark the orphan T1 kind hidden/removed once no longer referenced. **Inspect the 3 first** (codes, using-books, owners) before writing the migration.
- **SS-5 — T3 book kinds** (M). Per doc 94: `book_kinds`/`book_kind_attributes`, CRUD gated by **E0 book grants** (view=read, edit/manage=write — reuse the grantclient adopted across the codebase), book-kind management UI. Same soft-delete/recycle pattern as SS-4.
- **SS-6 — kind sync/compare** (L). Per doc 95: diff a user/book kind against its T1 (or T2) source, apply-sync API, `KindCompareModal`.
- **SS-7 — integration + polymorphic kind-ref** (M, the riskiest migration). Per doc 96 + supplement §3: `glossary_entities` kind reference becomes tier-aware (chosen shape from doc 89 — nullable `kind_id`/`user_kind_id`/`book_kind_id` + a discriminator, NOT a merged table); `entity_attribute_values.attr_def_id` likewise; a `v_attr_def` UNION view unifies T1/T2/T3 attribute defs for read paths (snapshot trigger, export, detail). Entity-create picker + filter bar show T1+T2+T3 (merged resolution). Wire extraction + wiki to the merged kind set.

## Cross-cutting decisions (this plan)
- **T1 is admin-only from SS-4 onward** — confirm the admin-auth mechanism before SS-4 build (don't invent one; reuse auth-service's admin-JWT / platform-admin if present).
- **Orphans → book owners** (PO option 1); inspect-then-migrate the 3.
- **Snapshot fallback (SS-1) covers orphan display** — a deleted T2/T3 kind still renders an entity via `entity_snapshot`.
- **Migrations:** additive + idempotent (`CREATE TABLE IF NOT EXISTS`, `ADD COLUMN IF NOT EXISTS`), each slice /amaw with a stated rollback; the SS-7 polymorphic-FK migration is the one needing the most care (backfill + a CHECK that exactly one tier-ref is non-null).
- **No regression to entity reads** — until SS-7, `glossary_entities.kind_id` stays the live ref; T2/T3 kinds exist but aren't yet selectable for entities (matches SS-4 doc's "no entity creation with T2 kinds until SS-7").

## Verify strategy (per slice)
Unit (handlers + scope-key filtering) → real-PG (the live :5555 / loreweave_glossary throwaway) for the migration + the tenancy guards (user A can't read/write user B's kinds; regular user can't write T1) → FE vitest + tsc + 4-locale i18n → cross-service live-smoke where extraction/wiki touch kinds (SS-7). The **executable tenancy guard** (a second user gets 404/403 on another's kind; a non-admin 403s on T1 writes) is mandatory — owner/admin-run tests hide cross-tenant leaks (the E0 lesson).

## Risks
- **R-T1-lock-breaks-callers:** internal/admin/seed paths write `entity_kinds` — gate only the *user-facing* routes, keep internal/seed write paths. Audit every `entity_kinds` writer.
- **R-orphan-attribution:** an orphan kind used across multiple owners' books → copy to each (idempotent on `UNIQUE(owner_user_id, code)`).
- **R-polymorphic-FK (SS-7):** the entity kind-ref migration is destructive-shaped; backfill + CHECK-constraint + extensive real-PG before deploy; /amaw.
- **R-extraction/wiki-drift:** extraction auto-selects kinds (memory [[glossary-kinds-global-extraction]]); SS-7 must point it at the merged resolution, not the global table.
