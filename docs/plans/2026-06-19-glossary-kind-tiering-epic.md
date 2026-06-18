# Glossary Kind/Attribute Tiering — Epic Master Plan (SS-4 → SS-7 + T1-lock)

> **Date:** 2026-06-19. **Phase:** PLAN (epic kickoff). **Size:** XL, multi-slice, **multiple DB migrations → /amaw + rollback plan per slice**. **Mode:** full epic in one continuous multi-session run (PO, 2026-06-19). Sequences the four Approved detailed designs (docs [93](../03_planning/93_SS4_USER_KIND_CRUD_DETAILED_DESIGN.md)/[94](../03_planning/94_SS5_BOOK_KIND_CRUD_DETAILED_DESIGN.md)/[95](../03_planning/95_SS6_KIND_SYNC_COMPARE_DETAILED_DESIGN.md)/[96](../03_planning/96_SS7_KIND_INTEGRATION_DETAILED_DESIGN.md)) + the supplement plan [89](../03_planning/89_MODULE05_SUPPLEMENT_DETAILED_DESIGN_PLAN.md), and adds the T1-lock + orphan-kind migration this plan decides.

## Why (root cause)
`entity_kinds` (glossary) is the ONLY kind table — global, `UNIQUE(code)`, **user-mutable** (`POST/PATCH/DELETE /v1/glossary/kinds*`). A user editing a "kind" mutates the shared row for **every** user — a multi-tenancy defect (see CLAUDE.md → "User Boundaries & Tenancy"; the agent's early self-hosted≠single-user misconception). Users have nowhere to put custom kinds except the global table, so they corrupt it.

## Target model (system → per-user → per-book = T1 → T2 → T3)
| Tier | Table | Writes | Read scope |
|---|---|---|---|
| **T1 system** | **`system_kinds` + `system_kind_attributes`** (NEW, explicit — see decision) | **admin/seed only** | everyone, read-only |
| **T2 per-user** | `user_kinds` + `user_kind_attributes` (SS-4) | the owning user | that user |
| **T3 per-book** | `book_kinds` + `book_kind_attributes` (SS-5) | book owner + E0 grantees | owner + grantees |

**PO DECISION (2026-06-19) — explicit separate system tables, NOT "lock entity_kinds in place".** The current `entity_kinds` name is ambiguous (sounds like "every entity's kind") and mixes the 13 system defaults with 3 user-created orphans — exactly the drift that caused the bug. So the system tier gets its **own clearly-named `system_kinds` table**, symmetric with `user_kinds`/`book_kinds`. Seed the 13 defaults into it; it has **no user-facing write API** (seed/admin/migration only). This makes all three tiers symmetric → simplifies SS-7's polymorphic ref (a clean per-tier ref + discriminator) and removes the "is this row system or user?" ambiguity for good.

**Resolution (lowest-precedence first):** System → Per-user → Per-book; higher tier shadows lower by `code`. A book-scoped kind list = system defaults + that user's kinds + that book's kinds, deduped by code (book wins, then user, then system).

## Slices (dependency-ordered; each = one /loom cycle, /amaw for the migration)
- **SS-4 — establish `system_kinds` (explicit T1) + T2 user kinds + orphan migration** (L). Per doc 93 for T2 + the PO explicit-system-tables decision:
  - **Establish T1 as `system_kinds`:** `ALTER TABLE entity_kinds RENAME TO system_kinds` + `attribute_definitions RENAME TO system_kind_attributes` (a RENAME preserves all FK refs from `glossary_entities.kind_id`/`attribute_definitions.kind_id` automatically — low-risk, no entity rewrite). Remove the **user-facing** write routes (`POST/PATCH/DELETE /v1/glossary/kinds*`, `/reorder`, `/kind-aliases`); system kinds are seed/admin/migration-only (no runtime user write API). Keep internal/seed write paths. Reads unchanged.
  - **T2:** `user_kinds`/`user_kind_attributes` (soft-delete + recycle bin), 9 CRUD endpoints, clone-from-system, `UserKindsPage` (per doc 93).
  - **Orphan migration (PO: attribute to book owners), inspected 2026-06-19:** `selfcode_smoke` (1 entity, synthetic test book `…0aaa-…0030`) → DELETE (junk: drop the entity + the kind). `concept`/Đạo (305 entities) + `technique`/Công pháp (84) → both in book `019ec783-efe5-7e3f-8dea-5124642bf76b`; resolve its owner via book-service, copy each kind + its system_kind_attributes into that owner's `user_kinds`. **Transition:** the 2 real orphans STAY in `system_kinds` (entities still FK them) until SS-7 repoints `glossary_entities` to the per-user copy + removes the system rows — until then the per-user copy exists but entities use the legacy ref (matches "kind_id stays live until SS-7"). Flag the 2 rows (e.g. `is_hidden=true` + a note) so they don't surface as system defaults.
- **SS-5 — T3 book kinds** (M). Per doc 94: `book_kinds`/`book_kind_attributes`, CRUD gated by **E0 book grants** (view=read, edit/manage=write — reuse the grantclient adopted across the codebase), book-kind management UI. Same soft-delete/recycle pattern as SS-4.
- **SS-6 — kind sync/compare** (L). Per doc 95: diff a user/book kind against its T1 (or T2) source, apply-sync API, `KindCompareModal`.
- **SS-7 — integration + polymorphic kind-ref** (M, the riskiest migration). Per doc 96 + supplement §3: `glossary_entities` kind reference becomes tier-aware (chosen shape from doc 89 — nullable `kind_id`/`user_kind_id`/`book_kind_id` + a discriminator, NOT a merged table); `entity_attribute_values.attr_def_id` likewise; a `v_attr_def` UNION view unifies T1/T2/T3 attribute defs for read paths (snapshot trigger, export, detail). Entity-create picker + filter bar show T1+T2+T3 (merged resolution). Wire extraction + wiki to the merged kind set.

## Cross-cutting decisions (this plan)
- **T1 = explicit `system_kinds` table, no user-facing write API** (PO 2026-06-19). Rename `entity_kinds`→`system_kinds` (FKs follow); strip the user-facing kind write routes. Runtime admin editing of system kinds is OUT OF SCOPE for now (seed/migration-managed) — if an admin kind-management UI is wanted later, wire glossary to verify the platform `adminjwt` then (a tracked follow-up, not this epic). This sidesteps adding admin-auth to glossary now while making the tier unambiguous.
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
